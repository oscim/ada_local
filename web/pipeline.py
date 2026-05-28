"""ADA Web Plugin — Chat Pipeline aligned with ADA app behavior."""
from __future__ import annotations

import json
import os
import re
import sys
from typing import AsyncGenerator

import httpx

# Ensure project root is in sys.path when run standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import OLLAMA_URL, RESPONDER_MODEL, FUNCTIONS
from core.function_executor import executor as function_executor
from core.memory_store import memory_store
from core.semantic_router import get_route as semantic_route
from core.skill_manager import skill_manager

# ---------------------------------------------------------------------------
# Ollama endpoint (normalise que OLLAMA_URL finisse en /api ou non)
# ---------------------------------------------------------------------------
_base = OLLAMA_URL.rstrip("/")
if _base.endswith("/api"):
    _base = _base[:-4]
_OLLAMA_CHAT_URL = f"{_base}/api/chat"

# ---------------------------------------------------------------------------
# Pattern : "ajoute l'URL https://... à l'infra" (et variantes)
_ADD_URL_RE = re.compile(
    r"(?:ajoute|surveille|monitore|vérifie|watch)\b"
    r".*?(https?://[^\s<>\"\)\]]+)",
    re.IGNORECASE,
)


# Triggers de recherche web → délégation à l'agent Playwright
# ---------------------------------------------------------------------------
_WEB_TRIGGERS = (
    "cherche sur le web", "cherche sur internet", "cherche en ligne",
    "recherche sur le web", "recherche sur internet", "recherche en ligne",
    "fais une recherche web", "fais une recherche sur le web",
    "fais une recherche sur internet", "trouve sur internet", "trouve sur le web",
    "google", "bing", "search the web", "search on the web",
    "dernières nouvelles", "actualités récentes", "latest news",
    "cherche l'info", "cherche des infos sur le web",
)


# ---------------------------------------------------------------------------
# Triggers déterministes: évitent un passage LLM inutile pour l'état infra.
_INFRA_TRIGGERS = frozenset(
    {
        "état infra",
        "etat infra",
        "status infra",
        "infrastructure status",
        "état de l'infra",
        "etat de l infra",
        "état de l'infrastructure",
        "etat de l infrastructure",
        "infrastructure",
    }
)


# ---------------------------------------------------------------------------
# Agent web Playwright (pipeline version — sans SSE, yield chunks)
# ---------------------------------------------------------------------------
async def _web_agent_search(instruction: str) -> AsyncGenerator[str, None]:
    """Execute l'agent Playwright headless et yield le résultat final."""
    from playwright.async_api import async_playwright
    from core.agent.text_agent import _SYSTEM_PROMPT as _AGENT_SYSTEM
    from core.settings_store import settings as app_settings

    MAX_STEPS = 12
    MAX_PAGE_CHARS = 4000
    ollama_url = app_settings.get("ollama_url", OLLAMA_URL)
    base = ollama_url.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    chat_url = f"{base}/api/chat"

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await ctx.new_page()
            history: list[dict] = []

            for step in range(1, MAX_STEPS + 1):
                try:
                    url = page.url
                    title = await page.title()
                    body = await page.eval_on_selector("body", "el => el.innerText") or ""
                    body = re.sub(r"\s{3,}", "\n", body)[:MAX_PAGE_CHARS]
                    links = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.slice(0,30).map(e => ({t:e.innerText.trim(), h:e.href})).filter(l=>l.t)",
                    )
                    links_str = "\n".join(
                        f"  [{l['t'][:60]}] {l['h'][:80]}" for l in links[:20]
                    )
                    page_summary = f"URL: {url}\nTitle: {title}\nLinks:\n{links_str}\nBody:\n{body}"
                except Exception as e:
                    page_summary = f"(erreur lecture page: {e})"

                user_msg = (
                    f"Goal: {instruction}\n\nStep {step}/{MAX_STEPS}\n\n"
                    f"Current page:\n{page_summary[:MAX_PAGE_CHARS + 500]}\n\n"
                    "Output the next JSON action:"
                )
                messages_llm = [
                    {"role": "system", "content": _AGENT_SYSTEM},
                    *history,
                    {"role": "user", "content": user_msg},
                ]

                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        r = await client.post(
                            chat_url,
                            json={"model": RESPONDER_MODEL, "messages": messages_llm,
                                  "stream": False, "think": False},
                        )
                        r.raise_for_status()
                        reply = r.json().get("message", {}).get("content", "").strip()
                except Exception as e:
                    yield f"Erreur LLM lors de la recherche : {e}"
                    await browser.close()
                    return

                action = None
                m = re.search(r"\{[^{}]+\}", reply, re.DOTALL)
                if m:
                    try:
                        action = json.loads(m.group())
                    except Exception:
                        pass

                if not action:
                    history.append({"role": "assistant", "content": reply})
                    history.append({"role": "user", "content": "Output a valid JSON action."})
                    continue

                history.append({"role": "assistant", "content": json.dumps(action)})
                action_name = action.get("action", "")

                if action_name in ("done", "extract"):
                    result = action.get("result", reply)
                    await browser.close()
                    yield result
                    return

                try:
                    if action_name == "navigate":
                        await page.goto(
                            action.get("url", ""),
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                        for sel in [
                            "button:has-text('Tout accepter')",
                            "button:has-text('Accept all')",
                        ]:
                            try:
                                btn = page.locator(sel).first
                                if await btn.is_visible(timeout=800):
                                    await btn.click(timeout=2000)
                                    break
                            except Exception:
                                pass
                    elif action_name == "click":
                        await page.get_by_text(
                            action.get("link_text", ""), exact=False
                        ).first.click(timeout=5_000)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                        except Exception:
                            pass
                    elif action_name == "scroll_down":
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")
                except Exception:
                    pass

            await browser.close()
            yield "Je n'ai pas pu trouver la réponse dans la limite d'étapes."
    except Exception as e:
        yield f"Erreur lors de la recherche web : {e}"


def _system_prompt() -> str:
    try:
        from core.i18n import ai_lang_instruction

        lang_instr = ai_lang_instruction()
    except Exception:
        lang_instr = "Réponds en français. Sois concis et précis."
    return (
        "Tu es ADA, une assistante IA locale. "
        f"{lang_instr} "
        "Tu es accessible via l'interface web mobile — sois utile, précise et naturelle."
    )


# ---------------------------------------------------------------------------
# Streaming chat simple (qwen_basic / qwen_thinking)
# ---------------------------------------------------------------------------
async def _stream_ollama(
    messages: list[dict],
    thinking: bool = False,
) -> AsyncGenerator[str, None]:
    payload: dict = {
        "model": RESPONDER_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": 1024, "temperature": 0.7},
    }
    if thinking:
        payload["think"] = True  # Qwen3 extended reasoning

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", _OLLAMA_CHAT_URL, json=payload) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # Skip thinking tokens, only yield visible content
                delta = data.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if data.get("done"):
                    break


async def _call_llm(messages: list[dict], thinking: bool = False) -> str:
    payload: dict = {
        "model": RESPONDER_MODEL,
        "messages": messages,
        "stream": False,
        "think": bool(thinking),
        "keep_alive": "5m",
    }
    async with httpx.AsyncClient(timeout=150.0) as client:
        r = await client.post(_OLLAMA_CHAT_URL, json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()


async def _call_with_tools(text: str, conversation_messages: list[dict]) -> str:
    """Tool-calling aligné avec l'app: outils complets + fallback passthrough."""
    try:
        async with httpx.AsyncClient(timeout=150.0) as client:
            r = await client.post(
                _OLLAMA_CHAT_URL,
                json={
                    "model": RESPONDER_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a function dispatcher. You MUST call one of the available tools. "
                                "NEVER respond with plain text. "
                                "For greetings or conversational questions: call passthrough."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "tools": FUNCTIONS,
                    "stream": False,
                    "think": False,
                    "keep_alive": "5m",
                },
            )
            r.raise_for_status()
            tool_calls = r.json().get("message", {}).get("tool_calls", [])
    except Exception:
        return await _call_llm(conversation_messages, thinking=False)

    if not tool_calls:
        return await _call_llm(conversation_messages, thinking=False)

    call = tool_calls[0]
    func_name = call.get("function", {}).get("name", "")
    params = call.get("function", {}).get("arguments", {}) or {}

    if func_name == "passthrough":
        thinking = bool(params.get("thinking", False))
        return await _call_llm(conversation_messages, thinking=thinking)

    result = function_executor.execute(func_name, params)
    success = result.get("success", False)
    result_msg = result.get("message", "")

    followup = list(conversation_messages)
    hint = f"[Résultat: {'succès' if success else 'échec'}. {result_msg}]"
    followup[-1] = {
        "role": "user",
        "content": f"{text}\n{hint}\nRéponds en français de façon naturelle et concise.",
    }
    return await _call_llm(followup, thinking=False)


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------
async def process_message(
    message: str,
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Route et traite un message, yield les chunks de réponse au fil de l'eau.
    Compatible SSE : chaque chunk est une petite chaîne de texte.
    """
    session_id = "web_chat"
    user_text = (message or "").strip()
    if not user_text:
        return

    text_lower = user_text.lower()

    # Ajout d'une URL à la surveillance d'infrastructure
    m_url = _ADD_URL_RE.search(user_text)
    if m_url and any(k in text_lower for k in ("infra", "infrastructure", "surveillance", "surveille", "monitore", "watch", "vérifie", "vérifie")):
        from urllib.parse import urlparse
        from core.runtime_state import add_custom_endpoint
        raw_url = m_url.group(1).rstrip(".,;)>")
        name = urlparse(raw_url).netloc or raw_url
        add_custom_endpoint(name, raw_url)
        response = (
            f"✅ **{name}** ajouté à la surveillance.\n"
            f"URL : `{raw_url}`\n"
            "Il apparaîtra dans l'état infrastructure dès la prochaine demande."
        )
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", response)
        yield response
        return

    # Détection d'une demande de recherche web → agent Playwright
    if any(trigger in text_lower for trigger in _WEB_TRIGGERS):
        yield "🔍 Recherche sur le web en cours…\n\n"
        full_response = "🔍 Recherche sur le web en cours…\n\n"
        async for chunk in _web_agent_search(user_text):
            full_response += chunk
            yield chunk
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", full_response)
        return

    # Routing déterministe pour l'état d'infrastructure
    if any(trigger in text_lower for trigger in _INFRA_TRIGGERS):
        from core.runtime_state import runtime_state

        runtime_state.refresh()
        infra = runtime_state.format_infra_status_fr()
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", infra)
        yield infra
        return

    # Contexte conversationnel de base
    messages: list[dict] = [{"role": "system", "content": _system_prompt()}]
    messages.extend(history[-20:])

    # Injection des skills + mémoire long terme, comme l'app
    messages = skill_manager.inject(messages, user_text)
    mem = memory_store.build_context(user_text, current_session_id=session_id)
    if mem:
        messages[0] = {
            "role": "system",
            "content": messages[0]["content"] + "\n\n" + mem,
        }

    messages.append({"role": "user", "content": user_text})

    try:
        route = semantic_route(user_text)
    except Exception:
        route = "function_gemma"

    # function_gemma: tool-calling complet puis réponse naturelle
    if route == "function_gemma":
        response = await _call_with_tools(user_text, messages)
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", response)
        if response:
            yield response
        return

    # qwen_thinking ou chat standard (vision/youtube/cad/print inclus en fallback texte)
    thinking = route == "qwen_thinking"
    full_response = ""
    async for chunk in _stream_ollama(messages, thinking=thinking):
        full_response += chunk
        yield chunk

    if full_response:
        memory_store.save(session_id, "user", user_text)
        memory_store.save(session_id, "assistant", full_response)

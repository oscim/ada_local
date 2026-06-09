"""
Semantic learner — extracts atomic facts from clarification answers and stores
them in consolidated_memories, or redirects procedural content to AutoSkill.

Also manages onboarding (first-use questions when memory is empty) and tracks
pending clarification state per session.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import httpx

from config import OLLAMA_URL, RESPONDER_MODEL

# ---------------------------------------------------------------------------
# In-memory session state (survives within a process; single-user Docker)
# ---------------------------------------------------------------------------
_PENDING: dict[str, dict] = {}
# { session_id: {"q": str, "mode": "clarification"|"onboarding", "turn": int} }


def set_pending(session_id: str, question: str, mode: str = "clarification", turn: int = 0) -> None:
    _PENDING[session_id] = {"q": question, "mode": mode, "turn": turn}


def get_pending(session_id: str) -> dict | None:
    return _PENDING.get(session_id)


def clear_pending(session_id: str) -> None:
    _PENDING.pop(session_id, None)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
_EXTRACT_SYSTEM = """\
Tu analyses la réponse d'un utilisateur à une question de clarification.
Extrait les faits atomiques pertinents sous forme de triplets JSON.

FORMAT DE SORTIE REQUIS — réponds UNIQUEMENT avec ce JSON (sans bloc markdown) :
{
  "type": "fact",
  "facts": [{"subject": "...", "relation": "...", "object": "..."}],
  "summary": "résumé en une phrase"
}

Ou si la réponse concerne une procédure/préférence technique :
{"type": "skill", "facts": [], "summary": "..."}

Ou si la réponse n'est pas exploitable :
{"type": "none", "facts": [], "summary": ""}

Règles triplets :
- "fact" : relation humaine, identité, lieu, contexte personnel
- subject : nom propre ou "utilisateur"
- relation : mot simple — chambre, relation, entreprise, rôle, enfant, collègue
- object : valeur concrète (identifiant domotique, nom propre, valeur)
"""

_CLARIF_SYSTEM = """\
Tu génères une question de clarification courte et naturelle pour lever une ambiguïté.
La question doit être conversationnelle, sans révéler qu'il s'agit d'un apprentissage.
Réponds UNIQUEMENT avec la question, rien d'autre.
"""

_ONBOARDING_SYSTEM = """\
Tu génères la prochaine question utile pour construire le profil de l'utilisateur.
Si le profil est suffisamment complet pour lever les ambiguïtés courantes, réponds DONE.
Sinon, réponds uniquement avec une question courte et naturelle.
Priorité : chambre de l'utilisateur dans le système domotique, relations proches (enfants, etc.).
"""


async def _call_raw(system: str, user_prompt: str, model: str = RESPONDER_MODEL) -> str:
    base = OLLAMA_URL.rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{base}/api/chat", json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()


async def _call_json(system: str, user_prompt: str, model: str = RESPONDER_MODEL) -> dict | None:
    raw = await _call_raw(system, user_prompt, model)
    # Strip markdown fences if any
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Clarification question generation
# ---------------------------------------------------------------------------
async def generate_clarification_question(
    unresolved_ref: str,
    known_facts: list[dict],
    system_entities: list[str],
    model: str = RESPONDER_MODEL,
) -> str:
    facts_str = "\n".join(
        f"• {f['subject']} → {f['relation']} → {f['object']}"
        for f in known_facts if isinstance(f, dict)
    ) or "(aucun)"
    entities_str = ", ".join(system_entities[:20]) or "(inconnues)"
    prompt = (
        f"Référence ambiguë détectée : « {unresolved_ref} »\n"
        f"Entités domotiques connues : {entities_str}\n"
        f"Faits déjà connus :\n{facts_str}\n\n"
        f"Génère une question naturelle et courte pour savoir à quoi correspond "
        f"« {unresolved_ref} » dans le système domotique."
    )
    try:
        return await _call_raw(_CLARIF_SYSTEM, prompt, model)
    except Exception:
        return f"Quand tu dis « {unresolved_ref} », tu fais référence à quelle zone ?"


# ---------------------------------------------------------------------------
# Fact extraction and storage
# ---------------------------------------------------------------------------
async def analyze_and_store(
    clarification_question: str,
    user_answer: str,
    session_id: str = "web_chat",
    model: str = RESPONDER_MODEL,
) -> dict:
    """
    Analyze user's answer to a clarification question.
    Stores facts in consolidated_memories (type='fact') or emits Radar
    event for AutoSkill redirect (type='skill').
    Returns {'type': str, 'facts': list, 'summary': str}.
    """
    prompt = (
        f"Question posée : {clarification_question}\n"
        f"Réponse de l'utilisateur : {user_answer}"
    )
    result = await _call_json(_EXTRACT_SYSTEM, prompt, model)
    if not result or not isinstance(result, dict):
        return {"type": "none", "facts": [], "summary": ""}

    fact_type = result.get("type", "none")
    facts = result.get("facts", []) or []
    summary = result.get("summary", "") or ""

    if fact_type == "fact" and facts:
        try:
            from core.memory_store import memory_store
            date_str = datetime.now().strftime("%Y-%m-%d")
            # Merge with existing facts for today
            existing_facts: list = []
            for rec in memory_store.get_consolidated(days=365):
                if rec["date"] == date_str:
                    existing_facts = rec.get("facts", [])
                    break
            merged = existing_facts + [f for f in facts if isinstance(f, dict)]
            memory_store.save_consolidated(
                date_str=date_str,
                summary=summary,
                facts=merged,
                topics=["identité", "sémantique"],
                raw_count=0,
            )
        except Exception:
            pass
        try:
            from web.radar.events import emit_event
            emit_event(
                type="semantic.fact_stored",
                level="info",
                module="core.memory.semantic_learner",
                metadata={"count": len(facts), "summary": summary[:100]},
            )
        except Exception:
            pass

    elif fact_type == "skill":
        try:
            from web.radar.events import emit_event
            emit_event(
                type="semantic.autoskill_redirect",
                level="info",
                module="core.memory.semantic_learner",
                metadata={"summary": summary[:100]},
            )
        except Exception:
            pass

    return {"type": fact_type, "facts": facts, "summary": summary}


# ---------------------------------------------------------------------------
# Onboarding — single-question generator
# ---------------------------------------------------------------------------
async def run_onboarding(
    active_universes: list[str],
    system_entities: list[str],
    turn: int = 0,
    max_turns: int = 10,
    model: str = RESPONDER_MODEL,
) -> str | None:
    """
    Generate the next onboarding question. Returns None when done.

    Reads current consolidated_memories to know what is already known.
    The LLM decides when enough facts are collected (returns 'DONE').
    """
    if turn >= max_turns:
        return None

    known_facts: list[dict] = []
    try:
        from core.memory_store import memory_store
        for rec in memory_store.get_consolidated(days=365):
            known_facts.extend(rec.get("facts", []))
    except Exception:
        pass

    facts_str = "\n".join(
        f"• {f['subject']} → {f['relation']} → {f['object']}"
        for f in known_facts if isinstance(f, dict)
    ) or "(aucun)"

    prompt = (
        f"Univers actifs : {', '.join(active_universes) or '(inconnus)'}\n"
        f"Entités domotiques connues : {', '.join(system_entities[:20]) or '(inconnues)'}\n"
        f"Faits déjà connus :\n{facts_str}"
    )
    try:
        answer = await _call_raw(_ONBOARDING_SYSTEM, prompt, model)
    except Exception:
        return None

    if not answer or answer.strip().upper() == "DONE":
        return None

    return answer.strip()

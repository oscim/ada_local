"""core/intent/intent_extractor.py — Couche 1 : Extraction LLM (SPEC_INTENT_PIPELINE2)

Appelle Ollama avec format:json, valide le schéma retourné.
Retourne None sur tout échec → le pipeline legacy prend le relais (aucune régression).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SCHEMA_KEYS = frozenset({"intent", "domain", "action", "params", "response", "confidence"})
_VALID_DOMAINS = frozenset({"home", "infra", "crm", "media", "system", "unknown"})
_VALID_ACTIONS = frozenset({"control", "query", "create", "delete", "backup", "passthrough"})

_PROMPT_PATH = Path(__file__).parent.parent.parent / "web" / "prompts" / "intent_system.txt"


class IntentExtractor:
    """Couche 1 — Extraction d'intention via LLM Ollama (format:json)."""

    def __init__(self) -> None:
        try:
            self._system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("IntentExtractor: prompt manquant — %s", exc)
            self._system_prompt = ""

    async def extract(
        self,
        user_text: str,
        ollama_base_url: str,
        model: str,
    ) -> Optional[dict]:
        """
        Extrait l'intention depuis user_text via Ollama JSON.

        Returns
        -------
        dict avec les clés (intent, domain, action, params, response, confidence)
        ou None si extraction échouée / JSON invalide / schéma incomplet.
        """
        if not self._system_prompt:
            return None

        # Normaliser l'URL Ollama
        base = ollama_base_url.rstrip("/")
        if base.endswith("/api"):
            base = base[:-4]
        chat_url = f"{base}/api/chat"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_text},
            ],
            "format": "json",
            "stream": False,
            "think": False,
            "keep_alive": "5m",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(chat_url, json=payload)
                r.raise_for_status()
                content = r.json().get("message", {}).get("content", "")
                data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.debug("IntentExtractor: JSON invalide — %s", exc)
            return None
        except Exception as exc:
            logger.debug("IntentExtractor: erreur Ollama — %s", exc)
            return None

        return self._validate(data)

    # ------------------------------------------------------------------
    # Validation du schéma

    def _validate(self, data: object) -> Optional[dict]:
        if not isinstance(data, dict):
            return None

        if not _SCHEMA_KEYS.issubset(data.keys()):
            logger.debug(
                "IntentExtractor: schéma incomplet — clés manquantes: %s",
                _SCHEMA_KEYS - data.keys(),
            )
            return None

        # Normaliser domain
        domain = str(data.get("domain", "unknown")).lower()
        data["domain"] = domain if domain in _VALID_DOMAINS else "unknown"

        # Normaliser action
        action = str(data.get("action", "")).lower()
        data["action"] = action if action in _VALID_ACTIONS else "passthrough"

        # Normaliser confidence
        try:
            data["confidence"] = float(data["confidence"])
        except (TypeError, ValueError):
            return None

        # params doit être un dict
        if not isinstance(data.get("params"), dict):
            data["params"] = {}

        # response doit être une chaîne
        if not isinstance(data.get("response"), str):
            data["response"] = str(data.get("response") or "")

        return data


# ---------------------------------------------------------------------------
# Singleton lazy

_extractor: IntentExtractor | None = None


def get_extractor() -> IntentExtractor:
    global _extractor
    if _extractor is None:
        _extractor = IntentExtractor()
    return _extractor

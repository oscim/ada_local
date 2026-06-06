"""core/intent/intent_miner.py — Extraction des intentions depuis le Radar ADA.

Corrèle les événements Radar par request_id pour produire des enregistrements
structurés dans intent_corpus.

Interface publique :
  IntentMiner(radar_store, intent_store, logger=None)
  .run_full_extraction(since=None)  -> dict   (rapport)
  .extract_for_request(request_id)  -> dict | None
  .get_corpus_stats()               -> dict
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types d'événements reconnus comme "action exécutée"
# ---------------------------------------------------------------------------
_ACTION_EVENT_TYPES: frozenset[str] = frozenset({
    "control_light.executed",
    "timer.fired",
    "proxmox.backup.started",
    "n8n.call.success",
    "autoskills.injected",
    "shell_exec.executed",
    "web_search.executed",
    "calendar.event.created",
    "music.played",
    "media.controlled",
    "volume.set",
    "book.searched",
    "n8n.webhook.sent",
})

# Préfixes considérés comme "action exécutée" (pour les events dynamiques)
_ACTION_PREFIXES: tuple[str, ...] = (
    "control_", "timer.", "proxmox.", "n8n.", "autoskills.",
    "shell_", "calendar.", "music.", "media.", "volume.", "book.",
)

_HALLUCINATION_TYPE = "llm.hallucinated_function"
_LLM_COMPLETED_TYPE = "llm.call.completed"

_OUTCOME_PRIORITY = {
    "hallucinated": 6,
    "cancelled":    5,
    "confirmed":    4,
    "success":      3,
    "llm_only":     2,
    "unknown":      1,
}


def _is_action_event(event_type: str) -> bool:
    if event_type in _ACTION_EVENT_TYPES:
        return True
    return any(event_type.startswith(p) for p in _ACTION_PREFIXES)


# ---------------------------------------------------------------------------
# IntentMiner
# ---------------------------------------------------------------------------

class IntentMiner:
    """
    Extrait et structure les intentions depuis le Radar.

    Paramètres
    ----------
    radar_store  : module web.radar.store (ou objet avec query_events / count_events)
    intent_store : module core.intent.intent_store
    logger       : logger Python optionnel
    """

    def __init__(self, radar_store=None, intent_store=None, logger_=None):
        self._log = logger_ or logger

        if radar_store is None:
            from web.radar import store as _rs
            radar_store = _rs
        self._radar = radar_store

        if intent_store is None:
            from core.intent import intent_store as _is
            intent_store = _is
        self._store = intent_store

        # S'assurer que le store est initialisé
        try:
            self._store.init_db()
        except Exception as e:
            self._log.warning("[IntentMiner] Erreur init store : %s", e)

    # ------------------------------------------------------------------
    # Extraction complète
    # ------------------------------------------------------------------

    def run_full_extraction(self, since: str | None = None) -> dict:
        """
        Extrait tous les request_id Radar sans enregistrement dans le corpus.
        Retourne un rapport d'extraction.
        """
        t0 = time.monotonic()
        processed = skipped = new_records = errors = 0

        try:
            all_request_ids = self._get_all_radar_request_ids(since=since)
            known = self._store.known_request_ids(since=since)

            pending = [rid for rid in all_request_ids if rid not in known]

            for request_id in pending:
                try:
                    result = self.extract_for_request(request_id)
                    if result is not None:
                        new_records += 1
                    processed += 1
                except Exception as e:
                    errors += 1
                    self._log.warning(
                        "[IntentMiner] Erreur extraction %s : %s", request_id, e
                    )

            skipped = len(known)

        except Exception as e:
            self._log.error("[IntentMiner] Erreur extraction complète : %s", e)
            errors += 1

        duration_ms = int((time.monotonic() - t0) * 1000)
        rapport = {
            "processed":        processed,
            "skipped_existing": skipped,
            "new_records":      new_records,
            "errors":           errors,
            "duration_ms":      duration_ms,
        }

        # Émet un événement Radar
        self._emit_radar_event(rapport)

        self._log.info(
            "[IntentMiner] Extraction terminée — %d nouveaux, %d ignorés, %d erreurs (%dms)",
            new_records, skipped, errors, duration_ms,
        )
        return rapport

    # ------------------------------------------------------------------
    # Extraction unitaire
    # ------------------------------------------------------------------

    def extract_for_request(self, request_id: str, force: bool = False) -> dict | None:
        """
        Extrait et stocke l'enregistrement pour un request_id.
        Retourne le dict inséré, ou None si déjà existant (sans force).
        """
        if not force:
            existing = self._store.get_record(request_id)
            if existing:
                return None

        events = self._radar.query_events(request_id=request_id, limit=500)
        if not events:
            return None

        record = self._correlate(request_id, events)
        if record is None:
            return None

        self._store.save_record(record, force=force)
        return record

    # ------------------------------------------------------------------
    # Stats corpus
    # ------------------------------------------------------------------

    def get_corpus_stats(self) -> dict:
        """Retourne des agrégats sur le corpus extrait + coverage."""
        base = self._store.stats()

        # Calcul du taux de couverture
        try:
            total_radar = len(self._get_all_radar_request_ids())
            total_corpus = base.get("total", 0)
            coverage = round(total_corpus / total_radar, 4) if total_radar > 0 else 0.0
        except Exception:
            coverage = 0.0

        base["extraction_coverage"] = coverage
        return base

    # ------------------------------------------------------------------
    # Corrélation
    # ------------------------------------------------------------------

    def _correlate(self, request_id: str, events: list[dict]) -> dict | None:
        """
        Corrèle les événements d'un request_id pour produire un enregistrement.
        Priorité des outcomes : hallucinated > cancelled > confirmed > success > llm_only > unknown
        """
        # Chercher l'événement source
        query_event = next(
            (e for e in events if e.get("type") == "rag.query.received"), None
        )
        if query_event is None:
            return None

        raw_text: str = query_event.get("message") or ""
        if not raw_text:
            # Essayer dans metadata
            meta = query_event.get("metadata") or {}
            raw_text = meta.get("message") or meta.get("query") or meta.get("query_preview") or ""
        if not raw_text:
            return None

        timestamp: str = query_event.get("timestamp", "")
        universe: str | None = query_event.get("metadata", {}).get("universe")

        # Analyse de tous les événements du request_id
        outcome        = "unknown"
        outcome_source = None
        detected_action = None
        detected_params = None
        has_hallucination = False
        confirm_required  = False
        confirm_result    = None
        duration_ms       = None
        best_priority     = 0

        for ev in events:
            etype = ev.get("type", "")
            meta  = ev.get("metadata") or {}

            def _set_outcome(o: str, src: str | None = None):
                nonlocal outcome, outcome_source, best_priority
                p = _OUTCOME_PRIORITY.get(o, 0)
                if p > best_priority:
                    outcome        = o
                    outcome_source = src
                    best_priority  = p

            if etype == _HALLUCINATION_TYPE:
                has_hallucination = True
                fn = meta.get("function") or meta.get("function_name") or etype
                _set_outcome("hallucinated", fn)

            elif etype == "confirm_required.cancelled":
                confirm_required = True
                confirm_result   = "cancelled"
                _set_outcome("cancelled", etype)

            elif etype == "confirm_required.confirmed":
                confirm_required = True
                confirm_result   = "confirmed"
                _set_outcome("confirmed", etype)

            elif etype == "confirm_required.created":
                confirm_required = True

            elif _is_action_event(etype):
                action = meta.get("function") or meta.get("action") or etype.split(".")[0]
                _set_outcome("success", etype)
                if detected_action is None:
                    detected_action = action
                    detected_params = {k: v for k, v in meta.items()
                                       if k not in ("function",)}

            elif etype == _LLM_COMPLETED_TYPE:
                dur = meta.get("duration_ms")
                if dur is not None:
                    try:
                        duration_ms = int(dur)
                    except (TypeError, ValueError):
                        pass
                _set_outcome("llm_only", etype)

        from core.intent.intent_store import _normalize

        record: dict[str, Any] = {
            "request_id":       request_id,
            "timestamp":        timestamp,
            "raw_text":         raw_text,
            "normalized_text":  _normalize(raw_text),
            "detected_action":  detected_action,
            "detected_params":  detected_params if detected_params else None,
            "outcome":          outcome,
            "outcome_source":   outcome_source,
            "has_hallucination": has_hallucination,
            "confirm_required": confirm_required,
            "confirm_result":   confirm_result,
            "duration_ms":      duration_ms,
            "universe":         universe,
        }
        return record

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_all_radar_request_ids(self, since: str | None = None) -> list[str]:
        """Récupère tous les request_id distincts des événements rag.query.received."""
        # On requête par lot pour éviter de charger tous les events en mémoire
        ids: list[str] = []
        offset = 0
        batch  = 1000
        while True:
            events = self._radar.query_events(
                type_="rag.query.received",
                from_ts=since,
                limit=batch,
                offset=offset,
            )
            for ev in events:
                rid = ev.get("request_id")
                if rid:
                    ids.append(rid)
            if len(events) < batch:
                break
            offset += batch
        return ids

    def _emit_radar_event(self, rapport: dict) -> None:
        """Émet un événement Radar à la fin de l'extraction."""
        try:
            from web.radar.events import emit_event
            emit_event(
                type="intent_miner.extraction.completed",
                level="info",
                module="intent_miner",
                message="Extraction terminée",
                metadata=rapport,
            )
        except Exception as e:
            self._log.debug("[IntentMiner] Impossible d'émettre événement Radar : %s", e)


# ---------------------------------------------------------------------------
# Singleton / helpers pour le démarrage
# ---------------------------------------------------------------------------

_miner: IntentMiner | None = None


def get_miner() -> IntentMiner:
    global _miner
    if _miner is None:
        _miner = IntentMiner()
    return _miner
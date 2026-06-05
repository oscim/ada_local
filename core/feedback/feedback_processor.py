"""core/feedback/feedback_processor.py — Traitement des signaux feedback ADA.

Classe : FeedbackProcessor
  process_response_feedback(request_id, signal, comment) -> dict
  process_radar_error(event)                              -> None
  flag_autoskill(autoskill_id, reason)                   -> None
  get_pending_rebuild_count()                             -> int
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Événements Radar qui déclenchent une entrée error_log automatique
_RADAR_ERROR_MAP: dict[str, str] = {
    "llm.hallucinated_function":           "hallucinated_function",
    "intent.entity_resolution_failed":     "entity_not_found",
    "n8n.call.failed":                     "action_failed",
    "llm.timeout":                         "timeout",
    "proxmox.backup.failed":               "action_failed",
}


class FeedbackProcessor:

    def __init__(
        self,
        intent_store=None,
        autoskill_store=None,
        error_store=None,
        intent_detector=None,
        radar=None,
        logger_=None,
    ) -> None:
        self._intent_store   = intent_store
        self._autoskill_store = autoskill_store
        self._error_store    = error_store
        self._intent_detector = intent_detector
        self._radar          = radar
        self._log            = logger_ or logger

        # Compteurs pour déclenchement de reconstruction différée
        self._lock = threading.Lock()
        self._pending_positive = 0
        self._pending_negative = 0

        try:
            from config import (
                FEEDBACK_REBUILD_TRIGGER_POSITIVE,
                FEEDBACK_REBUILD_TRIGGER_NEGATIVE,
                FEEDBACK_AUTOSKILL_VALIDATE_THRESHOLD,
                FEEDBACK_AUTOSKILL_REJECT_THRESHOLD,
            )
            self._rebuild_pos = FEEDBACK_REBUILD_TRIGGER_POSITIVE
            self._rebuild_neg = FEEDBACK_REBUILD_TRIGGER_NEGATIVE
            self._validate_threshold = FEEDBACK_AUTOSKILL_VALIDATE_THRESHOLD
            self._reject_threshold   = FEEDBACK_AUTOSKILL_REJECT_THRESHOLD
        except (ImportError, AttributeError):
            self._rebuild_pos = 10
            self._rebuild_neg = 3
            self._validate_threshold = 3
            self._reject_threshold   = 2

    # ------------------------------------------------------------------
    # Signal 👍 / 👎 principal
    # ------------------------------------------------------------------

    def process_response_feedback(
        self,
        request_id: str,
        signal: str,
        comment: str | None = None,
        response_summary: str | None = None,
    ) -> dict:
        """Traite un signal 👍/👎 envoyé depuis le chat."""
        if signal not in ("positive", "negative"):
            return {"error": "signal invalide"}

        # 1. Récupère le record intent_corpus
        record = self._get_corpus_record(request_id)

        # 2. Met à jour intent_corpus
        self._update_corpus(request_id, signal, comment, record)

        # 3. Met à jour l'index TF-IDF
        self._update_index(signal, record)

        # 4. Récupère les autoskills liés et met à jour leurs compteurs
        autoskill_ids = self._get_autoskill_ids(request_id)
        if autoskill_ids:
            self._update_autoskills(autoskill_ids, signal, request_id)

        # 5. Alimente error_log si signal négatif
        error_id = None
        if signal == "negative":
            try:
                from core.feedback.error_store import log_error
                error_id = log_error(
                    request_id=request_id,
                    source="user_feedback",
                    error_type="negative_feedback",
                    raw_text=record.get("raw_text") if record else None,
                    detected_action=record.get("detected_action") if record else None,
                    error_detail=comment,
                    autoskill_ids=autoskill_ids or None,
                )
            except Exception as exc:
                self._log.warning("[FeedbackProcessor] error_log échec : %s", exc)

        # 6. Émet un événement Radar
        evt_type = f"feedback.{'positive' if signal == 'positive' else 'negative'}.recorded"
        self._emit(evt_type, "info",
                   f"Signal {signal} enregistré pour {request_id}",
                   {"request_id": request_id, "comment": comment, "error_id": error_id})

        # 7. Vérification reconstruction différée
        self._check_rebuild(signal)

        return {"status": "recorded", "request_id": request_id}

    # ------------------------------------------------------------------
    # Alimentation automatique depuis événements Radar
    # ------------------------------------------------------------------

    def process_radar_error(self, event: dict) -> None:
        """Traite un événement Radar d'erreur → alimente error_log."""
        event_type = event.get("type", "")
        error_type = _RADAR_ERROR_MAP.get(event_type)
        if not error_type:
            return

        try:
            from config import FEEDBACK_ERROR_LOG_AUTO_RADAR
            if not FEEDBACK_ERROR_LOG_AUTO_RADAR:
                return
        except (ImportError, AttributeError):
            pass

        try:
            from core.feedback.error_store import log_error
            metadata = event.get("metadata", {})
            log_error(
                request_id=event.get("request_id", ""),
                source="radar_auto",
                error_type=error_type,
                raw_text=event.get("message"),
                detected_action=metadata.get("action") or metadata.get("function"),
                error_detail=metadata.get("error") or metadata.get("detail"),
                timestamp=event.get("timestamp"),
            )
            self._emit("error_log.created", "info",
                       f"error_log auto depuis {event_type}",
                       {"request_id": event.get("request_id"), "error_type": error_type})
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] process_radar_error : %s", exc)

    # ------------------------------------------------------------------
    # Flagging AutoSkill
    # ------------------------------------------------------------------

    def flag_autoskill(self, autoskill_id: str, reason: str) -> None:
        """Marque un AutoSkill pour révision manuelle."""
        try:
            from core.skills.skills_db import get_connection
            conn = get_connection()
            conn.execute(
                "UPDATE skills SET status='under_review', updated_at=datetime('now') WHERE id=?",
                (autoskill_id,),
            )
            conn.commit()
            conn.close()
            self._emit("autoskill.flagged", "warning",
                       f"AutoSkill {autoskill_id} mis en révision : {reason}",
                       {"autoskill_id": autoskill_id, "reason": reason})
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] flag_autoskill : %s", exc)

    # ------------------------------------------------------------------
    # Compteur de reconstruction différée
    # ------------------------------------------------------------------

    def get_pending_rebuild_count(self) -> int:
        with self._lock:
            return self._pending_positive + self._pending_negative

    # ------------------------------------------------------------------
    # Méthodes internes
    # ------------------------------------------------------------------

    def _get_corpus_record(self, request_id: str) -> dict | None:
        try:
            from core.intent.intent_store import get_record
            return get_record(request_id)
        except Exception:
            return None

    def _update_corpus(
        self,
        request_id: str,
        signal: str,
        comment: str | None,
        record: dict | None,
    ) -> None:
        try:
            from core.intent.intent_store import _conn as _ic_conn, _get_db_path
            now = datetime.now(timezone.utc).isoformat()
            # Ajout des colonnes feedback si absentes (migration légère)
            _ensure_feedback_columns()
            with _ic_conn() as con:
                if signal == "positive":
                    con.execute(
                        """UPDATE intent_corpus
                           SET is_validated=1, validated_at=?,
                               validated_action=detected_action,
                               feedback_signal=?, feedback_comment=?
                           WHERE request_id=?""",
                        (now, signal, comment, request_id),
                    )
                else:
                    con.execute(
                        """UPDATE intent_corpus
                           SET is_validated=1, validated_at=?,
                               validated_action=NULL,
                               feedback_signal=?, feedback_comment=?,
                               index_excluded=1
                           WHERE request_id=?""",
                        (now, signal, comment, request_id),
                    )
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] _update_corpus : %s", exc)

    def _update_index(self, signal: str, record: dict | None) -> None:
        try:
            from core.intent.intent_detector import get_detector
            detector = get_detector()
            if not detector.is_ready():
                return

            if signal == "positive" and record:
                detector.add_to_index(record)
                self._emit("feedback.index_updated", "info",
                           "Index TF-IDF mis à jour (ajout)",
                           {"request_id": record.get("request_id")})
            elif signal == "negative" and record:
                # Retrait incrémental : rebuild complet différé ; on marque juste excluded
                pass
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] _update_index : %s", exc)

    def _get_autoskill_ids(self, request_id: str) -> list[str]:
        try:
            from core.skills.skills_db import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT skill_id FROM autoskill_injections WHERE request_id=?",
                (request_id,),
            ).fetchall()
            conn.close()
            return [r["skill_id"] for r in rows]
        except Exception:
            return []

    def _update_autoskills(self, autoskill_ids: list[str], signal: str, request_id: str) -> None:
        try:
            _ensure_autoskill_feedback_columns()
            from core.skills.skills_db import get_connection
            conn = get_connection()
            now = datetime.now(timezone.utc).isoformat()

            for skill_id in autoskill_ids:
                if signal == "positive":
                    conn.execute(
                        """UPDATE skills
                           SET validated_count = COALESCE(validated_count, 0) + 1,
                               last_validated_at = ?,
                               updated_at = datetime('now')
                           WHERE id = ?""",
                        (now, skill_id),
                    )
                    row = conn.execute(
                        "SELECT validated_count, status FROM skills WHERE id=?",
                        (skill_id,),
                    ).fetchone()
                    if row and (row["validated_count"] or 0) >= self._validate_threshold:
                        if row["status"] not in ("confirmed", "archived"):
                            conn.execute(
                                "UPDATE skills SET status='confirmed', updated_at=datetime('now') WHERE id=?",
                                (skill_id,),
                            )
                            self._emit("autoskill.validated", "info",
                                       f"AutoSkill {skill_id} promu 'confirmed'",
                                       {"autoskill_id": skill_id,
                                        "validated_count": row["validated_count"]})
                else:  # negative
                    conn.execute(
                        """UPDATE skills
                           SET rejected_count = COALESCE(rejected_count, 0) + 1,
                               last_rejected_at = ?,
                               updated_at = datetime('now')
                           WHERE id = ?""",
                        (now, skill_id),
                    )
                    row = conn.execute(
                        "SELECT rejected_count, status FROM skills WHERE id=?",
                        (skill_id,),
                    ).fetchone()
                    if row and (row["rejected_count"] or 0) >= self._reject_threshold:
                        if row["status"] not in ("under_review", "archived"):
                            conn.execute(
                                "UPDATE skills SET status='under_review', updated_at=datetime('now') WHERE id=?",
                                (skill_id,),
                            )
                            self._emit("autoskill.flagged", "warning",
                                       f"AutoSkill {skill_id} mis en révision",
                                       {"autoskill_id": skill_id,
                                        "rejected_count": row["rejected_count"]})

            conn.commit()
            conn.close()
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] _update_autoskills : %s", exc)

    def _check_rebuild(self, signal: str) -> None:
        with self._lock:
            if signal == "positive":
                self._pending_positive += 1
            else:
                self._pending_negative += 1
            do_rebuild = (
                self._pending_positive >= self._rebuild_pos
                or self._pending_negative >= self._rebuild_neg
            )
            if do_rebuild:
                self._pending_positive = 0
                self._pending_negative = 0

        if do_rebuild:
            self._trigger_rebuild()

    def _trigger_rebuild(self) -> None:
        try:
            from core.intent.intent_detector import get_detector
            import threading as _t
            t = _t.Thread(
                target=get_detector().rebuild_index,
                daemon=True,
                name="intent-rebuild",
            )
            t.start()
            self._emit("feedback.index_rebuilt", "info",
                       "Reconstruction complète de l'index TF-IDF déclenchée", {})
        except Exception as exc:
            self._log.warning("[FeedbackProcessor] _trigger_rebuild : %s", exc)

    def _emit(self, type_: str, level: str, message: str, metadata: dict) -> None:
        try:
            from web.radar.events import emit_event
            emit_event(
                type=type_, level=level, module="core.feedback",
                message=message, metadata=metadata,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Migrations légères (colonnes ajoutées si absentes)
# ---------------------------------------------------------------------------

_feedback_cols_ensured = False
_autoskill_cols_ensured = False


def _ensure_feedback_columns() -> None:
    global _feedback_cols_ensured
    if _feedback_cols_ensured:
        return
    try:
        from core.intent.intent_store import _conn as _ic_conn
        with _ic_conn() as con:
            existing = {
                r[1] for r in con.execute("PRAGMA table_info(intent_corpus)").fetchall()
            }
            for col, definition in [
                ("feedback_signal",  "TEXT"),
                ("feedback_comment", "TEXT"),
                ("index_excluded",   "INTEGER NOT NULL DEFAULT 0"),
            ]:
                if col not in existing:
                    con.execute(f"ALTER TABLE intent_corpus ADD COLUMN {col} {definition}")
        _feedback_cols_ensured = True
    except Exception as exc:
        logger.warning("[FeedbackProcessor] _ensure_feedback_columns : %s", exc)


def _ensure_autoskill_feedback_columns() -> None:
    global _autoskill_cols_ensured
    if _autoskill_cols_ensured:
        return
    try:
        from core.skills.skills_db import get_connection
        conn = get_connection()
        existing = {
            r[1] for r in conn.execute("PRAGMA table_info(skills)").fetchall()
        }
        for col, definition in [
            ("validated_count",   "INTEGER NOT NULL DEFAULT 0"),
            ("rejected_count",    "INTEGER NOT NULL DEFAULT 0"),
            ("last_validated_at", "TEXT"),
            ("last_rejected_at",  "TEXT"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE skills ADD COLUMN {col} {definition}")
        conn.commit()
        conn.close()
        _autoskill_cols_ensured = True
    except Exception as exc:
        logger.warning("[FeedbackProcessor] _ensure_autoskill_feedback_columns : %s", exc)


# ---------------------------------------------------------------------------
# Instance globale
# ---------------------------------------------------------------------------

_processor: FeedbackProcessor | None = None


def get_processor() -> FeedbackProcessor:
    global _processor
    if _processor is None:
        _processor = FeedbackProcessor()
    return _processor

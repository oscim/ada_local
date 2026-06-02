"""
n8n_bridge.py — Connecteur n8n bidirectionnel pour ADA.
Phases 1–4 de la spec ADA_SPEC_N8N_BRIDGE-2.md

Composants :
  N8nEventStore       — journalisation SQLite integration_events
  N8nBridgeConnector  — envoi d'événements normalisés vers n8n (sortant)
  N8nEventValidator   — validation des événements entrants
  N8nEventRouter      — routage par domaine (entrant)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers config
# ---------------------------------------------------------------------------

def _cfg() -> dict:
    """Retourne la config n8n bridge depuis config.py (valeurs par défaut si absentes)."""
    try:
        import config as _c
        return {
            "enabled":          getattr(_c, "N8N_BRIDGE_ENABLED",         True),
            "base_url":         getattr(_c, "N8N_BASE_URL",                "http://localhost:5678"),
            "webhook_url":      getattr(_c, "N8N_DEFAULT_WEBHOOK_URL",     "http://localhost:5678/webhook/ada-event"),
            "timeout":          getattr(_c, "N8N_TIMEOUT_SECONDS",         10),
            "max_retries":      getattr(_c, "N8N_MAX_RETRIES",             2),
            "verify_ssl":       getattr(_c, "N8N_VERIFY_SSL",              True),
            "fallback_enabled": getattr(_c, "N8N_FALLBACK_ENABLED",        True),
            "allowed_domains":  getattr(_c, "N8N_ALLOWED_EVENT_DOMAINS",   [
                "domotic", "marketing", "social", "lead", "crm",
                "support", "content", "notification", "workflow", "system",
            ]),
        }
    except Exception:
        return {
            "enabled": False, "base_url": "", "webhook_url": "",
            "timeout": 10, "max_retries": 2, "verify_ssl": True,
            "fallback_enabled": False, "allowed_domains": [],
        }


# ---------------------------------------------------------------------------
# N8nEventStore — journalisation SQLite integration_events
# ---------------------------------------------------------------------------

class N8nEventStore:
    """Journalisation des événements n8n dans SQLite integration_events."""

    _DB_PATH = Path(__file__).parent.parent / "data" / "n8n" / "integration_events.sqlite"

    _CREATE_SQL = """
CREATE TABLE IF NOT EXISTS integration_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    source           TEXT NOT NULL,
    target           TEXT,
    direction        TEXT NOT NULL,
    initiated_by     TEXT,
    universe         TEXT,
    idempotency_key  TEXT,
    correlation_id   TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    payload_json     TEXT,
    metadata_json    TEXT,
    error_message    TEXT,
    created_at       TEXT NOT NULL,
    processed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ievents_event_id     ON integration_events(event_id);
CREATE INDEX IF NOT EXISTS idx_ievents_idempotency  ON integration_events(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_ievents_correlation  ON integration_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ievents_type         ON integration_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ievents_initiated_by ON integration_events(initiated_by);
CREATE INDEX IF NOT EXISTS idx_ievents_universe     ON integration_events(universe);
"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            self._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._DB_PATH)) as con:
                for stmt in self._CREATE_SQL.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        con.execute(stmt)
                con.commit()
        except Exception as exc:
            logger.error("[N8nStore] Erreur init DB : %s", exc)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._DB_PATH), check_same_thread=False)

    def save(self, event: dict, direction: str, status: str = "pending") -> int | None:
        """Enregistre un événement. Retourne l'id SQLite ou None."""
        try:
            payload = event.get("payload", {})
            meta    = event.get("metadata", {})
            now     = datetime.now(timezone.utc).isoformat()
            with self._lock:
                with self._conn() as con:
                    cur = con.execute(
                        """INSERT INTO integration_events
                           (event_id, event_type, source, target, direction,
                            initiated_by, universe, idempotency_key, correlation_id,
                            status, payload_json, metadata_json, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            event.get("event_id", ""),
                            event.get("event_type") or event.get("event", ""),
                            event.get("source", ""),
                            event.get("target", ""),
                            direction,
                            event.get("initiated_by", ""),
                            event.get("universe", ""),
                            event.get("idempotency_key", ""),
                            event.get("correlation_id", ""),
                            status,
                            json.dumps(payload, ensure_ascii=False),
                            json.dumps(meta,    ensure_ascii=False),
                            now,
                        ),
                    )
                    con.commit()
                    return cur.lastrowid
        except Exception as exc:
            logger.error("[N8nStore] save error : %s", exc)
            return None

    def update_status(self, event_id: str, status: str, error: str = "") -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._lock:
                with self._conn() as con:
                    con.execute(
                        "UPDATE integration_events SET status=?, error_message=?, processed_at=? WHERE event_id=?",
                        (status, error or None, now, event_id),
                    )
                    con.commit()
        except Exception as exc:
            logger.error("[N8nStore] update_status error : %s", exc)

    def is_duplicate(self, idempotency_key: str) -> bool:
        """Retourne True si l'idempotency_key a déjà été traitée avec succès."""
        if not idempotency_key:
            return False
        try:
            with self._conn() as con:
                row = con.execute(
                    "SELECT id FROM integration_events"
                    " WHERE idempotency_key=? AND status NOT IN ('failed', 'pending') LIMIT 1",
                    (idempotency_key,),
                ).fetchone()
                return row is not None
        except Exception:
            return False

    def list_events(
        self,
        direction:    str | None = None,
        status:       str | None = None,
        event_type:   str | None = None,
        universe:     str | None = None,
        initiated_by: str | None = None,
        limit:        int = 50,
        offset:       int = 0,
    ) -> list[dict]:
        """Liste les événements avec filtres optionnels."""
        conditions: list[str] = []
        params:     list      = []
        if direction:
            conditions.append("direction=?")
            params.append(direction)
        if status:
            conditions.append("status=?")
            params.append(status)
        if event_type:
            conditions.append("event_type LIKE ?")
            params.append(f"%{event_type}%")
        if universe:
            conditions.append("universe=?")
            params.append(universe)
        if initiated_by:
            conditions.append("initiated_by=?")
            params.append(initiated_by)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params += [limit, offset]
        try:
            with self._conn() as con:
                con.row_factory = sqlite3.Row
                rows = con.execute(
                    f"SELECT * FROM integration_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    params,
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("[N8nStore] list_events error : %s", exc)
            return []

    def get_by_event_id(self, event_id: str) -> dict | None:
        try:
            with self._conn() as con:
                con.row_factory = sqlite3.Row
                row = con.execute(
                    "SELECT * FROM integration_events WHERE event_id=? LIMIT 1",
                    (event_id,),
                ).fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def stats(self) -> dict:
        try:
            with self._conn() as con:
                total  = con.execute("SELECT COUNT(*) FROM integration_events").fetchone()[0]
                out    = con.execute("SELECT COUNT(*) FROM integration_events WHERE direction='outbound'").fetchone()[0]
                inb    = con.execute("SELECT COUNT(*) FROM integration_events WHERE direction='inbound'").fetchone()[0]
                failed = con.execute("SELECT COUNT(*) FROM integration_events WHERE status='failed'").fetchone()[0]
                return {"total": total, "outbound": out, "inbound": inb, "failed": failed}
        except Exception:
            return {"total": 0, "outbound": 0, "inbound": 0, "failed": 0}


# ---------------------------------------------------------------------------
# N8nBridgeConnector — sortant
# ---------------------------------------------------------------------------

class N8nBridgeConnector:
    """Envoi d'événements normalisés depuis ADA vers n8n."""

    def __init__(self, store: N8nEventStore | None = None) -> None:
        self._store = store or N8nEventStore()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_event_id() -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"evt_{ts}_{uuid.uuid4().hex[:6]}"

    def _build_envelope(
        self,
        event_type:      str,
        payload:         dict,
        initiated_by:    str        = "system",
        universe:        str | None = None,
        metadata:        dict | None = None,
        correlation_id:  str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        return {
            "event_id":        self._new_event_id(),
            "event_type":      event_type,
            "source":          "ada",
            "target":          "n8n",
            "timestamp":       self._now_iso(),
            "idempotency_key": idempotency_key or "",
            "correlation_id":  correlation_id  or "",
            "initiated_by":    initiated_by,
            "universe":        universe or "",
            "payload":         payload or {},
            "metadata":        metadata or {"origin_module": "n8n_bridge", "executor": "N8nBridgeConnector"},
        }

    @staticmethod
    def _build_headers() -> dict:
        """En-têtes HTTP pour les appels sortants vers n8n."""
        from core.settings_store import settings
        token   = settings.get("webhook.secret", "")
        headers = {"Content-Type": "application/json", "X-Source": "ada"}
        if token:
            headers["X-ADA-Token"] = token  # token n'est PAS loggé
        return headers

    def _emit_radar(self, radar_type: str, level: str, event_id: str, extra: dict | None = None) -> None:
        try:
            from web.radar.events import emit_event
            emit_event(
                type=radar_type,
                level=level,
                module="n8n_bridge",
                metadata={"event_id": event_id, **(extra or {})},
            )
        except Exception:
            pass

    # ── API publique ────────────────────────────────────────────────────────

    def send_event(
        self,
        event_type:      str,
        payload:         dict,
        initiated_by:    str        = "system",
        universe:        str | None = None,
        metadata:        dict | None = None,
        correlation_id:  str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """
        Envoie un événement normalisé vers n8n.
        Ne lève jamais d'exception.
        Retourne {"ok": bool, "event_id": str, ...}.
        """
        cfg = _cfg()
        if not cfg["enabled"]:
            return {"ok": False, "detail": "N8N bridge désactivé"}

        envelope = self._build_envelope(
            event_type, payload, initiated_by, universe, metadata,
            correlation_id, idempotency_key,
        )
        self._store.save(envelope, "outbound", "pending")

        url     = cfg["webhook_url"]
        timeout = cfg["timeout"]
        retries = cfg["max_retries"]
        verify  = cfg["verify_ssl"]

        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=envelope,
                    headers=self._build_headers(),
                    timeout=timeout,
                    verify=verify,
                )
                resp.raise_for_status()
                self._store.update_status(envelope["event_id"], "sent")
                self._emit_radar("n8n_event_sent", "info", envelope["event_id"],
                                 {"event_type": event_type, "attempt": attempt + 1})
                return {"ok": True, "event_id": envelope["event_id"]}
            except Exception as exc:
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                err_msg = str(exc)
                self._store.update_status(envelope["event_id"], "failed", err_msg)
                self._emit_radar("n8n_event_failed", "error", envelope["event_id"],
                                 {"error": err_msg[:200], "event_type": event_type})
                logger.error("[N8nBridge] send_event %s failed : %s", event_type, err_msg)
                return {"ok": False, "event_id": envelope["event_id"], "detail": err_msg}

        return {"ok": False, "event_id": envelope.get("event_id", ""), "detail": "max_retries exceeded"}

    def send_fallback(
        self,
        original_function: str,
        original_params:   dict,
        failure_reason:    str,
        user_message:      str,
        initiated_by:      str        = "system",
        universe:          str | None = None,
    ) -> dict:
        """
        Fallback pipeline : délègue la demande à n8n si la fonction locale échoue.
        Contrat réponse attendu de n8n : {"ok": true, "reply": "..."}.
        Ne lève jamais d'exception.
        """
        cfg = _cfg()
        if not cfg["enabled"] or not cfg["fallback_enabled"]:
            return {"ok": False, "detail": "Fallback n8n désactivé"}

        envelope = self._build_envelope(
            event_type="workflow.fallback_requested",
            payload={
                "original_function": original_function,
                "original_params":   original_params,
                "failure_reason":    failure_reason,
                "user_message":      user_message[:500],
            },
            initiated_by=initiated_by,
            universe=universe,
            metadata={"origin_module": "pipeline", "executor": "n8n_bridge_fallback"},
        )
        self._store.save(envelope, "outbound", "pending")
        self._emit_radar("n8n_fallback_triggered", "info", envelope["event_id"],
                         {"function": original_function, "reason": failure_reason})

        try:
            resp = requests.post(
                cfg["webhook_url"],
                json=envelope,
                headers=self._build_headers(),
                timeout=cfg["timeout"],
                verify=cfg["verify_ssl"],
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok") and data.get("reply"):
                self._store.update_status(envelope["event_id"], "sent")
                self._emit_radar("n8n_fallback_ok", "info", envelope["event_id"],
                                 {"reply_len": len(data["reply"])})
                return {"ok": True, "reply": data["reply"], "event_id": envelope["event_id"]}
            else:
                self._store.update_status(envelope["event_id"], "failed", "n8n: no reply field")
                self._emit_radar("n8n_fallback_failed", "warn", envelope["event_id"], {})
                return {"ok": False, "detail": "n8n n'a pas retourné de champ reply"}
        except Exception as exc:
            err = str(exc)
            self._store.update_status(envelope["event_id"], "failed", err)
            self._emit_radar("n8n_fallback_failed", "error", envelope["event_id"], {"error": err[:200]})
            logger.error("[N8nBridge] send_fallback failed : %s", err)
            return {"ok": False, "detail": err}


# ---------------------------------------------------------------------------
# N8nEventValidator — entrant
# ---------------------------------------------------------------------------

class N8nEventValidator:
    """Valide les événements entrants depuis n8n."""

    MAX_PAYLOAD_BYTES = 512 * 1024  # 512 KB

    def validate(self, payload: dict, raw_body_size: int = 0) -> tuple[bool, str]:
        """
        Retourne (ok, error_message).
        ok=True si le payload est valide pour le routage.
        """
        if raw_body_size > self.MAX_PAYLOAD_BYTES:
            return False, f"Payload trop volumineux ({raw_body_size} bytes, max 524288)"

        has_text   = bool({"text", "message", "query", "queryText"} & set(payload))
        has_event  = "event" in payload or "event_type" in payload
        has_action = "action" in payload

        if not (has_text or has_event or has_action):
            return False, "Payload non reconnu — champs attendus: text/message/action/event/event_type"

        # Validation domaine si event_type présent
        cfg        = _cfg()
        event_type = str(payload.get("event_type") or payload.get("event", ""))
        if event_type and "." in event_type:
            domain  = event_type.split(".")[0]
            allowed = cfg.get("allowed_domains", [])
            if allowed and domain not in allowed:
                return False, f"Event domain '{domain}' non autorisé"

        return True, ""


# ---------------------------------------------------------------------------
# N8nEventRouter — routage par domaine (entrant)
# ---------------------------------------------------------------------------

class N8nEventRouter:
    """Route les événements entrants vers le handler de domaine approprié."""

    def __init__(self, store: N8nEventStore | None = None) -> None:
        self._store = store or N8nEventStore()

    def route(self, event: dict) -> dict:
        """
        Route l'événement selon son domaine.
        Journalise dans integration_events.
        Retourne {"status": str, "action": str, "domain": str, ...}.
        """
        event_type = str(event.get("event_type") or event.get("event", "webhook.event"))
        domain     = event_type.split(".")[0] if "." in event_type else "generic"

        handlers = {
            "lead":         self._lead_handler,
            "marketing":    self._marketing_handler,
            "domotic":      self._domotic_handler,
            "workflow":     self._workflow_handler,
            "crm":          self._crm_handler,
            "support":      self._support_handler,
            "notification": self._notification_handler,
            "social":       self._social_handler,
            "content":      self._content_handler,
            "system":       self._system_handler,
        }
        handler = handlers.get(domain, self._default_handler)
        result  = handler(event, event_type)

        # Journalisation dans integration_events
        self._store.save(
            {
                "event_id":        event.get("event_id", f"in_{uuid.uuid4().hex[:12]}"),
                "event_type":      event_type,
                "source":          event.get("source", "n8n"),
                "correlation_id":  event.get("correlation_id", ""),
                "initiated_by":    event.get("initiated_by", ""),
                "universe":        event.get("universe", ""),
                "idempotency_key": event.get("idempotency_key", ""),
                "payload": {
                    k: v for k, v in event.items()
                    if k not in ("event", "event_type", "event_id")
                },
                "metadata": {"domain": domain, "handler": handler.__name__},
            },
            "inbound",
            result.get("status", "processed"),
        )

        self._emit_radar("n8n_event_processed", event_type, event.get("event_id", ""), domain)
        return result

    def _emit_radar(self, radar_type: str, event_type: str, event_id: str, domain: str) -> None:
        try:
            from web.radar.events import emit_event
            emit_event(
                type=radar_type,
                level="info",
                module=f"n8n.{domain}",
                metadata={"event_type": event_type, "event_id": event_id},
            )
        except Exception:
            pass

    # ── Handlers métier ─────────────────────────────────────────────────────

    def _default_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] event '%s' → default_handler (logged)", event_type)
        return {"status": "logged", "action": "none", "domain": "generic"}

    def _domotic_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] domotic event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "domotic"}

    def _lead_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] lead event : %s | name=%s", event_type, event.get("name", ""))
        return {"status": "processed", "action": "lead_logged", "domain": "lead",
                "name": event.get("name"), "company": event.get("company")}

    def _marketing_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] marketing event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "marketing"}

    def _workflow_handler(self, event: dict, event_type: str) -> dict:
        wf     = event.get("workflow", "")
        status = event.get("status", "unknown")
        logger.info("[N8nRouter] workflow event : %s | workflow=%s status=%s", event_type, wf, status)
        return {"status": "processed", "action": "workflow_logged", "domain": "workflow",
                "workflow": wf, "wf_status": status}

    def _crm_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] CRM event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "crm"}

    def _support_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] support event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "support"}

    def _notification_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] notification event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "notification"}

    def _social_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] social event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "social"}

    def _content_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] content event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "content"}

    def _system_handler(self, event: dict, event_type: str) -> dict:
        logger.info("[N8nRouter] system event : %s", event_type)
        return {"status": "processed", "action": "logged", "domain": "system"}


# ---------------------------------------------------------------------------
# Singletons (utilisés par router_webhook et router_n8n)
# ---------------------------------------------------------------------------

_store           = N8nEventStore()
bridge_connector = N8nBridgeConnector(store=_store)
event_validator  = N8nEventValidator()
event_router     = N8nEventRouter(store=_store)

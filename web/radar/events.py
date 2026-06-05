"""web/radar/events.py — Bus SSE + persistance des événements Radar.

Interface publique :
  subscribe_sse()    -> asyncio.Queue
  unsubscribe_sse(q) -> None
  publish(event)     -> None       ← appelé par radar_collector (événement déjà normalisé)
  emit_event(...)    -> None       ← appelé depuis pipeline/middleware (thread-safe)
                                      persiste ET diffuse en SSE
  set_main_loop(loop)-> None       ← appelé au startup
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_main_loop: asyncio.AbstractEventLoop | None = None
_subscribers: set[asyncio.Queue] = set()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop
    logger.debug("RadarSSE : boucle principale enregistrée.")


# ---------------------------------------------------------------------------
# Abonnements SSE
# ---------------------------------------------------------------------------

def subscribe_sse() -> asyncio.Queue:
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    logger.debug("RadarSSE : +1 abonné (%d total)", len(_subscribers))
    return q


def unsubscribe_sse(q: asyncio.Queue) -> None:
    _subscribers.discard(q)
    logger.debug("RadarSSE : -1 abonné (%d total)", len(_subscribers))


# ---------------------------------------------------------------------------
# Diffusion SSE seule (appelée par radar_collector — déjà persisté)
# ---------------------------------------------------------------------------

def publish(event: dict[str, Any]) -> None:
    """Diffuse un événement déjà persisté à tous les abonnés SSE."""
    dead: set[asyncio.Queue] = set()
    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("RadarSSE : queue abonné pleine, événement %s ignoré.", event.get("id"))
        except Exception as exc:
            logger.error("RadarSSE : erreur diffusion — %s", exc)
            dead.add(q)
    _subscribers.difference_update(dead)


# ---------------------------------------------------------------------------
# Émission complète : persistance SQLite + diffusion SSE
# Appelée depuis le pipeline et les middlewares
# ---------------------------------------------------------------------------

def emit_event(
    type: str,
    message: str = "",
    level: str = "info",
    module: str | None = None,
    metadata: dict | None = None,
    request_id: str | None = None,
    duration_ms: int | None = None,
    **kwargs: Any,
) -> None:
    """
    Persiste l'événement dans SQLite ET le diffuse aux abonnés SSE.
    Thread-safe : peut être appelé depuis n'importe quel contexte.
    """
    # Enrichir metadata avec duration_ms si fourni
    meta = metadata or {}
    if duration_ms is not None:
        meta = {**meta, "duration_ms": duration_ms}

    event: dict[str, Any] = {
        "id":          f"evt_{uuid4().hex[:20]}",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "level":       level,
        "type":        type,
        "module":      module,
        "message":     message,
        "metadata":    meta,
        "request_id":  request_id,
        "document_id": kwargs.get("document_id"),
        "job_id":      kwargs.get("job_id"),
        "session_id":  kwargs.get("session_id"),
    }

    # 1. Persistance SQLite — synchrone, directe
    try:
        from web.radar.store import save_event
        save_event(event)
    except Exception as exc:
        logger.error("RadarSSE : échec persistance SQLite — %s", exc)

    # 2. Hook FeedbackProcessor — alimentation automatique error_log depuis Radar
    _RADAR_ERROR_TYPES = frozenset({
        "llm.hallucinated_function",
        "intent.entity_resolution_failed",
        "n8n.call.failed",
        "llm.timeout",
        "proxmox.backup.failed",
    })
    if event.get("type") in _RADAR_ERROR_TYPES:
        try:
            from config import FEEDBACK_ENABLED, FEEDBACK_ERROR_LOG_AUTO_RADAR
            if FEEDBACK_ENABLED and FEEDBACK_ERROR_LOG_AUTO_RADAR:
                from core.feedback.feedback_processor import get_processor as _get_fp
                _get_fp().process_radar_error(event)
        except Exception:
            pass

    # 3. Diffusion SSE — directe si dans la boucle, sinon via call_soon_threadsafe
    try:
        loop = asyncio.get_running_loop()
        # On est dans une coroutine asyncio — diffusion directe
        loop.call_soon(publish, event)
    except RuntimeError:
        # Pas de boucle courante — contexte thread
        if _main_loop and _main_loop.is_running():
            _main_loop.call_soon_threadsafe(publish, event)
        else:
            logger.debug("RadarSSE : emit_event sans boucle active, SSE ignoré (persisté).")
    except Exception as exc:
        logger.error("RadarSSE : échec diffusion SSE — %s", exc)

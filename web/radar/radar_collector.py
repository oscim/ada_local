"""web/radar/radar_collector.py — Collecteur d'événements Radar ADA."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Instance globale — la Queue est créée dans start(), pas ici
_instance: RadarCollector | None = None


def get_collector() -> RadarCollector | None:
    """Retourne l'instance active du collecteur, ou None si non démarré."""
    return _instance


class RadarCollector:

    def __init__(self) -> None:
        self._running: bool = False
        self._worker_task: asyncio.Task | None = None
        self._queue: asyncio.Queue | None = None

    async def start(self) -> None:
        global _instance
        if self._running:
            logger.warning("RadarCollector déjà démarré.")
            return

        try:
            from web.radar.store import init_db
            init_db()
        except Exception as exc:
            logger.error("RadarCollector : échec init_db — %s", exc)
            return

        # Queue créée ICI sur la boucle uvicorn active
        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._running = True
        _instance = self
        self._worker_task = loop.create_task(self._worker(), name="radar_worker")
        logger.info("RadarCollector démarré (loop=%s).", id(loop))

    async def stop(self) -> None:
        global _instance
        if not self._running:
            return
        self._running = False
        if self._queue:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        _instance = None
        logger.info("RadarCollector arrêté.")

    def emit(self, event: dict[str, Any]) -> None:
        if not self._running or self._queue is None:
            return
        try:
            self._queue.put_nowait(self._normalize(event))
        except asyncio.QueueFull:
            logger.warning("RadarCollector : queue pleine, événement ignoré.")

    async def _worker(self) -> None:
        from web.radar import store as radar_store
        from web.radar import events as radar_events
        logger.info("radar_worker : actif sur loop=%s.", id(asyncio.get_running_loop()))
        while self._running or (self._queue and not self._queue.empty()):
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                radar_store.save_event(event)
                radar_events.publish(event)
            except Exception as exc:
                logger.error("RadarCollector : erreur — %s", exc)
            finally:
                self._queue.task_done()

    @staticmethod
    def _normalize(event: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id":          event.get("id") or f"evt_{uuid4().hex[:20]}",
            "timestamp":   event.get("timestamp") or now,
            "level":       event.get("level", "info"),
            "type":        event.get("type", "unknown"),
            "module":      event.get("module"),
            "message":     event.get("message", ""),
            "metadata":    event.get("metadata") or {},
            "request_id":  event.get("request_id"),
            "document_id": event.get("document_id"),
            "job_id":      event.get("job_id"),
            "session_id":  event.get("session_id"),
        }


# PAS de singleton instancié ici — créé dans server.py startup
# Pour émettre depuis le pipeline : utiliser emit_event() de radar_events.py
# qui ne dépend pas du collecteur
radar_collector = RadarCollector()

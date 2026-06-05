"""web/radar/events.py — Bus SSE pour la diffusion temps réel des événements Radar.

Interface publique attendue par router_radar.py et radar_collector.py :
  subscribe_sse()       -> asyncio.Queue
  unsubscribe_sse(q)    -> None
  publish(event)        -> None
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Ensemble des queues actives (une par client SSE connecté)
_subscribers: set[asyncio.Queue] = set()


def subscribe_sse() -> asyncio.Queue:
    """Enregistre un nouvel abonné SSE et retourne sa queue."""
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    logger.debug("RadarSSE : +1 abonné (%d total)", len(_subscribers))
    return q


def unsubscribe_sse(q: asyncio.Queue) -> None:
    """Supprime un abonné SSE. Appelé à la déconnexion du client."""
    _subscribers.discard(q)
    logger.debug("RadarSSE : -1 abonné (%d total)", len(_subscribers))


def publish(event: dict[str, Any]) -> None:
    """
    Diffuse un événement à tous les abonnés SSE actifs.

    Si la queue d'un abonné est pleine (client lent), l'événement est ignoré
    pour cet abonné uniquement — les autres ne sont pas affectés.
    """
    dead: set[asyncio.Queue] = set()

    for q in _subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("RadarSSE : queue abonné pleine, événement %s ignoré.", event.get("id"))
        except Exception as exc:
            logger.error("RadarSSE : erreur diffusion — %s", exc)
            dead.add(q)

    # Nettoie les abonnés défaillants
    _subscribers.difference_update(dead)

"""web/router_radar.py — Radar : exposition HTTP des événements ADA.

Routes :
  GET  /api/radar/events          — liste paginée / filtrée des événements
  GET  /api/radar/events/{id}     — détail d'un événement
  GET  /api/radar/stats           — compteurs globaux
  GET  /api/radar/stream          — flux SSE temps réel
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/radar", tags=["radar"])


# ---------------------------------------------------------------------------
# GET /api/radar/events
# ---------------------------------------------------------------------------
@router.get("/events")
async def radar_events(
    level:      str | None = Query(None, description="info | warning | error | critical"),
    type_:      str | None = Query(None, alias="type", description="Filtre sur le type d'événement"),
    module:     str | None = Query(None),
    request_id: str | None = Query(None),
    document_id: str | None = Query(None),
    job_id:     str | None = Query(None),
    session_id: str | None = Query(None),
    from_ts:    str | None = Query(None, description="ISO 8601 borne inférieure"),
    to_ts:      str | None = Query(None, description="ISO 8601 borne supérieure"),
    q:          str | None = Query(None, description="Recherche libre dans message/metadata"),
    limit:      int        = Query(50, ge=1, le=500),
    offset:     int        = Query(0,  ge=0),
):
    """Liste paginée des événements Radar (triés par timestamp desc)."""
    try:
        from web.radar.store import query_events, count_events
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    events = query_events(
        level=level,
        type_=type_,
        module=module,
        request_id=request_id,
        document_id=document_id,
        job_id=job_id,
        session_id=session_id,
        from_ts=from_ts,
        to_ts=to_ts,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "count": len(events), "offset": offset, "events": events}


# ---------------------------------------------------------------------------
# GET /api/radar/events/{event_id}
# ---------------------------------------------------------------------------
@router.get("/events/{event_id}")
async def radar_event_detail(event_id: str):
    """Détail d'un événement Radar par son identifiant."""
    try:
        from web.radar.store import get_event
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    evt = get_event(event_id)
    if evt is None:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    return {"ok": True, "event": evt}


# ---------------------------------------------------------------------------
# GET /api/radar/stats
# ---------------------------------------------------------------------------
@router.get("/stats")
async def radar_stats():
    """Compteurs globaux du Radar (total, erreurs, dernier événement)."""
    try:
        from web.radar.store import stats
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"ok": True, **stats()}


# ---------------------------------------------------------------------------
# GET /api/radar/stream  — SSE temps réel
# ---------------------------------------------------------------------------
@router.get("/stream")
async def radar_stream():
    """Flux SSE : reçoit les événements Radar en temps réel.

    Chaque événement est émis sous la forme :
        data: <JSON>\\n\\n

    Un keepalive (comment vide) est envoyé toutes les 30 s pour maintenir
    la connexion.
    """
    from web.radar.events import subscribe_sse, unsubscribe_sse

    async def _gen():
        q = subscribe_sse()
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive SSE (commentaire ignoré par les clients)
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_sse(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

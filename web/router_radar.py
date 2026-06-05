"""web/router_radar.py — Radar : exposition HTTP des événements ADA.

Routes :
  GET  /api/radar/events                          — liste paginée / filtrée des événements
  GET  /api/radar/events/stream                   — flux SSE temps réel (filtrable par request_id)
  GET  /api/radar/events/conversation/{request_id} — événements d'une conversation
  GET  /api/radar/events/{event_id}               — détail d'un événement
  GET  /api/radar/stats                           — compteurs globaux
  POST /api/radar/clear                           — vide le store (admin)
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/radar", tags=["radar"])


# ---------------------------------------------------------------------------
# GET /api/radar/events
# ---------------------------------------------------------------------------
@router.get("/events")
async def radar_events(
    level:       str | None = Query(None, description="info | warning | error | critical"),
    type_:       str | None = Query(None, alias="type", description="Filtre sur le type d'événement"),
    module:      str | None = Query(None),
    request_id:  str | None = Query(None),
    document_id: str | None = Query(None),
    job_id:      str | None = Query(None),
    session_id:  str | None = Query(None),
    since:       str | None = Query(None, description="ISO 8601 borne inférieure (alias from_ts)"),
    until:       str | None = Query(None, description="ISO 8601 borne supérieure"),
    q:           str | None = Query(None, description="Recherche libre dans message/metadata"),
    limit:       int        = Query(50, ge=1, le=500),
    offset:      int        = Query(0,  ge=0),
):
    """Liste paginée des événements Radar (triés par timestamp desc)."""
    try:
        from web.radar.store import query_events, count_events
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    filters = dict(
        level=level,
        type_=type_,
        module=module,
        request_id=request_id,
        document_id=document_id,
        job_id=job_id,
        session_id=session_id,
        from_ts=since,
        to_ts=until,
        q=q,
    )

    events = query_events(**filters, limit=limit, offset=offset)
    total  = count_events(**filters)

    return {"ok": True, "total": total, "count": len(events), "offset": offset, "events": events}


# ---------------------------------------------------------------------------
# GET /api/radar/events/stream  — SSE temps réel
# DOIT être déclaré avant /events/{event_id} pour éviter la capture par FastAPI
# ---------------------------------------------------------------------------
@router.get("/events/stream")
async def radar_stream(
    request_id: str | None = Query(None, description="Filtre SSE sur une conversation"),
    level:      str | None = Query(None, description="Filtre SSE sur le niveau"),
):
    """Flux SSE : reçoit les événements Radar en temps réel.

    Chaque événement est émis sous la forme :
        data: <JSON>\\n\\n

    Un keepalive (commentaire vide) est envoyé toutes les 30 s pour maintenir
    la connexion. Si request_id est fourni, seuls les événements de cette
    conversation sont émis.
    """
    from web.radar.events import subscribe_sse, unsubscribe_sse

    async def _gen():
        q = subscribe_sse()
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=30.0)

                    # Filtrage par request_id côté router
                    if request_id and evt.get("request_id") != request_id:
                        continue

                    # Filtrage par level côté router
                    if level and evt.get("level") != level:
                        continue

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


# ---------------------------------------------------------------------------
# GET /api/radar/events/conversation/{request_id}
# DOIT être déclaré avant /events/{event_id}
# ---------------------------------------------------------------------------
@router.get("/events/conversation/{request_id}")
async def radar_conversation(request_id: str):
    """Retourne tous les événements Radar d'une conversation identifiée par request_id."""
    try:
        from web.radar.store import query_events
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    events = query_events(request_id=request_id, limit=500, offset=0)
    return {"ok": True, "request_id": request_id, "count": len(events), "events": events}


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
    """Compteurs globaux du Radar (total, par level, par module, dernier événement)."""
    try:
        from web.radar.store import stats
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"ok": True, **stats()}


# ---------------------------------------------------------------------------
# POST /api/radar/clear  — admin uniquement
# ---------------------------------------------------------------------------
@router.post("/clear")
async def radar_clear(request: Request):
    """Vide le store Radar. Réservé aux utilisateurs admin."""
    # Vérification du flag admin porté par le middleware JWT
    user = getattr(request.state, "user", None)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin requis")

    try:
        from web.radar.store import clear_all
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    deleted = clear_all()
    return {"ok": True, "deleted": deleted}

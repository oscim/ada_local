"""web/router_feedback.py — Routes feedback et error_log ADA.

Routes :
  POST /api/feedback/response            — signal 👍/👎 depuis le chat
  GET  /api/errors                       — liste paginée des erreurs
  GET  /api/errors/stats                 — agrégats
  GET  /api/errors/export                — export CSV ou JSON
  GET  /api/errors/{id}                  — détail d'une erreur
  POST /api/errors/{id}/resolve          — marque une erreur résolue
"""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

router = APIRouter(tags=["feedback"])


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------

class FeedbackPayload(BaseModel):
    request_id: str
    signal: str                       # "positive" | "negative"
    comment: str | None = None
    response_summary: str | None = None


class ResolvePayload(BaseModel):
    resolution: str = "manual_fix"   # autoskill_flagged | index_excluded | manual_fix


# ---------------------------------------------------------------------------
# POST /api/feedback/response
# ---------------------------------------------------------------------------

@router.post("/api/feedback/response")
async def post_feedback(body: FeedbackPayload):
    """Enregistre un signal de satisfaction 👍/👎 pour une réponse ADA."""
    try:
        from config import FEEDBACK_ENABLED
        if not FEEDBACK_ENABLED:
            return {"status": "disabled", "request_id": body.request_id}
    except (ImportError, AttributeError):
        pass

    if body.signal not in ("positive", "negative"):
        raise HTTPException(status_code=400, detail="signal doit être 'positive' ou 'negative'")

    try:
        from core.feedback.feedback_processor import get_processor
        result = get_processor().process_response_feedback(
            request_id=body.request_id,
            signal=body.signal,
            comment=body.comment,
            response_summary=body.response_summary,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /api/errors
# ---------------------------------------------------------------------------

@router.get("/api/errors")
async def list_errors(
    limit:       int        = Query(50,   ge=1, le=500),
    offset:      int        = Query(0,    ge=0),
    source:      str | None = Query(None, description="user_feedback | radar_auto"),
    error_type:  str | None = Query(None),
    resolution:  str | None = Query(None, description="null | autoskill_flagged | index_excluded | manual_fix"),
    since:       str | None = Query(None, description="ISO 8601"),
):
    """Liste paginée des erreurs enregistrées."""
    try:
        from core.feedback.error_store import list_errors as _list, count_errors as _count
        items  = _list(source=source, error_type=error_type, resolution=resolution,
                       since=since, limit=limit, offset=offset)
        total  = _count(source=source, error_type=error_type, resolution=resolution, since=since)
        return {"total": total, "items": items, "limit": limit, "offset": offset}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /api/errors/stats
# ---------------------------------------------------------------------------

@router.get("/api/errors/stats")
async def error_stats():
    """Agrégats des erreurs (totaux, par type, top actions échouées, tendance 7j)."""
    try:
        from core.feedback.error_store import stats
        return stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /api/errors/export
# ---------------------------------------------------------------------------

@router.get("/api/errors/export")
async def export_errors(
    format:      str        = Query("json", description="json | csv"),
    limit:       int        = Query(500,  ge=1, le=500),
    offset:      int        = Query(0,    ge=0),
    source:      str | None = Query(None),
    error_type:  str | None = Query(None),
    resolution:  str | None = Query(None),
    since:       str | None = Query(None),
):
    """Export des erreurs en JSON ou CSV."""
    try:
        from core.feedback.error_store import export_errors as _export
        rows = _export(source=source, error_type=error_type, resolution=resolution,
                       since=since, limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if format == "csv":
        if not rows:
            return Response(content="", media_type="text/csv")
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            # Sérialise les champs JSON en string
            cleaned = {
                k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
                for k, v in row.items()
            }
            writer.writerow(cleaned)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=error_log.csv"},
        )
    # JSON par défaut
    return rows


# ---------------------------------------------------------------------------
# GET /api/errors/{id}
# ---------------------------------------------------------------------------

@router.get("/api/errors/{error_id}")
async def get_error(error_id: int):
    """Détail d'une erreur par son id."""
    try:
        from core.feedback.error_store import get_error as _get
        item = _get(error_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Erreur introuvable")
        return item
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /api/errors/{id}/resolve
# ---------------------------------------------------------------------------

@router.post("/api/errors/{error_id}/resolve")
async def resolve_error(error_id: int, body: ResolvePayload):
    """Marque une erreur comme résolue."""
    try:
        from core.feedback.error_store import resolve_error as _resolve
        ok = _resolve(error_id, body.resolution)
        if not ok:
            raise HTTPException(status_code=404, detail="Erreur introuvable")
        # Émet un événement Radar
        try:
            from web.radar.events import emit_event
            emit_event(
                type="error_log.resolved", level="info", module="web.router_feedback",
                message=f"Erreur #{error_id} résolue ({body.resolution})",
                metadata={"error_id": error_id, "resolution": body.resolution},
            )
        except Exception:
            pass
        return {"ok": True, "error_id": error_id, "resolution": body.resolution}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

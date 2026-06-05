"""web/router_intent.py — API Intent Mining ADA.

Routes :
  GET    /api/intent/corpus                  — liste paginée / filtrée
  GET    /api/intent/corpus/stats            — agrégats
  POST   /api/intent/corpus/extract          — déclenche extraction (tâche de fond)
  GET    /api/intent/corpus/{request_id}     — détail d'un enregistrement
  DELETE /api/intent/corpus/{request_id}     — supprime un enregistrement
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intent", tags=["intent"])

# ---------------------------------------------------------------------------
# Modèles Pydantic
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    since:  str | None = None   # ISO 8601 — borne inférieure
    force:  bool = False        # Retraiter les request_id déjà présents


# ---------------------------------------------------------------------------
# GET /api/intent/corpus
# ---------------------------------------------------------------------------

@router.get("/corpus")
async def list_corpus(
    limit:        int        = Query(50,  ge=1, le=500),
    offset:       int        = Query(0,   ge=0),
    outcome:      str | None = Query(None, description="success|hallucinated|cancelled|confirmed|llm_only|unknown"),
    action:       str | None = Query(None),
    universe:     str | None = Query(None),
    is_validated: bool | None = Query(None),
    since:        str | None = Query(None, description="ISO 8601"),
):
    """Liste paginée des enregistrements du corpus d'intentions."""
    try:
        from core.intent.intent_store import list_records, count_records
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    filters: dict[str, Any] = dict(
        outcome=outcome, action=action, universe=universe,
        is_validated=is_validated, since=since,
    )

    records = list_records(**filters, limit=limit, offset=offset)
    total   = count_records(**filters)

    return {
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "results": records,
    }


# ---------------------------------------------------------------------------
# GET /api/intent/corpus/stats
# ---------------------------------------------------------------------------

@router.get("/corpus/stats")
async def corpus_stats():
    """Agrégats sur le corpus : actions, outcomes, univers, couverture."""
    try:
        from core.intent.intent_miner import get_miner
        return get_miner().get_corpus_stats()
    except Exception as exc:
        logger.error("[IntentRouter] Erreur stats : %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /api/intent/corpus/extract
# ---------------------------------------------------------------------------

@router.post("/corpus/extract")
async def trigger_extraction(req: ExtractRequest):
    """
    Déclenche une extraction manuelle en tâche de fond.
    Retourne immédiatement un job_id.
    """
    try:
        from config import INTENT_MINING_ENABLED
        if not INTENT_MINING_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="Intent Mining désactivé (INTENT_MINING_ENABLED=False)"
            )
    except ImportError:
        pass

    job_id = f"extract_{uuid.uuid4().hex[:12]}"

    async def _run():
        try:
            from core.intent.intent_miner import get_miner
            miner = get_miner()
            miner.run_full_extraction(since=req.since)
        except Exception as e:
            logger.error("[IntentRouter] Erreur extraction %s : %s", job_id, e)

    asyncio.create_task(_run())

    return {"job_id": job_id, "status": "started", "since": req.since}


# ---------------------------------------------------------------------------
# GET /api/intent/corpus/{request_id}
# ---------------------------------------------------------------------------

@router.get("/corpus/{request_id}")
async def get_corpus_record(request_id: str):
    """Retourne le détail d'un enregistrement du corpus."""
    try:
        from core.intent.intent_store import get_record
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    record = get_record(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    return record


# ---------------------------------------------------------------------------
# DELETE /api/intent/corpus/{request_id}
# ---------------------------------------------------------------------------

@router.delete("/corpus/{request_id}")
async def delete_corpus_record(request_id: str):
    """Supprime un enregistrement du corpus."""
    try:
        from core.intent.intent_store import delete_record
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    deleted = delete_record(request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    return {"deleted": True, "request_id": request_id}

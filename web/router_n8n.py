"""
router_n8n.py — Supervision du bridge n8n bidirectionnel (Phase 3).

Routes :
  GET  /api/integrations/n8n/status                — état du bridge, stats, connectivité
  GET  /api/integrations/n8n/events                — liste paginée de integration_events
  POST /api/integrations/n8n/events/{event_id}/retry — relance d'un événement sortant échoué
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/n8n", tags=["n8n-bridge"])


# ---------------------------------------------------------------------------
# GET /api/integrations/n8n/status
# ---------------------------------------------------------------------------

@router.get("/status")
async def n8n_bridge_status():
    """Retourne l'état du bridge n8n : config active, stats journalisation, connectivité."""
    try:
        from core.n8n_bridge import bridge_connector, _cfg
        from config import MODULES_ENABLED
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Bridge n8n non initialisé : {exc}")

    cfg   = _cfg()
    stats = bridge_connector._store.stats()

    # Test de connectivité non-bloquant (timeout 3s)
    reachable = False
    try:
        import requests
        resp      = requests.get(cfg["base_url"] + "/healthz", timeout=3, verify=cfg["verify_ssl"])
        reachable = resp.status_code < 500
    except Exception:
        pass

    return {
        "enabled":          cfg["enabled"],
        "fallback_enabled": cfg["fallback_enabled"],
        "n8n_url":          cfg["base_url"],
        "webhook_url":      cfg["webhook_url"],
        "reachable":        reachable,
        "modules": {
            "n8n_bridge":   MODULES_ENABLED.get("n8n_bridge",   False),
            "n8n_fallback": MODULES_ENABLED.get("n8n_fallback", False),
        },
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# GET /api/integrations/n8n/events
# ---------------------------------------------------------------------------

@router.get("/events")
async def n8n_events(
    direction:    str | None = Query(None, description="inbound | outbound"),
    status:       str | None = Query(None, description="pending | sent | failed | processed | logged"),
    event_type:   str | None = Query(None, description="Filtre partiel sur event_type"),
    universe:     str | None = Query(None, description="Univers ADA (opent, home, margep, uscss)"),
    initiated_by: str | None = Query(None, description="Initiateur de l'événement"),
    limit:        int        = Query(50, ge=1, le=500),
    offset:       int        = Query(0,  ge=0),
):
    """Liste paginée des événements journalisés dans integration_events."""
    try:
        from core.n8n_bridge import bridge_connector
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    events = bridge_connector._store.list_events(
        direction=direction,
        status=status,
        event_type=event_type,
        universe=universe,
        initiated_by=initiated_by,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "count": len(events), "offset": offset, "events": events}


# ---------------------------------------------------------------------------
# POST /api/integrations/n8n/events/{event_id}/retry
# ---------------------------------------------------------------------------

@router.post("/events/{event_id}/retry")
async def n8n_retry_event(event_id: str):
    """
    Relance l'envoi d'un événement sortant en statut 'failed' ou 'pending'.
    Reconstruit l'enveloppe depuis la base et renvoi vers n8n.
    """
    try:
        from core.n8n_bridge import bridge_connector, _cfg
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    row = bridge_connector._store.get_by_event_id(event_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Événement '{event_id}' introuvable")

    if row.get("direction") != "outbound":
        raise HTTPException(status_code=400, detail="Seuls les événements sortants peuvent être relancés")

    if row.get("status") not in ("failed", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Événement au statut '{row.get('status')}' ne peut pas être relancé",
        )

    cfg = _cfg()
    try:
        import requests as _req
        payload_str = row.get("payload_json", "{}")
        payload     = json.loads(payload_str) if payload_str else {}
        envelope = {
            "event_id":        row["event_id"],
            "event_type":      row["event_type"],
            "source":          row.get("source",          "ada"),
            "target":          row.get("target",           "n8n"),
            "payload":         payload,
            "initiated_by":    row.get("initiated_by",    ""),
            "universe":        row.get("universe",         ""),
            "correlation_id":  row.get("correlation_id",  ""),
            "idempotency_key": row.get("idempotency_key", ""),
        }
        resp = _req.post(
            cfg["webhook_url"],
            json=envelope,
            headers={"Content-Type": "application/json", "X-Source": "ada-retry"},
            timeout=cfg["timeout"],
            verify=cfg["verify_ssl"],
        )
        resp.raise_for_status()
        bridge_connector._store.update_status(event_id, "sent")
        logger.info("[router_n8n] Retry OK — event_id=%s", event_id)
        return {"ok": True, "event_id": event_id, "status": "sent"}
    except Exception as exc:
        bridge_connector._store.update_status(event_id, "failed", str(exc))
        logger.error("[router_n8n] Retry échoué — event_id=%s err=%s", event_id, exc)
        raise HTTPException(status_code=502, detail=f"Retry échoué : {exc}")

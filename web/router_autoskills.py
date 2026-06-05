"""web/router_autoskills.py — Routes de révision manuelle des AutoSkills ADA.

Routes :
  GET  /api/autoskills/under_review          — liste des AutoSkills en révision
  POST /api/autoskills/{id}/rehabilitate     — réhabilite un AutoSkill (status → active, rejected_count → 0)
  POST /api/autoskills/{id}/disable          — désactive définitivement (status → archived)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["autoskills-review"])


@router.get("/api/autoskills/under_review")
async def list_under_review():
    """Retourne les AutoSkills actuellement en cours de révision."""
    try:
        from core.skills.skills_db import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM skills WHERE status='under_review' ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
        return {"skills": [dict(r) for r in rows]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/autoskills/{skill_id}/rehabilitate")
async def rehabilitate_autoskill(skill_id: str):
    """Réhabilite un AutoSkill : remet status='active' et rejected_count=0."""
    try:
        from core.skills.skills_db import get_connection
        conn = get_connection()
        row = conn.execute("SELECT id FROM skills WHERE id=?", (skill_id,)).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="AutoSkill introuvable")
        conn.execute(
            """UPDATE skills
               SET status='active', rejected_count=0, last_rejected_at=NULL,
                   updated_at=datetime('now')
               WHERE id=?""",
            (skill_id,),
        )
        conn.commit()
        conn.close()
        try:
            from web.radar.events import emit_event
            emit_event(
                type="autoskill.rehabilitated", level="info",
                module="web.router_autoskills",
                message=f"AutoSkill {skill_id} réhabilité",
                metadata={"autoskill_id": skill_id},
            )
        except Exception:
            pass
        return {"ok": True, "skill_id": skill_id, "status": "active"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/autoskills/{skill_id}/disable")
async def disable_autoskill(skill_id: str):
    """Désactive définitivement un AutoSkill (status → archived)."""
    try:
        from core.skills.skills_db import get_connection
        conn = get_connection()
        row = conn.execute("SELECT id FROM skills WHERE id=?", (skill_id,)).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail="AutoSkill introuvable")
        conn.execute(
            "UPDATE skills SET status='archived', updated_at=datetime('now') WHERE id=?",
            (skill_id,),
        )
        conn.commit()
        conn.close()
        try:
            from web.radar.events import emit_event
            emit_event(
                type="autoskill.disabled", level="warning",
                module="web.router_autoskills",
                message=f"AutoSkill {skill_id} désactivé définitivement",
                metadata={"autoskill_id": skill_id},
            )
        except Exception:
            pass
        return {"ok": True, "skill_id": skill_id, "status": "archived"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

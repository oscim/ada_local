"""web/radar/store.py — Store SQLite pour les événements Radar ADA.

Interface publique attendue par router_radar.py :
  query_events(...)  -> list[dict]
  count_events(...)  -> int
  get_event(id)      -> dict | None
  save_event(event)  -> None
  stats()            -> dict
  clear_all()        -> int
  init_db()          -> None
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = Path("data/radar.db")
RADAR_RETENTION_DAYS = 30
RADAR_MAX_EVENTS = 50_000

# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

@contextmanager
def _conn():
    """Context manager : connexion SQLite avec row_factory dict."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Crée les tables et index si inexistants. Purge les événements trop anciens."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS radar_events (
                id           TEXT PRIMARY KEY,
                timestamp    TEXT NOT NULL,
                level        TEXT NOT NULL,
                type         TEXT NOT NULL,
                module       TEXT,
                message      TEXT,
                metadata_json TEXT,
                request_id   TEXT,
                document_id  TEXT,
                job_id       TEXT,
                session_id   TEXT,
                created_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_radar_request_id ON radar_events(request_id);
            CREATE INDEX IF NOT EXISTS idx_radar_type       ON radar_events(type);
            CREATE INDEX IF NOT EXISTS idx_radar_level      ON radar_events(level);
            CREATE INDEX IF NOT EXISTS idx_radar_timestamp  ON radar_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_radar_module     ON radar_events(module);
        """)
    logger.info("RadarStore initialisé — %s", DB_PATH)
    _purge_old_events()


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def save_event(event: dict[str, Any]) -> None:
    """Insère un événement dans le store. Ignore les doublons (même id)."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO radar_events
                (id, timestamp, level, type, module, message,
                 metadata_json, request_id, document_id, job_id, session_id, created_at)
            VALUES
                (:id, :timestamp, :level, :type, :module, :message,
                 :metadata_json, :request_id, :document_id, :job_id, :session_id, :created_at)
            """,
            {
                "id":            event.get("id", ""),
                "timestamp":     event.get("timestamp", now),
                "level":         event.get("level", "info"),
                "type":          event.get("type", "unknown"),
                "module":        event.get("module"),
                "message":       event.get("message"),
                "metadata_json": json.dumps(event.get("metadata", {})),
                "request_id":    event.get("request_id"),
                "document_id":   event.get("document_id"),
                "job_id":        event.get("job_id"),
                "session_id":    event.get("session_id"),
                "created_at":    now,
            },
        )


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def _build_where(
    level=None, type_=None, module=None,
    request_id=None, document_id=None, job_id=None, session_id=None,
    from_ts=None, to_ts=None, q=None,
) -> tuple[str, list]:
    """Construit la clause WHERE et la liste de paramètres associée."""
    clauses, params = [], []

    if level:
        clauses.append("level = ?");         params.append(level)
    if type_:
        clauses.append("type = ?");          params.append(type_)
    if module:
        clauses.append("module = ?");        params.append(module)
    if request_id:
        clauses.append("request_id = ?");    params.append(request_id)
    if document_id:
        clauses.append("document_id = ?");   params.append(document_id)
    if job_id:
        clauses.append("job_id = ?");        params.append(job_id)
    if session_id:
        clauses.append("session_id = ?");    params.append(session_id)
    if from_ts:
        clauses.append("timestamp >= ?");    params.append(from_ts)
    if to_ts:
        clauses.append("timestamp <= ?");    params.append(to_ts)
    if q:
        clauses.append("(message LIKE ? OR metadata_json LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
    except (ValueError, KeyError):
        d["metadata"] = {}
    return d


def query_events(
    level=None, type_=None, module=None,
    request_id=None, document_id=None, job_id=None, session_id=None,
    from_ts=None, to_ts=None, q=None,
    limit: int = 50, offset: int = 0,
) -> list[dict]:
    """Retourne une liste paginée d'événements triés par timestamp décroissant."""
    where, params = _build_where(
        level=level, type_=type_, module=module,
        request_id=request_id, document_id=document_id,
        job_id=job_id, session_id=session_id,
        from_ts=from_ts, to_ts=to_ts, q=q,
    )
    sql = f"SELECT * FROM radar_events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_events(
    level=None, type_=None, module=None,
    request_id=None, document_id=None, job_id=None, session_id=None,
    from_ts=None, to_ts=None, q=None,
) -> int:
    """Compte le nombre total d'événements correspondant aux filtres."""
    where, params = _build_where(
        level=level, type_=type_, module=module,
        request_id=request_id, document_id=document_id,
        job_id=job_id, session_id=session_id,
        from_ts=from_ts, to_ts=to_ts, q=q,
    )
    sql = f"SELECT COUNT(*) FROM radar_events {where}"
    with _conn() as con:
        return con.execute(sql, params).fetchone()[0]


def get_event(event_id: str) -> dict | None:
    """Retourne un événement par son id, ou None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM radar_events WHERE id = ?", (event_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------

def stats() -> dict:
    """Retourne les agrégats globaux du store."""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM radar_events").fetchone()[0]

        by_level = {
            row["level"]: row["cnt"]
            for row in con.execute(
                "SELECT level, COUNT(*) AS cnt FROM radar_events GROUP BY level"
            ).fetchall()
        }

        by_module = {
            row["module"]: row["cnt"]
            for row in con.execute(
                "SELECT module, COUNT(*) AS cnt FROM radar_events WHERE module IS NOT NULL GROUP BY module ORDER BY cnt DESC LIMIT 20"
            ).fetchall()
        }

        last_row = con.execute(
            "SELECT timestamp FROM radar_events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        oldest_row = con.execute(
            "SELECT timestamp FROM radar_events ORDER BY timestamp ASC LIMIT 1"
        ).fetchone()

    return {
        "total":          total,
        "by_level":       by_level,
        "by_module":      by_module,
        "last_event_at":  last_row["timestamp"] if last_row else None,
        "oldest_event_at": oldest_row["timestamp"] if oldest_row else None,
    }


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def clear_all() -> int:
    """Vide le store. Retourne le nombre d'événements supprimés."""
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM radar_events").fetchone()[0]
        con.execute("DELETE FROM radar_events")
    logger.warning("RadarStore vidé — %d événements supprimés", count)
    return count


def _purge_old_events() -> None:
    """Supprime les événements plus anciens que RADAR_RETENTION_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RADAR_RETENTION_DAYS)).isoformat()
    with _conn() as con:
        deleted = con.execute(
            "DELETE FROM radar_events WHERE timestamp < ?", (cutoff,)
        ).rowcount
        # Si volume toujours trop élevé, supprimer les plus anciens
        total = con.execute("SELECT COUNT(*) FROM radar_events").fetchone()[0]
        if total > RADAR_MAX_EVENTS:
            overflow = total - RADAR_MAX_EVENTS
            con.execute(
                """DELETE FROM radar_events WHERE id IN (
                    SELECT id FROM radar_events ORDER BY timestamp ASC LIMIT ?
                )""",
                (overflow,),
            )
            deleted += overflow

    if deleted:
        logger.info("RadarStore purge : %d événements supprimés", deleted)

"""core/feedback/error_store.py — Store SQLite pour le registre error_log ADA.

Table : error_log
Interface :
  init_db()
  log_error(...)          -> int   (id de l'entrée créée)
  get_error(id)           -> dict | None
  list_errors(...)        -> list[dict]
  count_errors(...)       -> int
  resolve_error(id, resolution) -> bool
  stats()                 -> dict
  export_errors(...)      -> list[dict]
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None


def _get_db_path() -> Path:
    if _DB_PATH:
        return _DB_PATH
    try:
        from config import INTENT_MINING_DB_PATH
        # On partage la même DB que le corpus d'intentions
        return Path(INTENT_MINING_DB_PATH)
    except (ImportError, AttributeError):
        return Path("data/intent_corpus.db")


@contextmanager
def _conn():
    db = _get_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), check_same_thread=False)
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


_DDL = """
CREATE TABLE IF NOT EXISTS error_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id          TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    source              TEXT NOT NULL,
    error_type          TEXT NOT NULL,
    raw_text            TEXT,
    detected_action     TEXT,
    error_detail        TEXT,
    autoskill_ids       TEXT,
    radar_events_json   TEXT,
    resolution          TEXT,
    resolved_at         TEXT,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_el_error_type  ON error_log(error_type);
CREATE INDEX IF NOT EXISTS idx_el_source      ON error_log(source);
CREATE INDEX IF NOT EXISTS idx_el_timestamp   ON error_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_el_resolution  ON error_log(resolution);
CREATE INDEX IF NOT EXISTS idx_el_request_id  ON error_log(request_id);
"""


def init_db() -> None:
    """Crée la table error_log et ses index si inexistants."""
    with _conn() as con:
        con.executescript(_DDL)
    logger.info("ErrorStore initialisé — %s", _get_db_path())


def log_error(
    request_id: str,
    source: str,
    error_type: str,
    raw_text: str | None = None,
    detected_action: str | None = None,
    error_detail: str | None = None,
    autoskill_ids: list[str] | None = None,
    radar_events: list[dict] | None = None,
    timestamp: str | None = None,
) -> int:
    """Insère un enregistrement dans error_log. Retourne l'id généré."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO error_log
                (request_id, timestamp, source, error_type, raw_text, detected_action,
                 error_detail, autoskill_ids, radar_events_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                request_id,
                timestamp or now,
                source,
                error_type,
                raw_text,
                detected_action,
                error_detail,
                json.dumps(autoskill_ids) if autoskill_ids else None,
                json.dumps(radar_events) if radar_events else None,
                now,
            ),
        )
    return cur.lastrowid


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("autoskill_ids", "radar_events_json"):
        raw = d.pop(field, None)
        key = "autoskill_ids" if field == "autoskill_ids" else "radar_events"
        try:
            d[key] = json.loads(raw) if raw else None
        except (ValueError, TypeError):
            d[key] = None
    return d


def get_error(error_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM error_log WHERE id = ?", (error_id,)).fetchone()
    return _row_to_dict(row) if row else None


def _build_where(
    source: str | None = None,
    error_type: str | None = None,
    resolution: str | None = None,
    since: str | None = None,
    unresolved_only: bool = False,
) -> tuple[str, list]:
    clauses, params = [], []
    if source:
        clauses.append("source = ?"); params.append(source)
    if error_type:
        clauses.append("error_type = ?"); params.append(error_type)
    if resolution == "null":
        clauses.append("resolution IS NULL")
    elif resolution:
        clauses.append("resolution = ?"); params.append(resolution)
    if since:
        clauses.append("timestamp >= ?"); params.append(since)
    if unresolved_only:
        clauses.append("resolution IS NULL")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_errors(
    source: str | None = None,
    error_type: str | None = None,
    resolution: str | None = None,
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where, params = _build_where(source, error_type, resolution, since)
    sql = f"SELECT * FROM error_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_errors(
    source: str | None = None,
    error_type: str | None = None,
    resolution: str | None = None,
    since: str | None = None,
) -> int:
    where, params = _build_where(source, error_type, resolution, since)
    with _conn() as con:
        return con.execute(
            f"SELECT COUNT(*) FROM error_log {where}", params
        ).fetchone()[0]


def resolve_error(error_id: int, resolution: str) -> bool:
    """Marque une erreur comme résolue. Retourne True si mise à jour."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        cur = con.execute(
            "UPDATE error_log SET resolution=?, resolved_at=? WHERE id=?",
            (resolution, now, error_id),
        )
    return cur.rowcount > 0


def stats() -> dict:
    """Retourne les agrégats pour /api/errors/stats."""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM error_log").fetchone()[0]
        unresolved = con.execute(
            "SELECT COUNT(*) FROM error_log WHERE resolution IS NULL"
        ).fetchone()[0]

        by_type = {
            r["error_type"]: r["cnt"]
            for r in con.execute(
                "SELECT error_type, COUNT(*) AS cnt FROM error_log GROUP BY error_type ORDER BY cnt DESC"
            ).fetchall()
        }

        top_failing = [
            {"action": r["detected_action"], "count": r["cnt"]}
            for r in con.execute(
                """SELECT detected_action, COUNT(*) AS cnt FROM error_log
                   WHERE detected_action IS NOT NULL
                   GROUP BY detected_action ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
        ]

        trend_7d = [
            {"date": r["day"], "count": r["cnt"]}
            for r in con.execute(
                """SELECT DATE(timestamp) AS day, COUNT(*) AS cnt FROM error_log
                   WHERE timestamp >= DATE('now', '-7 days')
                   GROUP BY day ORDER BY day ASC"""
            ).fetchall()
        ]

    return {
        "total": total,
        "unresolved": unresolved,
        "by_type": by_type,
        "top_failing_actions": top_failing,
        "trend_7d": trend_7d,
    }


def export_errors(
    source: str | None = None,
    error_type: str | None = None,
    resolution: str | None = None,
    since: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """Retourne toutes les erreurs pour export CSV/JSON."""
    return list_errors(source, error_type, resolution, since, limit=min(limit, 500), offset=offset)

"""core/intent/intent_store.py — Store SQLite pour le corpus d'intentions ADA.

Schéma : table `intent_corpus`
Interface publique :
  init_db()
  save_record(record)          -> None
  get_record(request_id)       -> dict | None
  delete_record(request_id)    -> bool
  list_records(...)            -> list[dict]
  count_records(...)           -> int
  stats()                      -> dict
  known_request_ids(since)     -> set[str]
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

# ---------------------------------------------------------------------------
# Configuration (peut être surchargée par config.py)
# ---------------------------------------------------------------------------
_DB_PATH: Path | None = None


def _get_db_path() -> Path:
    if _DB_PATH:
        return _DB_PATH
    try:
        from config import INTENT_MINING_DB_PATH
        return Path(INTENT_MINING_DB_PATH)
    except (ImportError, AttributeError):
        return Path("data/intent_corpus.db")


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS intent_corpus (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id           TEXT NOT NULL UNIQUE,
    timestamp            TEXT NOT NULL,
    raw_text             TEXT NOT NULL,
    normalized_text      TEXT NOT NULL,
    detected_action      TEXT,
    detected_params_json TEXT,
    outcome              TEXT NOT NULL,
    outcome_source       TEXT,
    has_hallucination    INTEGER NOT NULL DEFAULT 0,
    confirm_required     INTEGER NOT NULL DEFAULT 0,
    confirm_result       TEXT,
    duration_ms          INTEGER,
    universe             TEXT,
    is_validated         INTEGER NOT NULL DEFAULT 0,
    validated_at         TEXT,
    validated_action     TEXT,
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ic_action    ON intent_corpus(detected_action);
CREATE INDEX IF NOT EXISTS idx_ic_outcome   ON intent_corpus(outcome);
CREATE INDEX IF NOT EXISTS idx_ic_universe  ON intent_corpus(universe);
CREATE INDEX IF NOT EXISTS idx_ic_timestamp ON intent_corpus(timestamp);
CREATE INDEX IF NOT EXISTS idx_ic_validated ON intent_corpus(is_validated);
"""


def init_db() -> None:
    """Crée la table et les index si inexistants."""
    with _conn() as con:
        con.executescript(_DDL)
    logger.info("IntentStore initialisé — %s", _get_db_path())


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def save_record(record: dict[str, Any], force: bool = False) -> bool:
    """
    Insère ou remplace un enregistrement d'intention.
    Retourne True si inséré/mis à jour, False si ignoré (déjà existant sans force).
    """
    now = datetime.now(timezone.utc).isoformat()
    params = {
        "request_id":           record["request_id"],
        "timestamp":            record.get("timestamp", now),
        "raw_text":             record["raw_text"],
        "normalized_text":      record.get("normalized_text", _normalize(record["raw_text"])),
        "detected_action":      record.get("detected_action"),
        "detected_params_json": json.dumps(record["detected_params"])
                                if record.get("detected_params") else None,
        "outcome":              record.get("outcome", "unknown"),
        "outcome_source":       record.get("outcome_source"),
        "has_hallucination":    1 if record.get("has_hallucination") else 0,
        "confirm_required":     1 if record.get("confirm_required") else 0,
        "confirm_result":       record.get("confirm_result"),
        "duration_ms":          record.get("duration_ms"),
        "universe":             record.get("universe"),
        "is_validated":         1 if record.get("is_validated") else 0,
        "validated_at":         record.get("validated_at"),
        "validated_action":     record.get("validated_action"),
        "created_at":           now,
    }

    sql = (
        "INSERT OR REPLACE INTO intent_corpus "
        "(request_id, timestamp, raw_text, normalized_text, detected_action, "
        " detected_params_json, outcome, outcome_source, has_hallucination, "
        " confirm_required, confirm_result, duration_ms, universe, "
        " is_validated, validated_at, validated_action, created_at) "
        "VALUES "
        "(:request_id, :timestamp, :raw_text, :normalized_text, :detected_action, "
        " :detected_params_json, :outcome, :outcome_source, :has_hallucination, "
        " :confirm_required, :confirm_result, :duration_ms, :universe, "
        " :is_validated, :validated_at, :validated_action, :created_at)"
        if force else
        "INSERT OR IGNORE INTO intent_corpus "
        "(request_id, timestamp, raw_text, normalized_text, detected_action, "
        " detected_params_json, outcome, outcome_source, has_hallucination, "
        " confirm_required, confirm_result, duration_ms, universe, "
        " is_validated, validated_at, validated_action, created_at) "
        "VALUES "
        "(:request_id, :timestamp, :raw_text, :normalized_text, :detected_action, "
        " :detected_params_json, :outcome, :outcome_source, :has_hallucination, "
        " :confirm_required, :confirm_result, :duration_ms, :universe, "
        " :is_validated, :validated_at, :validated_action, :created_at)"
    )

    with _conn() as con:
        cur = con.execute(sql, params)
        return cur.rowcount > 0


def delete_record(request_id: str) -> bool:
    """Supprime un enregistrement. Retourne True si supprimé."""
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM intent_corpus WHERE request_id = ?", (request_id,)
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    raw = d.pop("detected_params_json", None)
    try:
        d["detected_params"] = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        d["detected_params"] = None
    d["has_hallucination"] = bool(d.get("has_hallucination", 0))
    d["confirm_required"]  = bool(d.get("confirm_required", 0))
    d["is_validated"]      = bool(d.get("is_validated", 0))
    return d


def get_record(request_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM intent_corpus WHERE request_id = ?", (request_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def _build_where(
    outcome=None, action=None, universe=None,
    is_validated=None, since=None,
) -> tuple[str, list]:
    clauses, params = [], []
    if outcome:
        clauses.append("outcome = ?");        params.append(outcome)
    if action:
        clauses.append("detected_action = ?"); params.append(action)
    if universe:
        clauses.append("universe = ?");        params.append(universe)
    if is_validated is not None:
        clauses.append("is_validated = ?");    params.append(1 if is_validated else 0)
    if since:
        clauses.append("timestamp >= ?");      params.append(since)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_records(
    outcome=None, action=None, universe=None,
    is_validated=None, since=None,
    limit: int = 50, offset: int = 0,
) -> list[dict]:
    where, params = _build_where(outcome, action, universe, is_validated, since)
    sql = f"SELECT * FROM intent_corpus {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_records(
    outcome=None, action=None, universe=None,
    is_validated=None, since=None,
) -> int:
    where, params = _build_where(outcome, action, universe, is_validated, since)
    with _conn() as con:
        return con.execute(
            f"SELECT COUNT(*) FROM intent_corpus {where}", params
        ).fetchone()[0]


def known_request_ids(since: str | None = None) -> set[str]:
    """Retourne l'ensemble des request_id déjà présents dans le corpus."""
    if since:
        where, params = "WHERE timestamp >= ?", [since]
    else:
        where, params = "", []
    with _conn() as con:
        rows = con.execute(
            f"SELECT request_id FROM intent_corpus {where}", params
        ).fetchall()
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------

def stats() -> dict:
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM intent_corpus").fetchone()[0]

        by_outcome = {
            r["outcome"]: r["cnt"]
            for r in con.execute(
                "SELECT outcome, COUNT(*) AS cnt FROM intent_corpus GROUP BY outcome"
            ).fetchall()
        }

        by_action = {
            r["detected_action"]: r["cnt"]
            for r in con.execute(
                "SELECT detected_action, COUNT(*) AS cnt "
                "FROM intent_corpus WHERE detected_action IS NOT NULL "
                "GROUP BY detected_action ORDER BY cnt DESC LIMIT 20"
            ).fetchall()
        }

        by_universe = {
            r["universe"]: r["cnt"]
            for r in con.execute(
                "SELECT COALESCE(universe, 'unknown') AS universe, COUNT(*) AS cnt "
                "FROM intent_corpus GROUP BY universe ORDER BY cnt DESC"
            ).fetchall()
        }

        top_hallucinated = [
            {"function": r["outcome_source"], "count": r["cnt"]}
            for r in con.execute(
                "SELECT outcome_source, COUNT(*) AS cnt "
                "FROM intent_corpus WHERE outcome = 'hallucinated' "
                "AND outcome_source IS NOT NULL "
                "GROUP BY outcome_source ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
        ]

    return {
        "total":                     total,
        "by_outcome":                by_outcome,
        "by_action":                 by_action,
        "by_universe":               by_universe,
        "top_hallucinated_functions": top_hallucinated,
    }


# ---------------------------------------------------------------------------
# Normalisation du texte brut
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """
    Normalise un texte brut :
    - passage en minuscules
    - suppression de la ponctuation finale
    - suppression des espaces multiples
    Sans stemming ni lemmatisation. Le raw_text original est conservé séparément.
    """
    import re
    t = text.lower()
    # Suppression ponctuation finale (., !, ?, …)
    t = re.sub(r"[.!?…]+$", "", t.rstrip())
    # Suppression des espaces multiples
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t

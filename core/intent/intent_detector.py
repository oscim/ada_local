"""core/intent/intent_detector.py

Lightweight, personalized intent detector based on TF-IDF cosine similarity.

Pipeline position: step 2 — after rag.query.received, before deterministic routing.

The detector:
  - vectorizes the `intent_corpus` table (outcome IN ('success','confirmed'))
  - computes cosine similarity between the incoming query and corpus entries
  - returns an IntentMatch with confidence score and re-contextualized params
  - emits Radar events for every outcome
  - never raises — all exceptions are caught and logged to Radar
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import unicodedata
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB path for the intent corpus (created if absent)
# ---------------------------------------------------------------------------
_DEFAULT_CORPUS_DB = Path(__file__).parent.parent.parent / "data" / "intent_corpus.sqlite"

# ---------------------------------------------------------------------------
# Normalize text — strip accents, lowercase, collapse whitespace
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize a query for TF-IDF vectorization."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s]", " ", ascii_str)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


# ---------------------------------------------------------------------------
# IntentMatch dataclass
# ---------------------------------------------------------------------------

@dataclass
class IntentMatch:
    matched: bool
    confidence: float = 0.0
    action: str = ""
    params: dict = field(default_factory=dict)
    source_request_id: str = ""
    source_text: str = ""
    is_certain: bool = False

    @classmethod
    def no_match(cls) -> "IntentMatch":
        return cls(matched=False)


# ---------------------------------------------------------------------------
# IntentDetector
# ---------------------------------------------------------------------------

class IntentDetector:
    """
    TF-IDF cosine similarity matcher against the validated intent corpus.

    Thread-safe for concurrent reads. Index rebuilds swap the index atomically.
    """

    def __init__(
        self,
        intent_store=None,
        function_registry=None,
        entity_resolver=None,
        logger_=None,
        db_path: Path | None = None,
        threshold_certain: float | None = None,
        threshold_candidate: float | None = None,
        max_corpus_size: int | None = None,
        universe_filter: bool | None = None,
    ) -> None:
        from config import (
            INTENT_DETECTION_THRESHOLD_CERTAIN,
            INTENT_DETECTION_THRESHOLD_CANDIDATE,
            INTENT_DETECTION_MAX_CORPUS_SIZE,
            INTENT_DETECTION_UNIVERSE_FILTER,
        )

        self._intent_store = intent_store
        self._function_registry = function_registry
        self._entity_resolver = entity_resolver
        self._log = logger_ or logger

        self._db_path = db_path or _DEFAULT_CORPUS_DB
        self._threshold_certain = threshold_certain if threshold_certain is not None else INTENT_DETECTION_THRESHOLD_CERTAIN
        self._threshold_candidate = threshold_candidate if threshold_candidate is not None else INTENT_DETECTION_THRESHOLD_CANDIDATE
        self._max_corpus_size = max_corpus_size if max_corpus_size is not None else INTENT_DETECTION_MAX_CORPUS_SIZE
        self._universe_filter = universe_filter if universe_filter is not None else INTENT_DETECTION_UNIVERSE_FILTER

        # TF-IDF index state — protected by _lock
        self._lock = threading.RLock()
        self._vectorizer = None
        self._matrix = None       # sparse (n_docs, n_features)
        self._records: list[dict] = []   # parallel list of corpus records
        self._ready = False
        self._corpus_size = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return self._ready

    def load_index(self) -> None:
        """Load and vectorize the corpus from the intent_corpus DB."""
        try:
            self._ensure_db()
            records = self._fetch_records()
            if not records:
                self._log.info("[IntentDetector] Corpus vide — détecteur désactivé.")
                return
            self._build_index(records)
            self._emit_radar("intent.index_rebuilt", "info",
                             f"Index TF-IDF chargé ({len(records)} entrées)",
                             {"corpus_size": len(records)})
        except Exception as exc:
            self._log.warning("[IntentDetector] Erreur chargement index : %s", exc)

    def rebuild_index(self) -> None:
        """Full rebuild — called after corpus update (feedback or batch extraction)."""
        self.load_index()

    def add_to_index(self, record: dict) -> None:
        """Incremental add of a validated record without full rebuild."""
        try:
            with self._lock:
                if self._vectorizer is None or not self._records:
                    # Nothing loaded yet — do a full load
                    self.load_index()
                    return

                normalized = normalize_text(record.get("normalized_text", ""))
                if not normalized:
                    return

                import numpy as np
                from sklearn.metrics.pairwise import cosine_similarity as _cs

                vec = self._vectorizer.transform([normalized])
                # Append to matrix
                from scipy.sparse import vstack
                self._matrix = vstack([self._matrix, vec])
                self._records.append(record)
                self._corpus_size = len(self._records)
        except Exception as exc:
            self._log.warning("[IntentDetector] add_to_index error : %s", exc)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, normalized_text: str, universe: str | None = None) -> IntentMatch:
        """
        Return best IntentMatch or IntentMatch.no_match().

        Never raises — all exceptions are caught.
        """
        try:
            return self._detect_inner(normalized_text, universe)
        except Exception as exc:
            self._emit_radar("intent.error", "warning",
                             f"Erreur détection : {exc}", {"error": str(exc)})
            return IntentMatch.no_match()

    def _detect_inner(self, normalized_text: str, universe: str | None) -> IntentMatch:
        with self._lock:
            if not self._ready or self._vectorizer is None or self._matrix is None:
                return IntentMatch.no_match()

            records = self._records
            matrix = self._matrix

        # Filter by universe if enabled and universe is provided
        if self._universe_filter and universe:
            indices = [
                i for i, r in enumerate(records)
                if not r.get("universe") or r["universe"] == universe
            ]
            if not indices:
                self._emit_radar("intent.no_match", "info",
                                 "Aucune entrée dans l'univers courant",
                                 {"universe": universe, "corpus_size": self._corpus_size})
                return IntentMatch.no_match()
            import numpy as np
            sub_matrix = matrix[indices]
            sub_records = [records[i] for i in indices]
        else:
            import numpy as np
            sub_matrix = matrix
            sub_records = records

        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = self._vectorizer.transform([normalized_text])
        scores = cosine_similarity(query_vec, sub_matrix).flatten()
        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])

        if best_score < self._threshold_candidate:
            self._emit_radar("intent.no_match", "info",
                             f"Aucune correspondance (meilleur score {best_score:.3f})",
                             {"best_score": best_score, "corpus_size": self._corpus_size,
                              "universe": universe})
            return IntentMatch.no_match()

        record = sub_records[best_idx]
        action = record.get("action", "")
        source_params = {}
        raw_params = record.get("detected_params_json")
        if raw_params:
            try:
                source_params = json.loads(raw_params)
            except Exception:
                source_params = {}

        is_certain = best_score >= self._threshold_certain

        # Re-contextualize params
        resolved_params, all_resolved = self._recontextualize(
            normalized_text,
            normalize_text(record.get("normalized_text", "")),
            source_params,
            action,
        )

        if not all_resolved:
            is_certain = False
            self._emit_radar("intent.entity_resolution_failed", "warning",
                             f"Entité non résolue pour '{action}' (confidence {best_score:.3f})",
                             {"action": action, "confidence": best_score,
                              "source_request_id": record.get("request_id", "")})

        match = IntentMatch(
            matched=True,
            confidence=best_score,
            action=action,
            params=resolved_params,
            source_request_id=record.get("request_id", ""),
            source_text=record.get("normalized_text", ""),
            is_certain=is_certain,
        )

        if is_certain:
            self._emit_radar("intent.matched", "info",
                             f"Intention détectée : {action} (confidence {best_score:.3f})",
                             {"action": action, "confidence": best_score,
                              "source_request_id": match.source_request_id,
                              "corpus_size": self._corpus_size})
        else:
            self._emit_radar("intent.candidate", "info",
                             f"Candidat probable : {action} (confidence {best_score:.3f})",
                             {"action": action, "confidence": best_score,
                              "source_request_id": match.source_request_id,
                              "corpus_size": self._corpus_size})

        return match

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recontextualize(
        self,
        current_text: str,
        source_text: str,
        params: dict[str, Any],
        action: str,
    ) -> tuple[dict[str, Any], bool]:
        """Apply entity resolver to re-contextualize params."""
        if not params:
            return params, True
        try:
            resolver = self._entity_resolver
            if resolver is None:
                from core.intent.entity_resolver import get_resolver
                resolver = get_resolver()
            return resolver.resolve(current_text, source_text, params, action)
        except Exception as exc:
            self._log.warning("[IntentDetector] entity_resolver error : %s", exc)
            return params, True  # optimistic — don't block

    def _build_index(self, records: list[dict]) -> None:
        """Build TF-IDF index from records list. Swaps atomically."""
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [normalize_text(r.get("normalized_text", "")) for r in records]
        texts = [t if t else "." for t in texts]  # avoid empty strings

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)

        with self._lock:
            self._vectorizer = vectorizer
            self._matrix = matrix
            self._records = records
            self._corpus_size = len(records)
            self._ready = True

    def _fetch_records(self) -> list[dict]:
        """Load validated records from the intent_corpus SQLite table."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                """
                SELECT request_id, normalized_text, action,
                       detected_params_json, universe
                FROM   intent_corpus
                WHERE  outcome IN ('success', 'confirmed')
                  AND  normalized_text IS NOT NULL
                  AND  normalized_text != ''
                ORDER BY rowid DESC
                LIMIT  ?
                """,
                (self._max_corpus_size,),
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def _ensure_db(self) -> None:
        """Create the intent_corpus table if the DB / table doesn't exist yet."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_corpus (
                    request_id          TEXT PRIMARY KEY,
                    normalized_text     TEXT NOT NULL,
                    raw_text            TEXT,
                    action              TEXT,
                    detected_params_json TEXT,
                    outcome             TEXT DEFAULT 'unknown',
                    universe            TEXT,
                    created_at          TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _emit_radar(
        self,
        event_type: str,
        level: str,
        message: str,
        metadata: dict | None = None,
        request_id: str | None = None,
    ) -> None:
        try:
            from web.radar.events import emit_event
            emit_event(
                type=event_type,
                level=level,
                module="intent_detector",
                message=message,
                metadata={"corpus_size": self._corpus_size, **(metadata or {})},
                request_id=request_id,
            )
        except Exception:
            pass  # Radar must never block detection


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_detector: IntentDetector | None = None


def get_detector() -> IntentDetector:
    global _detector
    if _detector is None:
        _detector = IntentDetector()
    return _detector

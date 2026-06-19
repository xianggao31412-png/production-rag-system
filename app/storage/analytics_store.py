"""
Analytics / query-log store.

Every answered query is appended here so the dashboard and the ``/metrics``
endpoint can report how the system is actually behaving in production:
success rate, grounded rate, latency percentiles, and traffic per namespace.

This is deliberately a *separate* SQLite database from the document metadata
store. Operational telemetry has a very different lifecycle from primary data
(it is high-volume, append-only, and disposable), so keeping it in its own file
means it can be rotated, truncated, or shipped elsewhere without touching the
knowledge base.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, List, Tuple

from app.logging_config import get_logger
from app.models.domain import new_id, now_ts

logger = get_logger("eka.analytics")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_logs (
    id            TEXT PRIMARY KEY,
    ts            REAL NOT NULL,
    namespace     TEXT NOT NULL,
    question      TEXT NOT NULL,
    grounded      INTEGER NOT NULL,
    num_citations INTEGER NOT NULL,
    latency_ms    REAL NOT NULL,
    model         TEXT NOT NULL,
    success       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON query_logs(ts);
CREATE INDEX IF NOT EXISTS idx_logs_namespace ON query_logs(namespace);
"""


class AnalyticsStore:
    """Append-only store of answered queries, with aggregation helpers."""

    def __init__(self, db_path: str):
        self._path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        logger.info("analytics_store_ready", extra={"db_path": db_path})

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def record_query(
        self,
        namespace: str,
        question: str,
        grounded: bool,
        num_citations: int,
        latency_ms: float,
        model: str,
        success: bool,
    ) -> str:
        log_id = new_id("q")
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO query_logs
                    (id, ts, namespace, question, grounded, num_citations,
                     latency_ms, model, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    now_ts(),
                    namespace,
                    question[:2000],
                    1 if grounded else 0,
                    int(num_citations),
                    float(latency_ms),
                    model,
                    1 if success else 0,
                ),
            )
            self._conn.commit()
        return log_id

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def total_queries(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM query_logs").fetchone()
        return int(row["c"])

    def recent(self, limit: int = 50, offset: int = 0) -> Tuple[List[dict], int]:
        with self._lock:
            total = int(
                self._conn.execute("SELECT COUNT(*) AS c FROM query_logs").fetchone()["c"]
            )
            rows = self._conn.execute(
                """
                SELECT id, ts, namespace, question, grounded, num_citations,
                       latency_ms, model, success
                FROM query_logs
                ORDER BY ts DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        items = [
            {
                "id": r["id"],
                "ts": r["ts"],
                "namespace": r["namespace"],
                "question": r["question"],
                "grounded": bool(r["grounded"]),
                "num_citations": r["num_citations"],
                "latency_ms": r["latency_ms"],
                "model": r["model"],
                "success": bool(r["success"]),
            }
            for r in rows
        ]
        return items, total

    def metrics(self, window: int = 500) -> dict:
        """Aggregate metrics over the most recent ``window`` queries.

        A bounded window keeps the dashboard responsive to *current* behaviour
        rather than being dominated by stale history, and keeps the query cheap
        regardless of how large the log grows.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT grounded, latency_ms, success, namespace
                FROM query_logs
                ORDER BY ts DESC
                LIMIT ?
                """,
                (window,),
            ).fetchall()

        n = len(rows)
        if n == 0:
            return {
                "window": "last 0 queries",
                "total_queries": 0,
                "success_rate": 0.0,
                "grounded_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "queries_per_namespace": {},
            }

        successes = sum(1 for r in rows if r["success"])
        grounded = sum(1 for r in rows if r["grounded"])
        latencies = sorted(float(r["latency_ms"]) for r in rows)

        per_ns: Dict[str, int] = {}
        for r in rows:
            per_ns[r["namespace"]] = per_ns.get(r["namespace"], 0) + 1

        return {
            "window": f"last {n} queries",
            "total_queries": n,
            "success_rate": round(successes / n, 4),
            "grounded_rate": round(grounded / n, 4),
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
            "queries_per_namespace": per_ns,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _percentile(sorted_values: List[float], q: float) -> float:
    """Linear-interpolated percentile of an already-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac

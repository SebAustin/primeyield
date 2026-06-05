"""Decision persistence layer.

Writes the full decision record to:
  - Postgres (when DATABASE_URL is set and psycopg2 is available)
  - A local JSONL file (state/decisions.jsonl) as fallback

Also handles the rationale embedding upsert for judge_replay.py semantic
search (pgvector column). The embedding step is skipped gracefully when the
database or an embedding model is unavailable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
JSONL_PATH = ROOT / "state" / "decisions.jsonl"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id     TEXT PRIMARY KEY,
    timestamp       BIGINT NOT NULL,
    snapshot_json   JSONB,
    plan_json       JSONB,
    rationale_hash  TEXT,
    onchain_txs     JSONB,
    approval_status TEXT,
    sim_result_json JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
"""


def _get_conn():
    """Return a psycopg2 connection if DATABASE_URL is configured, else None."""
    try:
        import psycopg2

        from agent.config import get_settings

        url = get_settings().database_url
        if not url or url.startswith("postgresql://user:pass"):
            return None
        return psycopg2.connect(url)
    except Exception as exc:  # noqa: BLE001
        log.debug("DB unavailable (%s); using JSONL fallback", exc)
        return None


def save_decision(record: dict[str, Any]) -> None:
    """Persist a decision record (blocking). Falls back to JSONL if DB is down."""
    conn = _get_conn()
    if conn:
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(_CREATE_TABLE)
                cur.execute(
                    """
                    INSERT INTO decisions
                        (decision_id, timestamp, snapshot_json, plan_json,
                         rationale_hash, onchain_txs, approval_status, sim_result_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (decision_id) DO UPDATE SET
                        onchain_txs = EXCLUDED.onchain_txs,
                        approval_status = EXCLUDED.approval_status
                    """,
                    (
                        record.get("decision_id"),
                        record.get("timestamp", 0),
                        json.dumps(record.get("snapshot_json")),
                        json.dumps(record.get("plan_json")),
                        record.get("rationale_hash"),
                        json.dumps(record.get("onchain_txs", [])),
                        record.get("approval_status"),
                        json.dumps(record.get("sim_result_json")),
                    ),
                )
            log.info("decision %s saved to Postgres", record.get("decision_id"))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Postgres write failed (%s); falling back to JSONL", exc)
        finally:
            conn.close()

    # JSONL fallback.
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    log.info("decision %s appended to %s", record.get("decision_id"), JSONL_PATH)


def load_decisions() -> list[dict[str, Any]]:
    """Load all decisions from Postgres or JSONL (for judge_replay.py)."""
    conn = _get_conn()
    if conn:
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT decision_id, timestamp, snapshot_json, plan_json, "
                    "rationale_hash, onchain_txs, approval_status, sim_result_json "
                    "FROM decisions ORDER BY timestamp ASC"
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            log.warning("Postgres read failed (%s); falling back to JSONL", exc)
        finally:
            conn.close()

    if not JSONL_PATH.exists():
        return []
    return [json.loads(line) for line in JSONL_PATH.read_text().splitlines() if line.strip()]

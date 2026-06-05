"""Decision logging + on-chain provenance helpers.

Produces the canonical rationale hash that is committed to DecisionLog.sol
and the full record persisted to Postgres for judge_replay.py.
"""

from __future__ import annotations

import json


def canonical_json(obj: dict) -> str:
    """Deterministic JSON serialization for hashing (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def rationale_hash(rationale: dict) -> str:
    """Return keccak256(canonical_json(rationale)) as a 0x-prefixed hex string.

    This is the value stored in DecisionLog.sol and printed in judge_replay.py.
    """
    from eth_hash.auto import keccak

    payload = canonical_json(rationale).encode()
    return "0x" + keccak(payload).hex()

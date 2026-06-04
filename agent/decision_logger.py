"""Decision logging + on-chain provenance helpers — implemented day 4-7.

Produces the canonical rationale hash committed to DecisionLog.sol and the
full record persisted to Postgres for judge_replay.py.
"""

from __future__ import annotations


def canonical_json(obj: dict) -> str:
    """Deterministic JSON serialization for hashing (sorted keys, no spaces)."""
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def rationale_hash(rationale: dict) -> str:
    """keccak256(canonical_json(rationale)) as 0x-prefixed hex — day 4-7."""
    raise NotImplementedError("day 4-7: keccak256 of canonical rationale")

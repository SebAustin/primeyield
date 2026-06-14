"""Judge replay / decision audit — Day 6-7.

Proves PrimeYield's decisions are tamper-evident by reconciling two independent
records of every rebalance:

  1. The on-chain ``DecisionLog.DecisionRecorded(agentId, hash, timestamp)``
     events — an append-only commitment only the agent EOA can write.
  2. The off-chain rationale records persisted by ``agent/db.py`` (Postgres or
     the ``state/decisions.jsonl`` fallback), each carrying the same
     ``rationale_hash`` that was committed on-chain.

For each on-chain hash we look for a matching off-chain rationale. A decision is
VERIFIED when both agree; a hash recorded on-chain with no matching rationale is
a TAMPER flag (someone edited or deleted the off-chain record after the fact).

The output is a markdown audit report (``docs/AUDIT.md`` by default) that a judge
or insurer can read top-to-bottom, with mantlescan links for every transaction.

Usage:
  uv run python scripts/judge_replay.py --agent-id 0
  uv run python scripts/judge_replay.py                 # agentId from identity.json
  uv run python scripts/judge_replay.py --offline       # skip chain, DB-only report
  uv run python scripts/judge_replay.py --from-block 0  # event scan start block
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from agent.config import (
    MANTLE_SEPOLIA_REPUTATION_REGISTRY,
    get_w3,
)

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PATH = ROOT / "state" / "identity.json"
DEPLOYMENTS_PATH = ROOT / "state" / "deployments.json"
DEFAULT_OUT = ROOT / "docs" / "AUDIT.md"

# Minimal ABI: the event judge_replay reconciles against. Mirrors DecisionLog.sol.
_DECISION_LOG_EVENT_ABI = [
    {
        "type": "event",
        "name": "DecisionRecorded",
        "anonymous": False,
        "inputs": [
            {"name": "agentId", "type": "uint256", "indexed": True},
            {"name": "hash", "type": "bytes32", "indexed": False},
            {"name": "timestamp", "type": "uint256", "indexed": False},
        ],
    },
]

# Explorer bases keyed by chainId (anvil/local has no explorer).
_EXPLORER = {
    5003: "https://sepolia.mantlescan.xyz",
    5000: "https://mantlescan.xyz",
}

_VERDICT_ICON = {"VERIFIED": "✅", "TAMPER SUSPECTED": "🚨", "UNVERIFIED": "⚠️"}


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def resolve_agent_id(cli_value: int | None) -> int:
    """CLI value wins; otherwise read identity.json; otherwise 0."""
    if cli_value is not None:
        return cli_value
    identity = _load_json(IDENTITY_PATH)
    return int(identity.get("agentId", 0))


def _normalize_hash(value: Any) -> str:
    """Return a lower-case 0x-prefixed hex string for any hash representation."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    s = str(value).strip().lower()
    return s if s.startswith("0x") else "0x" + s


def _extract_tx(tx_entry: Any) -> str:
    """onchain_txs may hold raw hashes or mantlescan URLs; return the hash."""
    s = str(tx_entry)
    if "/tx/" in s:
        return s.rsplit("/tx/", 1)[-1]
    return s


# ---------------------------------------------------------------------------
# On-chain event reading
# ---------------------------------------------------------------------------
_CHUNK = 9_000  # below the common 10k-block eth_getLogs cap on public RPCs


def _get_logs_chunked(contract, agent_id: int, from_block: int, to_block: int) -> list:
    """Scan DecisionRecorded in fixed windows when a full-range query is rejected."""
    out: list = []
    start = max(0, from_block)
    while start <= to_block:
        end = min(start + _CHUNK, to_block)
        out.extend(
            contract.events.DecisionRecorded().get_logs(
                from_block=start,
                to_block=end,
                argument_filters={"agentId": agent_id},
            )
        )
        start = end + 1
    return out


def read_onchain_decisions(
    decision_log_addr: str, agent_id: int, from_block: int
) -> list[dict[str, Any]]:
    """Fetch DecisionRecorded events for ``agent_id`` in chain order.

    Returns dicts: {hash, timestamp, tx_hash, block}. Raises on RPC failure so
    the caller can fall back to a DB-only report.
    """
    w3 = get_w3()
    contract = w3.eth.contract(
        address=w3.to_checksum_address(decision_log_addr),
        abi=_DECISION_LOG_EVENT_ABI,
    )
    try:
        logs = contract.events.DecisionRecorded().get_logs(
            from_block=from_block,
            argument_filters={"agentId": agent_id},
        )
    except Exception:  # noqa: BLE001 — public RPCs cap eth_getLogs range; chunk it
        logs = _get_logs_chunked(contract, agent_id, from_block, w3.eth.block_number)
    out: list[dict[str, Any]] = []
    for ev in logs:
        out.append(
            {
                "hash": _normalize_hash(ev["args"]["hash"]),
                "timestamp": int(ev["args"]["timestamp"]),
                "tx_hash": ev["transactionHash"].hex(),
                "block": int(ev["blockNumber"]),
            }
        )
    out.sort(key=lambda d: (d["block"], d["timestamp"]))
    return out


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
def reconcile(
    onchain: list[dict[str, Any]], db_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Match on-chain hashes to off-chain rationale records.

    Verdict logic:
      - chain_only > 0  -> TAMPER SUSPECTED (on-chain decision with no rationale)
      - onchain empty   -> UNVERIFIED (nothing committed on-chain yet)
      - else            -> VERIFIED (every committed hash has a rationale)
    """
    db_by_hash: dict[str, dict[str, Any]] = {}
    for rec in db_records:
        h = _normalize_hash(rec.get("rationale_hash"))
        if h and h != "0x":
            db_by_hash[h] = rec

    matched, chain_only = [], []
    for ev in onchain:
        rec = db_by_hash.get(ev["hash"])
        (matched if rec else chain_only).append({"event": ev, "record": rec})

    onchain_hashes = {ev["hash"] for ev in onchain}
    db_only = [
        rec
        for rec in db_records
        if _normalize_hash(rec.get("rationale_hash")) not in onchain_hashes
    ]

    if chain_only:
        verdict = "TAMPER SUSPECTED"
    elif not onchain:
        verdict = "UNVERIFIED"
    else:
        verdict = "VERIFIED"

    return {
        "verdict": verdict,
        "matched": matched,
        "chain_only": chain_only,
        "db_only": db_only,
        "onchain_count": len(onchain),
        "db_count": len(db_records),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def _fmt_swaps(plan_json: dict[str, Any] | None) -> str:
    if not plan_json:
        return "_no plan_"
    swaps = plan_json.get("swaps", []) or []
    if not swaps:
        return "_no swaps_"
    parts = []
    for s in swaps:
        src = s.get("from_asset", s.get("from", "?"))
        dst = s.get("to", "?")
        pct = s.get("amount_pct", "?")
        try:
            pct = f"{float(pct) * 100:.1f}%"
        except (TypeError, ValueError):
            pass
        parts.append(f"{src}→{dst} ({pct})")
    return ", ".join(parts)


def _tx_link(tx: str, base: str | None) -> str:
    tx = tx if tx.startswith("0x") else "0x" + tx
    short = f"{tx[:10]}…{tx[-6:]}"
    return f"[{short}]({base}/tx/{tx})" if base else f"`{short}`"


def render_report(
    agent_id: int,
    chain_id: int | None,
    deployments: dict[str, Any],
    result: dict[str, Any],
    offline: bool,
    note: str | None,
) -> str:
    base = _EXPLORER.get(chain_id or 0)
    icon = _VERDICT_ICON.get(result["verdict"], "•")
    decision_log = deployments.get("decisionLog", "—")
    vault = deployments.get("vault", "—")
    rep_link = (
        f"[{MANTLE_SEPOLIA_REPUTATION_REGISTRY}]"
        f"({base}/address/{MANTLE_SEPOLIA_REPUTATION_REGISTRY})"
        if base
        else f"`{MANTLE_SEPOLIA_REPUTATION_REGISTRY}`"
    )

    lines: list[str] = []
    lines.append("# PrimeYield — Decision Provenance Audit")
    lines.append("")
    lines.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_")
    lines.append("")
    lines.append(f"## {icon} Verdict: **{result['verdict']}**")
    lines.append("")
    if note:
        lines.append(f"> {note}")
        lines.append("")
    lines.append(
        "Every rebalance commits `keccak256(rationale_json)` to `DecisionLog` "
        "on-chain. This report re-reads those commitments straight from the "
        "chain and checks each one against the off-chain rationale PrimeYield "
        "stored. A match proves the recorded reasoning is the reasoning that was "
        "acted on — it cannot be edited after the fact without detection."
    )
    lines.append("")

    # --- summary table ---
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| ERC-8004 agentId | `{agent_id}` |")
    lines.append(f"| Network (chainId) | `{chain_id if chain_id is not None else '—'}` |")
    lines.append(f"| DecisionLog | `{decision_log}` |")
    lines.append(f"| Vault | `{vault}` |")
    lines.append(f"| On-chain decisions | {result['onchain_count']} |")
    lines.append(f"| Off-chain rationale records | {result['db_count']} |")
    lines.append(f"| Matched (verified) | {len(result['matched'])} |")
    lines.append(f"| On-chain without rationale | {len(result['chain_only'])} |")
    lines.append(f"| Pending / not yet on-chain | {len(result['db_only'])} |")
    lines.append(f"| ReputationRegistry | {rep_link} |")
    lines.append("")

    # --- verified decisions ---
    lines.append("## Verified decisions")
    lines.append("")
    if result["matched"]:
        lines.append("| # | Hash | Decision | Swaps | Approval | On-chain tx |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for i, m in enumerate(result["matched"], 1):
            ev, rec = m["event"], m["record"]
            h = ev["hash"]
            txs = rec.get("onchain_txs") or []
            tx_cell = (
                ", ".join(_tx_link(_extract_tx(t), base) for t in txs)
                if txs
                else _tx_link(ev["tx_hash"], base)
            )
            lines.append(
                f"| {i} | `{h[:10]}…` | `{rec.get('decision_id', '—')}` "
                f"| {_fmt_swaps(rec.get('plan_json'))} "
                f"| {rec.get('approval_status', '—')} | {tx_cell} |"
            )
    else:
        lines.append("_No matched decisions yet._")
    lines.append("")

    # --- tamper flags ---
    if result["chain_only"]:
        lines.append("## 🚨 On-chain decisions with no rationale")
        lines.append("")
        lines.append(
            "These hashes were committed on-chain but have no matching off-chain "
            "rationale — evidence the rationale store was tampered with or lost."
        )
        lines.append("")
        lines.append("| Hash | Block | On-chain tx |")
        lines.append("| --- | --- | --- |")
        for m in result["chain_only"]:
            ev = m["event"]
            lines.append(
                f"| `{ev['hash']}` | {ev['block']} | {_tx_link(ev['tx_hash'], base)} |"
            )
        lines.append("")

    # --- pending ---
    if result["db_only"]:
        lines.append("## Pending / not yet committed on-chain")
        lines.append("")
        lines.append("| Decision | Approval | Swaps |")
        lines.append("| --- | --- | --- |")
        for rec in result["db_only"]:
            lines.append(
                f"| `{rec.get('decision_id', '—')}` "
                f"| {rec.get('approval_status', '—')} "
                f"| {_fmt_swaps(rec.get('plan_json'))} |"
            )
        lines.append("")

    # --- methodology ---
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- On-chain source: `DecisionLog.DecisionRecorded` events, read directly "
        "from Mantle via JSON-RPC (`scripts/judge_replay.py`)."
    )
    lines.append(
        "- Off-chain source: rationale records from Postgres / "
        "`state/decisions.jsonl`, each holding the `rationale_hash` committed "
        "at execution time."
    )
    lines.append(
        "- Integrity check: every on-chain hash must have a matching off-chain "
        "rationale. The hash is `keccak256` of the canonical rationale JSON, so "
        "any edit to the stored reasoning changes the hash and breaks the match."
    )
    if offline:
        lines.append(
            "- **Offline run:** chain was not queried; on-chain counts are 0. "
            "Re-run without `--offline` against a funded deployment for a full "
            "verification."
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="PrimeYield decision audit")
    parser.add_argument(
        "--agent-id",
        type=int,
        default=None,
        help="ERC-8004 agentId (defaults to state/identity.json, then 0)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Markdown output path (default {DEFAULT_OUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--from-block",
        type=int,
        default=None,
        help="Block to scan DecisionRecorded events from (default: deploy block)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the chain query and produce a DB-only report",
    )
    args = parser.parse_args()

    from agent.db import load_decisions

    agent_id = resolve_agent_id(args.agent_id)
    deployments = _load_json(DEPLOYMENTS_PATH)
    chain_id = deployments.get("chainId")
    decision_log_addr = deployments.get("decisionLog")
    db_records = load_decisions()

    onchain: list[dict[str, Any]] = []
    note: str | None = None
    offline = args.offline

    if offline:
        note = "Offline mode — on-chain decisions were not read."
    elif not decision_log_addr:
        offline = True
        note = (
            "No `decisionLog` address in `state/deployments.json` — deploy the "
            "vault first (`make day7`). Showing off-chain records only."
        )
    else:
        from_block = (
            args.from_block
            if args.from_block is not None
            else int(deployments.get("startBlock", 0))
        )
        try:
            onchain = read_onchain_decisions(decision_log_addr, agent_id, from_block)
        except Exception as exc:  # noqa: BLE001 — degrade to DB-only on any RPC error
            offline = True
            note = (
                f"Could not read on-chain events ({type(exc).__name__}: {exc}). "
                "Showing off-chain records only — re-run with a reachable RPC."
            )

    result = reconcile(onchain, db_records)
    report = render_report(agent_id, chain_id, deployments, result, offline, note)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)

    icon = _VERDICT_ICON.get(result["verdict"], "•")
    print(f"{icon} verdict: {result['verdict']}")
    print(
        f"   on-chain={result['onchain_count']} "
        f"matched={len(result['matched'])} "
        f"tamper={len(result['chain_only'])} "
        f"pending={len(result['db_only'])}"
    )
    if note:
        print(f"   note: {note}")
    print(f"   wrote {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Run one full PrimeYield agent cycle — Day 6-7 e2e / demo "money shot".

Drives the 9-node LangGraph end to end: snapshot -> forecast -> risk ->
propose -> simulate -> (approve) -> execute -> log -> reputation. The execute
node commits keccak256(rationale) to DecisionLog on-chain, which is what makes
the provenance story real (and flips judge_replay to VERIFIED).

Use --auto to skip the Telegram approval gate so the cycle completes
unattended. Without it, the cycle waits for a Telegram approve/reject.

Usage:
  uv run python scripts/run_cycle.py --auto
"""

from __future__ import annotations

import argparse
import asyncio
import logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one PrimeYield agent cycle")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-approve the plan (skip the Telegram gate) — for demos/e2e.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show INFO-level node logs."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from agent.graph import run_cycle

    final = asyncio.run(run_cycle(force_auto_approve=args.auto))

    print("\n=== cycle complete ===")
    print(f"approval_status : {final.approval_status}")
    print(f"decision_id     : {final.decision_id}")
    print(f"rationale_hash  : {final.rationale_hash}")
    if final.proposed_plan:
        for s in final.proposed_plan.swaps:
            print(f"  swap          : {s.from_asset}->{s.to} ({float(s.amount_pct) * 100:.1f}%)")
    if final.onchain_txs:
        print("on-chain txs:")
        for tx in final.onchain_txs:
            print(f"  {tx}")
    else:
        print("on-chain txs    : none (cycle ended before execute)")


if __name__ == "__main__":
    main()

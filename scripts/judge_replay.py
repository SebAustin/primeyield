"""Judge replay / decision audit — implemented day 6-7.

Given --agent-id, reads DecisionLog events from Mantle, reconciles each
on-chain hash against the rationale JSON in Postgres, fetches ERC-8004
reputation feedback, and emits a markdown audit report proving no tampering.
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="PrimeYield decision audit")
    parser.add_argument("--agent-id", required=True, help="ERC-8004 agentId")
    parser.parse_args()
    raise SystemExit("day 6-7: judge_replay.py not yet implemented")


if __name__ == "__main__":
    main()

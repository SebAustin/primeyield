# PrimeYield

> Autonomous RWA yield-rotation agent on **Mantle**, with a full on-chain audit
> trail. Submission to the **Mantle Turing Test Hackathon 2026** — AI × RWA track.

PrimeYield rotates capital across **mETH** (Mantle LSP), **USDY** (Ondo
Treasuries), and **USDe**, plus **Agni** and **Merchant Moe** LP positions. It
is orchestrated by a LangGraph state machine, gated by a Monte Carlo risk
engine, escalates large moves to a human via Telegram, and commits a hash of
its reasoning on-chain before every trade — so any decision can be replayed and
verified.

## Why

Manual RWA yield rotation is slow and loses alpha; existing black-box agents are
uninsurable because no one can verify what they decided or why. PrimeYield is
autonomous **and** auditable.

## Architecture

```
snapshot_state → forecast_yields → score_risks ─┬─ (risk fail) ─→ END
                                                 └─→ propose_plan → simulate_plan ─┬─ (<5% TVL) ──────────→ execute
                                                                                   └─ (≥5% TVL) → request_approval ─┬─ approve → execute
                                                                                                                    └─ reject → END
execute → log_decision → post_to_reputation → END
```

- **Orchestration:** LangGraph (`agent/graph.py`) + LangSmith tracing
- **Reasoning:** Claude via `langchain-anthropic`
- **Risk:** Monte Carlo VaR/ES + oracle-deviation, slippage, concentration gates (`agent/risk.py`)
- **Execution:** ERC-4626 vault (`contracts/src/PrimeYieldVault.sol`)
- **Provenance:** `keccak256(rationale)` → `DecisionLog.sol` + ERC-8004 identity & reputation
- **UX:** Telegram approval card; HTMX dashboard
- **Audit:** `scripts/judge_replay.py` reconciles on-chain hashes against stored rationales

## Quickstart

```bash
cp .env.example .env   # fill in secrets
make install           # uv sync + forge install (requires Foundry)
make test              # forge test --evm-version paris && pytest
```

## Mantle ecosystem fit

mETH, USDY, USDe, Agni Finance, Merchant Moe, and the ERC-8004 IdentityRegistry
are all on Mantle. See [JUDGES.md](JUDGES.md) for the full rubric mapping.

## Business potential / real-world impact

_(expanded days 8-11)_ RWA on-chain is a multi-billion-dollar market still
relying on manual rebalancing or black-box automation. PrimeYield demonstrates
agents managing real capital with bank-grade audit trails; the roadmap is
mainnet institutional vaults where agents are hired by verifiable credential.

## Status

Day-by-day build per the project plan. Scaffold complete; see
[DECISIONS.md](DECISIONS.md) for the engineering log.

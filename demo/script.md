# PrimeYield — Demo Video Script

> 3-minute target, never over 3:00. Record 1080p, unlisted YouTube + Loom backup.
> Sections: 0:00 hook / 0:20 problem / 0:45 live demo / 2:05 architecture / 2:35 impact.

---

## Pre-record runbook (do this once, before hitting record)

Two terminals + a browser. Have these ready so the demo is smooth:

```bash
cd primeyield

# Terminal A — dashboard (leave running)
uv run uvicorn api.main:app --port 8000
# open http://localhost:8000/dashboard

# Terminal B — you'll run these on camera:
uv run python scripts/run_cycle.py --auto --verbose   # the agent cycle
uv run python scripts/judge_replay.py                 # the audit → VERIFIED
```

Browser tabs to pre-open:
1. `http://localhost:8000/dashboard`
2. Vault on mantlescan: https://sepolia.mantlescan.xyz/address/0x9793b46d8a19B7B5cD6d397901cF2EE2fd1761c2
3. DecisionLog: https://sepolia.mantlescan.xyz/address/0xBb7A7f398f299E97BdeBFD12F357b70B2dcf7689
4. `docs/AUDIT.md` (rendered)
5. LangSmith trace (optional)

---

## 0:00 — Hook (20s)
> "This is an AI agent that manages real-world-asset yield on Mantle — and every
> single decision it makes is provable on-chain. Watch it make one, live, and
> then let me cryptographically verify it."

*(Screen: dashboard at localhost:8000/dashboard — vault, DecisionLog, decision log.)*

## 0:20 — Problem (25s)
> "RWA yield rotation across mETH, USDY, and USDe is slow to do by hand, and it
> loses alpha. You could hand it to an agent — but every yield agent today is a
> black box. No one can verify what it decided or why, so no serious treasury or
> insurer will touch it. PrimeYield fixes exactly that: autonomous AND auditable."

## 0:45 — Live demo (80s) — the money shot
*(Terminal B: run `run_cycle.py --auto --verbose`.)*
> "I trigger one agent cycle. It snapshots the portfolio, forecasts yields with
> gpt-4o, then runs four risk gates — Monte Carlo VaR, oracle-deviation,
> slippage, and concentration."

*(Point at the log: `score_risks: passed=True`, then the proposed swaps.)*
> "Risk passed. The model proposes a rebalance — USDY into USDe and mETH. Before
> it touches funds, it commits a keccak256 hash of its full reasoning to the
> DecisionLog contract."

*(Point at `execute: DecisionLog.record() → https://sepolia.mantlescan.xyz/tx/...`. Click it → show the tx on mantlescan.)*
> "There's the transaction on Mantle Sepolia — the decision is now permanent."

*(Terminal B: run `judge_replay.py`.)*
> "Now the audit. judge_replay re-reads every commitment straight from the chain
> and matches it against the stored rationale."

*(Point at: `✅ VERIFIED — on-chain=3, matched=3, tamper=0`. Open docs/AUDIT.md.)*
> "Verified. Three on-chain decisions, three matched, zero tampering. If anyone
> edited a stored rationale after the fact, the hash wouldn't match and this
> would flag it."

## 2:05 — Architecture (30s)
> "Under the hood: a 9-node LangGraph state machine, an ERC-4626 vault, an
> ERC-8004 on-chain identity — agent 207 — a Monte Carlo risk engine, and a
> Telegram approval gate that escalates large moves to a human. The provenance
> is the innovation: keccak256 of the rationale, on-chain, before every trade."

*(Optional: flash the LangSmith trace and the architecture diagram from README.)*

## 2:35 — Impact + close (25s)
> "mETH and USDY are live Mantle RWA assets with real TVL. PrimeYield is the
> trust layer that lets agents manage that capital — fast like an agent,
> verifiable like a smart contract. Autonomous and auditable. That's PrimeYield."

*(End card: GitHub URL, agentId 207, vault address.)*

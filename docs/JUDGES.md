# For the Judges — Rubric → Feature Map

> Pre-filled mapping of every scorecard dimension to the file/feature that earns
> it. Cells marked _(fill)_ get concrete evidence (tx hashes, URLs, screenshots)
> as each feature ships. Total: Mantle 50 + RWA track 50 = 100 pts.

## Mantle scorecard (50)

| Dimension | Pts | What earns it | File / Feature | Evidence _(fill)_ |
|---|---|---|---|---|
| Technical depth | 15 | LangGraph 9-node state machine, ERC-4626 vault, ERC-8004 identity, Monte Carlo risk engine | `agent/graph.py`, `contracts/`, `agent/risk.py` | _(LangSmith trace URL)_ |
| Ecosystem fit | 10 | mETH + USDY + USDe + Agni + Merchant Moe, all on Mantle | `agent/adapters/` | _(adapter fork tests)_ |
| Business potential | 10 | RWA yield-rotation TAM; institutional vault roadmap | `docs/README.md` | _(README business section)_ |
| Innovation | 10 | On-chain decision provenance via DecisionLog + ERC-8004 reputation | `contracts/DecisionLog.sol`, `scripts/judge_replay.py` | _(replay output)_ |
| UX | 5 | Telegram approval flow showing APY delta + max drawdown | `api/routes/telegram.py` | _(approval screenshot)_ |

## RWA track scorecard (50)

| Dimension | Pts | What earns it | File / Feature | Evidence _(fill)_ |
|---|---|---|---|---|
| Risk management | ~10 | 10k-path Monte Carlo (VaR95/ES95), oracle-deviation CB, 50bps slippage cap, 60% concentration limit | `agent/risk.py` | _(risk test output)_ |
| Oracle correctness | ~10 | USDY RWADynamicOracle reconciliation vs. Chainlink; preflight | `agent/adapters/ondo.py` | _(oracle address + spread)_ |
| Transparency | ~10 | `keccak256(rationale)` on-chain; hash-match audit | `scripts/judge_replay.py`, `contracts/DecisionLog.sol` | _(mantlescan tx + MATCH)_ |
| Blocklist compliance | ~10 | Ondo USDY `preflight()` before every USDY transfer; logged rejections | `agent/adapters/ondo.py` | _(USDYBlocklistError path)_ |
| Real-world impact | ~10 | mETH/USDY are live Mantle assets with real TVL | `docs/README.md` | _(impact section)_ |
| Demo quality | ~10 | 3-min video, LangSmith trace, mantlescan links | `demo/script.md`, YouTube | _(YouTube URL)_ |

## Key artifacts (fill in at submission)

- **Agent ID (ERC-8004):** _(fill)_
- **Vault address (Mantle Sepolia):** _(fill)_
- **DecisionLog address:** _(fill)_
- **GitHub:** _(fill)_ · **Demo video:** _(fill)_ · **X thread:** _(fill)_

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

## Key artifacts (Mantle Sepolia, chainId 5003)

- **Agent ID (ERC-8004):** `207` — register tx [`0x662e1ba0…47160`](https://sepolia.mantlescan.xyz/tx/0x662e1ba0be45601081e23fd52f2f53c03aec11ae564f6fe36b52840465a47160)
- **Vault address (ERC-4626):** [`0x9793b46d8a19B7B5cD6d397901cF2EE2fd1761c2`](https://sepolia.mantlescan.xyz/address/0x9793b46d8a19B7B5cD6d397901cF2EE2fd1761c2)
- **DecisionLog address:** [`0xBb7A7f398f299E97BdeBFD12F357b70B2dcf7689`](https://sepolia.mantlescan.xyz/address/0xBb7A7f398f299E97BdeBFD12F357b70B2dcf7689)
- **Mock assets:** mETH `0x042Eaf710e7f2Ee48fAf2699E38d8C67eeD77632` · USDY `0x264EFA8062ecC370AA5Ec837f56D683925cdc56A` · USDe `0xC4126e62f1F62fC76Ff3EB81D1b5407B4580BBCE`
- **Example AI decision on-chain** (USDY→USDe, USDY→mETH): [`0x463b020f…8ac5f0`](https://sepolia.mantlescan.xyz/tx/0x463b020fdb6ebd1a57c5fa4635f8c18f555dcf2378d0718efe90335bee8ac5f0)
- **Audit verdict:** `judge_replay` → **VERIFIED — on-chain=3, matched=3, tamper=0** (see `docs/AUDIT.md`)
- **GitHub:** https://github.com/SebAustin/primeyield · **Demo video:** _(fill)_ · **X thread:** _(fill)_

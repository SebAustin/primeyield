# PrimeYield — Decision Provenance Audit

_Generated 2026-06-14 21:08:26 UTC_

## ✅ Verdict: **VERIFIED**

Every rebalance commits `keccak256(rationale_json)` to `DecisionLog` on-chain. This report re-reads those commitments straight from the chain and checks each one against the off-chain rationale PrimeYield stored. A match proves the recorded reasoning is the reasoning that was acted on — it cannot be edited after the fact without detection.

## Summary

| Metric | Value |
| --- | --- |
| ERC-8004 agentId | `207` |
| Network (chainId) | `5003` |
| DecisionLog | `0xBb7A7f398f299E97BdeBFD12F357b70B2dcf7689` |
| Vault | `0x9793b46d8a19B7B5cD6d397901cF2EE2fd1761c2` |
| On-chain decisions | 3 |
| Off-chain rationale records | 3 |
| Matched (verified) | 3 |
| On-chain without rationale | 0 |
| Pending / not yet on-chain | 0 |
| ReputationRegistry | [0x8004B663056A597Dffe9eCcC1965A193B7388713](https://sepolia.mantlescan.xyz/address/0x8004B663056A597Dffe9eCcC1965A193B7388713) |

## Verified decisions

| # | Hash | Decision | Swaps | Approval | On-chain tx |
| --- | --- | --- | --- | --- | --- |
| 1 | `0x44a5033c…` | `59f494ce-50df-4db5-a6cd-931b8156af98` | _no swaps_ | auto | [0x170e1949…eda582](https://sepolia.mantlescan.xyz/tx/0x170e1949d6761731ab63911fb2d187d107be991034f9c96e24738e61f0eda582) |
| 2 | `0x40ffac96…` | `a08ee74b-32a1-4d37-9908-86577efa5026` | _no swaps_ | auto | [0xbdb745a4…532831](https://sepolia.mantlescan.xyz/tx/0xbdb745a426183e413ba89bf162ed99f798d666949e9e10099bdb3ad92d532831) |
| 3 | `0x202746f7…` | `7c707f77-a7f4-4f51-bcd4-8fe71270db80` | USDY→USDe (5.0%), USDY→mETH (5.0%) | auto | [0x463b020f…8ac5f0](https://sepolia.mantlescan.xyz/tx/0x463b020fdb6ebd1a57c5fa4635f8c18f555dcf2378d0718efe90335bee8ac5f0) |

## Methodology

- On-chain source: `DecisionLog.DecisionRecorded` events, read directly from Mantle via JSON-RPC (`scripts/judge_replay.py`).
- Off-chain source: rationale records from Postgres / `state/decisions.jsonl`, each holding the `rationale_hash` committed at execution time.
- Integrity check: every on-chain hash must have a matching off-chain rationale. The hash is `keccak256` of the canonical rationale JSON, so any edit to the stored reasoning changes the hash and breaks the match.

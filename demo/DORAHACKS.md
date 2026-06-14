# PrimeYield — DoraHacks BUIDL Submission

> Paste the section below into the DoraHacks BUIDL description (≥250 words, 3W1H).
> Fill the bracketed links once the GitHub repo and demo video are public.

---

## PrimeYield — autonomous RWA yield rotation on Mantle, fully auditable on-chain

**What it is.** PrimeYield is an autonomous agent that rotates capital across real-world-asset yield on Mantle — mETH (Mantle LSP), USDY (Ondo Treasuries), and USDe — and commits a cryptographic hash of its reasoning on-chain *before every trade*. It is orchestrated by a 9-node LangGraph state machine, gated by a Monte Carlo risk engine, escalates large moves to a human over Telegram, and carries an ERC-8004 on-chain identity (agentId **207**).

**Why it matters.** Manual RWA yield rotation is slow and bleeds alpha. The autonomous agents that could fix this are black boxes — uninsurable and untrustworthy, because no one can verify what an agent decided or why. PrimeYield is autonomous *and* auditable: every decision is independently replayable from the chain. That is the missing primitive for putting institutional RWA capital under agent control.

**Who it's for.** RWA treasuries, on-chain funds, and any allocator who wants agent speed without giving up an audit trail — plus the insurers and risk desks that underwrite them.

**How it works.** The agent snapshots the portfolio, forecasts per-asset yield with an LLM (gpt-4o via a provider-agnostic layer), and runs four risk gates — 10k-path Monte Carlo VaR/ES, oracle-deviation, slippage cap, and concentration limit. If risk passes, it proposes a rebalance, simulates it, and either auto-executes small moves or requests human approval via Telegram for large ones. Before executing, it writes `keccak256(rationale_json)` to a `DecisionLog` contract. The `judge_replay` tool then re-reads those commitments straight from Mantle and matches each against the stored rationale — producing a PASS/FAIL audit. Tampering with a stored decision breaks the hash match and is detected.

**Proof it's live (Mantle Sepolia, chainId 5003).**
- ERC-8004 agentId: **207** — register tx `0x662e1ba0…47160`
- Vault (ERC-4626): `0x9793b46d8a19B7B5cD6d397901cF2EE2fd1761c2`
- DecisionLog: `0xBb7A7f398f299E97BdeBFD12F357b70B2dcf7689`
- Example AI decision recorded on-chain (USDY→USDe, USDY→mETH): tx `0x463b020f…8ac5f0`
- `judge_replay` verdict: **VERIFIED — on-chain=3, matched=3, tamper=0**

**Tech stack.** LangGraph + LangSmith · OpenAI gpt-4o (provider-agnostic) · Solidity/Foundry · ERC-4626 vault · ERC-8004 identity + reputation · FastAPI + HTMX dashboard · Pinata/IPFS agent card · python-telegram-bot.

**What's next.** Wire live Agni / Merchant Moe routers for real swap execution; enable cross-agent ERC-8004 reputation feedback; add a vault depositor SDK; pilot with a real RWA treasury on Mantle mainnet.

**Links.** GitHub: [repo] · Demo video: [YouTube] · Dashboard: [screenshot] · Audit: `docs/AUDIT.md`

# PrimeYield — X Launch Thread

> 8 tweets. Post immediately AFTER the DoraHacks submission timestamp.
> Fill [video] and [github] before posting. Tag @0xMantle and the hackathon handle.

---

**1/ 🧵**
Meet PrimeYield: an AI agent that rotates real-world-asset yield on @0xMantle — and commits a cryptographic hash of every decision on-chain *before* it trades.

Autonomous AND auditable.

Built for the Mantle Turing Test Hackathon (AI × RWA). 👇

**2/**
The problem: rotating yield across mETH, USDY and USDe by hand is slow and loses alpha.

Hand it to an agent? Every yield agent today is a black box. No treasury or insurer will trust capital to something nobody can verify.

**3/**
PrimeYield's fix: it writes `keccak256(rationale)` to an on-chain DecisionLog contract before every trade.

Anyone can replay the chain and prove what the agent decided — and that it wasn't edited after the fact.

**4/**
How a cycle runs (9-node LangGraph state machine):

snapshot → forecast (gpt-4o) → 4 risk gates → propose → simulate → human approval for big moves → execute → log on-chain → reputation.

Risk = 10k-path Monte Carlo VaR/ES + oracle, slippage & concentration checks.

**5/**
It's live on Mantle Sepolia 🟢
• ERC-8004 agent #207
• ERC-4626 vault
• DecisionLog with real recorded decisions

Example AI decision (USDY→USDe, USDY→mETH) committed on-chain:
sepolia.mantlescan.xyz/tx/0x463b020fdb6ebd1a57c5fa4635f8c18f555dcf2378d0718efe90335bee8ac5f0

**6/**
The proof: a `judge_replay` tool re-reads every on-chain commitment and matches it to the stored rationale.

Verdict: ✅ VERIFIED — on-chain=3, matched=3, tamper=0.

Tamper with a decision → the hash breaks → the audit flags it.

**7/**
Stack: LangGraph + LangSmith · OpenAI gpt-4o (provider-agnostic) · Solidity/Foundry · ERC-4626 + ERC-8004 · FastAPI/HTMX dashboard · Telegram approval gate · Pinata/IPFS.

mETH + USDY are real Mantle RWA assets with real TVL.

**8/**
PrimeYield = agent speed, smart-contract verifiability.

The trust layer for putting RWA capital under agent control.

🎥 Demo: [video]
💻 Code: [github]
Built on @0xMantle for the Turing Test Hackathon.

#Mantle #RWA #AIagents

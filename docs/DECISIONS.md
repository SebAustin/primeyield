# Engineering Decision Log

Chronological record of non-obvious engineering choices.

## Day 0 — Scaffold

- **Pinata access via `requests` (REST), not `pinata-python-sdk`.** The package
  named in the brief is not a stable PyPI distribution; the Pinata REST API
  (`POST /pinning/pinFileToIPFS`) is used directly to keep `uv sync` reliable.
- **Runtime state lives in repo-root `state/`, not `agent/state/`.** A
  `agent/state/` directory would collide with the `agent/state.py` module in
  Python's import system. `register_agent.py` / `deploy_vault.py` write
  `state/identity.json` and `state/deployments.json`.
- **`evm_version = "paris"`** pinned in `foundry.toml` so the compiler never
  emits PUSH0 (unsupported on Mantle per the brief). ⚠️ VERIFY against current
  Mantle docs before mainnet — Mantle's opcode support has changed over time.
- **`AgentState` field names are frozen** (see `agent/state.py` docstring): they
  are the contract threaded through adapters, graph, API, and judge_replay.
- **`Swap.from_asset`** uses a Pydantic alias for `from` (reserved keyword).

## Day 1 — ERC-8004 identity + vault skeleton

- **ERC-8004 registry addresses VERIFIED** (2026-06-04) from the real
  erc-8004/erc-8004-contracts README (master branch), "Mantle Testnet" section.
  ⚠️ A first WebFetch *hallucinated* a "Mantle Sepolia" heading; the addresses
  happened to be right (deterministic across all ERC-8004 testnets) but the
  source text was confirmed by hand before trusting it. IdentityRegistry
  `0x8004A818…BD9e`, ReputationRegistry `0x8004B663…8713`. In `agent/config.py`.
- **`register(string agentURI) → uint256 agentId`**, emits
  `Registered(uint256 indexed agentId, string agentURI, address indexed owner)`.
  `register_agent.py` parses `agentId` from the `Registered` event.
- **Vault = ERC-4626 with USDe as the accounting asset.** ERC-4626 is
  single-asset by spec; mETH and USDY are tracked as rotation targets the agent
  rebalances into/out of. Share token `pyUSDe`.
- **2-of-2 emergency exit = on-chain owner+guardian confirmations**
  (`confirmEmergencyExit` ×2 → `emergencyExit(to)`), not raw EIP-712 sigs —
  cleaner and directly testable. Upgrade to signatures later if needed.
- **Day-1 scripts verified against a local anvil** (chainId 31337): full deploy
  of 3 mocks + vault + DecisionLog + funding succeeded; vault holds 1 mETH /
  1000 USDY / 1000 USDe. `register_agent.py --encode-only` produces correct
  `register(string)` calldata. Live Sepolia run still needs a funded EOA +
  PINATA_JWT (see open items).
- **Foundry installed** (forge/anvil 1.7.1) via `foundryup`. forge-std v1.16.1
  + OpenZeppelin v5.1.0 in `contracts/lib/`. Remappings in `foundry.toml`.

### Open VERIFY items (resolve before the relevant day)

- [ ] Ondo USDY `RWADynamicOracle` address on Mantle →
      `agent/config.py: USDY_ORACLE_ADDRESS` (Day 2-3).
- [ ] Agni & Merchant Moe ABIs (from mantlescan verified contracts) (Day 2-3).
- [ ] Live Sepolia registration/deploy needs a funded agent EOA + `PINATA_JWT`
      (only local-anvil dry-runs done so far).
- [ ] `agent-card.json` model string (`claude-sonnet-4-5`) vs. the model
      actually called at runtime.
- [x] ERC-8004 Mantle Sepolia IdentityRegistry address — resolved (Day 1).
- [x] Foundry installed in dev env (Day 1).

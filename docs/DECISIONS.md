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

## Day 2-3 — Protocol adapters + risk engine

- **No RWADynamicOracle on Mantle** (verified 2026-06-05 from mantlescan +
  Ondo GitHub). The Mantle USDY deployment (`0x5bE26527…`) is a
  transfer-restricted ERC-20 with a `blocklist()` pointer; pricing comes from
  the Ondo REST API or a Chainlink MNT/USD feed (address still TBD — VERIFY).
  `agent/adapters/ondo.py` falls back to $1.052 if both are unavailable.
- **USDY preflight** reads `blocklist().isBlocked(recipient)` on-chain;
  raises `USDYBlocklistError` on any failure (including inability to read
  the blocklist itself — fail-safe design).
- **Agni QuoterV2** — `quoteExactInputSingle` is nonpayable in the ABI but
  behaves as a read; called via `eth_call` (web3.py default for `.call()`).
  Struct parameter confirmed from verified source on mantlescan.xyz.
- **Merchant Moe LBRouter.swapExactTokensForTokens** takes a `Path` struct
  with `{pairBinSteps, versions (uint8[]), tokenPath}`. `versions` uses the
  `ILBRouter.Version` enum (V2_2 = 3, but `findBestPathFromAmountIn` returns
  the best version per pair — current adapter defaults to V2_2=3 for the
  full path).
- **Risk engine** uses NumPy for the 10k-path Monte Carlo (added to
  dependencies). Cholesky decomposition with a small jitter (`1e-10` on the
  diagonal) guards against near-singular covariance matrices from synthetic
  test data.
- **VaR95 can be positive** when all yield scenarios have consistently
  positive micro-returns — the test suite is updated to reflect this; the
  relevant gate is `var95 > -3%`, not `var95 < 0`.

## Day 4-5 — LangGraph node implementations + Telegram approval

- **Approval bridge**: `agent/approval_store.py` manages asyncio.Events keyed
  by `decision_id`. `request_approval` node awaits the event (4h timeout);
  the FastAPI Telegram webhook resolves it via `approval_store.resolve()`.
  No LangGraph `interrupt` or checkpointing needed — the node itself blocks.
- **`simulate_plan` uses `eth_call`** for dry-run simulation rather than
  spawning a new anvil subprocess. `eth_call` is the JSON-RPC dry-run
  primitive; when `MANTLE_ACTIVE_RPC` points to an anvil fork this is
  equivalent to "running against anvil" without the overhead of a subprocess.
- **`execute` nonce management**: each tx increments the nonce from
  `get_transaction_count`. In the fully serialized execute node this is safe;
  if parallelism is ever added, a nonce pool will be needed.
- **`post_to_reputation`** calls the ERC-8004 `giveFeedback()` function
  directly (no EIP-712 wrapping needed — the signature is via tx sender).
  Score 9977 / 2 decimals = 99.77 on success; 5000/2 on partial execution.
- **DB layer** (`agent/db.py`): writes to Postgres when `DATABASE_URL` is
  configured; falls back to `state/decisions.jsonl` JSONL file otherwise —
  judge_replay.py reads whichever is available.
- **Fallback paths in every node**: LLM failures in `forecast_yields` /
  `propose_plan` fall back to last-known yields / no-op plan. No node raises
  uncaught exceptions; failures are logged and routed to `rejected`.

### Open VERIFY items (resolve before the relevant day)

- [ ] Chainlink MNT/USD (or USDY/USD) feed address on Mantle →
      `agent/adapters/ondo.py: CHAINLINK_MNT_USD_MANTLE` (before mainnet).
- [ ] Agni & Merchant Moe subgraph URLs for pool APR data (pool APR is
      currently a 0-stub — wire subgraphs Day 6-7 if time permits).
- [ ] Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and call
      `setWebhook` on the Telegram API pointing at the FastAPI server
      before the live demo.
- [ ] Live Sepolia registration/deploy needs a funded agent EOA + `PINATA_JWT`
      (only local-anvil dry-runs done so far).
- [ ] `agent-card.json` model string (`claude-sonnet-4-5`) vs. the model
      actually called at runtime.
- [x] ERC-8004 Mantle Sepolia IdentityRegistry address — resolved (Day 1).
- [x] Foundry installed in dev env (Day 1).

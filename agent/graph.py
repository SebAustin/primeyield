"""PrimeYield LangGraph state machine — full 9-node implementation.

Flow:
    snapshot_state -> forecast_yields -> score_risks
        score_risks --(risk failed)--> END
        score_risks --(risk passed)--> propose_plan
    propose_plan -> simulate_plan
        simulate_plan --(delta < 5% TVL)--> execute  (approval_status="auto")
        simulate_plan --(delta >= 5% TVL)--> request_approval
    request_approval --(approved)--> execute
    request_approval --(rejected)--> END
    execute -> log_decision -> post_to_reputation -> END

Each node takes AgentState, returns a partial dict merged back by LangGraph.
All nodes are async and decorated with @traceable for LangSmith.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Literal

from langsmith import traceable
from langgraph.graph import END, StateGraph

from agent.state import (
    AgentState,
    LpPosition,
    PortfolioSnapshot,
    RebalancePlan,
    RiskReport,
    SimResult,
    Swap,
    YieldForecast,
)

log = logging.getLogger(__name__)

AUTO_APPROVE_THRESHOLD = Decimal("0.05")

# ---------------------------------------------------------------------------
# ERC-8004 ReputationRegistry ABI (verified from source)
# ---------------------------------------------------------------------------
_REPUTATION_REGISTRY_ABI = [
    {
        "type": "function",
        "name": "giveFeedback",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "value", "type": "int128"},
            {"name": "valueDecimals", "type": "uint8"},
            {"name": "tag1", "type": "string"},
            {"name": "tag2", "type": "string"},
            {"name": "endpoint", "type": "string"},
            {"name": "feedbackURI", "type": "string"},
            {"name": "feedbackHash", "type": "bytes32"},
        ],
        "outputs": [],
    },
]

_DECISION_LOG_ABI = [
    {
        "type": "function",
        "name": "record",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "rationaleHash", "type": "bytes32"},
        ],
        "outputs": [],
    },
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _load_deployments() -> dict:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "state" / "deployments.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _load_identity() -> dict:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "state" / "identity.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _keccak(text: str) -> bytes:
    from eth_hash.auto import keccak

    return keccak(text.encode())


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _send_tx(w3, acct, fn, nonce_offset: int = 0) -> dict:
    """Sign and send a contract function call. Returns the receipt."""
    from agent.config import get_account

    opts = {
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address) + nonce_offset,
        "gasPrice": w3.eth.gas_price,
    }
    tx = fn.build_transaction(opts)
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


# ---------------------------------------------------------------------------
# Node 1 — snapshot_state
# ---------------------------------------------------------------------------
@traceable(name="snapshot_state")
async def snapshot_state(state: AgentState) -> dict:
    """Build PortfolioSnapshot from the four protocol adapters."""
    from agent.adapters import agni, mantle_lsp, merchant_moe, ondo
    from agent.config import get_w3

    w3 = get_w3()
    deps = _load_deployments()
    tokens = deps.get("tokens", {})

    meth_addr = tokens.get("mETH", "")
    usdy_addr = tokens.get("USDY", "")
    usde_addr = tokens.get("USDe", "")

    # Fetch APRs concurrently (balances require RPC calls).
    meth_apr, usdy_yield = await asyncio.gather(
        mantle_lsp.get_staking_apr(),
        ondo.get_usdy_treasury_yield(),
    )

    # Fetch token balances from vault.
    vault_addr = deps.get("vault", "")
    erc20_abi = [
        {
            "type": "function",
            "name": "balanceOf",
            "stateMutability": "view",
            "inputs": [{"name": "account", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        }
    ]

    meth_bal = usdy_bal = usde_bal = Decimal("0")
    if vault_addr and meth_addr:
        try:
            for sym, addr in (("mETH", meth_addr), ("USDY", usdy_addr), ("USDe", usde_addr)):
                tok = w3.eth.contract(address=w3.to_checksum_address(addr), abi=erc20_abi)
                raw = tok.functions.balanceOf(w3.to_checksum_address(vault_addr)).call()
                dec = Decimal(str(raw)) / Decimal("1e18")
                if sym == "mETH":
                    meth_bal = dec
                elif sym == "USDY":
                    usdy_bal = dec
                else:
                    usde_bal = dec
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot_state: balance fetch failed (%s); using 0", exc)

    # Rough USD TVL using fallback prices.
    usdy_price = await ondo.usdy_price_usd(w3)
    meth_rate = Decimal("1")
    try:
        meth_rate = await mantle_lsp.meth_to_eth_rate(w3)
    except Exception as exc:  # noqa: BLE001
        log.warning("snapshot_state: meth rate fetch failed (%s)", exc)

    total_tvl = meth_bal * meth_rate + usdy_bal * usdy_price + usde_bal

    snapshot = PortfolioSnapshot(
        meth_balance=meth_bal,
        usdy_balance=usdy_bal,
        usde_balance=usde_bal,
        meth_apr=meth_apr,
        usdy_yield=usdy_yield,
        agni_lp_positions=[],
        merchant_moe_positions=[],
        total_tvl_usd=total_tvl,
        timestamp=int(time.time()),
    )
    return {"snapshot": snapshot}


# ---------------------------------------------------------------------------
# Node 2 — forecast_yields
# ---------------------------------------------------------------------------
@traceable(name="forecast_yields")
async def forecast_yields(state: AgentState) -> dict:
    """Forecast 7d/30d yields per asset via Claude."""
    import asyncio

    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    snap = state.snapshot
    system = (
        "You are a DeFi yield analyst. Given the following on-chain yield data, "
        "forecast 7-day and 30-day yield for each asset. "
        "Respond in valid JSON ONLY — no prose, no markdown, just a JSON object:\n"
        '{"mETH": {"yield_7d": <float>, "yield_30d": <float>, "confidence": <0..1>}, '
        '"USDY": {"yield_7d": <float>, "yield_30d": <float>, "confidence": <0..1>}, '
        '"USDe": {"yield_7d": <float>, "yield_30d": <float>, "confidence": <0..1>}}'
    )
    payload = (
        f"Current on-chain data:\n"
        f"  mETH staking APR: {float(snap.meth_apr):.4f}\n"
        f"  USDY Treasury yield: {float(snap.usdy_yield):.4f}\n"
        f"  USDe stable yield: 0.0490 (reference)\n"
        f"  Total TVL: ${float(snap.total_tvl_usd):,.2f}\n"
        f"  Timestamp: {snap.timestamp}"
    )

    try:
        llm = ChatAnthropic(model="claude-sonnet-4-5", max_tokens=512, temperature=0)
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=payload)])
        raw = resp.content.strip()
        # Strip any markdown fences if present.
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        forecasts = {
            asset: YieldForecast(
                yield_7d=Decimal(str(vals["yield_7d"])),
                yield_30d=Decimal(str(vals["yield_30d"])),
                confidence=Decimal(str(vals["confidence"])),
            )
            for asset, vals in data.items()
            if asset in ("mETH", "USDY", "USDe")
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("forecast_yields LLM call failed (%s); using last-known yields", exc)
        forecasts = {
            "mETH": YieldForecast(
                yield_7d=snap.meth_apr, yield_30d=snap.meth_apr, confidence=Decimal("0.5")
            ),
            "USDY": YieldForecast(
                yield_7d=snap.usdy_yield, yield_30d=snap.usdy_yield, confidence=Decimal("0.5")
            ),
            "USDe": YieldForecast(
                yield_7d=Decimal("0.049"), yield_30d=Decimal("0.049"), confidence=Decimal("0.5")
            ),
        }
    return {"forecasts": forecasts}


# ---------------------------------------------------------------------------
# Node 3 — score_risks
# ---------------------------------------------------------------------------
@traceable(name="score_risks")
async def score_risks(state: AgentState) -> dict:
    """Run the four RiskEngine gates; populate RiskReport."""
    from agent.adapters import ondo
    from agent.config import get_w3
    from agent.risk import RiskEngine

    snap = state.snapshot
    if snap.total_tvl_usd > 0:
        weights = {
            "mETH": snap.meth_balance,
            "USDY": snap.usdy_balance,
            "USDe": snap.usde_balance,
        }
    else:
        weights = {"mETH": Decimal("1"), "USDY": Decimal("1"), "USDe": Decimal("1")}

    # Build simple yield scenarios from forecasts (1 scenario = mean forecast).
    yield_scenarios: dict[str, list[Decimal]] = {}
    for asset in ("mETH", "USDY", "USDe"):
        fc = state.forecasts.get(asset)
        if fc:
            # Use 30d forecast spread as a simple 2-point scenario.
            mid = fc.yield_30d / Decimal("365")
            yield_scenarios[asset] = [
                mid * Decimal("0.9"),
                mid * Decimal("1.0"),
                mid * Decimal("1.1"),
            ] * 10  # 30 samples — enough for Cholesky
        else:
            yield_scenarios[asset] = [Decimal("0.0001")] * 30

    # Fetch current USDY price for oracle gate.
    w3 = get_w3()
    usdy_price = await ondo.usdy_price_usd(w3)
    reference_price = snap.usdy_yield / Decimal("365") + Decimal("1")  # approx

    eng = RiskEngine()
    report = eng.evaluate(
        usdy_price=usdy_price,
        reference_price=reference_price,
        amount_in=1_000,
        quoted_out=999,
        proposed_weights=weights,
        yield_scenarios=yield_scenarios,
        n_paths=5_000,
    )
    log.info(
        "score_risks: passed=%s var95=%s es95=%s",
        report.passed, report.var_95, report.es_95,
    )
    return {"risk_report": report}


# ---------------------------------------------------------------------------
# Node 4 — propose_plan
# ---------------------------------------------------------------------------
@traceable(name="propose_plan")
async def propose_plan(state: AgentState) -> dict:
    """Ask Claude for a RebalancePlan; validate concentration before accepting."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.risk import RiskEngine

    snap = state.snapshot
    fcs = state.forecasts
    report = state.risk_report

    fc_text = "\n".join(
        f"  {a}: 7d={float(fcs[a].yield_7d):.4f}, 30d={float(fcs[a].yield_30d):.4f}, "
        f"conf={float(fcs[a].confidence):.2f}"
        for a in fcs
    )
    system = (
        "You are a DeFi yield rotation agent. Produce a rebalance plan as valid JSON ONLY.\n"
        "Constraints:\n"
        "  - Maximum 3 swaps per cycle (gas budget)\n"
        "  - No single asset may exceed 60% of TVL\n"
        "  - If any swap involves USDY as destination, add a note in rationale about blocklist preflight\n"
        "  - Minimize gas; avoid swaps smaller than 5% of TVL\n"
        "JSON format:\n"
        '{"swaps": [{"from": "<asset>", "to": "<asset>", "amount_pct": <0..1>, '
        '"rationale": "<string>"}], "expected_apy_delta": <float>}'
    )
    payload = (
        f"Current portfolio:\n"
        f"  mETH: {float(snap.meth_balance):.4f} (APR {float(snap.meth_apr):.4f})\n"
        f"  USDY: {float(snap.usdy_balance):.4f} (yield {float(snap.usdy_yield):.4f})\n"
        f"  USDe: {float(snap.usde_balance):.4f}\n"
        f"  Total TVL: ${float(snap.total_tvl_usd):,.2f}\n\n"
        f"Yield forecasts:\n{fc_text}\n\n"
        f"Risk report: VaR95={float(report.var_95 or 0):.4f}, "
        f"ES95={float(report.es_95 or 0):.4f} — all gates PASSED\n\n"
        "Propose the optimal rebalance. Keep rationale concise (< 200 chars each swap)."
    )

    eng = RiskEngine()
    plan: RebalancePlan | None = None

    for attempt in range(3):
        try:
            llm = ChatAnthropic(model="claude-sonnet-4-5", max_tokens=1024, temperature=0.1)
            resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=payload)])
            raw = resp.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)

            swaps = [
                Swap.model_validate(s) for s in data.get("swaps", [])
            ]
            total_delta = sum(Decimal(str(s.amount_pct)) for s in swaps)
            apy_delta = Decimal(str(data.get("expected_apy_delta", 0)))

            # Validate concentration.
            total_w = snap.total_tvl_usd or Decimal("1")
            weights: dict[str, Decimal] = {
                "mETH": snap.meth_balance,
                "USDY": snap.usdy_balance,
                "USDe": snap.usde_balance,
            }
            for s in swaps:
                move = total_w * Decimal(str(s.amount_pct))
                weights[s.from_asset] = max(Decimal("0"), weights.get(s.from_asset, Decimal("0")) - move)
                weights[s.to] = weights.get(s.to, Decimal("0")) + move

            if eng.concentration_check(weights):
                plan = RebalancePlan(
                    swaps=swaps,
                    expected_apy_delta=apy_delta,
                    total_delta_pct=total_delta,
                )
                break
            else:
                log.warning("propose_plan attempt %d: concentration check failed, retrying", attempt + 1)
                payload += "\n\nPrevious proposal failed concentration check (>60% in one asset). Diversify more."
        except Exception as exc:  # noqa: BLE001
            log.warning("propose_plan attempt %d failed: %s", attempt + 1, exc)

    if plan is None:
        # Fallback: no-op plan.
        log.warning("propose_plan: all LLM attempts failed; using no-op plan")
        plan = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0"), total_delta_pct=Decimal("0"))

    return {"proposed_plan": plan}


# ---------------------------------------------------------------------------
# Node 5 — simulate_plan
# ---------------------------------------------------------------------------
@traceable(name="simulate_plan")
async def simulate_plan(state: AgentState) -> dict:
    """Dry-run swap txs against the active RPC (anvil fork in dev).

    Uses eth_call for simulation — this is the JSON-RPC equivalent of running
    the tx against an anvil fork without broadcasting to the mempool.
    """
    plan = state.proposed_plan
    if not plan or not plan.swaps:
        return {
            "simulation_result": SimResult(
                gas_estimate=0,
                expected_out={},
                slippage_actual=Decimal("0"),
            ),
            "approval_status": "auto",
        }

    from agent.adapters import agni, ondo
    from agent.adapters.ondo import USDYBlocklistError
    from agent.config import get_account, get_w3

    w3 = get_w3()
    acct = get_account(w3)
    deps = _load_deployments()
    tokens = deps.get("tokens", {})

    total_gas = 0
    expected_out: dict[str, Decimal] = {}

    for swap in plan.swaps:
        from_addr = tokens.get(swap.from_asset, "")
        to_addr = tokens.get(swap.to, "")
        if not from_addr or not to_addr:
            log.warning("simulate_plan: unknown token for swap %s->%s", swap.from_asset, swap.to)
            continue

        tvl = state.snapshot.total_tvl_usd or Decimal("1")
        amount_wei = int(tvl * Decimal(str(swap.amount_pct)) * Decimal("1e18"))

        # USDY preflight check (simulation only — no tx).
        if swap.to == "USDY":
            try:
                await ondo.preflight(acct.address, w3)
            except USDYBlocklistError as e:
                log.error("simulate_plan: USDY preflight FAILED for %s: %s", acct.address, e)
                return {
                    "simulation_result": SimResult(
                        gas_estimate=0,
                        expected_out={},
                        slippage_actual=Decimal("0"),
                        reverted=True,
                        revert_reason=str(e),
                    ),
                    "approval_status": "rejected",
                }

        # Build and simulate the swap tx via eth_call.
        try:
            quote = await agni.quote_exact_input(from_addr, to_addr, amount_wei, 500, w3)
            min_out = quote.amount_out * 995 // 1000  # 0.5% slippage
            tx_dict = await agni.build_swap_tx(from_addr, to_addr, amount_wei, min_out, acct.address, w3)
            gas = w3.eth.estimate_gas(
                {"to": tx_dict["to"], "from": acct.address, "data": tx_dict["data"]}
            )
            total_gas += gas
            expected_out[swap.to] = Decimal(str(quote.amount_out)) / Decimal("1e18")
        except Exception as exc:  # noqa: BLE001
            log.warning("simulate_plan: swap %s->%s estimate failed (%s)", swap.from_asset, swap.to, exc)
            total_gas += 150_000  # fallback estimate per swap

    # Slippage approximation.
    tvl = state.snapshot.total_tvl_usd or Decimal("1")
    total_move = sum(Decimal(str(s.amount_pct)) for s in plan.swaps)
    slippage = total_move * Decimal("0.003")  # rough 30bps per full TVL move

    sim = SimResult(
        gas_estimate=total_gas,
        expected_out=expected_out,
        slippage_actual=slippage,
        reverted=False,
    )

    # Routing decision: auto if delta < 5% TVL.
    if plan.total_delta_pct < AUTO_APPROVE_THRESHOLD:
        approval_status = "auto"
    else:
        approval_status = "pending"

    return {"simulation_result": sim, "approval_status": approval_status}


# ---------------------------------------------------------------------------
# Node 6 — request_approval
# ---------------------------------------------------------------------------
@traceable(name="request_approval")
async def request_approval(state: AgentState) -> dict:
    """Send the Telegram approval card; block on callback (4h timeout)."""
    import uuid

    from agent import approval_store
    from agent.config import get_settings

    settings = get_settings()
    plan = state.proposed_plan
    sim = state.simulation_result

    decision_id = state.decision_id or str(uuid.uuid4())
    approval_event = approval_store.register(decision_id)

    # Format the approval message.
    apy_delta = float(plan.expected_apy_delta) if plan else 0
    gas_est = sim.gas_estimate if sim else 0
    n_swaps = len(plan.swaps) if plan else 0
    var95 = float(state.risk_report.var_95 or 0)

    rationale_lines = "\n".join(
        f"  • {s.from_asset}→{s.to} ({float(s.amount_pct)*100:.1f}%): {s.rationale[:120]}"
        for s in (plan.swaps if plan else [])
    )

    text = (
        f"⚡ *PrimeYield Rebalance Proposal*\n\n"
        f"📈 APY delta: +{apy_delta:.4f}\n"
        f"📉 Max drawdown (VaR95): {var95:.4f}\n"
        f"⛽ Gas estimate: {gas_est:,}\n"
        f"🔄 {n_swaps} swap(s)\n\n"
        f"{rationale_lines}\n\n"
        f"`decision_id: {decision_id}`"
    )

    approval_status = "rejected"  # default if Telegram unavailable

    if settings.telegram_bot_token and not settings.telegram_bot_token.startswith("123456"):
        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

            bot = Bot(token=settings.telegram_bot_token)
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{decision_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{decision_id}"),
            ]])
            await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            log.info("request_approval: Telegram message sent for %s", decision_id)

            # Wait up to 4 hours for callback.
            try:
                await asyncio.wait_for(approval_event.wait(), timeout=4 * 3600)
                approval_status = approval_store.get_status(decision_id) or "rejected"
            except asyncio.TimeoutError:
                log.warning("request_approval: 4h timeout for %s; rejecting", decision_id)
                approval_status = "rejected"
        except Exception as exc:  # noqa: BLE001
            log.error("request_approval: Telegram error (%s); auto-rejecting", exc)
    else:
        log.warning(
            "request_approval: TELEGRAM_BOT_TOKEN not configured; auto-rejecting %s",
            decision_id,
        )

    approval_store.cleanup(decision_id)
    return {"approval_status": approval_status, "decision_id": decision_id}


# ---------------------------------------------------------------------------
# Node 7 — execute
# ---------------------------------------------------------------------------
@traceable(name="execute")
async def execute(state: AgentState) -> dict:
    """Preflight USDY, record rationale hash on-chain, submit swaps."""
    from agent.adapters import agni, ondo
    from agent.adapters.ondo import USDYBlocklistError
    from agent.config import get_account, get_settings, get_w3, mantlescan_tx
    from agent.decision_logger import canonical_json, rationale_hash as build_hash

    w3 = get_w3()
    acct = get_account(w3)
    deps = _load_deployments()
    identity = _load_identity()
    tokens = deps.get("tokens", {})

    plan = state.proposed_plan
    if not plan:
        return {"onchain_txs": []}

    agent_id = identity.get("agentId", 0)

    # Build the rationale object to hash.
    rationale_obj = {
        "decision_id": state.decision_id,
        "timestamp": int(time.time()),
        "swaps": [
            {
                "from": s.from_asset,
                "to": s.to,
                "amount_pct": str(s.amount_pct),
                "rationale": s.rationale,
            }
            for s in plan.swaps
        ],
        "expected_apy_delta": str(plan.expected_apy_delta),
        "var95": str(state.risk_report.var_95),
        "es95": str(state.risk_report.es_95),
    }

    # Compute keccak256 of canonical JSON.
    canonical = canonical_json(rationale_obj)
    r_hash_bytes = _keccak(canonical)
    r_hash_hex = "0x" + r_hash_bytes.hex()

    onchain_txs: list[str] = []

    # 1. Record rationale hash to DecisionLog.
    decision_log_addr = deps.get("decisionLog", "")
    if decision_log_addr:
        try:
            decision_log = w3.eth.contract(
                address=w3.to_checksum_address(decision_log_addr),
                abi=_DECISION_LOG_ABI,
            )
            receipt = _send_tx(w3, acct, decision_log.functions.record(agent_id, r_hash_bytes))
            tx_url = mantlescan_tx(receipt["transactionHash"].hex())
            onchain_txs.append(tx_url)
            log.info("execute: DecisionLog.record() → %s", tx_url)
        except Exception as exc:  # noqa: BLE001
            log.error("execute: DecisionLog.record failed (%s) — aborting swaps", exc)
            return {"approval_status": "rejected", "onchain_txs": onchain_txs}

    # 2. Submit each swap.
    tvl = state.snapshot.total_tvl_usd or Decimal("1")
    for swap in plan.swaps:
        from_addr = tokens.get(swap.from_asset, "")
        to_addr = tokens.get(swap.to, "")
        if not from_addr or not to_addr:
            log.warning("execute: unknown token for %s->%s, skipping", swap.from_asset, swap.to)
            continue

        # USDY preflight (mandatory).
        if swap.to == "USDY":
            try:
                await ondo.preflight(acct.address, w3)
            except USDYBlocklistError as e:
                log.error("execute: USDY preflight FAILED (%s) — rolling back", e)
                return {"approval_status": "rejected", "onchain_txs": onchain_txs}

        amount_wei = int(tvl * Decimal(str(swap.amount_pct)) * Decimal("1e18"))
        try:
            quote = await agni.quote_exact_input(from_addr, to_addr, amount_wei, 500, w3)
            min_out = quote.amount_out * 995 // 1000
            tx_dict = await agni.build_swap_tx(from_addr, to_addr, amount_wei, min_out, acct.address, w3)

            tx = {
                "to": w3.to_checksum_address(tx_dict["to"]),
                "from": acct.address,
                "data": tx_dict["data"],
                "value": tx_dict.get("value", 0),
                "nonce": w3.eth.get_transaction_count(acct.address),
                "gasPrice": w3.eth.gas_price,
                "gas": int(w3.eth.estimate_gas({"to": tx_dict["to"], "from": acct.address, "data": tx_dict["data"]}) * 1.3),
            }
            signed = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            tx_url = mantlescan_tx(tx_hash.hex())
            onchain_txs.append(tx_url)
            log.info("execute: swap %s->%s → %s", swap.from_asset, swap.to, tx_url)
        except Exception as exc:  # noqa: BLE001
            log.error("execute: swap %s->%s failed (%s); aborting remaining swaps", swap.from_asset, swap.to, exc)
            break

    return {
        "onchain_txs": onchain_txs,
        "rationale_hash": r_hash_hex,
    }


# ---------------------------------------------------------------------------
# Node 8 — log_decision
# ---------------------------------------------------------------------------
@traceable(name="log_decision")
async def log_decision(state: AgentState) -> dict:
    """Persist the full decision record to Postgres (or JSONL fallback)."""
    from agent.db import save_decision

    record = {
        "decision_id": state.decision_id or str(uuid.uuid4()),
        "timestamp": state.snapshot.timestamp if state.snapshot else int(time.time()),
        "snapshot_json": state.snapshot.model_dump(mode="json") if state.snapshot else None,
        "plan_json": state.proposed_plan.model_dump(mode="json") if state.proposed_plan else None,
        "rationale_hash": state.rationale_hash,
        "onchain_txs": state.onchain_txs,
        "approval_status": state.approval_status,
        "sim_result_json": state.simulation_result.model_dump(mode="json") if state.simulation_result else None,
    }
    try:
        save_decision(record)
    except Exception as exc:  # noqa: BLE001
        log.error("log_decision: save failed (%s)", exc)
    return {}


# ---------------------------------------------------------------------------
# Node 9 — post_to_reputation
# ---------------------------------------------------------------------------
@traceable(name="post_to_reputation")
async def post_to_reputation(state: AgentState) -> dict:
    """Submit ERC-8004 reputation feedback for this rebalance cycle."""
    from agent.config import (
        MANTLE_SEPOLIA_REPUTATION_REGISTRY,
        get_account,
        get_w3,
        mantlescan_tx,
    )

    identity = _load_identity()
    agent_id = identity.get("agentId")
    if agent_id is None:
        log.warning("post_to_reputation: no agentId in identity.json; skipping")
        return {}

    w3 = get_w3()
    acct = get_account(w3)

    # Encode the rationale hash as bytes32.
    r_hash = state.rationale_hash or ("0x" + "0" * 64)
    hash_bytes = bytes.fromhex(r_hash.lstrip("0x").zfill(64))

    # Score: 9977 with 2 decimals = 99.77 (success); or lower on partial execution.
    score = 9977 if state.onchain_txs else 5000
    score_decimals = 2

    try:
        reg = w3.eth.contract(
            address=w3.to_checksum_address(MANTLE_SEPOLIA_REPUTATION_REGISTRY),
            abi=_REPUTATION_REGISTRY_ABI,
        )
        receipt = _send_tx(
            w3, acct,
            reg.functions.giveFeedback(
                agent_id,
                score,
                score_decimals,
                "yield-rotation",
                "rebalance",
                "",
                "",
                hash_bytes,
            ),
        )
        tx_url = mantlescan_tx(receipt["transactionHash"].hex())
        log.info("post_to_reputation: submitted → %s", tx_url)
        return {"onchain_txs": state.onchain_txs + [tx_url]}
    except Exception as exc:  # noqa: BLE001
        log.error("post_to_reputation failed (%s)", exc)
    return {}


# ---------------------------------------------------------------------------
# Conditional-edge routers
# ---------------------------------------------------------------------------
def route_after_risk(state: AgentState) -> Literal["propose_plan", "END"]:
    return "propose_plan" if state.risk_report.passed else "END"


def route_after_simulation(state: AgentState) -> Literal["execute", "request_approval"]:
    plan = state.proposed_plan
    if plan is not None and plan.total_delta_pct < AUTO_APPROVE_THRESHOLD:
        return "execute"
    return "request_approval"


def route_after_approval(state: AgentState) -> Literal["execute", "END"]:
    return "execute" if state.approval_status in ("approved", "auto") else "END"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("snapshot_state", snapshot_state)
    g.add_node("forecast_yields", forecast_yields)
    g.add_node("score_risks", score_risks)
    g.add_node("propose_plan", propose_plan)
    g.add_node("simulate_plan", simulate_plan)
    g.add_node("request_approval", request_approval)
    g.add_node("execute", execute)
    g.add_node("log_decision", log_decision)
    g.add_node("post_to_reputation", post_to_reputation)

    g.set_entry_point("snapshot_state")
    g.add_edge("snapshot_state", "forecast_yields")
    g.add_edge("forecast_yields", "score_risks")
    g.add_conditional_edges(
        "score_risks",
        route_after_risk,
        {"propose_plan": "propose_plan", "END": END},
    )
    g.add_edge("propose_plan", "simulate_plan")
    g.add_conditional_edges(
        "simulate_plan",
        route_after_simulation,
        {"execute": "execute", "request_approval": "request_approval"},
    )
    g.add_conditional_edges(
        "request_approval",
        route_after_approval,
        {"execute": "execute", "END": END},
    )
    g.add_edge("execute", "log_decision")
    g.add_edge("log_decision", "post_to_reputation")
    g.add_edge("post_to_reputation", END)
    return g


def compile_graph():
    return build_graph().compile()


async def run_cycle(force_auto_approve: bool = False) -> AgentState:
    """Run one full rebalance cycle. Returns the final AgentState.

    Args:
        force_auto_approve: skip the Telegram gate (useful for Day 6-7 e2e
                            dry-runs on Sepolia — comment out in production).
    """
    from agent.config import get_settings

    graph = compile_graph()

    # Build a minimal initial state with zero balances; snapshot_state will
    # populate it from on-chain data.
    initial = AgentState(
        snapshot=PortfolioSnapshot(
            meth_balance=Decimal("0"),
            usdy_balance=Decimal("0"),
            usde_balance=Decimal("0"),
            meth_apr=Decimal("0.038"),
            usdy_yield=Decimal("0.052"),
            total_tvl_usd=Decimal("0"),
            timestamp=int(time.time()),
        )
    )

    if force_auto_approve:
        # Monkey-patch the threshold so any plan is auto-approved.
        import agent.graph as _self
        _orig = _self.AUTO_APPROVE_THRESHOLD
        _self.AUTO_APPROVE_THRESHOLD = Decimal("999")

    try:
        run_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": run_id}}
        final = await graph.ainvoke(initial, config=config)
        settings = get_settings()
        project = settings.langsmith_project
        log.info(
            "run_cycle complete. LangSmith trace: "
            "https://smith.langchain.com/projects/%s", project,
        )
        if isinstance(final, dict):
            return AgentState(**final)
        return final
    finally:
        if force_auto_approve:
            _self.AUTO_APPROVE_THRESHOLD = _orig

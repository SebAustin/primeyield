"""LangGraph topology and node unit tests.

Node logic tests use mocked adapters/LLM — no live RPC or Telegram needed.
Topology tests verify the graph wiring never regresses.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.graph import (
    AUTO_APPROVE_THRESHOLD,
    build_graph,
    compile_graph,
    route_after_approval,
    route_after_risk,
    route_after_simulation,
)
from agent.state import (
    AgentState,
    PortfolioSnapshot,
    RebalancePlan,
    RiskReport,
    SimResult,
    Swap,
    YieldForecast,
)


# ---------------------------------------------------------------------------
# State factories
# ---------------------------------------------------------------------------
def _snapshot(**kw) -> PortfolioSnapshot:
    defaults = dict(
        meth_balance=Decimal("1"),
        usdy_balance=Decimal("1000"),
        usde_balance=Decimal("1000"),
        meth_apr=Decimal("0.038"),
        usdy_yield=Decimal("0.052"),
        total_tvl_usd=Decimal("4000"),
        timestamp=int(time.time()),
    )
    return PortfolioSnapshot(**{**defaults, **kw})


def _state(**kw) -> AgentState:
    return AgentState(snapshot=_snapshot(), **kw)


# ===========================================================================
# Topology tests
# ===========================================================================
class TestTopology:
    def test_all_nine_nodes_present(self):
        g = build_graph()
        expected = {
            "snapshot_state", "forecast_yields", "score_risks", "propose_plan",
            "simulate_plan", "request_approval", "execute", "log_decision",
            "post_to_reputation",
        }
        assert expected.issubset(set(g.nodes))

    def test_graph_compiles(self):
        compile_graph()  # Must not raise.

    def test_route_after_risk_passed(self):
        assert route_after_risk(_state(risk_report=RiskReport(passed=True))) == "propose_plan"

    def test_route_after_risk_failed(self):
        assert route_after_risk(_state(risk_report=RiskReport(passed=False))) == "END"

    def test_route_after_simulation_auto(self):
        plan = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"),
                             total_delta_pct=Decimal("0.04"))
        assert route_after_simulation(_state(proposed_plan=plan)) == "execute"

    def test_route_after_simulation_approval(self):
        plan = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"),
                             total_delta_pct=Decimal("0.06"))
        assert route_after_simulation(_state(proposed_plan=plan)) == "request_approval"

    def test_route_after_approval_approved(self):
        assert route_after_approval(_state(approval_status="approved")) == "execute"

    def test_route_after_approval_auto(self):
        assert route_after_approval(_state(approval_status="auto")) == "execute"

    def test_route_after_approval_rejected(self):
        assert route_after_approval(_state(approval_status="rejected")) == "END"

    def test_auto_approve_threshold(self):
        assert AUTO_APPROVE_THRESHOLD == Decimal("0.05")


# ===========================================================================
# Node unit tests (mocked I/O)
# ===========================================================================
class TestSnapshotStateNode:
    @pytest.mark.asyncio
    async def test_returns_snapshot_with_timestamp(self):
        from agent.graph import snapshot_state

        with (
            patch("agent.graph._load_deployments", return_value={}),
            patch("agent.adapters.mantle_lsp.get_staking_apr", new_callable=AsyncMock, return_value=Decimal("0.038")),
            patch("agent.adapters.ondo.get_usdy_treasury_yield", new_callable=AsyncMock, return_value=Decimal("0.052")),
            patch("agent.adapters.ondo.usdy_price_usd", new_callable=AsyncMock, return_value=Decimal("1.052")),
            patch("agent.adapters.mantle_lsp.meth_to_eth_rate", new_callable=AsyncMock, return_value=Decimal("1.05")),
            patch("agent.config.get_w3", return_value=MagicMock()),
        ):
            state = _state()
            result = await snapshot_state(state)

        assert "snapshot" in result
        assert result["snapshot"].meth_apr == Decimal("0.038")
        assert result["snapshot"].timestamp > 0


class TestForecastYieldsNode:
    @pytest.mark.asyncio
    async def test_uses_fallback_on_llm_failure(self):
        from agent.graph import forecast_yields

        with patch("agent.llm.make_chat_llm", side_effect=Exception("no API key")):
            state = _state()
            result = await forecast_yields(state)

        forecasts = result["forecasts"]
        assert "mETH" in forecasts
        assert "USDY" in forecasts
        assert "USDe" in forecasts
        assert isinstance(forecasts["mETH"], YieldForecast)

    @pytest.mark.asyncio
    async def test_parses_llm_json_response(self):
        from agent.graph import forecast_yields

        mock_resp = MagicMock()
        mock_resp.content = '{"mETH": {"yield_7d": 0.038, "yield_30d": 0.039, "confidence": 0.8}, "USDY": {"yield_7d": 0.052, "yield_30d": 0.053, "confidence": 0.9}, "USDe": {"yield_7d": 0.049, "yield_30d": 0.049, "confidence": 0.85}}'

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

        with patch("agent.llm.make_chat_llm", return_value=mock_llm):
            state = _state()
            result = await forecast_yields(state)

        assert result["forecasts"]["mETH"].yield_7d == Decimal("0.038")
        assert result["forecasts"]["USDY"].confidence == Decimal("0.9")


class TestScoreRisksNode:
    @pytest.mark.asyncio
    async def test_populates_risk_report(self):
        from agent.graph import score_risks

        with (
            patch("agent.adapters.ondo.usdy_price_usd", new_callable=AsyncMock, return_value=Decimal("1.052")),
            patch("agent.config.get_w3", return_value=MagicMock()),
        ):
            forecasts = {
                "mETH": YieldForecast(yield_7d=Decimal("0.038"), yield_30d=Decimal("0.038"), confidence=Decimal("0.8")),
                "USDY": YieldForecast(yield_7d=Decimal("0.052"), yield_30d=Decimal("0.052"), confidence=Decimal("0.9")),
                "USDe": YieldForecast(yield_7d=Decimal("0.049"), yield_30d=Decimal("0.049"), confidence=Decimal("0.85")),
            }
            state = _state(forecasts=forecasts)
            result = await score_risks(state)

        assert "risk_report" in result
        report = result["risk_report"]
        assert isinstance(report, RiskReport)
        # With equal weights (1/1/1) concentration is fine.
        assert report.concentration_ok is True


class TestSimulatePlanNode:
    @pytest.mark.asyncio
    async def test_no_swaps_returns_auto(self):
        from agent.graph import simulate_plan

        plan = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0"), total_delta_pct=Decimal("0"))
        state = _state(proposed_plan=plan)
        result = await simulate_plan(state)

        assert result["approval_status"] == "auto"
        assert result["simulation_result"].gas_estimate == 0

    @pytest.mark.asyncio
    async def test_large_delta_sets_pending(self):
        """A plan with total_delta_pct >= 0.05 should set approval_status=pending."""
        from agent.graph import simulate_plan

        swap = Swap(**{"from": "mETH", "to": "USDY", "amount_pct": Decimal("0.06"), "rationale": "test"})
        plan = RebalancePlan(swaps=[swap], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.06"))

        mock_w3 = MagicMock()
        mock_w3.eth.estimate_gas.return_value = 150_000

        mock_quote = MagicMock()
        mock_quote.amount_out = 990_000

        with (
            patch("agent.graph._load_deployments", return_value={"tokens": {"mETH": "0x" + "a" * 40, "USDY": "0x" + "b" * 40}}),
            patch("agent.adapters.agni.quote_exact_input", new_callable=AsyncMock, return_value=mock_quote),
            patch("agent.adapters.agni.build_swap_tx", new_callable=AsyncMock, return_value={"to": "0x" + "c" * 40, "data": "0x", "value": 0}),
            patch("agent.adapters.ondo.preflight", new_callable=AsyncMock, return_value=True),
            patch("agent.config.get_w3", return_value=mock_w3),
            patch("agent.config.get_account", return_value=MagicMock(address="0x" + "d" * 40)),
        ):
            state = _state(proposed_plan=plan)
            result = await simulate_plan(state)

        assert result["approval_status"] == "pending"

    @pytest.mark.asyncio
    async def test_usdy_blocklist_rejects(self):
        from agent.adapters.ondo import USDYBlocklistError
        from agent.graph import simulate_plan

        swap = Swap(**{"from": "mETH", "to": "USDY", "amount_pct": Decimal("0.06"), "rationale": "test"})
        plan = RebalancePlan(swaps=[swap], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.06"))

        with (
            patch("agent.graph._load_deployments", return_value={"tokens": {"mETH": "0x" + "a" * 40, "USDY": "0x" + "b" * 40}}),
            patch("agent.adapters.ondo.preflight", new_callable=AsyncMock, side_effect=USDYBlocklistError("0xtest")),
            patch("agent.config.get_w3", return_value=MagicMock()),
            patch("agent.config.get_account", return_value=MagicMock(address="0xtest")),
        ):
            state = _state(proposed_plan=plan)
            result = await simulate_plan(state)

        assert result["approval_status"] == "rejected"
        assert result["simulation_result"].reverted is True


class TestRequestApprovalNode:
    @pytest.mark.asyncio
    async def test_rejects_when_telegram_not_configured(self):
        from agent.graph import request_approval

        state = _state(
            proposed_plan=RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.06")),
            simulation_result=SimResult(gas_estimate=100_000, expected_out={}, slippage_actual=Decimal("0.001")),
        )
        # Default settings have a placeholder token → should auto-reject gracefully.
        with patch("agent.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                telegram_bot_token="123456:placeholder",
                telegram_chat_id="0",
            )
            result = await request_approval(state)

        assert result["approval_status"] == "rejected"
        assert result["decision_id"] is not None

    @pytest.mark.asyncio
    async def test_approves_via_event(self):
        """Simulate the Telegram webhook firing the approval event."""
        from agent import approval_store
        from agent.graph import request_approval

        # Pre-seed an event that fires "approved" after a short delay.
        state = _state(
            proposed_plan=RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.06")),
            simulation_result=SimResult(gas_estimate=100_000, expected_out={}, slippage_actual=Decimal("0.001")),
        )

        original_register = approval_store.register

        def mock_register(decision_id: str):
            event = original_register(decision_id)
            # Schedule the approval after 50ms.
            async def _fire():
                await asyncio.sleep(0.05)
                approval_store.resolve(decision_id, "approved")
            asyncio.ensure_future(_fire())
            return event

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()

        with (
            patch("agent.approval_store.register", side_effect=mock_register),
            patch("agent.config.get_settings") as mock_settings,
            patch("telegram.Bot", return_value=mock_bot),
        ):
            mock_settings.return_value = MagicMock(
                telegram_bot_token="9999:realtoken",
                telegram_chat_id="12345",
            )
            result = await request_approval(state)

        assert result["approval_status"] == "approved"


class TestLogDecisionNode:
    @pytest.mark.asyncio
    async def test_saves_decision_record(self):
        from agent.graph import log_decision

        state = _state(
            decision_id="test-decision-123",
            rationale_hash="0xdeadbeef",
            onchain_txs=["https://sepolia.mantlescan.xyz/tx/0xabc"],
            approval_status="auto",
        )
        with patch("agent.db.save_decision") as mock_save:
            await log_decision(state)

        mock_save.assert_called_once()
        args = mock_save.call_args[0][0]
        assert args["decision_id"] == "test-decision-123"
        assert args["rationale_hash"] == "0xdeadbeef"

"""Topology smoke tests for the LangGraph state machine.

Node logic is stubbed until days 4-5; these tests assert the graph wiring is
correct so the topology contract doesn't silently regress.
"""

from __future__ import annotations

from decimal import Decimal

from agent.graph import (
    AUTO_APPROVE_THRESHOLD,
    build_graph,
    compile_graph,
    route_after_approval,
    route_after_risk,
    route_after_simulation,
)
from agent.state import AgentState, PortfolioSnapshot, RebalancePlan, RiskReport


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        meth_balance=Decimal("1"),
        usdy_balance=Decimal("1000"),
        usde_balance=Decimal("1000"),
        meth_apr=Decimal("0.038"),
        usdy_yield=Decimal("0.052"),
        total_tvl_usd=Decimal("4000"),
        timestamp=0,
    )


def _state(**kw) -> AgentState:
    return AgentState(snapshot=_snapshot(), **kw)


def test_graph_compiles_with_all_nodes():
    g = build_graph()
    nodes = set(g.nodes)
    expected = {
        "snapshot_state",
        "forecast_yields",
        "score_risks",
        "propose_plan",
        "simulate_plan",
        "request_approval",
        "execute",
        "log_decision",
        "post_to_reputation",
    }
    assert expected.issubset(nodes)
    # Should compile without raising.
    compile_graph()


def test_route_after_risk_gates_on_passed():
    assert route_after_risk(_state(risk_report=RiskReport(passed=True))) == "propose_plan"
    assert route_after_risk(_state(risk_report=RiskReport(passed=False))) == "END"


def test_route_after_simulation_auto_threshold():
    small = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.04"))
    big = RebalancePlan(swaps=[], expected_apy_delta=Decimal("0.01"), total_delta_pct=Decimal("0.06"))
    assert AUTO_APPROVE_THRESHOLD == Decimal("0.05")
    assert route_after_simulation(_state(proposed_plan=small)) == "execute"
    assert route_after_simulation(_state(proposed_plan=big)) == "request_approval"


def test_route_after_approval():
    assert route_after_approval(_state(approval_status="approved")) == "execute"
    assert route_after_approval(_state(approval_status="auto")) == "execute"
    assert route_after_approval(_state(approval_status="rejected")) == "END"
    assert route_after_approval(_state(approval_status="pending")) == "END"

"""PrimeYield LangGraph state machine — TOPOLOGY ONLY.

This module wires the nine-node rebalance cycle. Node bodies are intentionally
stubs (day 1 scaffold); the logic is filled in on days 4-5. The topology,
node names, and conditional-edge routing are the stable contract.

Flow:

    snapshot_state -> forecast_yields -> score_risks
        score_risks --(risk failed)--> END
        score_risks --(risk passed)--> propose_plan
    propose_plan -> simulate_plan
        simulate_plan --(delta < 5% TVL)--> execute            (approval_status="auto")
        simulate_plan --(delta >= 5% TVL)--> request_approval   (approval_status="pending")
    request_approval --(approved)--> execute
    request_approval --(rejected)--> END
    execute -> log_decision -> post_to_reputation -> END
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from langgraph.graph import END, StateGraph

from agent.state import AgentState

# Moves below this fraction of TVL execute automatically; larger moves require
# human approval via Telegram.
AUTO_APPROVE_THRESHOLD = Decimal("0.05")


# ---------------------------------------------------------------------------
# Node stubs (logic implemented on days 4-5)
# ---------------------------------------------------------------------------
def snapshot_state(state: AgentState) -> dict:
    """Build PortfolioSnapshot from the four protocol adapters."""
    raise NotImplementedError("day 4-5: snapshot_state")


def forecast_yields(state: AgentState) -> dict:
    """Forecast 7d/30d yields per asset via Claude."""
    raise NotImplementedError("day 4-5: forecast_yields")


def score_risks(state: AgentState) -> dict:
    """Run the four RiskEngine gates; populate RiskReport."""
    raise NotImplementedError("day 4-5: score_risks")


def propose_plan(state: AgentState) -> dict:
    """Ask Claude for a RebalancePlan; validate concentration before accepting."""
    raise NotImplementedError("day 4-5: propose_plan")


def simulate_plan(state: AgentState) -> dict:
    """Dry-run swap txs against an anvil fork; record SimResult."""
    raise NotImplementedError("day 4-5: simulate_plan")


def request_approval(state: AgentState) -> dict:
    """Send the Telegram approval card and block on the callback."""
    raise NotImplementedError("day 4-5: request_approval")


def execute(state: AgentState) -> dict:
    """Preflight, record rationale hash on-chain, submit swaps."""
    raise NotImplementedError("day 4-5: execute")


def log_decision(state: AgentState) -> dict:
    """Persist the full decision record to Postgres + pgvector."""
    raise NotImplementedError("day 4-5: log_decision")


def post_to_reputation(state: AgentState) -> dict:
    """Submit EIP-712 signed feedback to the ERC-8004 ReputationRegistry."""
    raise NotImplementedError("day 4-5: post_to_reputation")


# ---------------------------------------------------------------------------
# Conditional-edge routers
# ---------------------------------------------------------------------------
def route_after_risk(state: AgentState) -> Literal["propose_plan", "END"]:
    """Halt the cycle if any risk gate failed."""
    return "propose_plan" if state.risk_report.passed else "END"


def route_after_simulation(state: AgentState) -> Literal["execute", "request_approval"]:
    """Auto-execute small moves; escalate large moves to human approval."""
    plan = state.proposed_plan
    if plan is not None and plan.total_delta_pct < AUTO_APPROVE_THRESHOLD:
        return "execute"
    return "request_approval"


def route_after_approval(state: AgentState) -> Literal["execute", "END"]:
    """Execute on approval/auto; otherwise end the cycle."""
    return "execute" if state.approval_status in ("approved", "auto") else "END"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    """Construct the StateGraph topology (uncompiled)."""
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
    """Compile the graph for execution."""
    return build_graph().compile()


async def run_cycle() -> AgentState:
    """Entry point for one full rebalance cycle (wired on days 4-5)."""
    raise NotImplementedError("day 4-5: run_cycle")

"""Canonical agent state for PrimeYield.

These models are the single source of truth threaded through the LangGraph
state machine. Field names here are referenced across adapters, the risk
engine, the graph nodes, the API, and judge_replay.py — DO NOT rename them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Asset universe
# ---------------------------------------------------------------------------
Asset = Literal["mETH", "USDY", "USDe"]


# ---------------------------------------------------------------------------
# Portfolio snapshot (produced by snapshot_state node)
# ---------------------------------------------------------------------------
class LpPosition(BaseModel):
    """A single liquidity-pool position on Agni or Merchant Moe."""

    model_config = ConfigDict(extra="forbid")

    pool: str
    token_a: str
    token_b: str
    fee_tier: int
    liquidity_usd: Decimal
    apr: Decimal


class PortfolioSnapshot(BaseModel):
    """On-chain state of the vault at a point in time."""

    model_config = ConfigDict(extra="forbid")

    meth_balance: Decimal
    usdy_balance: Decimal
    usde_balance: Decimal
    meth_apr: Decimal
    usdy_yield: Decimal
    agni_lp_positions: list[LpPosition] = Field(default_factory=list)
    merchant_moe_positions: list[LpPosition] = Field(default_factory=list)
    total_tvl_usd: Decimal
    timestamp: int  # unix seconds


# ---------------------------------------------------------------------------
# Yield forecast (produced by forecast_yields node)
# ---------------------------------------------------------------------------
class YieldForecast(BaseModel):
    """Claude's forward yield estimate for a single asset."""

    model_config = ConfigDict(extra="forbid")

    yield_7d: Decimal
    yield_30d: Decimal
    confidence: Decimal  # 0..1


# ---------------------------------------------------------------------------
# Risk report (produced by score_risks node)
# ---------------------------------------------------------------------------
class RiskReport(BaseModel):
    """Outcome of the four RiskEngine gates plus Monte Carlo tail metrics."""

    model_config = ConfigDict(extra="forbid")

    oracle_deviation_ok: bool = False
    concentration_ok: bool = False
    slippage_ok: bool = False
    monte_carlo_ok: bool = False
    var_95: Optional[Decimal] = None  # negative decimal, e.g. -0.02
    es_95: Optional[Decimal] = None   # negative decimal, e.g. -0.04
    passed: bool = False
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Rebalance plan (produced by propose_plan node)
# ---------------------------------------------------------------------------
class Swap(BaseModel):
    """A single swap leg of a rebalance plan."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # `from` is a Python keyword, so expose it as `from_asset` with a JSON alias.
    from_asset: str = Field(alias="from")
    to: str
    amount_pct: Decimal  # fraction of TVL, 0..1
    rationale: str


class RebalancePlan(BaseModel):
    """The proposed set of swaps for one rebalance cycle."""

    model_config = ConfigDict(extra="forbid")

    swaps: list[Swap] = Field(default_factory=list)
    expected_apy_delta: Decimal
    # Total fraction of TVL moved this cycle; drives the auto-vs-approval edge.
    total_delta_pct: Decimal


# ---------------------------------------------------------------------------
# Simulation result (produced by simulate_plan node)
# ---------------------------------------------------------------------------
class SimResult(BaseModel):
    """Result of dry-running the plan against an anvil fork."""

    model_config = ConfigDict(extra="forbid")

    gas_estimate: int
    expected_out: dict[str, Decimal] = Field(default_factory=dict)
    slippage_actual: Decimal
    reverted: bool = False
    revert_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Canonical agent state
# ---------------------------------------------------------------------------
class AgentState(BaseModel):
    """The state object passed between every LangGraph node.

    Field names are part of the public contract — see module docstring.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    snapshot: PortfolioSnapshot
    forecasts: dict[str, YieldForecast] = Field(default_factory=dict)
    risk_report: RiskReport = Field(default_factory=RiskReport)
    proposed_plan: Optional[RebalancePlan] = None
    simulation_result: Optional[SimResult] = None
    approval_status: Literal["pending", "approved", "rejected", "auto"] = "pending"
    decision_id: Optional[str] = None
    rationale_hash: Optional[str] = None
    onchain_txs: list[str] = Field(default_factory=list)

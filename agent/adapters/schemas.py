"""Pydantic v2 schemas shared across all protocol adapters.

These are the wire-types for adapter inputs/outputs. They are kept separate
from agent/state.py (which holds the canonical AgentState) so adapters can
be tested independently.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Agni Finance (V3 Uniswap-style) schemas
# ---------------------------------------------------------------------------
class QuoteResult(BaseModel):
    """Result of a QuoterV2.quoteExactInputSingle call."""

    model_config = ConfigDict(extra="forbid")

    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    fee_tier: int
    sqrt_price_x96_after: int
    initialized_ticks_crossed: int
    gas_estimate: int


class SwapTx(BaseModel):
    """Encoded swap transaction ready to sign and send."""

    model_config = ConfigDict(extra="forbid")

    to: str
    data: str  # 0x-prefixed hex calldata
    value: int = 0
    gas_estimate: int = 0


# ---------------------------------------------------------------------------
# Merchant Moe (LB) schemas
# ---------------------------------------------------------------------------
class LBQuote(BaseModel):
    """Result of LBQuoter.findBestPathFromAmountIn."""

    model_config = ConfigDict(extra="forbid")

    route: list[str]
    pairs: list[str]
    bin_steps: list[int]
    amounts: list[int]      # amounts[0]=amountIn, amounts[-1]=amountOut
    fees: list[int]


# ---------------------------------------------------------------------------
# Shared position / APR schemas
# ---------------------------------------------------------------------------
class PoolApr(BaseModel):
    """On-chain or subgraph-derived pool APR."""

    model_config = ConfigDict(extra="forbid")

    pool: str
    token_a: str
    token_b: str
    fee_tier: Optional[int] = None  # None for Merchant Moe (bin-step, not fee-tier)
    apr: Decimal
    tvl_usd: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# mETH (Mantle LSP) schemas
# ---------------------------------------------------------------------------
class MethStakeQuote(BaseModel):
    """Stake/unstake quote from the Mantle LSP."""

    model_config = ConfigDict(extra="forbid")

    meth_to_eth_rate: Decimal   # 1 mETH = N ETH
    staking_apr: Decimal
    amount_wei: int
    expected_meth_out: Optional[int] = None
    expected_eth_out: Optional[int] = None

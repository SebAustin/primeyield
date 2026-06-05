"""Agni Finance V3 adapter (Uniswap V3 fork on Mantle).

Contract addresses verified on mantlescan.xyz:
  QuoterV2:   0xc4aaDc921E1cdb66c5300Bc158a313292923C0cb
  SwapRouter: 0x319B69888b0d11cEC22caA5034e25FfFBDc88421

Function signatures confirmed from verified source on mantlescan.xyz.

Note: quoteExactInputSingle is marked nonpayable (not view) in the ABI but
behaves as a read — call it via eth_call (w3 default for contract.call()).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from langsmith import traceable

from agent.adapters.schemas import PoolApr, QuoteResult, SwapTx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agni ABIs (verified from mantlescan.xyz)
# ---------------------------------------------------------------------------
_QUOTER_V2_ABI = [
    {
        "type": "function",
        "name": "quoteExactInputSingle",
        "stateMutability": "nonpayable",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
            }
        ],
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
    },
]

_SWAP_ROUTER_ABI = [
    {
        "type": "function",
        "name": "exactInputSingle",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
            }
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
    },
]

# Minimal pool ABI for fee-tier + slot0 state.
_POOL_ABI = [
    {
        "type": "function",
        "name": "fee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint24"}],
    },
    {
        "type": "function",
        "name": "token0",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "token1",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "liquidity",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint128"}],
    },
]


@traceable(name="agni_quote_exact_input")
async def quote_exact_input(
    token_in: str,
    token_out: str,
    amount_in: int,
    fee_tier: int,
    w3,  # noqa: ANN001
) -> QuoteResult:
    """Quote a single-hop exactInput swap via Agni QuoterV2.

    Note: quoteExactInputSingle is nonpayable but is a simulation — web3.py
    calls it via eth_call which is correct.
    """
    from agent.config import AGNI_QUOTER_V2

    quoter = w3.eth.contract(
        address=w3.to_checksum_address(AGNI_QUOTER_V2),
        abi=_QUOTER_V2_ABI,
    )
    params = {
        "tokenIn": w3.to_checksum_address(token_in),
        "tokenOut": w3.to_checksum_address(token_out),
        "amountIn": amount_in,
        "fee": fee_tier,
        "sqrtPriceLimitX96": 0,
    }
    result = quoter.functions.quoteExactInputSingle(params).call()
    amount_out, sqrt_price, ticks_crossed, gas_est = result

    return QuoteResult(
        token_in=token_in,
        token_out=token_out,
        amount_in=amount_in,
        amount_out=amount_out,
        fee_tier=fee_tier,
        sqrt_price_x96_after=sqrt_price,
        initialized_ticks_crossed=ticks_crossed,
        gas_estimate=gas_est,
    )


@traceable(name="agni_build_swap_tx")
async def build_swap_tx(
    token_in: str,
    token_out: str,
    amount_in: int,
    min_out: int,
    recipient: str,
    w3,  # noqa: ANN001
    fee_tier: int = 500,
    deadline_offset: int = 600,
) -> SwapTx:
    """Build calldata for an Agni exactInputSingle swap.

    deadline_offset: seconds added to current block timestamp.
    """
    import time

    from agent.config import AGNI_SWAP_ROUTER

    router = w3.eth.contract(
        address=w3.to_checksum_address(AGNI_SWAP_ROUTER),
        abi=_SWAP_ROUTER_ABI,
    )
    deadline = int(time.time()) + deadline_offset
    params = {
        "tokenIn": w3.to_checksum_address(token_in),
        "tokenOut": w3.to_checksum_address(token_out),
        "fee": fee_tier,
        "recipient": w3.to_checksum_address(recipient),
        "deadline": deadline,
        "amountIn": amount_in,
        "amountOutMinimum": min_out,
        "sqrtPriceLimitX96": 0,
    }
    calldata = router.encode_abi("exactInputSingle", args=[params])
    return SwapTx(
        to=AGNI_SWAP_ROUTER,
        data=calldata,
        value=0,
    )


@traceable(name="agni_get_pool_apr")
async def get_pool_apr(
    token_a: str,
    token_b: str,
    fee_tier: int,
    w3,  # noqa: ANN001
) -> Decimal:
    """Estimate pool APR from on-chain liquidity + fee data.

    Uses a simplified approximation: daily volume ≈ not available from a
    single block, so this returns a placeholder until a subgraph is wired in.
    Day 2-3 wires the Agni subgraph; this stub returns 0.
    """
    log.warning(
        "agni.get_pool_apr: subgraph not yet wired; returning 0 for %s/%s fee=%s",
        token_a, token_b, fee_tier,
    )
    return Decimal("0")

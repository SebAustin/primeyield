"""Merchant Moe Liquidity Book (LB) adapter.

Contract addresses verified on mantlescan.xyz:
  LBQuoter: 0x501b8AFd35df20f531fF45F6f695793AC3316c85
  LBRouter: 0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a

Function signatures confirmed from verified source on mantlescan.xyz.

The ILBRouter.Path struct:
  struct Path {
    uint256[] pairBinSteps;
    ILBRouter.Version[] versions;
    IERC20[] tokenPath;       // full token list including start and end
  }
Version enum: V1=0, V2=1, V2_1=2, V2_2=3
"""

from __future__ import annotations

import logging
from decimal import Decimal

from langsmith import traceable

from agent.adapters.schemas import LBQuote, SwapTx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Merchant Moe ABIs (verified from mantlescan.xyz)
# ---------------------------------------------------------------------------
_LB_QUOTER_ABI = [
    {
        "type": "function",
        "name": "findBestPathFromAmountIn",
        "stateMutability": "view",
        "inputs": [
            {"name": "route", "type": "address[]"},
            {"name": "amountIn", "type": "uint128"},
        ],
        "outputs": [
            {
                "name": "quote",
                "type": "tuple",
                "components": [
                    {"name": "route", "type": "address[]"},
                    {"name": "pairs", "type": "address[]"},
                    {"name": "binSteps", "type": "uint256[]"},
                    {
                        "name": "versions",
                        "type": "uint8[]",
                    },  # ILBRouter.Version enum encoded as uint8
                    {"name": "amounts", "type": "uint128[]"},
                    {"name": "virtualAmountsWithoutSlippage", "type": "uint128[]"},
                    {"name": "fees", "type": "uint128[]"},
                ],
            }
        ],
    },
]

_LB_ROUTER_ABI = [
    {
        "type": "function",
        "name": "swapExactTokensForTokens",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {
                "name": "path",
                "type": "tuple",
                "components": [
                    {"name": "pairBinSteps", "type": "uint256[]"},
                    {"name": "versions", "type": "uint8[]"},
                    {"name": "tokenPath", "type": "address[]"},
                ],
            },
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
    },
]


@traceable(name="merchant_moe_quote_exact_input")
async def quote_exact_input(
    token_in: str,
    token_out: str,
    amount_in: int,
    w3,  # noqa: ANN001
) -> LBQuote:
    """Quote a swap from token_in to token_out via LBQuoter.findBestPathFromAmountIn."""
    from agent.config import MERCHANT_MOE_LB_QUOTER

    quoter = w3.eth.contract(
        address=w3.to_checksum_address(MERCHANT_MOE_LB_QUOTER),
        abi=_LB_QUOTER_ABI,
    )
    route = [
        w3.to_checksum_address(token_in),
        w3.to_checksum_address(token_out),
    ]
    q = quoter.functions.findBestPathFromAmountIn(route, amount_in).call()

    return LBQuote(
        route=[str(a) for a in q[0]],
        pairs=[str(a) for a in q[1]],
        bin_steps=[int(b) for b in q[2]],
        amounts=[int(a) for a in q[4]],
        fees=[int(f) for f in q[6]],
    )


@traceable(name="merchant_moe_build_swap_tx")
async def build_swap_tx(
    token_in: str,
    token_out: str,
    amount_in: int,
    min_out: int,
    recipient: str,
    w3,  # noqa: ANN001
    deadline_offset: int = 600,
) -> SwapTx:
    """Build calldata for a Merchant Moe swapExactTokensForTokens call.

    Gets the best path from LBQuoter first to populate pairBinSteps/versions.
    """
    import time

    from agent.config import MERCHANT_MOE_LB_ROUTER

    lb_quote = await quote_exact_input(token_in, token_out, amount_in, w3)

    router = w3.eth.contract(
        address=w3.to_checksum_address(MERCHANT_MOE_LB_ROUTER),
        abi=_LB_ROUTER_ABI,
    )
    path = {
        "pairBinSteps": lb_quote.bin_steps,
        "versions": [2] * len(lb_quote.bin_steps),  # assume V2_2 for best path
        "tokenPath": [w3.to_checksum_address(a) for a in lb_quote.route],
    }
    deadline = int(time.time()) + deadline_offset
    calldata = router.encode_abi(
        "swapExactTokensForTokens",
        args=[amount_in, min_out, path, w3.to_checksum_address(recipient), deadline],
    )
    return SwapTx(to=MERCHANT_MOE_LB_ROUTER, data=calldata, value=0)


@traceable(name="merchant_moe_get_bin_apr")
async def get_bin_apr(
    token_a: str,
    token_b: str,
    w3,  # noqa: ANN001
) -> Decimal:
    """Estimate Merchant Moe LB pool APR.

    Day 2-3 placeholder; wires the Merchant Moe subgraph in the full
    implementation.
    """
    log.warning(
        "merchant_moe.get_bin_apr: subgraph not yet wired; returning 0 for %s/%s",
        token_a,
        token_b,
    )
    return Decimal("0")

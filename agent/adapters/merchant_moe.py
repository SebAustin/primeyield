"""Merchant Moe (Liquidity Book) adapter — implemented day 2-3.

LB Quoter / Router addresses live in agent/config.py.
ABI source: verified contracts on mantlescan.xyz.
"""

from __future__ import annotations

from decimal import Decimal


async def quote_exact_input(token_in, token_out, amount_in, w3):  # noqa: ANN001
    raise NotImplementedError("day 2-3: LBQuoter.findBestPathFromAmountIn")


async def build_swap_tx(token_in, token_out, amount_in, min_out, recipient, w3):  # noqa: ANN001
    raise NotImplementedError("day 2-3: LBRouter.swapExactTokensForTokens")


async def get_bin_apr(token_a, token_b, w3) -> Decimal:  # noqa: ANN001
    raise NotImplementedError("day 2-3")

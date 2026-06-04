"""Agni Finance V3 adapter — implemented day 2-3.

QuoterV2 / SwapRouter addresses live in agent/config.py.
ABI source: agni-finance.gitbook.io or verified contracts on mantlescan.xyz.
"""

from __future__ import annotations

from decimal import Decimal


async def quote_exact_input(token_in, token_out, amount_in, fee_tier, w3):  # noqa: ANN001
    raise NotImplementedError("day 2-3: QuoterV2.quoteExactInputSingle")


async def build_swap_tx(token_in, token_out, amount_in, min_out, recipient, w3):  # noqa: ANN001
    raise NotImplementedError("day 2-3: SwapRouter.exactInputSingle")


async def get_pool_apr(token_a, token_b, fee_tier, w3) -> Decimal:  # noqa: ANN001
    raise NotImplementedError("day 2-3")

"""Mantle LSP (mETH) adapter — implemented day 2-3.

Docs: https://docs.mantle.xyz/meth
"""

from __future__ import annotations

from decimal import Decimal

# from web3 import Web3  # day 2-3


async def meth_to_eth_rate(w3) -> Decimal:  # noqa: ANN001
    raise NotImplementedError("day 2-3: mETH.mETHToETH(1e18)")


async def get_staking_apr() -> Decimal:
    raise NotImplementedError("day 2-3: Mantle LSP subgraph; fallback 3.8%")


async def build_stake_tx(amount_wei: int, recipient: str) -> dict:
    raise NotImplementedError("day 2-3")


async def build_unstake_request_tx(meth_amount_wei: int) -> dict:
    raise NotImplementedError("day 2-3")

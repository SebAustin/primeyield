"""Ondo (USDY) adapter — implemented day 2-3.

Docs: https://docs.ondo.finance/developer-guides/mantle-integration-guidelines

CRITICAL: any path that transfers USDY MUST call preflight(recipient) first.
If preflight fails (blocklisted), raise USDYBlocklistError and log the
rejection in AgentState — never swallow silently.
"""

from __future__ import annotations

from decimal import Decimal


class USDYBlocklistError(Exception):
    """Raised when a recipient fails the USDY transfer blocklist preflight."""


async def usdy_price_usd(w3) -> Decimal:  # noqa: ANN001
    # Reads RWADynamicOracle. VERIFY oracle address at docs.ondo.finance/mantle.
    raise NotImplementedError("day 2-3: RWADynamicOracle price")


async def preflight(recipient: str, w3) -> bool:  # noqa: ANN001
    # Simulate USDY.beforeTransfer(zero_address, recipient, 0); raise on revert.
    raise NotImplementedError("day 2-3: USDY blocklist preflight")


async def get_usdy_treasury_yield() -> Decimal:
    raise NotImplementedError("day 2-3: Ondo API/subgraph; fallback 5.2%")

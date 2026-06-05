"""Ondo (USDY) adapter for Mantle.

Source: https://docs.ondo.finance/developer-guides/mantle-integration-guidelines

USDY on Mantle mainnet: 0x5bE26527e817998A7206475496fDE1E68957c5A6
Implementation:         0x3b355A7A25E75A320f631F9736afB3Dcc9F3Ef66

Key Mantle-specific finding (verified 2026-06-05 from mantlescan):
  The Mantle deployment of USDY is a transfer-restricted ERC-20 with an
  on-chain `blocklist()` but NO on-chain RWADynamicOracle deployed on Mantle
  mainnet. Price is obtained via Chainlink's MNT/USD price feed or Ondo's REST
  API (fallback 5.2%). The `beforeTransfer` hook is checked by calling
  `blocklist().isBlocked(address)` directly.

CRITICAL: any code path that transfers USDY MUST call preflight(recipient)
first.  If preflight fails (address is blocked), raise USDYBlocklistError and
log the rejection in AgentState — NEVER swallow silently.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from langsmith import traceable

from agent.adapters.ondo_abi import USDY_ABI, USDY_BLOCKLIST_ABI

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Addresses (Mantle mainnet)
# ---------------------------------------------------------------------------
USDY_MANTLE_MAINNET = "0x5bE26527e817998A7206475496fDE1E68957c5A6"

# Chainlink MNT/USD data feed on Mantle — VERIFY before mainnet use.
# If unavailable, the adapter falls back to the Ondo REST API price.
CHAINLINK_MNT_USD_MANTLE: str | None = None  # VERIFY: docs.chain.link/data-feeds

_PRICE_FALLBACK = Decimal("1.052")          # ~5.2% Treasury yield → ~$1.052 USDY
_YIELD_FALLBACK = Decimal("0.052")          # 5.2% APY


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class USDYBlocklistError(Exception):
    """Raised when a recipient fails the USDY transfer blocklist preflight.

    Attributes:
        recipient: the blocked address
        reason:    a human-readable description of why the preflight failed
    """

    def __init__(self, recipient: str, reason: str = "address is blocklisted"):
        self.recipient = recipient
        self.reason = reason
        super().__init__(f"USDY preflight failed for {recipient}: {reason}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------
@traceable(name="usdy_price_usd")
async def usdy_price_usd(w3) -> Decimal:  # noqa: ANN001
    """Return the current USDY price in USD.

    Tries (in order):
      1. Chainlink MNT/USD aggregator if the address is configured.
      2. Ondo REST price API.
      3. Static fallback ($1.052).
    """
    # 1. Chainlink aggregator (when we have the address)
    if CHAINLINK_MNT_USD_MANTLE:
        try:
            agg_abi = [
                {
                    "type": "function",
                    "name": "latestRoundData",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [
                        {"name": "roundId", "type": "uint80"},
                        {"name": "answer", "type": "int256"},
                        {"name": "startedAt", "type": "uint256"},
                        {"name": "updatedAt", "type": "uint256"},
                        {"name": "answeredInRound", "type": "uint80"},
                    ],
                }
            ]
            agg = w3.eth.contract(
                address=w3.to_checksum_address(CHAINLINK_MNT_USD_MANTLE),
                abi=agg_abi,
            )
            _, answer, _, _, _ = agg.functions.latestRoundData().call()
            # Chainlink USDY/USD typically has 8 decimals.
            price = Decimal(str(answer)) / Decimal("1e8")
            log.debug("USDY price from Chainlink: %s", price)
            return price
        except Exception as exc:  # noqa: BLE001
            log.warning("Chainlink USDY price failed (%s); trying REST", exc)

    # 2. Ondo REST API
    try:
        import requests

        resp = requests.get(
            "https://api.ondo.finance/api/v1/usdy/price", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        price_str = data.get("price") or data.get("data", {}).get("price")
        if price_str:
            price = Decimal(str(price_str))
            log.debug("USDY price from Ondo API: %s", price)
            return price
    except Exception as exc:  # noqa: BLE001
        log.warning("Ondo REST price failed (%s); using fallback", exc)

    log.warning("Using USDY price fallback: %s", _PRICE_FALLBACK)
    return _PRICE_FALLBACK


@traceable(name="usdy_preflight")
async def preflight(recipient: str, w3) -> bool:  # noqa: ANN001
    """Check whether `recipient` can receive USDY.

    Reads the on-chain blocklist contract to determine whether the address is
    blocked.  Raises USDYBlocklistError if it is; returns True if safe.

    This MUST be called before any USDY transfer — never swallow the error.
    """
    usdy_contract = w3.eth.contract(
        address=w3.to_checksum_address(USDY_MANTLE_MAINNET),
        abi=USDY_ABI,
    )
    # Get blocklist address from the USDY contract.
    try:
        blocklist_addr = usdy_contract.functions.blocklist().call()
    except Exception as exc:
        # If we cannot read the blocklist, fail safe.
        raise USDYBlocklistError(recipient, f"could not read blocklist: {exc}") from exc

    blocklist = w3.eth.contract(
        address=w3.to_checksum_address(blocklist_addr),
        abi=USDY_BLOCKLIST_ABI,
    )
    try:
        is_blocked = blocklist.functions.isBlocked(
            w3.to_checksum_address(recipient)
        ).call()
    except Exception as exc:
        raise USDYBlocklistError(recipient, f"blocklist call failed: {exc}") from exc

    if is_blocked:
        log.warning("USDY preflight: %s is blocked", recipient)
        raise USDYBlocklistError(recipient)

    log.debug("USDY preflight: %s is safe to receive", recipient)
    return True


@traceable(name="get_usdy_treasury_yield")
async def get_usdy_treasury_yield() -> Decimal:
    """Return the current USDY Treasury yield (APY).

    Tries the Ondo REST API; falls back to 5.2%.
    """
    try:
        import requests

        resp = requests.get(
            "https://api.ondo.finance/api/v1/usdy/yield", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        yield_str = data.get("apy") or data.get("yield") or data.get("data", {}).get("apy")
        if yield_str:
            apy = Decimal(str(yield_str))
            log.debug("USDY treasury yield from Ondo API: %s", apy)
            return apy
    except Exception as exc:  # noqa: BLE001
        log.warning("Ondo yield API failed (%s); using fallback %s", exc, _YIELD_FALLBACK)

    return _YIELD_FALLBACK

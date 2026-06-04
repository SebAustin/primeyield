"""Adapter tests — anvil fork tests land day 2-3.

The scaffold only verifies the modules import and expose their public API;
real fork tests (anvil --fork-url $MANTLE_SEPOLIA_RPC) are added day 2-3.
"""

from __future__ import annotations

import pytest

from agent.adapters import agni, mantle_lsp, merchant_moe, ondo


def test_adapter_modules_expose_public_api():
    assert hasattr(mantle_lsp, "meth_to_eth_rate")
    assert hasattr(ondo, "preflight")
    assert hasattr(ondo, "USDYBlocklistError")
    assert hasattr(agni, "quote_exact_input")
    assert hasattr(merchant_moe, "quote_exact_input")


def test_usdy_blocklist_error_is_exception():
    assert issubclass(ondo.USDYBlocklistError, Exception)


@pytest.mark.skip(reason="day 2-3: anvil fork integration tests")
def test_meth_to_eth_rate_against_fork():
    ...

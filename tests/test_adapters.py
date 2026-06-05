"""Adapter tests.

Structure:
  - Unit tests (always run): verify module structure, schemas, error types,
    pure-logic helpers.
  - Fork tests (skipped unless MANTLE_SEPOLIA_RPC env var is set): call
    contracts on an anvil --fork-url $MANTLE_SEPOLIA_RPC node.

To run fork tests:
  anvil --fork-url $MANTLE_SEPOLIA_RPC &
  MANTLE_ACTIVE_RPC=http://127.0.0.1:8545 pytest -k fork
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from agent.adapters import agni, mantle_lsp, merchant_moe, ondo
from agent.adapters.ondo import USDYBlocklistError
from agent.adapters.schemas import LBQuote, MethStakeQuote, PoolApr, QuoteResult, SwapTx

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_FORK_RPC = os.environ.get("MANTLE_SEPOLIA_RPC") or os.environ.get("MANTLE_MAINNET_RPC")
fork_test = pytest.mark.skipif(
    not _FORK_RPC,
    reason="Set MANTLE_SEPOLIA_RPC or MANTLE_MAINNET_RPC to run fork tests",
)


# ===========================================================================
# Module-structure tests (always run)
# ===========================================================================
class TestModuleStructure:
    def test_all_adapter_modules_importable(self):
        from agent.adapters import agni, mantle_lsp, merchant_moe, ondo  # noqa: F401

    def test_public_api_exists(self):
        assert callable(mantle_lsp.meth_to_eth_rate)
        assert callable(mantle_lsp.get_staking_apr)
        assert callable(mantle_lsp.build_stake_tx)
        assert callable(mantle_lsp.build_unstake_request_tx)

        assert callable(ondo.usdy_price_usd)
        assert callable(ondo.preflight)
        assert callable(ondo.get_usdy_treasury_yield)

        assert callable(agni.quote_exact_input)
        assert callable(agni.build_swap_tx)
        assert callable(agni.get_pool_apr)

        assert callable(merchant_moe.quote_exact_input)
        assert callable(merchant_moe.build_swap_tx)
        assert callable(merchant_moe.get_bin_apr)

    def test_usdy_blocklist_error_is_exception(self):
        assert issubclass(USDYBlocklistError, Exception)

    def test_usdy_blocklist_error_fields(self):
        err = USDYBlocklistError("0xDEAD", "test reason")
        assert err.recipient == "0xDEAD"
        assert err.reason == "test reason"
        assert "0xDEAD" in str(err)


# ===========================================================================
# Schema tests (always run)
# ===========================================================================
class TestSchemas:
    def test_quote_result_valid(self):
        q = QuoteResult(
            token_in="0x" + "a" * 40,
            token_out="0x" + "b" * 40,
            amount_in=1_000,
            amount_out=998,
            fee_tier=500,
            sqrt_price_x96_after=0,
            initialized_ticks_crossed=1,
            gas_estimate=120_000,
        )
        assert q.amount_out == 998

    def test_lb_quote_valid(self):
        q = LBQuote(
            route=["0x" + "a" * 40, "0x" + "b" * 40],
            pairs=["0x" + "c" * 40],
            bin_steps=[20],
            amounts=[1_000, 998],
            fees=[100],
        )
        assert q.amounts[-1] == 998

    def test_swap_tx_valid(self):
        tx = SwapTx(to="0x" + "a" * 40, data="0xdeadbeef", value=0, gas_estimate=100_000)
        assert tx.value == 0

    def test_pool_apr_valid(self):
        apr = PoolApr(
            pool="0x" + "a" * 40,
            token_a="0x" + "b" * 40,
            token_b="0x" + "c" * 40,
            apr=Decimal("0.072"),
        )
        assert apr.fee_tier is None  # optional for Merchant Moe pools


# ===========================================================================
# Unit tests — mocked I/O (always run)
# ===========================================================================
class TestMantleLspUnit:
    @pytest.mark.asyncio
    async def test_get_staking_apr_uses_fallback_on_error(self):
        with patch("requests.post", side_effect=ConnectionError("no network")):
            apr = await mantle_lsp.get_staking_apr()
        assert apr == Decimal("0.038")

    @pytest.mark.asyncio
    async def test_get_staking_apr_parses_subgraph_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"protocolMetrics": {"apr": "0.041"}}}
        with patch("requests.post", return_value=mock_resp):
            apr = await mantle_lsp.get_staking_apr()
        assert apr == Decimal("0.041")


class TestOndoUnit:
    @pytest.mark.asyncio
    async def test_preflight_raises_on_blocked(self):
        """preflight() must raise USDYBlocklistError for a blocked address."""
        mock_w3 = MagicMock()
        mock_usdy = MagicMock()
        mock_blocklist_contract = MagicMock()

        # usdy.functions.blocklist().call() → some address
        mock_usdy.functions.blocklist.return_value.call.return_value = "0x" + "d" * 40
        mock_blocklist_contract.functions.isBlocked.return_value.call.return_value = True

        mock_w3.eth.contract.side_effect = [mock_usdy, mock_blocklist_contract]
        mock_w3.to_checksum_address.side_effect = lambda x: x

        blocked_addr = "0x" + "e" * 40
        with pytest.raises(USDYBlocklistError) as exc_info:
            await ondo.preflight(blocked_addr, mock_w3)
        assert exc_info.value.recipient == blocked_addr

    @pytest.mark.asyncio
    async def test_preflight_returns_true_when_safe(self):
        mock_w3 = MagicMock()
        mock_usdy = MagicMock()
        mock_blocklist_contract = MagicMock()

        mock_usdy.functions.blocklist.return_value.call.return_value = "0x" + "d" * 40
        mock_blocklist_contract.functions.isBlocked.return_value.call.return_value = False

        mock_w3.eth.contract.side_effect = [mock_usdy, mock_blocklist_contract]
        mock_w3.to_checksum_address.side_effect = lambda x: x

        result = await ondo.preflight("0x" + "f" * 40, mock_w3)
        assert result is True

    @pytest.mark.asyncio
    async def test_usdy_price_fallback_on_all_failure(self):
        mock_w3 = MagicMock()
        with patch("requests.get", side_effect=ConnectionError("no network")):
            price = await ondo.usdy_price_usd(mock_w3)
        assert price == Decimal("1.052")

    @pytest.mark.asyncio
    async def test_get_usdy_treasury_yield_fallback(self):
        with patch("requests.get", side_effect=ConnectionError("no network")):
            yield_ = await ondo.get_usdy_treasury_yield()
        assert yield_ == Decimal("0.052")


class TestAgniUnit:
    @pytest.mark.asyncio
    async def test_get_pool_apr_returns_zero_placeholder(self):
        mock_w3 = MagicMock()
        apr = await agni.get_pool_apr("0x" + "a" * 40, "0x" + "b" * 40, 500, mock_w3)
        assert apr == Decimal("0")

    @pytest.mark.asyncio
    async def test_quote_exact_input_builds_correct_params(self):
        """quote_exact_input should call quoter with the right struct."""
        mock_w3 = MagicMock()
        mock_quoter = MagicMock()
        mock_quoter.functions.quoteExactInputSingle.return_value.call.return_value = (
            950,   # amountOut
            0,     # sqrtPriceX96After
            1,     # initializedTicksCrossed
            80_000,  # gasEstimate
        )
        mock_w3.eth.contract.return_value = mock_quoter
        mock_w3.to_checksum_address.side_effect = lambda x: x

        result = await agni.quote_exact_input(
            "0x" + "a" * 40, "0x" + "b" * 40, 1_000, 500, mock_w3
        )
        assert result.amount_out == 950
        assert result.fee_tier == 500


class TestMerchantMoeUnit:
    @pytest.mark.asyncio
    async def test_get_bin_apr_returns_zero_placeholder(self):
        mock_w3 = MagicMock()
        apr = await merchant_moe.get_bin_apr("0x" + "a" * 40, "0x" + "b" * 40, mock_w3)
        assert apr == Decimal("0")

    @pytest.mark.asyncio
    async def test_quote_exact_input_returns_lb_quote(self):
        mock_w3 = MagicMock()
        mock_quoter = MagicMock()
        # Simulate LBQuoter.findBestPathFromAmountIn return tuple
        mock_quoter.functions.findBestPathFromAmountIn.return_value.call.return_value = (
            ["0xaaa", "0xbbb"],  # route
            ["0xccc"],            # pairs
            [20],                 # binSteps
            [2],                  # versions
            [1_000, 995],         # amounts
            [1_000, 996],         # virtualAmounts
            [5],                  # fees
        )
        mock_w3.eth.contract.return_value = mock_quoter
        mock_w3.to_checksum_address.side_effect = lambda x: x

        result = await merchant_moe.quote_exact_input("0xaaa", "0xbbb", 1_000, mock_w3)
        assert result.amounts[-1] == 995
        assert result.bin_steps == [20]


# ===========================================================================
# Fork tests (skipped without RPC)
# ===========================================================================
@fork_test
class TestMantleLspFork:
    @pytest.mark.asyncio
    async def test_meth_to_eth_rate_on_fork(self):
        """mETH→ETH rate should be >= 1.0 (mETH accrues ETH value over time)."""
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        rpc = _FORK_RPC
        w3 = Web3(Web3.HTTPProvider(rpc))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        rate = await mantle_lsp.meth_to_eth_rate(w3)
        assert rate >= Decimal("1.0"), f"mETH rate should be >= 1, got {rate}"


@fork_test
class TestOndoFork:
    @pytest.mark.asyncio
    async def test_preflight_zero_address_not_blocked(self):
        """The zero address is a degenerate case — the contract should either
        return False or revert; we just ensure no unhandled exception."""
        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        rpc = _FORK_RPC
        w3 = Web3(Web3.HTTPProvider(rpc))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        zero = "0x" + "0" * 40
        try:
            result = await ondo.preflight(zero, w3)
            # If it returns without raising, zero is not blocklisted (unusual but valid).
            assert result is True
        except USDYBlocklistError:
            pass  # Expected if zero address is pre-blocked.
        except Exception as exc:
            pytest.fail(f"Unexpected exception from preflight: {exc}")

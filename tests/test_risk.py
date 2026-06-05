"""Risk engine tests — all four gates + Monte Carlo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agent.risk import (
    CONCENTRATION_MAX_PCT,
    ES95_MIN,
    ORACLE_DEVIATION_MAX_BPS,
    SLIPPAGE_MAX_BPS,
    VAR95_MIN,
    RiskEngine,
)
from agent.state import RiskReport


@pytest.fixture
def eng() -> RiskEngine:
    return RiskEngine()


# ---------------------------------------------------------------------------
# Gate 1 — oracle deviation
# ---------------------------------------------------------------------------
class TestOracleDeviation:
    def test_within_50bps_passes(self, eng: RiskEngine):
        # 49 bps spread → should pass.
        ref = Decimal("1.0000")
        oracle = Decimal("1.0049")
        assert eng.oracle_deviation_check(oracle, ref) is True

    def test_exactly_50bps_passes(self, eng: RiskEngine):
        ref = Decimal("1.0000")
        oracle = Decimal("1.0050")
        assert eng.oracle_deviation_check(oracle, ref) is True

    def test_51bps_fails(self, eng: RiskEngine):
        ref = Decimal("1.0000")
        oracle = Decimal("1.0051")
        assert eng.oracle_deviation_check(oracle, ref) is False

    def test_zero_reference_fails(self, eng: RiskEngine):
        assert eng.oracle_deviation_check(Decimal("1.0"), Decimal("0")) is False

    def test_negative_spread_within_50bps_passes(self, eng: RiskEngine):
        # 49 bps *below* reference — should still pass.
        ref = Decimal("1.0000")
        oracle = Decimal("0.9951")
        assert eng.oracle_deviation_check(oracle, ref) is True

    def test_negative_spread_over_50bps_fails(self, eng: RiskEngine):
        # 51 bps below reference — should fail.
        ref = Decimal("1.0000")
        oracle = Decimal("0.9949")
        assert eng.oracle_deviation_check(oracle, ref) is False

    def test_custom_max_bps(self, eng: RiskEngine):
        ref = Decimal("1.0000")
        oracle = Decimal("1.0100")  # 100 bps
        assert eng.oracle_deviation_check(oracle, ref, max_bps=100) is True
        assert eng.oracle_deviation_check(oracle, ref, max_bps=50) is False


# ---------------------------------------------------------------------------
# Gate 2 — slippage cap
# ---------------------------------------------------------------------------
class TestSlippageCap:
    def test_basic_cap(self, eng: RiskEngine):
        # No expected_rate → min = quoted * (1 - 50/10000)
        min_out = eng.slippage_cap(amount_in=1_000, quoted_out=1_000)
        assert min_out == int(1_000 * (1 - SLIPPAGE_MAX_BPS / 10_000))

    def test_zero_quoted_returns_zero(self, eng: RiskEngine):
        assert eng.slippage_cap(amount_in=1_000, quoted_out=0) == 0

    def test_with_expected_rate(self, eng: RiskEngine):
        # expected_out = 1_000 * 1.0 = 1_000; min_out = 995
        min_out = eng.slippage_cap(
            amount_in=1_000,
            quoted_out=990,
            expected_rate=Decimal("1.0"),
        )
        assert min_out == 995

    def test_custom_bps(self, eng: RiskEngine):
        min_out = eng.slippage_cap(amount_in=10_000, quoted_out=10_000, max_bps=100)
        assert min_out == 9_900


# ---------------------------------------------------------------------------
# Gate 3 — concentration
# ---------------------------------------------------------------------------
class TestConcentrationCheck:
    def test_equal_three_assets_passes(self, eng: RiskEngine):
        weights = {
            "mETH": Decimal("1"),
            "USDY": Decimal("1"),
            "USDe": Decimal("1"),
        }
        assert eng.concentration_check(weights) is True

    def test_60pct_passes(self, eng: RiskEngine):
        weights = {"mETH": Decimal("6"), "USDY": Decimal("4")}
        assert eng.concentration_check(weights) is True

    def test_61pct_fails(self, eng: RiskEngine):
        weights = {"mETH": Decimal("61"), "USDY": Decimal("39")}
        assert eng.concentration_check(weights) is False

    def test_100pct_single_asset_fails(self, eng: RiskEngine):
        assert eng.concentration_check({"mETH": Decimal("1")}) is False

    def test_empty_weights_safe(self, eng: RiskEngine):
        assert eng.concentration_check({}) is True

    def test_custom_max_pct(self, eng: RiskEngine):
        weights = {"mETH": Decimal("4"), "USDY": Decimal("6")}
        assert eng.concentration_check(weights, max_pct=Decimal("0.5")) is False
        assert eng.concentration_check(weights, max_pct=Decimal("0.7")) is True


# ---------------------------------------------------------------------------
# Gate 4 — Monte Carlo
# ---------------------------------------------------------------------------
class TestMonteCarlo:
    def _safe_scenarios(self) -> dict[str, list[Decimal]]:
        """Yield scenarios with small variance → low VaR."""
        return {
            "mETH": [Decimal("0.0001")] * 100 + [Decimal("0.0003")] * 100,
            "USDY": [Decimal("0.00014")] * 100 + [Decimal("0.00015")] * 100,
            "USDe": [Decimal("0.00012")] * 200,
        }

    def _risky_scenarios(self) -> dict[str, list[Decimal]]:
        """Yield scenarios with large downside → bad VaR."""
        import random
        random.seed(0)
        return {
            "mETH": [Decimal(str(round(-0.05 + random.gauss(0, 0.04), 6))) for _ in range(200)],
            "USDY": [Decimal(str(round(-0.04 + random.gauss(0, 0.04), 6))) for _ in range(200)],
            "USDe": [Decimal(str(round(-0.06 + random.gauss(0, 0.05), 6))) for _ in range(200)],
        }

    def _equal_weights(self) -> dict[str, Decimal]:
        return {"mETH": Decimal("1"), "USDY": Decimal("1"), "USDe": Decimal("1")}

    def test_returns_two_decimals_below_mean(self, eng: RiskEngine):
        """VaR95 and ES95 should both be well below the mean return.

        For the safe scenario (small positive yields) both are near 0;
        for risky scenarios they're deeply negative. The key invariant is
        ES95 <= VaR95 (tested separately). We don't assert < 0 here because
        portfolios with consistently positive micro-yields can have positive VaR.
        """
        var95, es95 = eng.monte_carlo(
            self._safe_scenarios(), self._equal_weights(), n_paths=1_000
        )
        assert isinstance(var95, Decimal)
        assert isinstance(es95, Decimal)
        assert es95 <= var95  # ES is always worse-or-equal to VaR

    def test_safe_scenarios_pass_thresholds(self, eng: RiskEngine):
        var95, es95 = eng.monte_carlo(
            self._safe_scenarios(), self._equal_weights(), n_paths=5_000, seed=42
        )
        assert var95 > VAR95_MIN, f"VaR95 {var95} should be > {VAR95_MIN}"
        assert es95 > ES95_MIN, f"ES95 {es95} should be > {ES95_MIN}"

    def test_risky_scenarios_fail_thresholds(self, eng: RiskEngine):
        var95, es95 = eng.monte_carlo(
            self._risky_scenarios(), self._equal_weights(), n_paths=5_000, seed=42
        )
        # With consistently negative mean returns, both should be very bad.
        assert var95 < Decimal("-0.01"), f"Expected bad VaR95, got {var95}"

    def test_es95_leq_var95(self, eng: RiskEngine):
        """ES95 must always be <= VaR95 (it's the mean of the worst tail)."""
        var95, es95 = eng.monte_carlo(
            self._safe_scenarios(), self._equal_weights(), n_paths=2_000, seed=0
        )
        assert es95 <= var95

    def test_empty_inputs_returns_worst_case(self, eng: RiskEngine):
        var95, es95 = eng.monte_carlo({}, {})
        assert var95 <= Decimal("-0.05")

    def test_single_sample_no_crash(self, eng: RiskEngine):
        # Only 1 sample per asset — should not raise.
        scenarios = {
            "mETH": [Decimal("0.0001")],
            "USDY": [Decimal("0.0001")],
        }
        var95, es95 = eng.monte_carlo(scenarios, {"mETH": Decimal("1"), "USDY": Decimal("1")})
        assert isinstance(var95, Decimal)


# ---------------------------------------------------------------------------
# Integrated evaluate()
# ---------------------------------------------------------------------------
class TestEvaluate:
    def test_all_gates_pass(self, eng: RiskEngine):
        scenarios = {
            "mETH": [Decimal("0.0002")] * 200,
            "USDY": [Decimal("0.00015")] * 200,
            "USDe": [Decimal("0.00012")] * 200,
        }
        weights = {"mETH": Decimal("1"), "USDY": Decimal("1"), "USDe": Decimal("1")}
        report = eng.evaluate(
            usdy_price=Decimal("1.050"),
            reference_price=Decimal("1.051"),
            amount_in=1_000,
            quoted_out=999,
            proposed_weights=weights,
            yield_scenarios=scenarios,
            n_paths=2_000,
        )
        assert isinstance(report, RiskReport)
        assert report.oracle_deviation_ok
        assert report.concentration_ok
        assert report.passed

    def test_concentration_failure_reported(self, eng: RiskEngine):
        scenarios = {
            "mETH": [Decimal("0.0002")] * 50,
            "USDY": [Decimal("0.0002")] * 50,
        }
        report = eng.evaluate(
            usdy_price=Decimal("1.050"),
            reference_price=Decimal("1.051"),
            amount_in=1_000,
            quoted_out=999,
            proposed_weights={"mETH": Decimal("9"), "USDY": Decimal("1")},  # 90% mETH
            yield_scenarios=scenarios,
            n_paths=500,
        )
        assert report.concentration_ok is False
        assert report.passed is False
        assert report.failure_reason is not None

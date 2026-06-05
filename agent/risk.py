"""PrimeYield risk engine.

All four gates MUST pass before propose_plan may emit a plan. The
score_risks graph node calls each gate in sequence and populates
AgentState.risk_report; a failing gate routes to END.

Gates:
  1. oracle_deviation_check — USDY price spread vs. reference <= 50 bps
  2. slippage_cap           — min_amount_out enforcing max_bps hard cap
  3. concentration_check    — no single asset > 60% of TVL
  4. monte_carlo            — VaR95 > -3% AND ES95 > -5%
"""

from __future__ import annotations

import logging
import warnings
from decimal import Decimal

import numpy as np

log = logging.getLogger(__name__)

# Gate thresholds (all tunable via kwargs for testing).
ORACLE_DEVIATION_MAX_BPS = 50     # 0.50%
SLIPPAGE_MAX_BPS = 50             # 0.50%
CONCENTRATION_MAX_PCT = Decimal("0.60")   # 60%
VAR95_MIN = Decimal("-0.03")      # VaR95 must be > -3%
ES95_MIN = Decimal("-0.05")       # ES95  must be > -5%


class RiskEngine:
    """Stateless risk-gate evaluator.

    All methods are synchronous and deterministic (no I/O).
    They are called by the score_risks graph node.
    """

    # -----------------------------------------------------------------------
    # Gate 1 — oracle deviation
    # -----------------------------------------------------------------------
    def oracle_deviation_check(
        self,
        usdy_oracle_price: Decimal,
        chainlink_usd_treasury: Decimal,
        max_bps: int = ORACLE_DEVIATION_MAX_BPS,
    ) -> bool:
        """Return True (safe) if the spread between the two price sources is
        <= max_bps basis points; log a WARNING and return False otherwise.

        When the Chainlink MNT/USD aggregator is unavailable on Mantle,
        chainlink_usd_treasury is expected to be the most recent cached price.
        """
        if chainlink_usd_treasury <= 0:
            log.warning("oracle_deviation_check: reference price <= 0, treating as failed")
            return False

        spread_bps = abs(usdy_oracle_price - chainlink_usd_treasury) / chainlink_usd_treasury * 10_000
        safe = spread_bps <= max_bps
        if not safe:
            log.warning(
                "oracle_deviation_check FAILED: spread %.1f bps > %d bps limit "
                "(usdy=%s, ref=%s)",
                float(spread_bps), max_bps, usdy_oracle_price, chainlink_usd_treasury,
            )
        else:
            log.debug(
                "oracle_deviation_check OK: spread %.1f bps", float(spread_bps)
            )
        return safe

    # -----------------------------------------------------------------------
    # Gate 2 — slippage cap
    # -----------------------------------------------------------------------
    def slippage_cap(
        self,
        amount_in: int,
        quoted_out: int,
        max_bps: int = SLIPPAGE_MAX_BPS,
        expected_rate: Decimal | None = None,
    ) -> int:
        """Return min_amount_out enforcing a max_bps slippage cap.

        If expected_rate is given (e.g. the oracle price) it is used as the
        reference; otherwise the quoted_out itself is the reference and
        min_amount_out = quoted_out * (1 - max_bps/10000).

        The returned value is what should be passed as amountOutMinimum to the
        swap router so the tx reverts on-chain if slippage is exceeded.
        """
        if quoted_out <= 0:
            log.warning("slippage_cap: quoted_out <= 0, returning 0")
            return 0

        if expected_rate is not None and expected_rate > 0:
            expected_out = int(Decimal(str(amount_in)) * expected_rate)
            slippage_bps = (Decimal(str(expected_out)) - Decimal(str(quoted_out))) / Decimal(
                str(expected_out)
            ) * 10_000
            if slippage_bps > max_bps:
                log.warning(
                    "slippage_cap: observed slippage %.1f bps > %d bps limit",
                    float(slippage_bps), max_bps,
                )
            min_out = int(Decimal(str(expected_out)) * (1 - Decimal(str(max_bps)) / 10_000))
        else:
            min_out = int(Decimal(str(quoted_out)) * (1 - Decimal(str(max_bps)) / 10_000))

        return min_out

    # -----------------------------------------------------------------------
    # Gate 3 — concentration check
    # -----------------------------------------------------------------------
    def concentration_check(
        self,
        proposed_weights: dict[str, Decimal],
        max_pct: Decimal = CONCENTRATION_MAX_PCT,
    ) -> bool:
        """Return True if no single asset exceeds max_pct of TVL.

        proposed_weights: {asset_name: weight} where weights sum to ~1.0.
        """
        if not proposed_weights:
            log.warning("concentration_check: empty weights, treating as safe")
            return True

        total = sum(proposed_weights.values())
        if total <= 0:
            log.warning("concentration_check: weights sum to 0, treating as failed")
            return False

        for asset, weight in proposed_weights.items():
            normalized = weight / total
            if normalized > max_pct:
                log.warning(
                    "concentration_check FAILED: %s at %.1f%% > %.0f%% limit",
                    asset, float(normalized * 100), float(max_pct * 100),
                )
                return False

        log.debug(
            "concentration_check OK: max single-asset %s%%",
            float(max(w / total for w in proposed_weights.values()) * 100),
        )
        return True

    # -----------------------------------------------------------------------
    # Gate 4 — Monte Carlo VaR / ES
    # -----------------------------------------------------------------------
    def monte_carlo(
        self,
        yield_scenarios: dict[str, list[Decimal]],
        weights: dict[str, Decimal],
        n_paths: int = 10_000,
        seed: int | None = 42,
        var_min: Decimal = VAR95_MIN,
        es_min: Decimal = ES95_MIN,
    ) -> tuple[Decimal, Decimal]:
        """Simulate `n_paths` portfolio return paths and return (VaR95, ES95).

        Args:
            yield_scenarios: historical or forecasted yield samples per asset
                             (e.g. 252 daily returns).  At least 2 samples per
                             asset required for meaningful covariance.
            weights:         portfolio weights (will be normalized to sum=1).
            n_paths:         Monte Carlo paths to simulate.
            seed:            NumPy RNG seed for reproducibility (pass None for
                             non-deterministic).

        Returns:
            (VaR95, ES95) — both are negative Decimals, e.g. (-0.02, -0.04).

        The plan is SAFE if VaR95 > VAR95_MIN (-3%) AND ES95 > ES95_MIN (-5%).
        Logs a WARNING if either threshold is breached.
        """
        if not yield_scenarios or not weights:
            log.warning("monte_carlo: empty inputs, returning worst-case")
            return (Decimal("-0.10"), Decimal("-0.15"))

        assets = [a for a in weights if a in yield_scenarios]
        if not assets:
            log.warning("monte_carlo: no overlap between weights and scenarios")
            return (Decimal("-0.10"), Decimal("-0.15"))

        # Normalize weights to sum to 1.
        total_w = sum(weights[a] for a in assets)
        w = np.array([float(weights[a]) / float(total_w) for a in assets])

        # Build returns matrix: shape (n_samples, n_assets).
        min_samples = min(len(yield_scenarios[a]) for a in assets)
        if min_samples < 2:
            log.warning("monte_carlo: not enough samples for covariance; using diagonal fallback")
            R = np.array([[float(s) for a, s in zip(assets, [yield_scenarios[a][0] for a in assets])] for _ in range(2)])
        else:
            R = np.array([[float(yield_scenarios[a][i]) for a in assets] for i in range(min_samples)])

        # Compute mean returns and covariance.
        mu = R.mean(axis=0)          # (n_assets,)
        cov = np.cov(R, rowvar=False) if R.shape[0] > 1 else np.diag(np.abs(mu) * 0.1)

        if cov.ndim == 0:
            # Single asset: cov is a scalar.
            cov = np.array([[float(cov)]])

        # Cholesky decomposition for correlated sampling.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                L = np.linalg.cholesky(cov + np.eye(len(assets)) * 1e-10)
            except np.linalg.LinAlgError:
                L = np.diag(np.sqrt(np.abs(np.diag(cov)) + 1e-10))

        rng = np.random.default_rng(seed)
        z = rng.standard_normal((n_paths, len(assets)))        # iid standard normal
        sim_returns = z @ L.T + mu                              # (n_paths, n_assets)
        portfolio_returns = sim_returns @ w                     # (n_paths,)

        # VaR95: the 5th percentile return (loss not exceeded with 95% probability).
        var95_float = float(np.percentile(portfolio_returns, 5))
        # ES95 (CVaR): mean of returns below VaR95.
        tail = portfolio_returns[portfolio_returns <= var95_float]
        es95_float = float(tail.mean()) if len(tail) > 0 else var95_float

        var95 = Decimal(str(round(var95_float, 6)))
        es95 = Decimal(str(round(es95_float, 6)))

        if var95 <= var_min:
            log.warning(
                "monte_carlo FAILED: VaR95 %s <= threshold %s", var95, var_min
            )
        if es95 <= es_min:
            log.warning(
                "monte_carlo FAILED: ES95 %s <= threshold %s", es95, es_min
            )

        log.debug("monte_carlo: VaR95=%s ES95=%s (n=%d)", var95, es95, n_paths)
        return (var95, es95)

    # -----------------------------------------------------------------------
    # Convenience: run all four gates and return a RiskReport
    # -----------------------------------------------------------------------
    def evaluate(
        self,
        usdy_price: Decimal,
        reference_price: Decimal,
        amount_in: int,
        quoted_out: int,
        proposed_weights: dict[str, Decimal],
        yield_scenarios: dict[str, list[Decimal]],
        n_paths: int = 10_000,
    ):
        """Run all four gates and return a populated RiskReport.

        Import is local to avoid circular-import with agent.state at module load.
        """
        from agent.state import RiskReport

        oracle_ok = self.oracle_deviation_check(usdy_price, reference_price)
        slippage_ok = quoted_out > 0 and (
            self.slippage_cap(amount_in, quoted_out) > 0
        )
        concentration_ok = self.concentration_check(proposed_weights)
        var95, es95 = self.monte_carlo(yield_scenarios, proposed_weights, n_paths)
        mc_ok = var95 > VAR95_MIN and es95 > ES95_MIN

        passed = oracle_ok and slippage_ok and concentration_ok and mc_ok

        failures = []
        if not oracle_ok:
            failures.append("oracle_deviation > 50bps")
        if not slippage_ok:
            failures.append("slippage_cap failed (quoted_out <= 0)")
        if not concentration_ok:
            failures.append("concentration > 60%")
        if not mc_ok:
            failures.append(f"Monte Carlo: VaR95={var95} ES95={es95}")

        return RiskReport(
            oracle_deviation_ok=oracle_ok,
            concentration_ok=concentration_ok,
            slippage_ok=slippage_ok,
            monte_carlo_ok=mc_ok,
            var_95=var95,
            es_95=es95,
            passed=passed,
            failure_reason="; ".join(failures) if failures else None,
        )

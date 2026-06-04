"""Risk engine — implemented day 2-3.

All four gates must pass before propose_plan may emit a plan:
  1. oracle_deviation_check  (<= 50 bps spread)
  2. slippage_cap            (<= 50 bps enforced as min_amount_out)
  3. concentration_check     (no asset > 60% of TVL)
  4. monte_carlo             (VaR95 > -3% and ES95 > -5%)
"""

from __future__ import annotations

from decimal import Decimal


class RiskEngine:
    def oracle_deviation_check(
        self, usdy_oracle_price: Decimal, chainlink_usd_treasury: Decimal
    ) -> bool:
        raise NotImplementedError("day 2-3: <=50bps spread")

    def slippage_cap(self, amount_in: int, quoted_out: int, max_bps: int = 50) -> int:
        raise NotImplementedError("day 2-3: min_amount_out")

    def concentration_check(self, proposed_weights: dict[str, Decimal]) -> bool:
        raise NotImplementedError("day 2-3: no asset > 60%")

    def monte_carlo(
        self,
        yield_scenarios: dict[str, list[Decimal]],
        weights: dict[str, Decimal],
        n_paths: int = 10_000,
    ) -> tuple[Decimal, Decimal]:
        raise NotImplementedError("day 2-3: (VaR95, ES95)")

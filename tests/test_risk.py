"""Risk engine tests — full assertions land day 2-3.

The scaffold only verifies the interface exists; real gate logic is added
day 2-3 against anvil fork data.
"""

from __future__ import annotations

import pytest

from agent.risk import RiskEngine


def test_risk_engine_interface_exists():
    eng = RiskEngine()
    for method in ("oracle_deviation_check", "slippage_cap", "concentration_check", "monte_carlo"):
        assert callable(getattr(eng, method))


@pytest.mark.skip(reason="day 2-3: implement gate logic")
def test_concentration_check_rejects_over_60pct():
    ...

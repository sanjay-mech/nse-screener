"""
Unit tests for Price Cross-Validation (NSE vs Yahoo LTP).
Guards against bad ticks, corrupted exchange data, and test prints.
"""

from datetime import datetime
from signals.models import PriceTick
from signals.validator import signal_validator


def test_cross_validation_matching_ticks():
    """NSE and Yahoo prices within 0.2% -> Valid."""
    nse_tick = PriceTick(
        symbol="TATASTEEL",
        ltp=150.0,
        day_high=152.0,
        day_low=148.0,
        day_open=149.0,
        prev_close=148.5,
        p_change=1.01,
        volume=5000000,
        turnover_cr=75.0,
        source="NSE",
        timestamp=datetime.utcnow()
    )

    yahoo_tick = PriceTick(
        symbol="TATASTEEL",
        ltp=150.20,  # 0.13% divergence
        day_high=152.0,
        day_low=148.0,
        day_open=149.0,
        prev_close=148.5,
        p_change=1.14,
        volume=4900000,
        turnover_cr=74.5,
        source="YAHOO",
        timestamp=datetime.utcnow()
    )

    is_valid, div_pct, msg = signal_validator.cross_validate_quotes(nse_tick, yahoo_tick)
    assert is_valid is True
    assert div_pct < 1.0
    assert msg is None


def test_cross_validation_rejects_divergent_ticks():
    """NSE and Yahoo prices diverge by > 1.0% -> Rejected."""
    nse_tick = PriceTick(
        symbol="SBIN",
        ltp=800.0,
        day_high=805.0,
        day_low=790.0,
        day_open=792.0,
        prev_close=790.0,
        p_change=1.26,
        volume=3000000,
        turnover_cr=240.0,
        source="NSE",
        timestamp=datetime.utcnow()
    )

    yahoo_tick = PriceTick(
        symbol="SBIN",
        ltp=785.0,  # 1.89% divergence (> 1.0%)
        day_high=795.0,
        day_low=780.0,
        day_open=782.0,
        prev_close=790.0,
        p_change=-0.63,
        volume=3000000,
        turnover_cr=235.0,
        source="YAHOO",
        timestamp=datetime.utcnow()
    )

    is_valid, div_pct, msg = signal_validator.cross_validate_quotes(nse_tick, yahoo_tick)
    assert is_valid is False
    assert div_pct > 1.0
    assert "Cross-validation FAILED" in msg

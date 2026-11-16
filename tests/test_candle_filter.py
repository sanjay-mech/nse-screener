"""
Tests for 5-minute candle breakout hit confirmation.
Verifies that alerts ONLY fire if the breakout or breakdown hit in the previous or current 5m candle.
"""
from datetime import date
from signals.breakout_detector import breakout_detector
from signals.models import PriceTick, PrecomputedLevels, TriggerType


def test_5m_candle_fresh_breakout_fires():
    levels = PrecomputedLevels(
        symbol="ABC",
        calculated_date=date.today(),
        ath_high=1000.0,
        ath_date="2025-01-01",
        high_52w=950.0,
        high_52w_date="2025-01-01",
        donchian_50_high=900.0,
        donchian_50_date="2025-01-01",
        avg_vol_20d=500000.0,
        atr_20d=20.0,
        last_close=990.0,
    )

    # Fresh breakout: prior close was 995 (<1000), current 5m candle high reached 1005 (>1000)
    tick_fresh = PriceTick(
        symbol="ABC",
        ltp=1004.0,
        day_high=1005.0,
        day_low=990.0,
        day_open=992.0,
        prev_close=990.0,
        p_change=1.41,
        volume=200000,
        turnover_cr=20.0,
        candle_5m_curr_high=1005.0,
        candle_5m_curr_low=998.0,
        candle_5m_prev_high=997.0,
        candle_5m_prev_low=993.0,
        candle_5m_prior_close=995.0  # Was below 1000 prior to recent 2 candles!
    )

    sigs = breakout_detector.evaluate_breakouts(tick_fresh, levels)
    triggers = [s.trigger for s in sigs]
    assert TriggerType.ATH in triggers


def test_5m_candle_old_breakout_suppressed():
    levels = PrecomputedLevels(
        symbol="ABC",
        calculated_date=date.today(),
        ath_high=1000.0,
        ath_date="2025-01-01",
        high_52w=950.0,
        high_52w_date="2025-01-01",
        donchian_50_high=900.0,
        donchian_50_date="2025-01-01",
        avg_vol_20d=500000.0,
        atr_20d=20.0,
        last_close=990.0,
    )

    # Old breakout from 2 hours ago:
    # Prior close was ALREADY 1010 (>1000). Current candle is 1012.
    # Did NOT hit in the last 5-10 minutes!
    tick_old = PriceTick(
        symbol="ABC",
        ltp=1012.0,
        day_high=1020.0,
        day_low=990.0,
        day_open=992.0,
        prev_close=990.0,
        p_change=2.22,
        volume=600000,
        turnover_cr=60.0,
        candle_5m_curr_high=1014.0,
        candle_5m_curr_low=1010.0,
        candle_5m_prev_high=1015.0,
        candle_5m_prev_low=1009.0,
        candle_5m_prior_close=1011.0  # Already broke out long ago!
    )

    sigs = breakout_detector.evaluate_breakouts(tick_old, levels)
    triggers = [s.trigger for s in sigs]
    # ATH must NOT trigger because it was not hit in recent 5m!
    assert TriggerType.ATH not in triggers

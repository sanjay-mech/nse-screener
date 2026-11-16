"""
Unit tests for Institutional Time-Normalized RVOL.
"""
from datetime import datetime, time
import pytz
import pytest
from signals.rvol import get_expected_day_fraction, calculate_time_normalized_rvol
from signals.breakout_detector import breakout_detector
from signals.models import PriceTick, PrecomputedLevels, TriggerType
from config.settings import settings

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


def test_expected_day_fraction_market_times():
    # 09:15 IST (Market open)
    dt_open = datetime(2026, 11, 16, 9, 15, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_open) == pytest.approx(0.02, abs=0.005)

    # 09:30 IST (15 mins in)
    dt_930 = datetime(2026, 11, 16, 9, 30, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_930) == pytest.approx(0.08, abs=0.005)

    # 10:00 IST (45 mins in)
    dt_1000 = datetime(2026, 11, 16, 10, 0, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_1000) == pytest.approx(0.20, abs=0.005)

    # 11:00 IST (105 mins in)
    dt_1100 = datetime(2026, 11, 16, 11, 0, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_1100) == pytest.approx(0.35, abs=0.005)

    # 13:00 IST (225 mins in)
    dt_1300 = datetime(2026, 11, 16, 13, 0, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_1300) == pytest.approx(0.57, abs=0.005)

    # 15:30 IST (Market close)
    dt_close = datetime(2026, 11, 16, 15, 30, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_close) == 1.0

    # 16:30 IST (Post market)
    dt_post = datetime(2026, 11, 16, 16, 30, tzinfo=KOLKATA_TZ)
    assert get_expected_day_fraction(dt_post) == 1.0


def test_expected_day_fraction_daily_bar():
    # Midnight daily historical bar (00:00:00) should be treated as full day (1.0)
    dt_daily = datetime(2026, 11, 16, 0, 0)
    assert get_expected_day_fraction(dt_daily) == 1.0


def test_rvol_calculations():
    avg_vol_20d = 1_000_000.0

    # At 10:00 AM, expected volume is ~200,000 (20%)
    # If 500,000 shares traded, RVOL = 500,000 / 200,000 = 2.50x
    dt_1000 = datetime(2026, 11, 16, 10, 0, tzinfo=KOLKATA_TZ)
    rvol = calculate_time_normalized_rvol(
        current_volume=500_000,
        avg_vol_20d=avg_vol_20d,
        timestamp=dt_1000
    )
    assert rvol == pytest.approx(2.50, abs=0.05)

    # At 09:30 AM, expected volume is ~80,000 (8%)
    # If 80,000 shares traded, RVOL = 1.0x
    dt_930 = datetime(2026, 11, 16, 9, 30, tzinfo=KOLKATA_TZ)
    rvol_normal = calculate_time_normalized_rvol(
        current_volume=80_000,
        avg_vol_20d=avg_vol_20d,
        timestamp=dt_930
    )
    assert rvol_normal == pytest.approx(1.0, abs=0.05)

    # Zero volume
    assert calculate_time_normalized_rvol(0, avg_vol_20d, dt_1000) == 0.0

    # Zero avg volume fallback
    assert calculate_time_normalized_rvol(500_000, 0, dt_1000) == 1.0


def test_breakout_detector_with_time_normalized_rvol():
    # Simulate a morning breakout at 09:30 AM with explosive volume
    dt_930 = datetime(2026, 11, 16, 9, 30, tzinfo=KOLKATA_TZ)
    levels = PrecomputedLevels(
        symbol="TATASTEEL",
        calculated_date=dt_930.date(),
        ath_high=160.0,
        ath_date="2026-01-01",
        high_52w=150.0,
        high_52w_date="2026-01-01",
        donchian_50_high=148.0,
        donchian_50_date="2026-01-01",
        donchian_20_high=145.0,
        avg_vol_20d=1_000_000.0,
        atr_20d=3.0,
        sector="Metals"
    )

    # At 09:30 AM, stock traded 240,000 shares (3x normal pace of 80,000)
    # With old formula, 240,000 / 1,000,000 = 0.24x (falsely rejected)
    # With new time-normalized formula, RVOL = 3.0x (passes with flying colors)
    tick = PriceTick(
        symbol="TATASTEEL",
        ltp=165.0,
        day_high=165.0,
        day_low=152.0,
        day_open=153.0,
        prev_close=152.0,
        p_change=8.55,
        volume=240_000,
        turnover_cr=39.6,
        timestamp=dt_930
    )

    sigs = breakout_detector.evaluate_breakouts(tick, levels)
    assert len(sigs) > 0
    # RVOL on the signal should be ~3.0x
    assert sigs[0].rvol == pytest.approx(3.0, abs=0.1)

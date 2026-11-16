"""
Unit tests for Breakout & Breakdown Signal Calculations (Separate Buy & Sell alerts).
Verifies:
1. Strict exclusion of current day (zero look-ahead bias)
2. Separate alerts for Buy conditions: ATH, 52W, DC50, DC20, ST 15m (10,1), ST 15m (10,2), ST Daily (10,1), ST Daily (10,2)
3. Separate alerts for Sell conditions: ATL, 52W Low, DC50 Low, DC20 Low, ST 15m (10,1), ST 15m (10,2), ST Daily (10,1), ST Daily (10,2)
"""

from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
import pytest

from signals.models import PriceTick, PrecomputedLevels, TriggerType
from signals.level_calculator import compute_levels_for_symbol, calculate_atr
from signals.breakout_detector import breakout_detector


def generate_sample_history(num_days: int = 300, base_price: float = 1000.0) -> pd.DataFrame:
    """Generate synthetic daily OHLCV series."""
    dates = pd.date_range(end=datetime.now() - timedelta(days=1), periods=num_days, freq="B")
    
    np.random.seed(42)
    daily_returns = np.random.normal(0.0005, 0.015, num_days)
    close_prices = base_price * np.exp(np.cumsum(daily_returns))
    
    high_prices = close_prices * (1 + np.random.uniform(0.002, 0.01, num_days))
    low_prices = close_prices * (1 - np.random.uniform(0.002, 0.01, num_days))
    open_prices = close_prices * (1 + np.random.normal(0, 0.005, num_days))
    volume = np.random.randint(50000, 500000, num_days)

    df = pd.DataFrame({
        "Open": open_prices,
        "High": high_prices,
        "Low": low_prices,
        "Close": close_prices,
        "Volume": volume
    }, index=dates)

    return df


def test_zero_lookahead_bias():
    """Verify today's in-progress candle is strictly excluded from levels calculation."""
    df = generate_sample_history(300, 1000.0)
    today = date.today()
    
    today_bar = pd.DataFrame({
        "Open": [99999.0],
        "High": [99999.0],
        "Low": [99999.0],
        "Close": [99999.0],
        "Volume": [1000000]
    }, index=[pd.to_datetime(today)])

    leaked_df = pd.concat([df, today_bar])
    levels = compute_levels_for_symbol("TESTSTOCK", leaked_df, as_of_date=today)

    assert levels is not None
    assert levels.ath_high < 90000.0
    assert levels.high_52w < 90000.0
    assert levels.donchian_50_high < 90000.0
    assert levels.donchian_20_high < 90000.0


def test_separate_buy_and_sell_signals():
    """Verify separate buy and sell signal generation including DC20 and individual STs."""
    today = date.today()
    levels = PrecomputedLevels(
        symbol="RELIANCE",
        calculated_date=today,
        ath_high=3020.0,
        ath_date="2024-05-10",
        high_52w=3000.0,
        high_52w_date="2024-08-15",
        donchian_50_high=2990.0,
        donchian_50_date="2024-09-01",
        donchian_20_high=2980.0,
        donchian_20_high_date="2024-09-10",
        atl_low=2000.0,
        atl_date="2020-03-23",
        low_52w=2400.0,
        low_52w_date="2023-11-01",
        donchian_50_low=2500.0,
        donchian_50_low_date="2024-07-01",
        donchian_20_low=2600.0,
        donchian_20_low_date="2024-08-01",
        avg_vol_20d=100000.0,
        atr_20d=35.0,
        last_close=2950.0,
        sector="Energy",
        st_daily_10_1_val=2970.0,
        st_daily_10_1_dir=1,
        st_daily_10_1_flip=1,
        st_daily_10_2_val=2960.0,
        st_daily_10_2_dir=1,
        st_daily_10_2_flip=1,
        st_15m_10_1_val=2990.0,
        st_15m_10_1_dir=1,
        st_15m_10_1_flip=1,
        st_15m_10_2_val=2985.0,
        st_15m_10_2_dir=1,
        st_15m_10_2_flip=1
    )

    # 1. Price is 3050 (triggers ATH, 52W, DC50, DC20, and all ST buy alerts separately)
    tick_buy = PriceTick(
        symbol="RELIANCE",
        ltp=3050.0,
        day_high=3060.0,
        day_low=2960.0,
        day_open=2970.0,
        prev_close=2950.0,
        p_change=3.39,
        volume=250000,
        turnover_cr=76.25
    )

    buy_sigs = breakout_detector.evaluate_breakouts(tick_buy, levels)
    assert len(buy_sigs) >= 4
    trigger_names = [s.trigger for s in buy_sigs]
    assert TriggerType.ATH in trigger_names
    assert TriggerType.HIGH_52W in trigger_names
    assert TriggerType.DC50_HIGH in trigger_names
    assert TriggerType.DC20_HIGH in trigger_names
    assert TriggerType.ST_15M_10_1_BUY not in trigger_names
    assert TriggerType.ST_15M_10_2_BUY not in trigger_names
    assert TriggerType.ST_DAILY_10_1_BUY in trigger_names
    assert TriggerType.ST_DAILY_10_2_BUY in trigger_names

    # 2. Sell side test: price breaks down below 20-day, 50-day, and 52-week lows and ST sell bands
    levels_sell = PrecomputedLevels(
        symbol="INFY",
        calculated_date=today,
        ath_high=2000.0,
        ath_date="2022-01-10",
        high_52w=1900.0,
        high_52w_date="2024-05-10",
        donchian_50_high=1800.0,
        donchian_50_date="2024-08-10",
        donchian_20_high=1750.0,
        donchian_20_high_date="2024-09-10",
        atl_low=800.0,
        atl_date="2020-03-23",
        low_52w=1400.0,
        low_52w_date="2023-11-01",
        donchian_50_low=1450.0,
        donchian_50_low_date="2024-07-01",
        donchian_20_low=1500.0,
        donchian_20_low_date="2024-08-01",
        avg_vol_20d=150000.0,
        atr_20d=25.0,
        last_close=1550.0,
        sector="IT",
        st_daily_10_1_val=1520.0,
        st_daily_10_1_dir=-1,
        st_daily_10_1_flip=-1,
        st_daily_10_2_val=1540.0,
        st_daily_10_2_dir=-1,
        st_daily_10_2_flip=-1,
        st_15m_10_1_val=1510.0,
        st_15m_10_1_dir=-1,
        st_15m_10_1_flip=-1,
        st_15m_10_2_val=1530.0,
        st_15m_10_2_dir=-1,
        st_15m_10_2_flip=-1
    )

    # Price drops to 1380
    tick_sell = PriceTick(
        symbol="INFY",
        ltp=1380.0,
        day_high=1420.0,
        day_low=1375.0,
        day_open=1410.0,
        prev_close=1550.0,
        p_change=-10.97,
        volume=500000,
        turnover_cr=69.0
    )

    sell_sigs = breakout_detector.evaluate_breakouts(tick_sell, levels_sell)
    assert len(sell_sigs) >= 4
    sell_triggers = [s.trigger for s in sell_sigs]
    assert TriggerType.LOW_52W in sell_triggers
    assert TriggerType.DC50_LOW in sell_triggers
    assert TriggerType.DC20_LOW in sell_triggers
    assert TriggerType.ST_15M_10_1_SELL not in sell_triggers
    assert TriggerType.ST_15M_10_2_SELL not in sell_triggers
    assert TriggerType.ST_DAILY_10_1_SELL in sell_triggers
    assert TriggerType.ST_DAILY_10_2_SELL in sell_triggers


def test_supertrend_15m_not_in_screener():
    """Verify that Supertrend on 15m does not fire screener alerts."""
    levels = PrecomputedLevels(
        symbol="HDFCBANK",
        calculated_date=date.today(),
        ath_high=1800.0,
        ath_date="2024-01-10",
        high_52w=1750.0,
        high_52w_date="2024-05-10",
        donchian_50_high=1700.0,
        donchian_50_date="2024-08-10",
        avg_vol_20d=200000.0,
        atr_20d=25.0,
        last_close=1640.0,
        sector="Financial Services",
        st_daily_10_1_val=1680.0,
        st_daily_10_1_dir=-1,
        st_daily_10_2_val=1700.0,
        st_daily_10_2_dir=-1,
        st_15m_10_1_val=1645.0,
        st_15m_10_1_dir=1,
        st_15m_10_1_flip=1,
        st_15m_10_2_val=1650.0,
        st_15m_10_2_dir=1,
        st_15m_10_2_flip=1
    )

    tick = PriceTick(
        symbol="HDFCBANK",
        ltp=1660.0,
        day_high=1665.0,
        day_low=1635.0,
        day_open=1640.0,
        prev_close=1640.0,
        p_change=1.22,
        volume=300000,
        turnover_cr=49.8
    )

    sigs = breakout_detector.evaluate_breakouts(tick, levels)
    triggers = [s.trigger for s in sigs]
    # 15m Supertrend should NOT fire screener alerts
    assert TriggerType.ST_15M_10_1_BUY not in triggers
    assert TriggerType.ST_15M_10_2_BUY not in triggers
    assert len(sigs) == 0


def test_supertrend_daily_standalone_trigger():
    """Verify that Supertrend (10,1) and (10,2) on Daily trigger separate alerts."""
    levels = PrecomputedLevels(
        symbol="ICICIBANK",
        calculated_date=date.today(),
        ath_high=1400.0,
        ath_date="2024-01-10",
        high_52w=1350.0,
        high_52w_date="2024-05-10",
        donchian_50_high=1300.0,
        donchian_50_date="2024-08-10",
        avg_vol_20d=150000.0,
        atr_20d=20.0,
        last_close=1260.0,
        sector="Financial Services",
        st_daily_10_1_val=1265.0,
        st_daily_10_1_dir=1,
        st_daily_10_1_flip=1,
        st_daily_10_2_val=1270.0,
        st_daily_10_2_dir=1,
        st_daily_10_2_flip=1,
        st_15m_10_1_val=1280.0,
        st_15m_10_1_dir=-1,
        st_15m_10_2_val=1285.0,
        st_15m_10_2_dir=-1
    )

    tick = PriceTick(
        symbol="ICICIBANK",
        ltp=1275.0,
        day_high=1280.0,
        day_low=1255.0,
        day_open=1260.0,
        prev_close=1260.0,
        p_change=1.19,
        volume=250000,
        turnover_cr=31.87
    )

    sigs = breakout_detector.evaluate_breakouts(tick, levels)
    triggers = [s.trigger for s in sigs]
    assert TriggerType.ST_DAILY_10_1_BUY in triggers
    assert TriggerType.ST_DAILY_10_2_BUY in triggers

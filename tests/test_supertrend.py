"""
Unit tests for Supertrend (10, 1) and (10, 2) Indicators.
Verifies calculation accuracy on both Daily and 15-Minute timeframes.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytest

from signals.supertrend import calculate_supertrend, get_latest_supertrend
from signals.level_calculator import compute_levels_for_symbol


def generate_ohlcv_data(num_bars: int = 50, freq: str = "1D", trend: str = "bullish") -> pd.DataFrame:
    """Generate synthetic OHLCV data with known trend characteristics."""
    dates = pd.date_range(end=datetime.now(), periods=num_bars, freq=freq)
    
    if trend == "bullish":
        base = np.linspace(100.0, 150.0, num_bars)
    elif trend == "bearish":
        base = np.linspace(150.0, 100.0, num_bars)
    else:
        base = np.full(num_bars, 100.0)

    # Add realistic high/low spreads
    highs = base + 2.0
    lows = base - 2.0
    opens = base - 0.5
    closes = base + 0.5
    volume = np.random.randint(1000, 50000, num_bars)

    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volume
    }, index=dates)


def test_supertrend_10_1_and_10_2_daily():
    """Verify ST(10, 1) and ST(10, 2) on daily timeframe."""
    df_bull = generate_ohlcv_data(60, freq="1D", trend="bullish")
    
    st_10_1 = get_latest_supertrend(df_bull, period=10, multiplier=1.0)
    st_10_2 = get_latest_supertrend(df_bull, period=10, multiplier=2.0)

    # In a continuous strong uptrend, both should be Bullish (direction == 1)
    assert st_10_1.direction == 1
    assert st_10_1.is_bullish is True
    assert st_10_2.direction == 1
    assert st_10_2.is_bullish is True

    # Multiplier 2.0 bands should sit wider (lower stop in uptrend) than Multiplier 1.0
    assert st_10_2.value < st_10_1.value


def test_supertrend_10_1_and_10_2_15min():
    """Verify ST(10, 1) and ST(10, 2) on 15-minute intraday timeframe."""
    df_15m = generate_ohlcv_data(80, freq="15min", trend="bearish")
    
    st_15m_1 = get_latest_supertrend(df_15m, period=10, multiplier=1.0)
    st_15m_2 = get_latest_supertrend(df_15m, period=10, multiplier=2.0)

    # In a continuous strong downtrend, both should be Bearish (direction == -1)
    assert st_15m_1.direction == -1
    assert st_15m_1.is_bullish is False
    assert st_15m_2.direction == -1
    assert st_15m_2.is_bullish is False

    # Multiplier 2.0 bands should sit higher (wider resistance in downtrend) than Multiplier 1.0
    assert st_15m_2.value > st_15m_1.value


def test_supertrend_flip_on_reversal():
    """Verify that Supertrend flips from bearish (-1) to bullish (+1) on a breakout candle."""
    # 25 bearish bars followed by a sharp breakout upward
    df_bear = generate_ohlcv_data(25, freq="15min", trend="bearish")
    
    # Add a massive green breakout candle that shatters the upper band
    last_date = df_bear.index[-1] + timedelta(minutes=15)
    breakout_bar = pd.DataFrame({
        "Open": [120.0],
        "High": [180.0],
        "Low": [119.0],
        "Close": [178.0],
        "Volume": [200000]
    }, index=[last_date])

    df_combined = pd.concat([df_bear, breakout_bar])
    st_res = get_latest_supertrend(df_combined, period=10, multiplier=1.0)

    # Breakout candle must flip Supertrend to Bullish
    assert st_res.direction == 1
    assert st_res.is_bullish is True


def test_compute_levels_includes_all_supertrends():
    """Verify that compute_levels_for_symbol embeds both Daily and 15m Supertrends."""
    df_daily = generate_ohlcv_data(70, freq="1D", trend="bullish")
    df_15m = generate_ohlcv_data(70, freq="15min", trend="bullish")

    levels = compute_levels_for_symbol(
        symbol="TATASTEEL",
        df=df_daily,
        df_15m=df_15m
    )

    assert levels is not None
    # Verify Daily Supertrends
    assert levels.st_daily_10_1_dir in (1, -1)
    assert levels.st_daily_10_2_dir in (1, -1)
    assert levels.st_daily_10_1_val > 0
    assert levels.st_daily_10_2_val > 0

    # Verify 15m Supertrends
    assert levels.st_15m_10_1_dir in (1, -1)
    assert levels.st_15m_10_2_dir in (1, -1)
    assert levels.st_15m_10_1_val > 0
    assert levels.st_15m_10_2_val > 0

"""
Unit tests for Corporate Actions Discontinuity Detection.
Verifies identification of unadjusted splits or bonus issues (>20% price gaps).
"""

import pandas as pd
from datetime import datetime, timedelta
from data.corporate_actions import corporate_action_detector


def test_detect_split_discontinuity():
    """Simulate a 1:1 bonus issue (50% price drop overnight) and verify detection."""
    dates = pd.date_range(end=datetime.now(), periods=10, freq="B")
    
    # 5 days at ~2000, then sudden drop to ~1000 on ex-bonus date
    closes = [2000.0, 2010.0, 1995.0, 2005.0, 2020.0, 1010.0, 1015.0, 1020.0, 1005.0, 1012.0]
    opens =  [1990.0, 2005.0, 2000.0, 2000.0, 2010.0, 1005.0, 1010.0, 1018.0, 1010.0, 1010.0]
    highs =  [2020.0, 2025.0, 2010.0, 2015.0, 2030.0, 1020.0, 1025.0, 1030.0, 1015.0, 1020.0]
    lows =   [1980.0, 1995.0, 1990.0, 1990.0, 2000.0, 1000.0, 1005.0, 1010.0, 1000.0, 1005.0]
    volume = [100000] * 10

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volume
    }, index=dates)

    has_disc, reason = corporate_action_detector.check_discontinuity("TEST_SPLIT", df)
    assert has_disc is True
    assert "price drop" in reason.lower()


def test_normal_movement_no_discontinuity():
    """Verify normal 1-2% daily market moves do not trigger false discontinuity alerts."""
    dates = pd.date_range(end=datetime.now(), periods=10, freq="B")
    closes = [1000.0, 1010.0, 1005.0, 995.0, 1002.0, 1015.0, 1020.0, 1010.0, 1015.0, 1025.0]
    opens = closes
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    volume = [100000] * 10

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volume
    }, index=dates)

    has_disc, reason = corporate_action_detector.check_discontinuity("TEST_NORMAL", df)
    assert has_disc is False
    assert reason is None

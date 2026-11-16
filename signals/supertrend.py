"""
Supertrend Indicator Implementation.
Calculates Supertrend(period, multiplier) with exact TradingView/institutional parity:
- Calculates True Range (TR) and Average True Range (ATR)
- Tracks Upper Band and Lower Band persistence
- Returns (supertrend_value, direction, is_bullish)
  where direction: 1 = Bullish (Uptrend), -1 = Bearish (Downtrend)
"""

from typing import Tuple, NamedTuple
import numpy as np
import pandas as pd


class SupertrendResult(NamedTuple):
    value: float
    direction: int  # 1 for Bullish, -1 for Bearish
    upper_band: float
    lower_band: float
    is_bullish: bool
    prev_direction: int = 0
    is_flip_buy: bool = False
    is_flip_sell: bool = False


def calculate_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 1.0
) -> pd.DataFrame:
    """
    Calculate Supertrend for a given DataFrame containing 'High', 'Low', 'Close'.
    Returns a DataFrame with columns:
    ['ST_val', 'ST_dir', 'ST_upper', 'ST_lower', 'ST_bullish']
    """
    if df is None or len(df) < period + 1:
        empty = pd.DataFrame(index=df.index if df is not None else None)
        empty["ST_val"] = np.nan
        empty["ST_dir"] = 0
        empty["ST_upper"] = np.nan
        empty["ST_lower"] = np.nan
        empty["ST_bullish"] = False
        return empty

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n = len(df)

    # 1. Calculate True Range (TR)
    tr = np.zeros(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hpc = abs(high[i] - close[i - 1])
        lpc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hpc, lpc)

    # 2. Calculate ATR using Wilder's Smoothing (RMA)
    atr = np.zeros(n, dtype=float)
    if period > 0 and n >= period:
        # Initial ATR is simple moving average of first 'period' bars
        atr[period - 1] = np.mean(tr[:period])
        # Wilder's RMA: ATR[i] = (ATR[i-1] * (period - 1) + TR[i]) / period
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    # 3. Calculate Basic Upper and Lower Bands
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    # 4. Calculate Final Upper and Lower Bands
    final_upper = np.zeros(n, dtype=float)
    final_lower = np.zeros(n, dtype=float)
    supertrend = np.zeros(n, dtype=float)
    direction = np.ones(n, dtype=int)  # 1 for Bullish, -1 for Bearish

    for i in range(period, n):
        # Final Upper Band
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final Lower Band
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Supertrend switch logic
        prev_st = supertrend[i - 1]
        prev_dir = direction[i - 1]

        if prev_st == final_upper[i - 1] or prev_dir == -1:
            if close[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]
        else:
            if close[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]

    res_df = pd.DataFrame(index=df.index)
    res_df["ST_val"] = supertrend
    res_df["ST_dir"] = direction
    res_df["ST_upper"] = final_upper
    res_df["ST_lower"] = final_lower
    res_df["ST_bullish"] = direction == 1

    return res_df


def get_latest_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 1.0
) -> SupertrendResult:
    """
    Convenience function returning the most recent Supertrend state as a SupertrendResult,
    including detection of fresh trend flips (reversals) between previous and latest bar.
    """
    if df is None or len(df) < period + 1:
        return SupertrendResult(
            value=0.0, direction=0, upper_band=0.0, lower_band=0.0, is_bullish=False,
            prev_direction=0, is_flip_buy=False, is_flip_sell=False
        )

    st_df = calculate_supertrend(df, period=period, multiplier=multiplier)
    last_row = st_df.iloc[-1]
    prev_row = st_df.iloc[-2] if len(st_df) >= 2 else last_row

    val = float(last_row["ST_val"])
    direction = int(last_row["ST_dir"])
    prev_dir = int(prev_row["ST_dir"])
    ub = float(last_row["ST_upper"])
    lb = float(last_row["ST_lower"])

    is_flip_buy = bool(prev_dir == -1 and direction == 1)
    is_flip_sell = bool(prev_dir == 1 and direction == -1)

    return SupertrendResult(
        value=round(val, 2),
        direction=direction,
        upper_band=round(ub, 2),
        lower_band=round(lb, 2),
        is_bullish=(direction == 1),
        prev_direction=prev_dir,
        is_flip_buy=is_flip_buy,
        is_flip_sell=is_flip_sell
    )

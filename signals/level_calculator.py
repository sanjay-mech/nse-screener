"""
Level Calculator for Institutional Breakout Signals.
Precomputes ATH, 52W High, Donchian Channel 50, 20D Average Volume, and 20D ATR.
Enforces zero look-ahead bias by strictly excluding the current in-progress session.
"""

from datetime import date, datetime
from typing import Optional, Dict
import numpy as np
import pandas as pd
import pytz
from loguru import logger
from config.settings import settings
from signals.models import PrecomputedLevels
from signals.supertrend import get_latest_supertrend
from data.sectors import get_stock_sector

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


def calculate_atr(df: pd.DataFrame, period: int = 20) -> float:
    """Calculate Average True Range (ATR) over specified period."""
    if len(df) < period + 1:
        return 0.0

    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    tr_list = []
    for i in range(1, len(df)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr_list.append(max(hl, hc, lc))

    if len(tr_list) < period:
        return float(np.mean(tr_list)) if tr_list else 0.0

    return float(np.mean(tr_list[-period:]))


def compute_levels_for_symbol(
    symbol: str,
    df: pd.DataFrame,
    as_of_date: Optional[date] = None,
    sector: str = "N/A",
    df_15m: Optional[pd.DataFrame] = None
) -> Optional[PrecomputedLevels]:
    """
    Compute ATH, 52W High, Donchian 50 High, 20D Volume, 20D ATR,
    and Supertrend (10,1) & (10,2) on both Daily and 15-Minute timeframes.
    STRICT ZERO LOOK-AHEAD:
    - If `exclude_today_from_history` is enabled, any bar matching today's date is excluded.
    - Only completed historical daily bars are used.
    """
    if df is None or df.empty or len(df) < 20:
        logger.warning(f"Insufficient history for {symbol} (rows: {len(df) if df is not None else 0})")
        return None

    if as_of_date is None:
        as_of_date = datetime.now(KOLKATA_TZ).date()

    if sector == "N/A" or not sector:
        sector = get_stock_sector(symbol)

    # Clean DataFrame and sort by date ascending
    clean_df = df.copy()
    if not isinstance(clean_df.index, pd.DatetimeIndex):
        clean_df.index = pd.to_datetime(clean_df.index)
    clean_df = clean_df.sort_index()

    # Drop any row matching today's date if exclude_today is configured
    if settings.EXCLUDE_TODAY_FROM_HISTORY:
        clean_df = clean_df[clean_df.index.date < as_of_date]

    if clean_df.empty or len(clean_df) < 20:
        return None

    # Last completed close
    last_close = float(clean_df["Close"].iloc[-1])

    # 1. All-Time High (ATH) and All-Time Low (ATL)
    ath_idx = clean_df["High"].idxmax()
    ath_high = float(clean_df["High"].loc[ath_idx])
    ath_date_str = str(ath_idx.date())

    atl_idx = clean_df["Low"].idxmin()
    atl_low = float(clean_df["Low"].loc[atl_idx])
    atl_date_str = str(atl_idx.date())

    # 2. 52-Week High and 52-Week Low (previous 252 completed trading days)
    lookback_52w = min(settings.HIGH_52W_LOOKBACK_DAYS, len(clean_df))
    df_52w = clean_df.iloc[-lookback_52w:]
    h52_idx = df_52w["High"].idxmax()
    high_52w = float(df_52w["High"].loc[h52_idx])
    high_52w_date_str = str(h52_idx.date())

    l52_idx = df_52w["Low"].idxmin()
    low_52w = float(df_52w["Low"].loc[l52_idx])
    low_52w_date_str = str(l52_idx.date())

    # 3. Donchian Channel 50 High and Low (previous 50 completed trading days)
    lookback_dc50 = min(settings.DONCHIAN_LOOKBACK_DAYS, len(clean_df))
    df_dc50 = clean_df.iloc[-lookback_dc50:]
    dc50_h_idx = df_dc50["High"].idxmax()
    dc50_high = float(df_dc50["High"].loc[dc50_h_idx])
    dc50_high_date_str = str(dc50_h_idx.date())

    dc50_l_idx = df_dc50["Low"].idxmin()
    dc50_low = float(df_dc50["Low"].loc[dc50_l_idx])
    dc50_low_date_str = str(dc50_l_idx.date())

    # 4. Donchian Channel 20 High and Low (previous 20 completed trading days)
    lookback_dc20 = min(20, len(clean_df))
    df_dc20 = clean_df.iloc[-lookback_dc20:]
    dc20_h_idx = df_dc20["High"].idxmax()
    dc20_high = float(df_dc20["High"].loc[dc20_h_idx])
    dc20_high_date_str = str(dc20_h_idx.date())

    dc20_l_idx = df_dc20["Low"].idxmin()
    dc20_low = float(df_dc20["Low"].loc[dc20_l_idx])
    dc20_low_date_str = str(dc20_l_idx.date())

    # 5. 20-Day Average Volume
    lookback_vol = min(20, len(clean_df))
    avg_vol_20d = float(clean_df["Volume"].iloc[-lookback_vol:].mean())

    # 6. 20-Day ATR
    atr_20d = calculate_atr(clean_df, period=20)

    # 7. Supertrend (10, 1) and (10, 2) on Daily Timeframe
    st_d_10_1 = get_latest_supertrend(clean_df, period=10, multiplier=1.0)
    st_d_10_2 = get_latest_supertrend(clean_df, period=10, multiplier=2.0)

    # 8. Supertrend (10, 1) and (10, 2) on 15-Minute Timeframe
    if df_15m is not None and not df_15m.empty and len(df_15m) >= 15:
        st_15_10_1 = get_latest_supertrend(df_15m, period=10, multiplier=1.0)
        st_15_10_2 = get_latest_supertrend(df_15m, period=10, multiplier=2.0)
    else:
        st_15_10_1 = st_d_10_1
        st_15_10_2 = st_d_10_2

    d_10_1_flip = 1 if st_d_10_1.is_flip_buy else (-1 if st_d_10_1.is_flip_sell else 0)
    d_10_2_flip = 1 if st_d_10_2.is_flip_buy else (-1 if st_d_10_2.is_flip_sell else 0)
    m15_10_1_flip = 1 if st_15_10_1.is_flip_buy else (-1 if st_15_10_1.is_flip_sell else 0)
    m15_10_2_flip = 1 if st_15_10_2.is_flip_buy else (-1 if st_15_10_2.is_flip_sell else 0)

    return PrecomputedLevels(
        symbol=symbol.upper(),
        calculated_date=as_of_date,
        ath_high=round(ath_high, 2),
        ath_date=ath_date_str,
        high_52w=round(high_52w, 2),
        high_52w_date=high_52w_date_str,
        donchian_50_high=round(dc50_high, 2),
        donchian_50_date=dc50_high_date_str,
        donchian_20_high=round(dc20_high, 2),
        donchian_20_high_date=dc20_high_date_str,
        atl_low=round(atl_low, 2),
        atl_date=atl_date_str,
        low_52w=round(low_52w, 2),
        low_52w_date=low_52w_date_str,
        donchian_50_low=round(dc50_low, 2),
        donchian_50_low_date=dc50_low_date_str,
        donchian_20_low=round(dc20_low, 2),
        donchian_20_low_date=dc20_low_date_str,
        avg_vol_20d=round(avg_vol_20d, 0),
        atr_20d=round(atr_20d, 2),
        last_close=round(last_close, 2),
        sector=sector,
        st_daily_10_1_val=st_d_10_1.value,
        st_daily_10_1_dir=st_d_10_1.direction,
        st_daily_10_1_flip=d_10_1_flip,
        st_daily_10_2_val=st_d_10_2.value,
        st_daily_10_2_dir=st_d_10_2.direction,
        st_daily_10_2_flip=d_10_2_flip,
        st_15m_10_1_val=st_15_10_1.value,
        st_15m_10_1_dir=st_15_10_1.direction,
        st_15m_10_1_flip=m15_10_1_flip,
        st_15m_10_2_val=st_15_10_2.value,
        st_15m_10_2_dir=st_15_10_2.direction,
        st_15m_10_2_flip=m15_10_2_flip
    )

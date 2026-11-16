"""
Institutional Time-Normalized RVOL (Relative Volume) Module for Indian Equities (NSE).
Accounts for the intraday U-curve volume distribution across the 375-minute trading session (09:15 - 15:30 IST).
"""
import pytz
from datetime import datetime, time
from typing import Optional
from config.settings import settings

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)

# Empirical NSE Equity Cumulative Intraday Volume Profile (375 minutes total: 09:15 - 15:30 IST)
# Format: (minutes_elapsed_from_0915, cumulative_volume_fraction)
NSE_INTRADAY_VOLUME_PROFILE = [
    (0, 0.02),      # 09:15 IST - Market Open floor (2%)
    (15, 0.08),     # 09:30 IST - Initial opening burst (~8% of total day volume)
    (30, 0.14),     # 09:45 IST - First 30 mins (~14%)
    (45, 0.20),     # 10:00 IST - Opening momentum (~20%)
    (75, 0.28),     # 10:30 IST - Early session (~28%)
    (105, 0.35),    # 11:00 IST - Mid-morning (~35%)
    (135, 0.41),    # 11:30 IST - European pre-open (~41%)
    (165, 0.47),    # 12:00 IST - Midday lunch lull starts (~47%)
    (195, 0.52),    # 12:30 IST - Midday lull (~52%)
    (225, 0.57),    # 13:00 IST - Early afternoon (~57%)
    (255, 0.63),    # 13:30 IST - European market open (~63%)
    (285, 0.70),    # 14:00 IST - Institutional positioning (~70%)
    (315, 0.78),    # 14:30 IST - Power hour setup (~78%)
    (345, 0.88),    # 15:00 IST - Closing square-off rush (~88%)
    (375, 1.00),    # 15:30 IST - Market Close (100%)
]


def get_expected_day_fraction(timestamp: Optional[datetime] = None) -> float:
    """
    Returns the expected cumulative volume fraction (0.02 to 1.00) based on
    time elapsed in the NSE trading session (09:15 to 15:30 IST).
    
    - If timestamp is None, the current live time in IST is used.
    - If timestamp is midnight (00:00:00), it's treated as an EOD daily bar -> 1.0.
    - If time is after 15:30 IST, returns 1.0.
    """
    if timestamp is None:
        now = datetime.now(KOLKATA_TZ)
    else:
        # Check if timestamp represents a daily bar (midnight)
        if timestamp.time() == time(0, 0):
            return 1.0

        if timestamp.tzinfo is not None:
            now = timestamp.astimezone(KOLKATA_TZ)
        else:
            # Naive timestamp:
            # If hour is between 3 and 11, it is UTC during market hours (03:45 to 10:00 UTC = 09:15 to 15:30 IST)
            if 3 <= timestamp.hour <= 11:
                now = pytz.utc.localize(timestamp).astimezone(KOLKATA_TZ)
            else:
                now = KOLKATA_TZ.localize(timestamp)

    t = now.time()
    market_open = time(9, 15)
    market_close = time(15, 30)

    # Post-market / EOD
    if t >= market_close:
        return 1.0

    # Pre-market
    if t < market_open:
        # If pre-market auction (09:00 - 09:15), use floor fraction
        if t >= time(9, 0):
            return NSE_INTRADAY_VOLUME_PROFILE[0][1]
        # Otherwise outside trading session, default to 1.0 so we don't skew testing / offline analysis
        return 1.0

    # Minutes elapsed from 09:15:00 IST
    minutes_elapsed = (t.hour - 9) * 60 + (t.minute - 15) + (t.second / 60.0)

    # Piecewise linear interpolation across the volume profile
    for i in range(len(NSE_INTRADAY_VOLUME_PROFILE) - 1):
        m0, f0 = NSE_INTRADAY_VOLUME_PROFILE[i]
        m1, f1 = NSE_INTRADAY_VOLUME_PROFILE[i + 1]
        if m0 <= minutes_elapsed <= m1:
            ratio = (minutes_elapsed - m0) / (m1 - m0)
            return round(f0 + ratio * (f1 - f0), 4)

    return 1.0


def calculate_time_normalized_rvol(
    current_volume: float,
    avg_vol_20d: float,
    timestamp: Optional[datetime] = None
) -> float:
    """
    Calculates institutional Time-Normalized Relative Volume (RVOL).
    
    Formula:
        Expected Volume(t) = avg_vol_20d * get_expected_day_fraction(t)
        RVOL = current_volume / Expected Volume(t)
    """
    if avg_vol_20d <= 0:
        return 1.0
    if current_volume <= 0:
        return 0.0

    fraction = get_expected_day_fraction(timestamp)
    expected_vol = avg_vol_20d * fraction
    if expected_vol <= 0:
        return 1.0

    return round(float(current_volume) / expected_vol, 2)

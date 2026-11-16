"""
Corporate Actions & Discontinuity Detector.
Detects unadjusted splits, bonuses, or anomalous historical gaps (>20%)
and signals the system to re-pull clean adjusted history for affected stocks.
"""

from typing import Tuple, Optional
import pandas as pd
from loguru import logger
from config.settings import settings


class CorporateActionDetector:
    def __init__(self, gap_threshold_pct: float = settings.CORPORATE_ACTION_GAP_THRESHOLD_PCT):
        self.gap_threshold_pct = gap_threshold_pct

    def check_discontinuity(
        self, symbol: str, df: pd.DataFrame
    ) -> Tuple[bool, Optional[str]]:
        """
        Scan daily historical prices for unadjusted discontinuities (splits/bonuses).
        Returns (has_discontinuity, reason).
        """
        if df.empty or len(df) < 5:
            return False, None

        # Check for sudden single-day downward gap exceeding threshold
        closes = df["Close"].values
        highs = df["High"].values
        lows = df["Low"].values

        for i in range(1, len(closes)):
            prev_close = closes[i - 1]
            curr_open = df["Open"].iloc[i]
            curr_low = lows[i]

            if prev_close <= 0:
                continue

            # Check overnight drop (typical for 1:1, 1:2 bonus/split)
            overnight_drop_pct = ((prev_close - curr_open) / prev_close) * 100.0

            # If overnight drop > 20%, verify if intraday recovered or if it's an unadjusted drop
            if overnight_drop_pct >= self.gap_threshold_pct:
                drop_date = str(df.index[i].date()) if hasattr(df.index[i], "date") else str(df.index[i])
                reason = f"Detected {overnight_drop_pct:.1f}% price drop on {drop_date} (potential unadjusted split/bonus)"
                logger.warning(f"[{symbol}] {reason}")
                return True, reason

        return False, None


corporate_action_detector = CorporateActionDetector()

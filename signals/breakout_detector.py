"""
Institutional Breakout & Breakdown Detector.
Evaluates incoming price ticks against precomputed levels:
- Generates separate individual alerts for each condition:
  Buy side: ATH, 52W High, DC50 High, DC20 High, ST 15m (10,1), ST 15m (10,2), ST Daily (10,1), ST Daily (10,2)
  Sell side: ATL, 52W Low, DC50 Low, DC20 Low, ST 15m (10,1), ST 15m (10,2), ST Daily (10,1), ST Daily (10,2)
"""

from datetime import datetime
from typing import Optional, List, Tuple
from loguru import logger
from config.settings import settings
from signals.models import (
    PriceTick,
    PrecomputedLevels,
    BreakoutSignal,
    TriggerType,
    TriggerMode
)
from signals.rvol import calculate_time_normalized_rvol


class BreakoutDetector:
    def __init__(self):
        self.trigger_mode = settings.TRIGGER_MODE

    def _determine_eval_price(self, tick: PriceTick, mode: str, side: str = "BUY") -> float:
        """Select price to evaluate based on trigger mode and side."""
        if mode == TriggerMode.INTRADAY_TOUCH.value:
            return tick.day_high if side == "BUY" else tick.day_low
        return tick.ltp

    def evaluate_breakouts(
        self,
        tick: PriceTick,
        levels: PrecomputedLevels,
        ban_status: str = "NORMAL",
        force_mode: Optional[str] = None
    ) -> List[BreakoutSignal]:
        """
        Evaluate all individual Buy and Sell breakout/breakdown conditions separately.
        Each triggered condition generates its own distinct BreakoutSignal.
        """
        mode = force_mode or self.trigger_mode
        buy_price = self._determine_eval_price(tick, mode, "BUY")
        sell_price = self._determine_eval_price(tick, mode, "SELL")

        # 1. Base Price Filter
        if tick.ltp < settings.MIN_PRICE or tick.ltp > settings.MAX_PRICE:
            return []

        # 2. Minimum Average Daily Volume Filter
        if levels.avg_vol_20d < settings.MIN_AVG_VOLUME_20D:
            return []

        # 3. Minimum Turnover Filter
        if tick.turnover_cr < settings.MIN_TURNOVER_CR and tick.volume > 0:
            return []

        rvol = calculate_time_normalized_rvol(tick.volume, levels.avg_vol_20d, tick.timestamp)
        if settings.REQUIRE_VOLUME_CONFIRMATION and rvol < settings.MIN_RVOL:
            return []

        signals: List[BreakoutSignal] = []

        # Check if the level was hit/crossed in the current or previous 5-minute candle
        def did_hit_recent_buy(level_val: float) -> bool:
            if tick.candle_5m_curr_high is None:
                return True
            recent_high = max(tick.candle_5m_curr_high, tick.candle_5m_prev_high if tick.candle_5m_prev_high is not None else tick.candle_5m_curr_high)
            if recent_high < level_val:
                return False
            if tick.candle_5m_prior_close is not None and tick.candle_5m_prior_close >= level_val:
                return False
            return True

        def did_hit_recent_sell(level_val: float) -> bool:
            if tick.candle_5m_curr_low is None:
                return True
            recent_low = min(tick.candle_5m_curr_low, tick.candle_5m_prev_low if tick.candle_5m_prev_low is not None else tick.candle_5m_curr_low)
            if recent_low > level_val:
                return False
            if tick.candle_5m_prior_close is not None and tick.candle_5m_prior_close <= level_val:
                return False
            return True

        def build_sig(side: str, trigger: TriggerType, title: str, level_val: float, dist_pct: float) -> BreakoutSignal:
            return BreakoutSignal(
                symbol=tick.symbol,
                ltp=tick.ltp,
                pct_change=tick.p_change,
                level_broken=round(level_val, 2),
                pct_above=round(dist_pct, 2),
                triggers=[trigger],
                trigger_label=trigger.value,
                prior_high_date=None,
                rvol=rvol,
                atr_20=levels.atr_20d,
                sector=levels.sector,
                ban_status=ban_status,
                timestamp=tick.timestamp,
                trigger_mode=mode,
                volume=tick.volume,
                turnover_cr=tick.turnover_cr,
                side=side,
                trigger=trigger,
                title=title,
                pct_distance=round(dist_pct, 2),
                st_daily_10_1_dir=levels.st_daily_10_1_dir,
                st_daily_10_2_dir=levels.st_daily_10_2_dir,
                st_15m_10_1_dir=levels.st_15m_10_1_dir,
                st_15m_10_2_dir=levels.st_15m_10_2_dir,
                conditions_met=[f"{side} ({title})"]
            )

        # ==========================================
        # BUY / LONG SIDE CONDITIONS (SEPARATE ALERTS)
        # ==========================================
        # 1. ATH Breakout
        if levels.ath_high > 0 and buy_price > levels.ath_high and tick.p_change >= 0 and did_hit_recent_buy(levels.ath_high):
            dist = ((buy_price - levels.ath_high) / levels.ath_high) * 100.0
            if dist >= settings.MIN_DISTANCE_ABOVE_LEVEL_PCT and dist <= settings.MAX_DISTANCE_FROM_LEVEL_PCT:
                signals.append(build_sig("BUY", TriggerType.ATH, "ATH BREAKOUT", levels.ath_high, dist))

        # 2. 52W High Breakout
        if levels.high_52w > 0 and buy_price > levels.high_52w and tick.p_change >= 0 and did_hit_recent_buy(levels.high_52w):
            dist = ((buy_price - levels.high_52w) / levels.high_52w) * 100.0
            if dist >= settings.MIN_DISTANCE_ABOVE_LEVEL_PCT and dist <= settings.MAX_DISTANCE_FROM_LEVEL_PCT:
                signals.append(build_sig("BUY", TriggerType.HIGH_52W, "52W HIGH", levels.high_52w, dist))

        # 3. Donchian 50 High Breakout
        if levels.donchian_50_high > 0 and buy_price > levels.donchian_50_high and tick.p_change >= 0 and did_hit_recent_buy(levels.donchian_50_high):
            dist = ((buy_price - levels.donchian_50_high) / levels.donchian_50_high) * 100.0
            if dist >= settings.MIN_DISTANCE_ABOVE_LEVEL_PCT and dist <= settings.MAX_DISTANCE_FROM_LEVEL_PCT:
                signals.append(build_sig("BUY", TriggerType.DC50_HIGH, "DC50 BREAKOUT", levels.donchian_50_high, dist))

        # 4. Donchian 20 High Breakout
        if levels.donchian_20_high > 0 and buy_price > levels.donchian_20_high and tick.p_change >= 0 and did_hit_recent_buy(levels.donchian_20_high):
            dist = ((buy_price - levels.donchian_20_high) / levels.donchian_20_high) * 100.0
            if dist >= settings.MIN_DISTANCE_ABOVE_LEVEL_PCT and dist <= settings.MAX_DISTANCE_FROM_LEVEL_PCT:
                signals.append(build_sig("BUY", TriggerType.DC20_HIGH, "DC20 BREAKOUT", levels.donchian_20_high, dist))

        # 5. Supertrend Daily (10,1) Buy - Fresh Intraday Flip (Red -> Green) only:
        # Prior completed day was Bearish (dir == -1), and price breaks strictly above resistance level today with positive gain
        is_std_1_buy_flip = (levels.st_daily_10_1_dir == -1 and buy_price > levels.st_daily_10_1_val and tick.p_change >= 0)
        if levels.st_daily_10_1_val > 0 and is_std_1_buy_flip and did_hit_recent_buy(levels.st_daily_10_1_val):
            dist = ((buy_price - levels.st_daily_10_1_val) / levels.st_daily_10_1_val) * 100.0
            signals.append(build_sig("BUY", TriggerType.ST_DAILY_10_1_BUY, "ST DAILY (10,1) BUY FLIP", levels.st_daily_10_1_val, dist))

        # 6. Supertrend Daily (10,2) Buy - Fresh Intraday Flip (Red -> Green) only:
        is_std_2_buy_flip = (levels.st_daily_10_2_dir == -1 and buy_price > levels.st_daily_10_2_val and tick.p_change >= 0)
        if levels.st_daily_10_2_val > 0 and is_std_2_buy_flip and did_hit_recent_buy(levels.st_daily_10_2_val):
            dist = ((buy_price - levels.st_daily_10_2_val) / levels.st_daily_10_2_val) * 100.0
            signals.append(build_sig("BUY", TriggerType.ST_DAILY_10_2_BUY, "ST DAILY (10,2) BUY FLIP", levels.st_daily_10_2_val, dist))

        # ==========================================
        # SELL / SHORT SIDE CONDITIONS (SEPARATE ALERTS)
        # ==========================================
        # 1. ATL Breakdown
        if levels.atl_low > 0 and sell_price < levels.atl_low and tick.p_change <= 0 and did_hit_recent_sell(levels.atl_low):
            dist = -((levels.atl_low - sell_price) / levels.atl_low) * 100.0
            signals.append(build_sig("SELL", TriggerType.ATL, "ATL BREAKDOWN", levels.atl_low, dist))

        # 2. 52W Low Breakdown
        if levels.low_52w > 0 and sell_price < levels.low_52w and tick.p_change <= 0 and did_hit_recent_sell(levels.low_52w):
            dist = -((levels.low_52w - sell_price) / levels.low_52w) * 100.0
            signals.append(build_sig("SELL", TriggerType.LOW_52W, "52W LOW BREAKDOWN", levels.low_52w, dist))

        # 3. Donchian 50 Low Breakdown
        if levels.donchian_50_low > 0 and sell_price < levels.donchian_50_low and tick.p_change <= 0 and did_hit_recent_sell(levels.donchian_50_low):
            dist = -((levels.donchian_50_low - sell_price) / levels.donchian_50_low) * 100.0
            signals.append(build_sig("SELL", TriggerType.DC50_LOW, "DC50 BREAKDOWN", levels.donchian_50_low, dist))

        # 4. Donchian 20 Low Breakdown
        if levels.donchian_20_low > 0 and sell_price < levels.donchian_20_low and tick.p_change <= 0 and did_hit_recent_sell(levels.donchian_20_low):
            dist = -((levels.donchian_20_low - sell_price) / levels.donchian_20_low) * 100.0
            signals.append(build_sig("SELL", TriggerType.DC20_LOW, "DC20 BREAKDOWN", levels.donchian_20_low, dist))

        # 5. Supertrend Daily (10,1) Sell - Fresh Intraday Flip (Green -> Red) only:
        # Prior completed day was Bullish (dir == 1), and price breaks strictly below support level today with negative change
        is_std_1_sell_flip = (levels.st_daily_10_1_dir == 1 and sell_price < levels.st_daily_10_1_val and tick.p_change <= 0)
        if levels.st_daily_10_1_val > 0 and is_std_1_sell_flip and did_hit_recent_sell(levels.st_daily_10_1_val):
            dist = -((levels.st_daily_10_1_val - sell_price) / levels.st_daily_10_1_val) * 100.0
            signals.append(build_sig("SELL", TriggerType.ST_DAILY_10_1_SELL, "ST DAILY (10,1) SELL FLIP", levels.st_daily_10_1_val, dist))

        # 6. Supertrend Daily (10,2) Sell - Fresh Intraday Flip (Green -> Red) only:
        is_std_2_sell_flip = (levels.st_daily_10_2_dir == 1 and sell_price < levels.st_daily_10_2_val and tick.p_change <= 0)
        if levels.st_daily_10_2_val > 0 and is_std_2_sell_flip and did_hit_recent_sell(levels.st_daily_10_2_val):
            dist = -((levels.st_daily_10_2_val - sell_price) / levels.st_daily_10_2_val) * 100.0
            signals.append(build_sig("SELL", TriggerType.ST_DAILY_10_2_SELL, "ST DAILY (10,2) SELL FLIP", levels.st_daily_10_2_val, dist))

        return signals

    def evaluate_breakout(
        self,
        tick: PriceTick,
        levels: PrecomputedLevels,
        ban_status: str = "NORMAL",
        force_mode: Optional[str] = None
    ) -> Optional[BreakoutSignal]:
        """
        Backward-compatible single-signal evaluator.
        Returns the first triggered signal, or None.
        """
        all_sigs = self.evaluate_breakouts(tick, levels, ban_status, force_mode)
        return all_sigs[0] if all_sigs else None

    def is_near_breakout(
        self,
        tick: PriceTick,
        levels: PrecomputedLevels,
        threshold_pct: float = settings.NEAR_BREAKOUT_THRESHOLD_PCT
    ) -> Optional[Tuple[str, float, float]]:
        """
        Check if stock is hovering within threshold_pct of its ATH, 52W, or DC50.
        Returns: (level_name, target_level, distance_pct) or None
        """
        if tick.ltp <= 0:
            return None

        checks = [
            ("ATH", levels.ath_high),
            ("52W", levels.high_52w),
            ("DC50", levels.donchian_50_high),
            ("DC20", levels.donchian_20_high)
        ]

        closest_level = None
        min_dist = float("inf")
        closest_name = ""

        for name, lvl in checks:
            if lvl <= 0:
                continue
            if tick.ltp < lvl:
                dist = ((lvl - tick.ltp) / lvl) * 100.0
                if 0 <= dist <= threshold_pct and dist < min_dist:
                    min_dist = dist
                    closest_level = lvl
                    closest_name = name

        if closest_level is not None:
            return closest_name, closest_level, round(min_dist, 2)

        return None


breakout_detector = BreakoutDetector()

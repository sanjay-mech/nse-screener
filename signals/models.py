"""
Data models and typed structures for price ticks, calculated levels,
breakout signals, and trigger types.
Supports Buy & Sell sides, DC20, DC50, 52W, ATH/ATL, and multi-timeframe Supertrends.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import List, Optional


class TriggerType(str, Enum):
    # Buy / Long Side
    ATH = "ATH"
    HIGH_52W = "52W_HIGH"
    DC50_HIGH = "DC50_HIGH"
    DC20_HIGH = "DC20_HIGH"
    ST_15M_10_1_BUY = "ST_15M_10_1_BUY"
    ST_15M_10_2_BUY = "ST_15M_10_2_BUY"
    ST_DAILY_10_1_BUY = "ST_DAILY_10_1_BUY"
    ST_DAILY_10_2_BUY = "ST_DAILY_10_2_BUY"

    # Sell / Short Side
    ATL = "ATL"
    LOW_52W = "52W_LOW"
    DC50_LOW = "DC50_LOW"
    DC20_LOW = "DC20_LOW"
    ST_15M_10_1_SELL = "ST_15M_10_1_SELL"
    ST_15M_10_2_SELL = "ST_15M_10_2_SELL"
    ST_DAILY_10_1_SELL = "ST_DAILY_10_1_SELL"
    ST_DAILY_10_2_SELL = "ST_DAILY_10_2_SELL"

    # Legacy aliases for backward compatibility
    DC50 = "DC50"
    ST_15M = "ST_15M"
    ST_DAILY = "ST_DAILY"


class TriggerMode(str, Enum):
    INTRADAY_TOUCH = "intraday_touch"
    LTP_ABOVE = "ltp_above"
    CANDLE_CLOSE = "candle_close"


@dataclass
class PriceTick:
    symbol: str
    ltp: float
    day_high: float
    day_low: float
    day_open: float
    prev_close: float
    p_change: float
    volume: int
    turnover_cr: float
    upper_circuit: Optional[float] = None
    lower_circuit: Optional[float] = None
    source: str = "NSE"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_stale: bool = False
    # 5-minute candle tracking for recent hit validation (previous and current 5m candle)
    candle_5m_curr_high: Optional[float] = None
    candle_5m_curr_low: Optional[float] = None
    candle_5m_prev_high: Optional[float] = None
    candle_5m_prev_low: Optional[float] = None
    candle_5m_prior_close: Optional[float] = None


@dataclass
class PrecomputedLevels:
    symbol: str
    calculated_date: date
    # Buy / Breakout Levels
    ath_high: float
    ath_date: Optional[str]
    high_52w: float
    high_52w_date: Optional[str]
    donchian_50_high: float
    donchian_50_date: Optional[str]
    donchian_20_high: float = 0.0
    donchian_20_high_date: Optional[str] = None
    # Sell / Breakdown Levels
    atl_low: float = 0.0
    atl_date: Optional[str] = None
    low_52w: float = 0.0
    low_52w_date: Optional[str] = None
    donchian_50_low: float = 0.0
    donchian_50_low_date: Optional[str] = None
    donchian_20_low: float = 0.0
    donchian_20_low_date: Optional[str] = None
    # Volume & Volatility
    avg_vol_20d: float = 0.0
    atr_20d: float = 0.0
    last_close: float = 0.0
    sector: str = "N/A"
    upper_circuit: Optional[float] = None
    lower_circuit: Optional[float] = None
    # Supertrend (10, 1) and (10, 2) on Daily TF
    st_daily_10_1_val: float = 0.0
    st_daily_10_1_dir: int = 1  # 1 = Bullish, -1 = Bearish
    st_daily_10_1_flip: int = 0  # 1 = BUY flip, -1 = SELL flip, 0 = no flip
    st_daily_10_2_val: float = 0.0
    st_daily_10_2_dir: int = 1
    st_daily_10_2_flip: int = 0
    # Supertrend (10, 1) and (10, 2) on 15-Minute TF
    st_15m_10_1_val: float = 0.0
    st_15m_10_1_dir: int = 1
    st_15m_10_1_flip: int = 0
    st_15m_10_2_val: float = 0.0
    st_15m_10_2_dir: int = 1
    st_15m_10_2_flip: int = 0


@dataclass
class BreakoutSignal:
    symbol: str
    ltp: float
    pct_change: float
    level_broken: float
    pct_above: float
    triggers: List[TriggerType]
    trigger_label: str  # e.g., "ATH" or "ST_15M_10_1_BUY"
    prior_high_date: Optional[str]
    rvol: float
    atr_20: float
    sector: str
    ban_status: str
    timestamp: datetime
    trigger_mode: str
    volume: int
    turnover_cr: float
    side: str = "BUY"  # "BUY" or "SELL"
    trigger: TriggerType = TriggerType.ATH  # Specific individual trigger
    title: str = ""  # Display title, e.g. "DC20 BREAKOUT" or "ST 15m (10,1) BUY"
    pct_distance: float = 0.0  # +X% above level (BUY) or -X% below level (SELL)
    st_daily_10_1_dir: int = 1
    st_daily_10_2_dir: int = 1
    st_15m_10_1_dir: int = 1
    st_15m_10_2_dir: int = 1
    conditions_met: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.title:
            self.title = self.trigger_label or (self.trigger.value if hasattr(self.trigger, "value") else str(self.trigger))
        if not self.trigger_label:
            self.trigger_label = self.trigger.value if hasattr(self.trigger, "value") else str(self.trigger)
        if not self.triggers:
            self.triggers = [self.trigger]
        if self.pct_distance == 0.0:
            self.pct_distance = self.pct_above

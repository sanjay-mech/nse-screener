"""
In-Memory Real-Time State Manager.
Maintains high-speed volatile state (levels, latest ticks, signals, metrics)
for instant API querying and scanning speed.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Dict, List, Optional, Set, Any
import pytz
from config.settings import settings
from signals.models import PrecomputedLevels, PriceTick, BreakoutSignal

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)

DEFAULT_SUBSCRIBED_TRIGGERS: Set[str] = {
    "ATH", "ATL", "52W_HIGH", "52W_LOW",
    "DC50_HIGH", "DC50_LOW", "DC20_HIGH", "DC20_LOW",
    "ST_DAILY_10_1_BUY", "ST_DAILY_10_1_SELL", "ST_DAILY_10_2_BUY", "ST_DAILY_10_2_SELL"
}


class StateManager:
    def __init__(self):
        self.levels: Dict[str, PrecomputedLevels] = {}
        self.latest_ticks: Dict[str, PriceTick] = {}
        self.today_signals: List[BreakoutSignal] = []
        self.is_paused: bool = False
        self.last_scan_time: Optional[datetime] = None
        self.last_scan_duration_ms: float = 0.0
        self.health_status: str = "INITIALIZING"
        self.last_error: Optional[str] = None
        self.active_universe: List[str] = []
        self.scan_callback: Optional[Any] = None
        self.subscribed_triggers: Set[str] = set(DEFAULT_SUBSCRIBED_TRIGGERS)

    def is_subscribed(self, trigger_id: str) -> bool:
        return trigger_id in self.subscribed_triggers

    def set_subscriptions(self, triggers: List[str]) -> None:
        self.subscribed_triggers = set(triggers)

    def set_levels(self, levels_map: Dict[str, PrecomputedLevels]) -> None:
        self.levels = levels_map

    def update_tick(self, tick: PriceTick) -> None:
        self.latest_ticks[tick.symbol] = tick

    def get_current_date(self) -> date:
        return datetime.now(KOLKATA_TZ).date()

    def record_signal(self, signal: BreakoutSignal) -> None:
        today = self.get_current_date()
        # Auto-purge older signals from prior days when a new day begins
        self.today_signals = [
            s for s in self.today_signals
            if getattr(s, "timestamp", None) and (
                s.timestamp.date() == today if hasattr(s.timestamp, "date") else True
            )
        ]
        self.today_signals.append(signal)

    def get_today_signals(self, target_date: Optional[date] = None) -> List[BreakoutSignal]:
        today = target_date or self.get_current_date()
        return [
            s for s in self.today_signals
            if getattr(s, "timestamp", None) and (
                s.timestamp.date() == today if hasattr(s.timestamp, "date") else True
            )
        ]

    def clear_today_signals(self) -> None:
        self.today_signals.clear()

    def clear_ticks(self) -> None:
        self.latest_ticks.clear()


state_manager = StateManager()

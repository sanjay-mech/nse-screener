"""
Alert Deduplicator and Re-Alert Manager.
Guarantees at most 1 alert per symbol per trigger type per calendar day,
while allowing optional re-alerts if the stock continues to rally (+X% above prior alert).
Survives process restarts via persistent database storage.
"""

from datetime import date
from typing import Dict, Tuple, Optional
from loguru import logger
from config.settings import settings
from signals.models import BreakoutSignal
from storage.repository import Repository


class AlertDeduplicator:
    def __init__(self, repository: Repository):
        self.repo = repository
        # In-memory fast cache: (symbol, date, trigger_label) -> highest_alerted_ltp
        self._cache: Dict[Tuple[str, date, str], float] = {}
        self._initialized: bool = False

    async def warm_up(self, today: Optional[date] = None) -> None:
        """Load today's already dispatched alerts from DB into cache."""
        if today is None:
            today = date.today()

        try:
            db_alerts = await self.repo.get_alerts_by_date(today)
            for alert in db_alerts:
                key = (alert.symbol, alert.alert_date, alert.trigger_types)
                prev_high = self._cache.get(key, 0.0)
                if alert.ltp > prev_high:
                    self._cache[key] = alert.ltp
            self._initialized = True
            logger.info(f"Alert deduplicator warmed up with {len(self._cache)} records for {today}.")
        except Exception as e:
            logger.warning(f"Could not warm up alert deduplicator: {e}")

    async def should_alert(self, signal: BreakoutSignal, today: Optional[date] = None) -> Tuple[bool, str]:
        """
        Determine if an alert should be dispatched.
        Returns: (should_send, reason)
        """
        if not settings.DEDUPLICATE_PER_DAY:
            return True, "Deduplication disabled"

        if today is None:
            today = date.today()

        key = (signal.symbol, today, signal.trigger_label)

        # Check in-memory cache
        if key in self._cache:
            last_alerted_ltp = self._cache[key]
            
            # Check re-alert eligibility
            if settings.ALLOW_RE_ALERT_ON_NEW_HIGH:
                pct_gain = ((signal.ltp - last_alerted_ltp) / last_alerted_ltp) * 100.0
                if pct_gain >= settings.RE_ALERT_THRESHOLD_PCT:
                    return True, f"Re-alert triggered (+{pct_gain:.2f}% above previous alert price ₹{last_alerted_ltp:.2f})"
                else:
                    return False, f"Already alerted today at ₹{last_alerted_ltp:.2f} (current gain {pct_gain:.2f}% < threshold {settings.RE_ALERT_THRESHOLD_PCT}%)"
            else:
                return False, f"Already alerted for {signal.trigger_label} today"

        # Check database directly if not in memory
        db_records = await self.repo.get_today_alerts_for_symbol(signal.symbol, today)
        for r in db_records:
            if r.trigger_types == signal.trigger_label:
                self._cache[key] = r.ltp
                if settings.ALLOW_RE_ALERT_ON_NEW_HIGH:
                    pct_gain = ((signal.ltp - r.ltp) / r.ltp) * 100.0
                    if pct_gain >= settings.RE_ALERT_THRESHOLD_PCT:
                        return True, f"Re-alert triggered (+{pct_gain:.2f}% above ₹{r.ltp:.2f})"
                    return False, f"Already logged in DB today at ₹{r.ltp:.2f}"
                return False, f"Already logged in DB today for {signal.trigger_label}"

        return True, "New breakout today"

    def record_alert_dispatched(self, signal: BreakoutSignal, today: Optional[date] = None) -> None:
        """Update cache upon successful dispatch."""
        if today is None:
            today = date.today()
        key = (signal.symbol, today, signal.trigger_label)
        self._cache[key] = max(self._cache.get(key, 0.0), signal.ltp)

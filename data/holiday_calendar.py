"""
NSE Market Holiday Calendar and Market Hours Validator.
Supports dynamic fetch with comprehensive hardcoded fallback for 2025, 2026, and 2027.
"""

from datetime import datetime, date, time
from typing import Set, Optional
import pytz
import httpx
from loguru import logger
from config.settings import settings

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)

# Known NSE Trading Holidays (Equities & Equity Derivatives)
# Format: YYYY-MM-DD
NSE_HOLIDAYS_FALLBACK: Set[str] = {
    # 2025
    "2025-02-26",  # Mahashivratri
    "2025-03-14",  # Holi
    "2025-03-31",  # Id-Ul-Fitr
    "2025-04-10",  # Mahavir Jayanti
    "2025-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Ganesh Chaturthi
    "2025-10-02",  # Mahatma Gandhi Jayanti / Dussehra
    "2025-10-21",  # Diwali Laxmi Pujan (Muhurat trading evening only)
    "2025-10-22",  # Diwali Balipratipada
    "2025-11-05",  # Prakash Gurpurb Sri Guru Nanak Dev
    "2025-12-25",  # Christmas
    # 2026
    "2026-01-26",  # Republic Day
    "2026-02-17",  # Mahashivratri
    "2026-03-04",  # Holi
    "2026-03-20",  # Id-Ul-Fitr
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-27",  # Bakri Id
    "2026-08-15",  # Independence Day (Saturday)
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-09",  # Diwali Laxmi Pujan
    "2026-11-10",  # Diwali Balipratipada
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
    # 2027
    "2027-01-26",  # Republic Day
    "2027-03-08",  # Mahashivratri
    "2027-03-23",  # Holi
    "2027-03-26",  # Good Friday
    "2027-04-14",  # Ambedkar Jayanti
    "2027-05-01",  # Maharashtra Day
    "2027-08-15",  # Independence Day
    "2027-10-02",  # Gandhi Jayanti
    "2027-10-11",  # Dussehra
    "2027-10-29",  # Diwali
    "2027-12-25",  # Christmas
}


class HolidayCalendar:
    def __init__(self):
        self.holidays: Set[str] = set(NSE_HOLIDAYS_FALLBACK)
        self.last_fetch: Optional[datetime] = None

    async def refresh_holidays_from_nse(self) -> None:
        """Attempt to fetch live holiday list from NSE API."""
        url = "https://www.nseindia.com/api/holiday-master?type=trading"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # CM = Capital Market / Equities
                    cm_holidays = data.get("CM", [])
                    for item in cm_holidays:
                        h_date_str = item.get("tradingDate")
                        if h_date_str:
                            try:
                                d = datetime.strptime(h_date_str, "%d-%b-%Y").strftime("%Y-%m-%d")
                                self.holidays.add(d)
                            except Exception:
                                pass
                    self.last_fetch = datetime.utcnow()
                    logger.info("Successfully refreshed NSE holiday calendar.")
        except Exception as e:
            logger.warning(f"Could not refresh NSE holiday master, using fallback calendar: {e}")

    def is_holiday(self, check_date: date) -> bool:
        date_str = check_date.strftime("%Y-%m-%d")
        return date_str in self.holidays

    def is_weekend(self, check_date: date) -> bool:
        # 5 = Saturday, 6 = Sunday
        return check_date.weekday() in (5, 6)

    def is_trading_day(self, check_date: date) -> bool:
        if self.is_weekend(check_date):
            return False
        if settings.SKIP_HOLIDAYS and self.is_holiday(check_date):
            return False
        return True

    def is_market_open(self, now: Optional[datetime] = None) -> bool:
        """
        Check if Indian equity market is currently within trading hours (09:15 - 15:30 IST).
        """
        if now is None:
            now = datetime.now(KOLKATA_TZ)
        else:
            if now.tzinfo is None:
                now = KOLKATA_TZ.localize(now)
            else:
                now = now.astimezone(KOLKATA_TZ)

        current_date = now.date()
        if not self.is_trading_day(current_date):
            return False

        current_time = now.time()
        start_time = datetime.strptime(settings.TRADING_START, "%H:%M:%S").time()
        end_time = datetime.strptime(settings.TRADING_END, "%H:%M:%S").time()

        return start_time <= current_time <= end_time


holiday_calendar = HolidayCalendar()

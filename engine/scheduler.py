"""
Scheduler and Orchestration Engine.
Manages timed tasks via APScheduler:
- 08:30 IST: Universe refresh and levels pre-computation
- 09:10 IST: Pre-market watchlist broadcast (stocks near breakout levels)
- 09:15 - 15:30 IST: High-frequency scanner loop (every 30-60s)
- 15:45 IST: End-of-day summary with close confirmation
- 16:30 IST: Post-market historical database update
"""

from __future__ import annotations
import asyncio
from datetime import datetime, date
from typing import Dict, List, Tuple
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from config.settings import settings
from data.universe import universe_manager
from data.yahoo_client import yahoo_client
from data.corporate_actions import corporate_action_detector
from data.holiday_calendar import holiday_calendar
from signals.level_calculator import compute_levels_for_symbol
from data.sectors import get_stock_sector
from signals.breakout_detector import breakout_detector
from signals.models import PrecomputedLevels, PriceTick
from alerts.formatter import (
    format_premarket_summary,
    format_eod_summary,
    format_heartbeat_alert
)
from alerts.telegram_bot import TelegramBot
from alerts.deduplicator import AlertDeduplicator
from storage.repository import Repository
from engine.state_manager import state_manager
from engine.scanner import BreakoutScanner

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


class ScreenerEngine:
    def __init__(
        self,
        repository: Repository,
        telegram_bot: TelegramBot,
        deduplicator: AlertDeduplicator,
        scanner: BreakoutScanner
    ):
        self.repo = repository
        self.bot = telegram_bot
        self.deduplicator = deduplicator
        self.scanner = scanner
        self.scheduler = AsyncIOScheduler(timezone=KOLKATA_TZ)
        state_manager.scan_callback = self.scanner.scan_once

    async def warm_up(self) -> None:
        """Startup warm-up: load universe, warm up deduplicator, compute/load levels."""
        logger.info("Initializing Screener Engine warm-up...")
        
        # 1. Start Telegram bot
        await self.bot.start()

        # Connect bot hooks
        self.bot.status_provider = self._get_status_dict
        self.bot.pause_callback = lambda: setattr(state_manager, "is_paused", True)
        self.bot.resume_callback = lambda: setattr(state_manager, "is_paused", False)

        # 2. Warm up deduplicator
        today = datetime.now(KOLKATA_TZ).date()
        state_manager.clear_today_signals()
        await self.deduplicator.warm_up(today)

        # 2b. Load saved alert subscriptions
        saved_subs = await self.repo.get_state("ALERT_SUBSCRIPTIONS")
        if saved_subs:
            try:
                import json
                sub_list = json.loads(saved_subs)
                state_manager.set_subscriptions(sub_list)
                logger.info(f"Loaded {len(sub_list)} active alert subscriptions from database.")
            except Exception as e:
                logger.warning(f"Failed to load subscriptions: {e}")

        # 3. Load universe
        symbols = await universe_manager.get_symbols(force_refresh=settings.auto_refresh_on_startup if hasattr(settings, "auto_refresh_on_startup") else False)
        state_manager.active_universe = symbols
        logger.info(f"Loaded {len(symbols)} symbols into active universe.")

        # 4. Check if levels exist in database for today, or compute them
        db_levels = await self.repo.get_all_stock_levels()
        levels_map: Dict[str, PrecomputedLevels] = {}

        if db_levels and db_levels[0].calculated_date == today and len(db_levels) >= len(symbols) * 0.8:
            logger.info(f"Found {len(db_levels)} valid precomputed levels for today in database.")
            for row in db_levels:
                levels_map[row.symbol] = PrecomputedLevels(
                    symbol=row.symbol,
                    calculated_date=row.calculated_date,
                    ath_high=row.ath_high,
                    ath_date=row.ath_date,
                    high_52w=row.high_52w,
                    high_52w_date=row.high_52w_date,
                    donchian_50_high=row.donchian_50_high,
                    donchian_50_date=row.donchian_50_date,
                    donchian_20_high=getattr(row, "donchian_20_high", 0.0),
                    donchian_20_high_date=getattr(row, "donchian_20_high_date", None),
                    atl_low=getattr(row, "atl_low", 0.0),
                    atl_date=getattr(row, "atl_date", None),
                    low_52w=getattr(row, "low_52w", 0.0),
                    low_52w_date=getattr(row, "low_52w_date", None),
                    donchian_50_low=getattr(row, "donchian_50_low", 0.0),
                    donchian_50_low_date=getattr(row, "donchian_50_low_date", None),
                    donchian_20_low=getattr(row, "donchian_20_low", 0.0),
                    donchian_20_low_date=getattr(row, "donchian_20_low_date", None),
                    avg_vol_20d=row.avg_vol_20d,
                    atr_20d=row.atr_20d,
                    last_close=row.last_close,
                    sector=row.sector if (row.sector and row.sector != "N/A") else get_stock_sector(row.symbol),
                    st_daily_10_1_val=getattr(row, "st_daily_10_1_val", 0.0),
                    st_daily_10_1_dir=getattr(row, "st_daily_10_1_dir", 1),
                    st_daily_10_2_val=getattr(row, "st_daily_10_2_val", 0.0),
                    st_daily_10_2_dir=getattr(row, "st_daily_10_2_dir", 1),
                    st_15m_10_1_val=getattr(row, "st_15m_10_1_val", 0.0),
                    st_15m_10_1_dir=getattr(row, "st_15m_10_1_dir", 1),
                    st_15m_10_2_val=getattr(row, "st_15m_10_2_val", 0.0),
                    st_15m_10_2_dir=getattr(row, "st_15m_10_2_dir", 1)
                )
            state_manager.set_levels(levels_map)
        else:
            logger.info("Precomputed levels not found or outdated. Running levels builder...")
            await self.rebuild_levels()

        state_manager.health_status = "READY"
        logger.info("Screener Engine warm-up complete.")

        # Immediately execute an initial scan to populate live quotes across active universe (silent warmup)
        logger.info("Executing initial live market scan...")
        asyncio.create_task(self.scanner.scan_once(force_execution=True, is_warmup=True))

    def _get_status_dict(self) -> Dict[str, any]:
        return {
            "state": "PAUSED" if state_manager.is_paused else state_manager.health_status,
            "market_open": holiday_calendar.is_market_open(),
            "universe_size": len(state_manager.active_universe),
            "last_scan": str(state_manager.last_scan_time) if state_manager.last_scan_time else "Never",
            "last_scan_duration_ms": state_manager.last_scan_duration_ms,
            "today_alerts_count": len(state_manager.today_signals)
        }

    async def rebuild_levels(self) -> None:
        """Download historical adjusted data and precompute breakout levels."""
        symbols = state_manager.active_universe or await universe_manager.get_symbols()
        if not symbols:
            return

        logger.info(f"Rebuilding breakout levels and Supertrend for {len(symbols)} symbols...")
        hist_data = await yahoo_client.fetch_historical_daily(symbols, period="max")
        hist_15m = await yahoo_client.fetch_15m_history(symbols, period="5d")
        today = datetime.now(KOLKATA_TZ).date()
        state_manager.clear_today_signals()

        levels_list_for_db = []
        levels_map: Dict[str, PrecomputedLevels] = {}

        for sym, df in hist_data.items():
            # Check for corporate action discontinuities
            has_gap, gap_reason = corporate_action_detector.check_discontinuity(sym, df)
            if has_gap:
                logger.warning(f"Re-pulling clean history for {sym} due to: {gap_reason}")

            df_15 = hist_15m.get(sym)
            lvl = compute_levels_for_symbol(sym, df, as_of_date=today, sector=get_stock_sector(sym), df_15m=df_15)
            if lvl:
                levels_map[sym] = lvl
                levels_list_for_db.append({
                    "symbol": lvl.symbol,
                    "calculated_date": today,
                    "ath_high": lvl.ath_high,
                    "ath_date": lvl.ath_date,
                    "high_52w": lvl.high_52w,
                    "high_52w_date": lvl.high_52w_date,
                    "donchian_50_high": lvl.donchian_50_high,
                    "donchian_50_date": lvl.donchian_50_date,
                    "donchian_20_high": lvl.donchian_20_high,
                    "donchian_20_high_date": lvl.donchian_20_high_date,
                    "atl_low": lvl.atl_low,
                    "atl_date": lvl.atl_date,
                    "low_52w": lvl.low_52w,
                    "low_52w_date": lvl.low_52w_date,
                    "donchian_50_low": lvl.donchian_50_low,
                    "donchian_50_low_date": lvl.donchian_50_low_date,
                    "donchian_20_low": lvl.donchian_20_low,
                    "donchian_20_low_date": lvl.donchian_20_low_date,
                    "avg_vol_20d": lvl.avg_vol_20d,
                    "atr_20d": lvl.atr_20d,
                    "last_close": lvl.last_close,
                    "sector": lvl.sector,
                    "is_fno": True,
                    "st_daily_10_1_val": lvl.st_daily_10_1_val,
                    "st_daily_10_1_dir": lvl.st_daily_10_1_dir,
                    "st_daily_10_2_val": lvl.st_daily_10_2_val,
                    "st_daily_10_2_dir": lvl.st_daily_10_2_dir,
                    "st_15m_10_1_val": lvl.st_15m_10_1_val,
                    "st_15m_10_1_dir": lvl.st_15m_10_1_dir,
                    "st_15m_10_2_val": lvl.st_15m_10_2_val,
                    "st_15m_10_2_dir": lvl.st_15m_10_2_dir
                })

        if levels_list_for_db:
            await self.repo.bulk_upsert_stock_levels(levels_list_for_db)
            state_manager.set_levels(levels_map)
            logger.info(f"Successfully precomputed and saved levels for {len(levels_map)} symbols.")

    async def send_premarket_alert(self) -> None:
        """09:10 IST Pre-Market Broadcast: stocks within 1% of key levels."""
        today = datetime.now(KOLKATA_TZ).date()
        if not holiday_calendar.is_trading_day(today):
            return

        logger.info("Compiling 09:10 pre-market watchlist...")
        near_stocks: List[Tuple[str, str, float, float]] = []

        for sym, lvl in state_manager.levels.items():
            # Use last close to assess proximity
            dummy_tick = PriceTick(
                symbol=sym,
                ltp=lvl.last_close,
                day_high=lvl.last_close,
                day_low=lvl.last_close,
                day_open=lvl.last_close,
                prev_close=lvl.last_close,
                p_change=0.0,
                volume=0,
                turnover_cr=0.0
            )
            near_info = breakout_detector.is_near_breakout(dummy_tick, lvl)
            if near_info:
                name, target_lvl, dist = near_info
                near_stocks.append((sym, name, target_lvl, dist))

        near_stocks.sort(key=lambda x: x[3])
        msg = format_premarket_summary(near_stocks)
        await self.bot.broadcast_alert(msg)

    async def send_eod_summary(self) -> None:
        """15:45 IST End-Of-Day Summary with Candle-Close confirmation."""
        today = datetime.now(KOLKATA_TZ).date()
        if not holiday_calendar.is_trading_day(today):
            return

        logger.info("Generating 15:45 End-Of-Day summary...")
        today_alerts = await self.repo.get_alerts_by_date(today)
        close_confirmed: List[str] = []

        # Validate which breakouts closed strictly above their breakout levels
        for a in today_alerts:
            latest_tick = state_manager.latest_ticks.get(a.symbol)
            if latest_tick and latest_tick.ltp > a.level_broken:
                close_confirmed.append(a.symbol)
                await self.repo.update_alert_confirmed_close(a.symbol, today, confirmed=True)

        close_confirmed = list(dict.fromkeys(close_confirmed))
        # Strictly use today's signals or today's DB records, never multi-day accumulation
        today_signals = state_manager.get_today_signals(today)
        alerts_to_report = today_signals if today_signals else today_alerts
        msg = format_eod_summary(alerts_to_report, close_confirmed)
        await self.bot.broadcast_alert(msg)

    async def daily_reset(self) -> None:
        """Midnight rollover: reset today's signals, cached ticks, and deduplicator for the new date."""
        today = datetime.now(KOLKATA_TZ).date()
        logger.info(f"Running daily state rollover for {today}...")
        state_manager.clear_today_signals()
        state_manager.clear_ticks()
        await self.deduplicator.warm_up(today)

    async def heartbeat_check(self) -> None:
        """Periodic health check and heartbeat."""
        status = state_manager.health_status
        active_count = len(state_manager.active_universe)
        latency = state_manager.last_scan_duration_ms
        if status == "ERROR":
            msg = format_heartbeat_alert(status, active_count, latency, state_manager.last_error or "")
            await self.bot.send_admin_alert(msg)

    def start_schedules(self) -> None:
        """Configure and start APScheduler cron and interval triggers."""
        # Midnight daily reset at 00:01 IST (every day)
        self.scheduler.add_job(
            self.daily_reset,
            CronTrigger(hour=0, minute=1, timezone=KOLKATA_TZ),
            id="job_daily_reset"
        )

        # Pre-open levels rebuild at 08:30 IST (Mon-Fri)
        self.scheduler.add_job(
            self.rebuild_levels,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=KOLKATA_TZ),
            id="job_rebuild_levels"
        )

        # Pre-market summary at 09:10 IST (Mon-Fri)
        self.scheduler.add_job(
            self.send_premarket_alert,
            CronTrigger(day_of_week="mon-fri", hour=9, minute=10, timezone=KOLKATA_TZ),
            id="job_premarket_summary"
        )

        # Real-time scanning loop during market hours (every POLL_INTERVAL_SEC)
        self.scheduler.add_job(
            self.scanner.scan_once,
            IntervalTrigger(seconds=settings.POLL_INTERVAL_SEC, timezone=KOLKATA_TZ),
            id="job_realtime_scanner"
        )

        # EOD Summary at 15:45 IST (Mon-Fri)
        self.scheduler.add_job(
            self.send_eod_summary,
            CronTrigger(day_of_week="mon-fri", hour=15, minute=45, timezone=KOLKATA_TZ),
            id="job_eod_summary"
        )

        # Post-market refresh at 16:30 IST (Mon-Fri)
        self.scheduler.add_job(
            self.rebuild_levels,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=KOLKATA_TZ),
            id="job_post_market_refresh"
        )

        # Heartbeat check every 15 minutes
        self.scheduler.add_job(
            self.heartbeat_check,
            IntervalTrigger(minutes=15, timezone=KOLKATA_TZ),
            id="job_heartbeat"
        )

        self.scheduler.start()
        logger.info(f"Scheduler started. Scanner polling interval: {settings.POLL_INTERVAL_SEC}s.")

    async def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        await self.bot.stop()
        logger.info("Screener Engine shut down.")

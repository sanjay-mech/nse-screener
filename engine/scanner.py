"""
Core Real-Time Breakout Scanner Engine.
Executes high-speed scanning cycles across the entire NSE F&O universe.
Handles multi-source data acquisition, cross-validation, breakout detection,
deduplication, and alert dispatch.
"""

from __future__ import annotations
import asyncio
import time
from datetime import datetime, date
from typing import Dict, List, Optional
import pytz
from loguru import logger

from config.settings import settings
from data.holiday_calendar import holiday_calendar
from data.nse_client import nse_client
from data.yahoo_client import yahoo_client
from signals.models import PriceTick, PrecomputedLevels, BreakoutSignal
from signals.breakout_detector import breakout_detector
from signals.validator import signal_validator
from alerts.formatter import format_breakout_alert
from alerts.deduplicator import AlertDeduplicator
from alerts.telegram_bot import TelegramBot
from storage.repository import Repository
from engine.state_manager import state_manager

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


class BreakoutScanner:
    def __init__(
        self,
        repository: Repository,
        telegram_bot: TelegramBot,
        deduplicator: AlertDeduplicator
    ):
        self.repo = repository
        self.bot = telegram_bot
        self.deduplicator = deduplicator

    async def scan_once(self, force_execution: bool = False, is_warmup: bool = False) -> List[BreakoutSignal]:
        """
        Execute a single real-time scan cycle across all tracked F&O stocks.
        Returns list of newly triggered signals in this cycle.
        If is_warmup=True, live ticks are cached and deduplicator is primed without dispatching Telegram alerts.
        """
        start_time = time.time()
        now_dt = datetime.now(KOLKATA_TZ)
        today = now_dt.date()

        # Check if scanner is paused
        if state_manager.is_paused:
            logger.debug("Scanner is paused by user command. Skipping scan cycle.")
            return []

        # Market hours check
        if not force_execution and not holiday_calendar.is_market_open(now_dt):
            logger.debug("Market is closed. Skipping real-time scan cycle.")
            state_manager.health_status = "MARKET_CLOSED"
            return []

        symbols = state_manager.active_universe
        if not symbols or not state_manager.levels:
            logger.info("Active universe or levels not yet in memory. Auto-loading from cache and database...")
            if not symbols:
                from data.universe import universe_manager
                symbols = await universe_manager.get_symbols()
                state_manager.active_universe = symbols
            if not state_manager.levels:
                db_levels = await self.repo.get_all_stock_levels()
                if db_levels:
                    levels_map = {}
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
                            sector=row.sector,
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
            if not symbols or not state_manager.levels:
                logger.warning("Still no active universe or levels available. Skipping scan cycle.")
                return []

        state_manager.health_status = "SCANNING"
        triggered_signals: List[BreakoutSignal] = []

        try:
            # 1. Fetch live quotes from primary feed (NSE Bulk F&O)
            nse_ticks = await nse_client.fetch_all_fno_quotes()
            used_source = "NSE_BULK"

            # 2. Check if primary feed failed or was empty -> fallback to Yahoo
            min_expected = min(5, len(symbols))
            if not nse_ticks or len(nse_ticks) < min_expected:
                logger.warning(f"NSE bulk feed returned insufficient data ({len(nse_ticks)} < {min_expected}). Falling back to Yahoo Finance intraday...")
                prev_closes = {s: lvl.last_close for s, lvl in state_manager.levels.items() if lvl.last_close > 0}
                yahoo_ticks = await yahoo_client.fetch_intraday_fallback(symbols, prev_closes=prev_closes)
                ticks_to_process = yahoo_ticks
                used_source = "LIVE (YAHOO)"
            else:
                ticks_to_process = nse_ticks
                # If cross-validation is enabled, fetch secondary quotes for validation
                yahoo_ticks = {}
                if settings.ENABLE_CROSS_VALIDATION:
                    # Sample or fetch when a potential breakout is detected
                    pass

            # 3. Process every symbol against precomputed levels
            for sym in symbols:
                tick = ticks_to_process.get(sym)
                if not tick:
                    continue

                # Freshness validation
                is_fresh, freshness_err = signal_validator.validate_tick_freshness(tick)
                if not is_fresh:
                    continue

                levels = state_manager.levels.get(sym)
                if levels and levels.last_close > 0:
                    tick.prev_close = levels.last_close
                    tick.p_change = round(((tick.ltp - levels.last_close) / levels.last_close) * 100, 2)

                state_manager.update_tick(tick)

                if not levels:
                    continue

                # 4. Breakout Detection (Evaluates all Buy & Sell conditions separately)
                signals = breakout_detector.evaluate_breakouts(tick, levels)
                if not signals:
                    continue

                for signal in signals:
                    # 4b. Alert Subscription Check (Only dispatch if user subscribed to this screener)
                    trig_key = signal.trigger.value if hasattr(signal.trigger, "value") else str(signal.trigger)
                    if not state_manager.is_subscribed(trig_key) and not state_manager.is_subscribed(signal.trigger_label):
                        continue

                    # 5. Cross-Validation (Guard against bad ticks)
                    if settings.ENABLE_CROSS_VALIDATION and used_source == "NSE_BULK":
                        sec_tick_map = await yahoo_client.fetch_intraday_fallback([sym])
                        sec_tick = sec_tick_map.get(sym)
                        is_valid, div_pct, div_err = signal_validator.cross_validate_quotes(tick, sec_tick)
                        if not is_valid:
                            logger.warning(f"Skipping alert for {sym} due to bad tick / price mismatch ({div_pct:.2f}%)")
                            continue

                    # 6. Deduplication and Re-Alert Check (per symbol and separate trigger)
                    should_alert, reason = await self.deduplicator.should_alert(signal, today)
                    if not should_alert:
                        logger.debug(f"[{sym}] Suppressed alert for {signal.trigger_label}: {reason}")
                        continue

                    # 7. Dispatch Alert (Only on live scanning, never during warm-up)
                    html_msg = format_breakout_alert(signal)
                    state_manager.record_signal(signal)
                    triggered_signals.append(signal)

                    if not is_warmup:
                        logger.info(f"🚨 LIVE ALERT CONFIRMED: {sym} -> {signal.side} {signal.title} at ₹{signal.ltp:,.2f} ({reason})")
                        await self.bot.broadcast_alert(html_msg, trigger=signal.trigger_label)
                        self.deduplicator.record_alert_dispatched(signal, today)
                        await self.repo.log_alert({
                            "symbol": signal.symbol,
                            "alert_date": today,
                            "alert_time": datetime.utcnow(),
                            "side": signal.side,
                            "trigger_types": signal.trigger_label,
                            "trigger_mode": signal.trigger_mode,
                            "ltp": signal.ltp,
                            "pct_change": signal.pct_change,
                            "level_broken": signal.level_broken,
                            "pct_above": signal.pct_distance,
                            "prior_high_date": signal.prior_high_date,
                            "rvol": signal.rvol,
                            "atr_20": signal.atr_20,
                            "sector": signal.sector,
                            "ban_status": signal.ban_status,
                            "message_sent": html_msg,
                            "confirmed_close": False
                        })
                    else:
                        # Warmup mode: cache live quotes only, never suppress today's pending alerts
                        logger.debug(f"[WARMUP] Cached live move for {sym} ({signal.title}) without consuming alert")

            duration_ms = (time.time() - start_time) * 1000.0
            state_manager.last_scan_time = datetime.utcnow()
            state_manager.last_scan_duration_ms = duration_ms
            state_manager.health_status = "HEALTHY"
            logger.info(
                f"Scan cycle complete in {duration_ms:.1f}ms | Processed: {len(ticks_to_process)} | "
                f"Breakouts: {len(triggered_signals)}"
            )

        except Exception as e:
            state_manager.health_status = "ERROR"
            state_manager.last_error = str(e)
            logger.error(f"Error during scan cycle: {e}", exc_info=True)
            await self.bot.send_admin_alert(f"⚠️ <b>Scanner Error</b>: <code>{str(e)}</code>")

        return triggered_signals

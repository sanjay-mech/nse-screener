"""
Async Telegram Bot API Client and Interactive Commands Engine.
Features:
- Outbound message queue with strict rate-limiting (20 msgs/sec)
- Automatic retry with exponential backoff on HTTP 429 (Too Many Requests)
- Multi-recipient broadcasting (channels, groups, user chats)
- Admin alert channel for system errors
- Interactive command polling: /status, /today, /watch, /unwatch, /levels, /pause, /resume
"""

from __future__ import annotations
import asyncio
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Callable
import httpx
from loguru import logger
from config.settings import settings
from data.symbol_mapper import nse_to_yahoo_ticker
from storage.repository import Repository


class TelegramBot:
    def __init__(self, repository: Repository):
        self.repo = repository
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self._client: Optional[httpx.AsyncClient] = None
        self._outbound_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._last_update_id: int = 0

        # Command hooks (injected by engine)
        self.status_provider: Optional[Callable[[], Dict[str, Any]]] = None
        self.pause_callback: Optional[Callable[[], None]] = None
        self.resume_callback: Optional[Callable[[], None]] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def start(self) -> None:
        """Start the background rate-limited outbound message worker and command listener."""
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN is not set. Telegram alerts will be skipped.")
            return

        self._running = True
        # Drain any residual messages in queue so stale alerts are never sent on startup
        while not self._outbound_queue.empty():
            try:
                self._outbound_queue.get_nowait()
                self._outbound_queue.task_done()
            except Exception:
                break

        self._worker_task = asyncio.create_task(self._queue_worker())
        self._poll_task = asyncio.create_task(self._command_poller())
        logger.info("Telegram Bot service started successfully.")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
        if self._poll_task:
            self._poll_task.cancel()
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        logger.info("Telegram Bot service stopped.")

    async def _queue_worker(self) -> None:
        """Processes outgoing Telegram messages respecting rate limits."""
        client = await self._get_client()
        rate_limit_delay = 1.0 / 20.0  # max 20 messages per second

        while self._running:
            try:
                chat_id, text, parse_mode = await self._outbound_queue.get()
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True
                }

                # Attempt send with retries
                max_retries = getattr(settings, "MAX_TELEGRAM_RETRIES", 4)
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = await client.post(f"{self.base_url}/sendMessage", json=payload)
                        if resp.status_code == 200:
                            break
                        elif resp.status_code == 429:
                            retry_after = float(resp.json().get("parameters", {}).get("retry_after", 3.0))
                            logger.warning(f"Telegram 429 Rate Limit. Sleeping {retry_after}s")
                            await asyncio.sleep(retry_after)
                        else:
                            logger.warning(f"Telegram API error {resp.status_code}: {resp.text}")
                    except Exception as e:
                        logger.warning(f"Error sending telegram message: {e}")
                    await asyncio.sleep(0.5 * attempt)

                self._outbound_queue.task_done()
                await asyncio.sleep(rate_limit_delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telegram queue worker: {e}")
                await asyncio.sleep(1.0)

    async def broadcast_alert(self, html_text: str, trigger: Optional[str] = None) -> None:
        """
        Enqueue alert message to the appropriate Telegram channel based on trigger type:
        - 52-Week High/Low and ATH/ATL -> TELEGRAM_CHANNEL_ATH_52W (-1004490443970)
        - Donchian Channels (DC) and Supertrend (ST) -> TELEGRAM_CHANNEL_DC_ST (-1004314287084)
        - Admin Chat ID (1016641982) receives all alerts if configured
        - General broadcast (trigger is None) goes to both channels
        """
        if not self.token:
            return

        target_chats = set()

        if trigger:
            trig_upper = trigger.upper()
            # 1. 52-Week & ATH / ATL
            if any(k in trig_upper for k in ["ATH", "ATL", "52W"]):
                if settings.TELEGRAM_CHANNEL_ATH_52W:
                    target_chats.add(settings.TELEGRAM_CHANNEL_ATH_52W.strip())
            # 2. Donchian & Supertrend
            elif any(k in trig_upper for k in ["DC", "DONCHIAN", "ST", "SUPERTREND"]):
                if settings.TELEGRAM_CHANNEL_DC_ST:
                    target_chats.add(settings.TELEGRAM_CHANNEL_DC_ST.strip())
            else:
                if settings.TELEGRAM_CHANNEL_ATH_52W:
                    target_chats.add(settings.TELEGRAM_CHANNEL_ATH_52W.strip())
                elif settings.TELEGRAM_CHANNEL_DC_ST:
                    target_chats.add(settings.TELEGRAM_CHANNEL_DC_ST.strip())
        else:
            if settings.TELEGRAM_CHANNEL_ATH_52W:
                target_chats.add(settings.TELEGRAM_CHANNEL_ATH_52W.strip())
            if settings.TELEGRAM_CHANNEL_DC_ST:
                target_chats.add(settings.TELEGRAM_CHANNEL_DC_ST.strip())

        # If neither channel was configured, fall back to telegram_chat_ids
        if not target_chats:
            target_chats = set(settings.telegram_chat_ids)

        # Admin receives all alerts
        if settings.ADMIN_CHAT_ID:
            target_chats.add(settings.ADMIN_CHAT_ID.strip())

        for chat_id in target_chats:
            await self._outbound_queue.put((chat_id, html_text, "HTML"))

    async def send_admin_alert(self, text: str) -> None:
        """Send critical system or error alert to admin chat."""
        if not self.token or not settings.ADMIN_CHAT_ID:
            return
        await self._outbound_queue.put((settings.ADMIN_CHAT_ID, text, "HTML"))

    def _is_chat_authorized(self, chat_id: str) -> bool:
        """Verify if the sender has permission to execute bot commands."""
        authorized = set(settings.telegram_chat_ids)
        if settings.ADMIN_CHAT_ID:
            authorized.add(str(settings.ADMIN_CHAT_ID))
        return str(chat_id) in authorized

    async def _handle_command(self, chat_id: str, command_text: str) -> None:
        """Process incoming slash commands."""
        parts = command_text.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1:]

        if not self._is_chat_authorized(chat_id):
            await self._outbound_queue.put(
                (chat_id, "⛔ <i>Unauthorized chat ID. Access denied.</i>", "HTML")
            )
            return

        if cmd in ("/status", "/health"):
            status_data = self.status_provider() if self.status_provider else {}
            msg = (
                f"📊 <b>SYSTEM STATUS</b>\n"
                f"State: <b>{status_data.get('state', 'RUNNING')}</b>\n"
                f"Market Open: <b>{status_data.get('market_open', False)}</b>\n"
                f"Tracked Symbols: <b>{status_data.get('universe_size', 0)}</b>\n"
                f"Last Scan: <b>{status_data.get('last_scan', 'N/A')}</b>\n"
                f"Scan Duration: <b>{status_data.get('last_scan_duration_ms', 0):.1f}ms</b>\n"
                f"Today's Breakouts: <b>{status_data.get('today_alerts_count', 0)}</b>"
            )
            await self._outbound_queue.put((chat_id, msg, "HTML"))

        elif cmd == "/today":
            today_alerts = await self.repo.get_alerts_by_date(date.today())
            if not today_alerts:
                await self._outbound_queue.put(
                    (chat_id, "ℹ️ <i>No breakout signals recorded today yet.</i>", "HTML")
                )
                return

            lines = [f"📋 <b>TODAY'S BREAKOUT ALERTS ({len(today_alerts)})</b>:\n"]
            for a in today_alerts[:25]:
                lines.append(f"• <b>{a.symbol}</b> ({a.trigger_types}) @ ₹{a.ltp:,.2f} (+{a.pct_above:.1f}%)")
            await self._outbound_queue.put((chat_id, "\n".join(lines), "HTML"))

        elif cmd == "/watch":
            if not args:
                await self._outbound_queue.put((chat_id, "Usage: <code>/watch SYMBOL</code>", "HTML"))
                return
            sym = args[0].upper()
            await self.repo.add_to_watchlist(sym, added_by=chat_id)
            await self._outbound_queue.put((chat_id, f"✅ Added <b>{sym}</b> to custom watchlist.", "HTML"))

        elif cmd == "/unwatch":
            if not args:
                await self._outbound_queue.put((chat_id, "Usage: <code>/unwatch SYMBOL</code>", "HTML"))
                return
            sym = args[0].upper()
            removed = await self.repo.remove_from_watchlist(sym)
            if removed:
                await self._outbound_queue.put((chat_id, f"🗑️ Removed <b>{sym}</b> from watchlist.", "HTML"))
            else:
                await self._outbound_queue.put((chat_id, f"⚠️ <b>{sym}</b> not found in watchlist.", "HTML"))

        elif cmd == "/levels":
            if not args:
                await self._outbound_queue.put((chat_id, "Usage: <code>/levels SYMBOL</code>", "HTML"))
                return
            sym = args[0].upper()
            lvl = await self.repo.get_stock_level(sym)
            if not lvl:
                await self._outbound_queue.put(
                    (chat_id, f"⚠️ No precomputed levels found for <b>{sym}</b>.", "HTML")
                )
                return

            msg = (
                f"🎯 <b>BREAKOUT LEVELS | {sym}</b>\n"
                f"ATH High: <b>₹{lvl.ath_high:,.2f}</b> (Date: {lvl.ath_date})\n"
                f"52W High: <b>₹{lvl.high_52w:,.2f}</b> (Date: {lvl.high_52w_date})\n"
                f"Donchian 50: <b>₹{lvl.donchian_50_high:,.2f}</b> (Date: {lvl.donchian_50_date})\n"
                f"Prior Close: <b>₹{lvl.last_close:,.2f}</b>\n"
                f"20D Avg Vol: <b>{int(lvl.avg_vol_20d):,}</b> | 20D ATR: <b>₹{lvl.atr_20d:.2f}</b>"
            )
            await self._outbound_queue.put((chat_id, msg, "HTML"))

        elif cmd == "/pause":
            if self.pause_callback:
                self.pause_callback()
            await self.repo.set_state("SCANNER_PAUSED", "true")
            await self._outbound_queue.put((chat_id, "⏸️ <b>Screener paused.</b> No alerts will be sent.", "HTML"))

        elif cmd == "/resume":
            if self.resume_callback:
                self.resume_callback()
            await self.repo.set_state("SCANNER_PAUSED", "false")
            await self._outbound_queue.put((chat_id, "▶️ <b>Screener resumed.</b> Real-time monitoring active.", "HTML"))

        else:
            help_text = (
                "🤖 <b>Available Commands:</b>\n"
                "/status - Check scanner state & health\n"
                "/today - View today's breakouts\n"
                "/levels SYMBOL - Show ATH, 52W & Donchian levels\n"
                "/watch SYMBOL - Add stock to watchlist\n"
                "/unwatch SYMBOL - Remove stock from watchlist\n"
                "/pause - Pause alerts\n"
                "/resume - Resume alerts"
            )
            await self._outbound_queue.put((chat_id, help_text, "HTML"))

    async def _command_poller(self) -> None:
        """Long-poll getUpdates from Telegram for interactive commands."""
        client = await self._get_client()

        while self._running:
            try:
                params = {
                    "offset": self._last_update_id + 1,
                    "timeout": 20,
                    "allowed_updates": ["message"]
                }
                resp = await client.get(f"{self.base_url}/getUpdates", params=params, timeout=25.0)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self._last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        if text.startswith("/"):
                            await self._handle_command(chat_id, text)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Telegram poll error: {e}")
                await asyncio.sleep(5.0)

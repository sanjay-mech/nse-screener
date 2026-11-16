"""
Background Worker Entry Point.
Initializes database, runs startup warm-up, and drives the real-time scanning engine.
Designed for running as an independent background worker on Render / Docker.
"""

import asyncio
import signal
import sys
from loguru import logger

from storage.database import init_db
from storage.repository import Repository
from alerts.deduplicator import AlertDeduplicator
from alerts.telegram_bot import TelegramBot
from engine.scanner import BreakoutScanner
from engine.scheduler import ScreenerEngine


async def main():
    logger.info("Starting Indian Equities Breakout Screener Background Worker...")
    
    # Initialize DB tables
    await init_db()
    
    repo = Repository()
    dedup = AlertDeduplicator(repo)
    bot = TelegramBot(repo)
    scanner = BreakoutScanner(repo, bot, dedup)
    engine = ScreenerEngine(repo, bot, dedup, scanner)

    # Perform startup warm-up (loads universe, computes levels, starts bot)
    await engine.warm_up()
    
    # Start APScheduler tasks
    engine.start_schedules()

    # Graceful shutdown handler
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received. Stopping worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals
            pass

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await engine.stop()
        logger.info("Worker gracefully terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

"""
Shared Screener Engine Instance.
Provides singleton instances of Repository, TelegramBot, AlertDeduplicator,
BreakoutScanner, and ScreenerEngine for FastAPI lifespan and CLI commands.
"""

from storage.repository import Repository
from alerts.deduplicator import AlertDeduplicator
from alerts.telegram_bot import TelegramBot
from engine.scanner import BreakoutScanner
from engine.scheduler import ScreenerEngine

repo = Repository()
dedup = AlertDeduplicator(repo)
bot = TelegramBot(repo)
scanner = BreakoutScanner(repo, bot, dedup)
engine = ScreenerEngine(repo, bot, dedup, scanner)

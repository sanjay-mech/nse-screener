"""
End-to-End Integration Test with Mocked Market Feeds.
Simulates a full real-time scan cycle:
- Mocks NSE bulk feed with breakout stocks
- Executes BreakoutScanner.scan_once
- Verifies detection, database persistence, and alert formatting
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import date, datetime

from storage.database import init_db
from storage.repository import Repository
from signals.models import PriceTick, PrecomputedLevels, TriggerType
from alerts.deduplicator import AlertDeduplicator
from alerts.telegram_bot import TelegramBot
from engine.scanner import BreakoutScanner
from engine.state_manager import state_manager


@pytest.mark.asyncio
async def test_full_scanner_integration():
    await init_db()
    repo = Repository()
    bot = TelegramBot(repo)
    # Mock bot broadcast to avoid actual network calls
    bot.broadcast_alert = AsyncMock()
    dedup = AlertDeduplicator(repo)
    scanner = BreakoutScanner(repo, bot, dedup)

    today = date.today()
    await repo.clear_alerts_for_date(today)
    dedup._cache.clear()

    # Pre-populate state manager with levels for 2 stocks
    state_manager.active_universe = ["RELIANCE", "TCS"]
    state_manager.levels = {
        "RELIANCE": PrecomputedLevels(
            symbol="RELIANCE",
            calculated_date=today,
            ath_high=3000.0,
            ath_date="2024-06-01",
            high_52w=2950.0,
            high_52w_date="2024-07-01",
            donchian_50_high=2900.0,
            donchian_50_date="2024-08-01",
            avg_vol_20d=200000.0,
            atr_20d=40.0,
            last_close=2960.0,
            sector="Energy"
        ),
        "TCS": PrecomputedLevels(
            symbol="TCS",
            calculated_date=today,
            ath_high=4200.0,
            ath_date="2024-03-01",
            high_52w=4100.0,
            high_52w_date="2024-05-01",
            donchian_50_high=4000.0,
            donchian_50_date="2024-07-01",
            avg_vol_20d=150000.0,
            atr_20d=50.0,
            last_close=3950.0,
            sector="IT"
        )
    }

    # Mock NSE bulk return: RELIANCE breaks ATH (3050 > 3000), TCS is normal (3980 < 4000)
    mock_ticks = {
        "RELIANCE": PriceTick(
            symbol="RELIANCE",
            ltp=3050.0,
            day_high=3055.0,
            day_low=2960.0,
            day_open=2970.0,
            prev_close=2960.0,
            p_change=3.04,
            volume=350000,
            turnover_cr=106.75,
            source="NSE_BULK",
            timestamp=datetime.utcnow()
        ),
        "TCS": PriceTick(
            symbol="TCS",
            ltp=3980.0,
            day_high=3990.0,
            day_low=3940.0,
            day_open=3950.0,
            prev_close=3950.0,
            p_change=0.76,
            volume=120000,
            turnover_cr=47.76,
            source="NSE_BULK",
            timestamp=datetime.utcnow()
        )
    }

    with patch("data.nse_client.nse_client.fetch_all_fno_quotes", new=AsyncMock(return_value=mock_ticks)), \
         patch("data.yahoo_client.yahoo_client.fetch_intraday_fallback", new=AsyncMock(return_value=mock_ticks)):
        signals = await scanner.scan_once(force_execution=True)

        assert len(signals) >= 1
        ath_sigs = [s for s in signals if s.trigger == TriggerType.ATH]
        assert len(ath_sigs) == 1
        sig = ath_sigs[0]
        assert sig.symbol == "RELIANCE"
        assert sig.level_broken == 3000.0
        assert sig.ltp == 3050.0

        # Verify broadcast was invoked
        assert bot.broadcast_alert.call_count >= 1

        # Verify alert logged to database
        db_alerts = await repo.get_alerts_by_date(today)
        rel_alerts = [a for a in db_alerts if a.symbol == "RELIANCE"]
        assert len(rel_alerts) >= 1
        assert any(a.trigger_types == "ATH" for a in rel_alerts)

        # Clean up test alerts so test records do not persist in live database
        await repo.clear_alerts_for_date(today)

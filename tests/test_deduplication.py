"""
Unit tests for Alert Deduplication and Re-Alert Logic.
Verifies:
1. Max 1 alert per symbol per trigger per calendar day
2. Re-alert triggered only if price pushes +X% above prior alert
"""

import pytest
from datetime import date, datetime
from signals.models import BreakoutSignal, TriggerType
from alerts.deduplicator import AlertDeduplicator
from storage.repository import Repository
from storage.database import init_db


@pytest.mark.asyncio
async def test_alert_deduplication_and_realert():
    await init_db()
    repo = Repository()
    today = date.today()
    await repo.clear_alerts_for_date(today)
    dedup = AlertDeduplicator(repo)
    dedup._cache.clear()

    signal_initial = BreakoutSignal(
        symbol="BAJFINANCE",
        ltp=7000.0,
        pct_change=2.5,
        level_broken=6950.0,
        pct_above=0.72,
        triggers=[TriggerType.HIGH_52W, TriggerType.DC50],
        trigger_label="52W + DC50",
        prior_high_date="2024-01-10",
        rvol=1.8,
        atr_20=120.0,
        sector="Financial Services",
        ban_status="NORMAL",
        timestamp=datetime.utcnow(),
        trigger_mode="ltp_above",
        volume=500000,
        turnover_cr=350.0
    )

    # 1. First alert should pass
    should_send, reason = await dedup.should_alert(signal_initial, today)
    assert should_send is True
    dedup.record_alert_dispatched(signal_initial, today)

    # 2. Immediate duplicate at same or slightly higher price (+0.5% < 1.5% threshold) should be suppressed
    signal_duplicate = BreakoutSignal(
        symbol="BAJFINANCE",
        ltp=7035.0,  # +0.5% above 7000
        pct_change=3.0,
        level_broken=6950.0,
        pct_above=1.22,
        triggers=[TriggerType.HIGH_52W, TriggerType.DC50],
        trigger_label="52W + DC50",
        prior_high_date="2024-01-10",
        rvol=2.0,
        atr_20=120.0,
        sector="Financial Services",
        ban_status="NORMAL",
        timestamp=datetime.utcnow(),
        trigger_mode="ltp_above",
        volume=550000,
        turnover_cr=386.0
    )

    should_send_dup, reason_dup = await dedup.should_alert(signal_duplicate, today)
    assert should_send_dup is False
    assert "Already alerted" in reason_dup

    # 3. Price surges +2.0% above 7000 (>= 1.5% threshold) -> Re-alert should trigger
    signal_realert = BreakoutSignal(
        symbol="BAJFINANCE",
        ltp=7140.0,  # +2.0% above 7000
        pct_change=4.5,
        level_broken=6950.0,
        pct_above=2.73,
        triggers=[TriggerType.HIGH_52W, TriggerType.DC50],
        trigger_label="52W + DC50",
        prior_high_date="2024-01-10",
        rvol=2.5,
        atr_20=120.0,
        sector="Financial Services",
        ban_status="NORMAL",
        timestamp=datetime.utcnow(),
        trigger_mode="ltp_above",
        volume=700000,
        turnover_cr=499.8
    )

    should_send_re, reason_re = await dedup.should_alert(signal_realert, today)
    assert should_send_re is True
    assert "Re-alert triggered" in reason_re

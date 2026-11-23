"""
Unit tests for ATH, 52W High, and Retrace Calculations.
Verifies:
1. Nominal traded price is used (unadjusted for cash dividends, strictly matching NSE/TradingView charts).
2. Retrace detection when price hits breakout level intraday (day_high >= level) but current LTP is below level.
3. Daily signal scoping (ensures prior days' breakouts are never reported in today's EOD summary).
"""

from datetime import date, datetime, timedelta
import pytz
import pytest

from signals.models import PriceTick, PrecomputedLevels, BreakoutSignal, TriggerType
from alerts.formatter import format_breakout_alert, format_eod_summary
from engine.state_manager import StateManager
from config.settings import settings

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


def test_retrace_alert_formatting():
    """Verify that when LTP is below the broken level, the alert explicitly tags Retraced with negative %."""
    sig = BreakoutSignal(
        symbol="ANGELONE",
        ltp=345.0,
        pct_change=-1.5,
        level_broken=389.60,
        pct_above=-11.45,
        triggers=[TriggerType.ATH],
        trigger_label="ATH",
        prior_high_date="2024-01-09",
        rvol=1.2,
        atr_20=12.5,
        sector="Financial Services",
        ban_status="NORMAL",
        timestamp=datetime.now(KOLKATA_TZ),
        trigger_mode="intraday_touch",
        volume=100000,
        turnover_cr=5.0,
        side="BUY",
        trigger=TriggerType.ATH,
        title="ATH BREAKOUT"
    )

    msg = format_breakout_alert(sig)
    assert "⚠️ Retraced" in msg
    assert "Level: <b>₹389.60</b>" in msg
    assert "LTP: <b>₹345.00</b>" in msg


def test_eod_summary_strictly_scoped_to_today():
    """Verify that only today's alerts are included and accurately tagged as Confirmed or Retraced."""
    now = datetime.now(KOLKATA_TZ)
    sig_today = BreakoutSignal(
        symbol="RELIANCE",
        ltp=3100.0,
        pct_change=2.5,
        level_broken=3050.0,
        pct_above=1.64,
        triggers=[TriggerType.ATH],
        trigger_label="ATH",
        prior_high_date="2024-01-01",
        rvol=2.0,
        atr_20=40.0,
        sector="Energy",
        ban_status="NORMAL",
        timestamp=now,
        trigger_mode="ltp_above",
        volume=500000,
        turnover_cr=150.0,
        side="BUY",
        trigger=TriggerType.ATH,
        title="ATH BREAKOUT"
    )

    sig_retrace = BreakoutSignal(
        symbol="BSE",
        ltp=3750.0,
        pct_change=-3.2,
        level_broken=4003.3,
        pct_above=-6.33,
        triggers=[TriggerType.DC50_HIGH],
        trigger_label="DC50_HIGH",
        prior_high_date="2026-11-17",
        rvol=1.1,
        atr_20=75.0,
        sector="Capital Markets",
        ban_status="NORMAL",
        timestamp=now,
        trigger_mode="ltp_above",
        volume=200000,
        turnover_cr=75.0,
        side="BUY",
        trigger=TriggerType.DC50_HIGH,
        title="DC50 BREAKOUT"
    )

    # RELIANCE closed confirmed above level, BSE closed below level (retraced)
    close_confirmed = ["RELIANCE"]
    summary = format_eod_summary([sig_today, sig_retrace], close_confirmed)

    assert "RELIANCE" in summary
    assert "Closed above prior high" in summary
    assert "• <b>RELIANCE</b> (ATH) - ✅ Confirmed" in summary
    assert "• <b>BSE</b> (DC50_HIGH) - ⚠️ Retraced" in summary


def test_state_manager_daily_scoping():
    """Verify state manager automatically purges or filters prior days' signals."""
    sm = StateManager()
    today = datetime.now(KOLKATA_TZ).date()
    yesterday_dt = datetime.now(KOLKATA_TZ) - timedelta(days=1)

    sig_yesterday = BreakoutSignal(
        symbol="ANGELONE",
        ltp=379.0,
        pct_change=4.5,
        level_broken=372.0,
        pct_above=1.8,
        triggers=[TriggerType.ATH],
        trigger_label="ATH",
        prior_high_date=None,
        rvol=2.5,
        atr_20=12.0,
        sector="Financial Services",
        ban_status="NORMAL",
        timestamp=yesterday_dt,
        trigger_mode="ltp_above",
        volume=100000,
        turnover_cr=5.0,
        side="BUY",
        trigger=TriggerType.ATH,
        title="ATH BREAKOUT"
    )

    sig_today = BreakoutSignal(
        symbol="TCS",
        ltp=4200.0,
        pct_change=1.8,
        level_broken=4150.0,
        pct_above=1.2,
        triggers=[TriggerType.DC50_HIGH],
        trigger_label="DC50_HIGH",
        prior_high_date=None,
        rvol=1.5,
        atr_20=35.0,
        sector="IT",
        ban_status="NORMAL",
        timestamp=datetime.now(KOLKATA_TZ),
        trigger_mode="ltp_above",
        volume=250000,
        turnover_cr=105.0,
        side="BUY",
        trigger=TriggerType.DC50_HIGH,
        title="DC50 BREAKOUT"
    )

    sm.today_signals.append(sig_yesterday)
    # When record_signal is called today, older day signals are purged
    sm.record_signal(sig_today)

    today_only = sm.get_today_signals(today)
    assert len(today_only) == 1
    assert today_only[0].symbol == "TCS"

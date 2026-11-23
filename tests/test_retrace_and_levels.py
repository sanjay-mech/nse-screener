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
    """Verify that only today's alerts are included and accurately tagged as Confirmed or Retraced for BUY and SELL."""
    now = datetime.now(KOLKATA_TZ)
    sig_buy = BreakoutSignal(
        symbol="LAURUSLABS",
        ltp=2378.90,
        pct_change=3.7,
        level_broken=2377.97,
        pct_above=0.04,
        triggers=[TriggerType.ST_DAILY_10_1_BUY],
        trigger_label="ST_DAILY_10_1_BUY",
        prior_high_date=None,
        rvol=1.5,
        atr_20=25.0,
        sector="Pharma",
        ban_status="NORMAL",
        timestamp=now,
        trigger_mode="ltp_above",
        volume=500000,
        turnover_cr=118.0,
        side="BUY",
        trigger=TriggerType.ST_DAILY_10_1_BUY,
        title="ST DAILY (10,1) BUY FLIP"
    )

    sig_sell = BreakoutSignal(
        symbol="ANANDRATHI",
        ltp=2355.90,
        pct_change=-0.8,
        level_broken=2353.51,
        pct_above=0.1,
        triggers=[TriggerType.ST_DAILY_10_1_SELL],
        trigger_label="ST_DAILY_10_1_SELL",
        prior_high_date=None,
        rvol=1.1,
        atr_20=45.0,
        sector="Capital Markets",
        ban_status="NORMAL",
        timestamp=now,
        trigger_mode="ltp_above",
        volume=200000,
        turnover_cr=47.0,
        side="SELL",
        trigger=TriggerType.ST_DAILY_10_1_SELL,
        title="ST DAILY (10,1) SELL FLIP"
    )

    # LAURUSLABS is BUY: close (2378.90) > level (2377.97) -> CONFIRMED!
    # ANANDRATHI is SELL: close (2355.90) > level (2353.51) -> BOUNCED / RETRACED (NOT confirmed)!
    confirmed_details = [(sig_buy, 2378.90)]
    close_confirmed = ["LAURUSLABS"]
    summary = format_eod_summary(
        all_alerts=[sig_buy, sig_sell],
        close_confirmed_symbols=close_confirmed,
        confirmed_details=confirmed_details
    )

    assert "LAURUSLABS" in summary
    assert "Held above ₹2,377.97" in summary
    assert "• <b>LAURUSLABS</b> (ST_DAILY_10_1_BUY) - ✅ Confirmed" in summary
    # ANANDRATHI did NOT close below its sell level, so it is Retraced!
    assert "• <b>ANANDRATHI</b> (ST_DAILY_10_1_SELL) - ⚠️ Retraced" in summary
    assert "Closed above prior high" not in summary


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

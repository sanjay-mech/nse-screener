"""
Telegram Alert Message Formatters.
Generates rich HTML messages for real-time breakouts, pre-market watchlists,
EOD summaries, and system heartbeats.
"""

from datetime import datetime
from typing import List, Tuple, Dict
import pytz
from config.settings import settings
from signals.models import BreakoutSignal, PrecomputedLevels

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)


def format_breakout_alert(signal: BreakoutSignal) -> str:
    """
    Format an individual Buy or Sell alert into an ultra-concise, high-density Telegram alert (3 lines).
    """
    now_ist = datetime.now(KOLKATA_TZ).strftime("%H:%M IST")
    p_sign = "+" if signal.pct_change >= 0 else ""

    side = getattr(signal, "side", "BUY")
    title = getattr(signal, "title", signal.trigger_label)

    # Dynamic emoji based on side and trigger
    if side == "SELL":
        if "ATL" in title or "52W" in title:
            icon = "🔻"
        elif "DC" in title:
            icon = "⚡"
        else:
            icon = "🔴"
        side_tag = "SELL"
        dist_sign = "-"
    else:
        if "ATH" in title:
            icon = "🚀"
        elif "52W" in title:
            icon = "🔥"
        elif "DC" in title:
            icon = "⚡"
        else:
            icon = "🟢"
        side_tag = "BUY"
        dist_sign = "+"

    dist_val = abs(getattr(signal, "pct_distance", signal.pct_above))
    is_retraced = (side == "BUY" and signal.ltp < signal.level_broken) or (side == "SELL" and signal.ltp > signal.level_broken)
    if is_retraced and signal.level_broken > 0:
        retrace_pct = abs(((signal.ltp - signal.level_broken) / signal.level_broken) * 100.0)
        level_str = f"Level: <b>₹{signal.level_broken:,.2f}</b> (⚠️ Retraced -{retrace_pct:.1f}%)"
    else:
        level_str = f"Level: <b>₹{signal.level_broken:,.2f}</b> ({dist_sign}{dist_val:.1f}%)"

    # Clean 3-line institutional separate alert
    msg = (
        f"{icon} <b>{signal.symbol}</b> | <b>{title}</b> ({p_sign}{signal.pct_change:.1f}%)\n"
        f"LTP: <b>₹{signal.ltp:,.2f}</b> | {level_str}\n"
        f"Trigger: <b>{side_tag} ({title})</b> | RVOL: <b>{signal.rvol:.1f}x</b> | <i>{now_ist}</i>"
    )
    return msg


def format_premarket_summary(near_stocks: List[Tuple[str, str, float, float]]) -> str:
    """
    Format 09:10 IST pre-market summary for stocks within 1% of breakout levels.
    near_stocks: [(symbol, level_name, level_price, distance_pct)]
    """
    now_ist = datetime.now(KOLKATA_TZ).strftime("%d-%b-%Y %H:%M IST")
    if not near_stocks:
        return (
            f"🔔 <b>NSE F&O PRE-MARKET WATCHLIST</b>\n"
            f"<i>{now_ist}</i>\n\n"
            f"No stocks currently within {settings.NEAR_BREAKOUT_THRESHOLD_PCT}% of ATH/52W/DC50 levels."
        )

    lines = [
        f"🔔 <b>NSE F&O PRE-MARKET WATCHLIST</b>",
        f"<i>{now_ist}</i>",
        f"Stocks within {settings.NEAR_BREAKOUT_THRESHOLD_PCT}% of key breakout levels:\n"
    ]

    for sym, lvl_name, lvl_price, dist in near_stocks[:25]:
        lines.append(f"• <b>{sym}</b>: {dist:.2f}% below {lvl_name} (₹{lvl_price:,.2f})")

    if len(near_stocks) > 25:
        lines.append(f"\n<i>...and {len(near_stocks) - 25} more on the dashboard.</i>")

    return "\n".join(lines)


def format_eod_summary(
    all_alerts: List[Any],
    close_confirmed_symbols: List[str],
    confirmed_details: Optional[List[Tuple[Any, float]]] = None,
    retraced_details: Optional[List[Tuple[Any, float]]] = None
) -> str:
    """
    Format 15:45 IST End-Of-Day breakout summary with close confirmation.
    Properly distinguishes between BUY breakouts (close > level) and SELL breakdowns (close < level).
    """
    now_ist = datetime.now(KOLKATA_TZ).strftime("%d-%b-%Y")
    total = len(all_alerts)
    confirmed_count = len(confirmed_details) if confirmed_details is not None else len(close_confirmed_symbols)

    lines = [
        f"📊 <b>END-OF-DAY BREAKOUT REPORT | NSE F&O</b>",
        f"Date: <b>{now_ist}</b>",
        f"Total Alerts Today: <b>{total}</b>",
        f"Close Confirmed: <b>{confirmed_count}</b>\n"
    ]

    if not all_alerts:
        lines.append("No stocks broke ATH, 52W, DC50, or Supertrend today.")
        return "\n".join(lines)

    lines.append("<b>✅ Close-Confirmed Moves:</b>")
    if confirmed_details:
        for a, close_p in confirmed_details[:20]:
            sym = a.symbol
            trig = getattr(a, "trigger_label", getattr(a, "trigger_types", "BREAKOUT"))
            side = getattr(a, "side", "BUY")
            lvl = a.level_broken
            if side == "BUY":
                lines.append(f"• <b>{sym}</b> ({trig}) - Closed @ ₹{close_p:,.2f} (Held above ₹{lvl:,.2f})")
            else:
                lines.append(f"• <b>{sym}</b> ({trig}) - Closed @ ₹{close_p:,.2f} (Held below ₹{lvl:,.2f})")
    elif close_confirmed_symbols:
        for sym in close_confirmed_symbols[:20]:
            lines.append(f"• <b>{sym}</b> (Confirmed at close)")
    else:
        lines.append("<i>None closed confirming their breakout/breakdown level.</i>")

    lines.append("\n<b>⚡ Today's Intraday Alerts & Status:</b>")
    seen_breakouts = set()
    for sig in all_alerts[:30]:
        sym = sig.symbol
        trig = getattr(sig, "trigger_label", getattr(sig, "trigger_types", "BREAKOUT"))
        if (sym, trig) in seen_breakouts:
            continue
        seen_breakouts.add((sym, trig))
        status = "✅ Confirmed" if sym in close_confirmed_symbols else "⚠️ Retraced"
        lines.append(f"• <b>{sym}</b> ({trig}) - {status}")

    return "\n".join(lines)


def format_heartbeat_alert(
    status: str,
    active_stocks_count: int,
    latency_ms: float,
    error_msg: str = ""
) -> str:
    """
    Format health check / alert message.
    """
    now_ist = datetime.now(KOLKATA_TZ).strftime("%H:%M:%S IST")
    icon = "🟢" if status == "HEALTHY" else "🔴"

    msg = (
        f"{icon} <b>SYSTEM HEARTBEAT | {status}</b>\n"
        f"Tracked F&O Symbols: <b>{active_stocks_count}</b>\n"
        f"Feed Latency: <b>{latency_ms:.1f}ms</b>\n"
        f"Time: <i>{now_ist}</i>"
    )
    if error_msg:
        msg += f"\n⚠️ Error: <code>{error_msg}</code>"

    return msg

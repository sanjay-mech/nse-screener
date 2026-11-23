"""
FastAPI REST API Routes.
Provides JSON endpoints for health checks, real-time breakouts,
levels lookup, alert logs, and operational controls.
"""

from datetime import date, datetime
import json
from typing import Dict, Any, List, Optional
import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from config.settings import settings
from signals.models import PrecomputedLevels, PriceTick
from signals.breakout_detector import breakout_detector
from signals.rvol import calculate_time_normalized_rvol
from storage.repository import Repository
from engine.state_manager import state_manager
from data.holiday_calendar import holiday_calendar
from data.sectors import get_stock_sector
from api.auth import verify_token

KOLKATA_TZ = pytz.timezone(settings.TIMEZONE)

router = APIRouter()
repo = Repository()

AVAILABLE_SCREENERS = [
    {"id": "ATH", "title": "ATH Breakout", "side": "BUY", "category": "ATH / ATL", "badge": "🚀 ATH", "description": "LTP crosses prior All-Time High"},
    {"id": "ATL", "title": "ATL Breakdown", "side": "SELL", "category": "ATH / ATL", "badge": "🔻 ATL", "description": "LTP drops below prior All-Time Low"},
    {"id": "52W_HIGH", "title": "52-Week High Breakout", "side": "BUY", "category": "52-Week", "badge": "📈 52W-H", "description": "LTP crosses 252-day highest high"},
    {"id": "52W_LOW", "title": "52-Week Low Breakdown", "side": "SELL", "category": "52-Week", "badge": "📉 52W-L", "description": "LTP drops below 252-day lowest low"},
    {"id": "DC50_HIGH", "title": "Donchian 50 High Breakout", "side": "BUY", "category": "Donchian Channels", "badge": "🎯 DC50-H", "description": "LTP crosses 50-day Donchian channel high"},
    {"id": "DC50_LOW", "title": "Donchian 50 Low Breakdown", "side": "SELL", "category": "Donchian Channels", "badge": "🔻 DC50-L", "description": "LTP drops below 50-day Donchian channel low"},
    {"id": "DC20_HIGH", "title": "Donchian 20 High Breakout", "side": "BUY", "category": "Donchian Channels", "badge": "🎯 DC20-H", "description": "LTP crosses 20-day Donchian channel high"},
    {"id": "DC20_LOW", "title": "Donchian 20 Low Breakdown", "side": "SELL", "category": "Donchian Channels", "badge": "🔻 DC20-L", "description": "LTP drops below 20-day Donchian channel low"},
    {"id": "ST_DAILY_10_1_BUY", "title": "Supertrend Daily (10,1) BUY", "side": "BUY", "category": "Supertrend Daily", "badge": "🟢 ST Daily (10,1)", "description": "Daily Supertrend (10,1) turns Bullish"},
    {"id": "ST_DAILY_10_1_SELL", "title": "Supertrend Daily (10,1) SELL", "side": "SELL", "category": "Supertrend Daily", "badge": "🔴 ST Daily (10,1)", "description": "Daily Supertrend (10,1) turns Bearish"},
    {"id": "ST_DAILY_10_2_BUY", "title": "Supertrend Daily (10,2) BUY", "side": "BUY", "category": "Supertrend Daily", "badge": "🟢 ST Daily (10,2)", "description": "Daily Supertrend (10,2) turns Bullish"},
    {"id": "ST_DAILY_10_2_SELL", "title": "Supertrend Daily (10,2) SELL", "side": "SELL", "category": "Supertrend Daily", "badge": "🔴 ST Daily (10,2)", "description": "Daily Supertrend (10,2) turns Bearish"},
]


class SubscriptionUpdateRequest(BaseModel):
    subscriptions: List[str]


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """System health check endpoint."""
    return {
        "status": state_manager.health_status,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "market_open": holiday_calendar.is_market_open(),
        "is_paused": state_manager.is_paused,
        "universe_size": len(state_manager.active_universe),
        "levels_loaded": len(state_manager.levels),
        "last_scan_utc": state_manager.last_scan_time.isoformat() if state_manager.last_scan_time else None,
        "last_scan_duration_ms": round(state_manager.last_scan_duration_ms, 2),
        "last_error": state_manager.last_error
    }


@router.get("/signals")
async def get_signals(
    limit: int = Query(50, ge=1, le=200),
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """Retrieve today's active breakout signals (latest alerts) and near-breakout candidates."""
    today = datetime.now(KOLKATA_TZ).date()
    alerts = await repo.get_alerts_by_date(today)
    latest_alerts = alerts[:limit]

    near_breakouts = []
    for sym, lvl in state_manager.levels.items():
        tick = state_manager.latest_ticks.get(sym)
        eval_tick = tick if tick else PriceTick(
            symbol=sym, ltp=lvl.last_close, day_high=lvl.last_close,
            day_low=lvl.last_close, day_open=lvl.last_close, prev_close=lvl.last_close,
            p_change=0.0, volume=0, turnover_cr=0.0
        )
        near_info = breakout_detector.is_near_breakout(eval_tick, lvl)
        if near_info:
            name, target_lvl, dist = near_info
            near_breakouts.append({
                "symbol": sym,
                "target_type": name,
                "target_level": target_lvl,
                "current_price": eval_tick.ltp,
                "distance_pct": dist,
                "sector": lvl.sector if (lvl.sector and lvl.sector != "N/A") else get_stock_sector(sym)
            })

    near_breakouts.sort(key=lambda x: x["distance_pct"])

    breakout_items = []
    for a in latest_alerts:
        curr_tick = state_manager.latest_ticks.get(a.symbol)
        curr_ltp = curr_tick.ltp if curr_tick else a.ltp
        curr_change = curr_tick.p_change if curr_tick else a.pct_change
        is_buy = getattr(a, "side", "BUY") == "BUY"
        is_holding = curr_ltp >= a.level_broken if is_buy else curr_ltp <= a.level_broken
        live_dist = round(((curr_ltp - a.level_broken) / a.level_broken) * 100, 2) if a.level_broken > 0 else 0.0

        breakout_items.append({
            "symbol": a.symbol,
            "trigger_types": a.trigger_types,
            "side": getattr(a, "side", "BUY"),
            "ltp": curr_ltp,
            "alert_ltp": a.ltp,
            "pct_change": curr_change,
            "level_broken": a.level_broken,
            "pct_above": live_dist,
            "alert_pct_above": a.pct_above,
            "is_holding": is_holding,
            "holding_status": "HOLDING" if is_holding else "RETRACED",
            "prior_high_date": a.prior_high_date,
            "rvol": curr_tick.volume if curr_tick else a.rvol,
            "atr_20": a.atr_20,
            "sector": a.sector if (a.sector and a.sector != "N/A") else get_stock_sector(a.symbol),
            "time": a.alert_time.isoformat(),
            "confirmed_close": a.confirmed_close
        })

    return {
        "date": str(today),
        "today_breakouts_count": len(alerts),
        "breakouts": breakout_items,
        "near_breakouts": near_breakouts
    }


@router.get("/levels/{symbol}")
async def get_symbol_levels(
    symbol: str,
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """Fetch precomputed ATH, 52W, and Donchian levels for a specific symbol."""
    sym = symbol.strip().upper()
    lvl = await repo.get_stock_level(sym)
    if not lvl:
        raise HTTPException(status_code=404, detail=f"Stock levels for {sym} not found")

    tick = state_manager.latest_ticks.get(sym)

    return {
        "symbol": lvl.symbol,
        "calculated_date": str(lvl.calculated_date),
        "ath_high": lvl.ath_high,
        "ath_date": lvl.ath_date,
        "high_52w": lvl.high_52w,
        "high_52w_date": lvl.high_52w_date,
        "donchian_50_high": lvl.donchian_50_high,
        "donchian_50_date": lvl.donchian_50_date,
        "avg_vol_20d": lvl.avg_vol_20d,
        "atr_20d": lvl.atr_20d,
        "last_close": lvl.last_close,
        "sector": lvl.sector,
        "supertrend": {
            "daily_10_1": {"value": lvl.st_daily_10_1_val, "bullish": lvl.st_daily_10_1_dir == 1},
            "daily_10_2": {"value": lvl.st_daily_10_2_val, "bullish": lvl.st_daily_10_2_dir == 1},
            "tf15m_10_1": {"value": lvl.st_15m_10_1_val, "bullish": lvl.st_15m_10_1_dir == 1},
            "tf15m_10_2": {"value": lvl.st_15m_10_2_val, "bullish": lvl.st_15m_10_2_dir == 1}
        },
        "live_quote": {
            "ltp": tick.ltp if tick else None,
            "p_change": tick.p_change if tick else None,
            "day_high": tick.day_high if tick else None,
            "day_low": tick.day_low if tick else None,
            "volume": tick.volume if tick else None,
            "turnover_cr": tick.turnover_cr if tick else None,
            "source": tick.source if tick else None,
            "timestamp": tick.timestamp.isoformat() if tick else None
        } if tick else None
    }


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    authorized: bool = Depends(verify_token)
) -> List[Dict[str, Any]]:
    """Retrieve historical alert log."""
    today = datetime.now(KOLKATA_TZ).date()
    records = await repo.get_alerts_by_date(today)
    return [
        {
            "id": r.id,
            "symbol": r.symbol,
            "alert_time": r.alert_time.isoformat(),
            "trigger_types": r.trigger_types,
            "ltp": r.ltp,
            "pct_change": r.pct_change,
            "level_broken": r.level_broken,
            "pct_above": r.pct_above,
            "rvol": r.rvol,
            "atr_20": r.atr_20,
            "sector": r.sector if (r.sector and r.sector != "N/A") else get_stock_sector(r.symbol),
            "confirmed_close": r.confirmed_close
        }
        for r in records[:limit]
    ]


@router.get("/table")
async def get_table_data(
    authorized: bool = Depends(verify_token)
) -> List[Dict[str, Any]]:
    """
    Returns full universe snapshot with distances to ATH, 52W, and DC50,
    RVOL, % change, and breakout status for the live web dashboard.
    """
    rows = []
    if not state_manager.levels and state_manager.active_universe:
        for sym in state_manager.active_universe:
            rows.append({
                "symbol": sym,
                "ltp": 0.0,
                "p_change": 0.0,
                "day_high": 0.0,
                "ath_high": 0.0,
                "dist_ath": 0.0,
                "high_52w": 0.0,
                "dist_52w": 0.0,
                "donchian_50": 0.0,
                "dist_dc50": 0.0,
                "rvol": 1.0,
                "atr_20": 0.0,
                "turnover_cr": 0.0,
                "sector": "N/A",
                "status": "INITIALIZING",
                "st_daily_10_1": 1,
                "st_daily_10_2": 1,
                "st_15m_10_1": 1,
                "st_15m_10_2": 1,
                "source": "LOADING"
            })
        return rows

    for sym, lvl in state_manager.levels.items():
        tick = state_manager.latest_ticks.get(sym)
        ltp = tick.ltp if tick else lvl.last_close
        if lvl.last_close > 0 and ltp > 0:
            p_change = round(((ltp - lvl.last_close) / lvl.last_close) * 100, 2)
        elif tick:
            p_change = tick.p_change
        else:
            p_change = 0.0
        day_high = tick.day_high if tick else ltp
        vol = tick.volume if tick else 0
        turnover = tick.turnover_cr if tick else 0.0
        tick_ts = tick.timestamp if tick else None
        rvol = calculate_time_normalized_rvol(vol, lvl.avg_vol_20d, tick_ts)

        # Distances: negative means below level, positive means above
        dist_ath = round(((ltp - lvl.ath_high) / lvl.ath_high) * 100.0, 2) if lvl.ath_high > 0 else -100.0
        dist_52w = round(((ltp - lvl.high_52w) / lvl.high_52w) * 100.0, 2) if lvl.high_52w > 0 else -100.0
        dist_dc50 = round(((ltp - lvl.donchian_50_high) / lvl.donchian_50_high) * 100.0, 2) if lvl.donchian_50_high > 0 else -100.0

        status = "NORMAL"
        is_retraced = False
        retrace_type = None

        if dist_ath >= 0:
            status = "ATH BREAKOUT"
        elif dist_52w >= 0:
            status = "52W BREAKOUT"
        elif dist_dc50 >= 0:
            status = "DC50 BREAKOUT"
        elif lvl.donchian_20_high > 0 and ltp >= lvl.donchian_20_high:
            status = "DC20 BREAKOUT"
        elif lvl.ath_high > 0 and day_high >= lvl.ath_high and ltp < lvl.ath_high:
            status = "ATH RETRACED"
            is_retraced = True
            retrace_type = "ATH"
        elif lvl.high_52w > 0 and day_high >= lvl.high_52w and ltp < lvl.high_52w:
            status = "52W RETRACED"
            is_retraced = True
            retrace_type = "52W_HIGH"
        elif lvl.donchian_50_high > 0 and day_high >= lvl.donchian_50_high and ltp < lvl.donchian_50_high:
            status = "DC50 RETRACED"
            is_retraced = True
            retrace_type = "DC50_HIGH"
        elif lvl.donchian_20_high > 0 and day_high >= lvl.donchian_20_high and ltp < lvl.donchian_20_high:
            status = "DC20 RETRACED"
            is_retraced = True
            retrace_type = "DC20_HIGH"
        elif max(dist_ath, dist_52w, dist_dc50) >= -1.0:
            status = "NEAR BREAKOUT"

        matching_triggers = []
        if dist_ath >= 0: matching_triggers.append("ATH")
        if dist_52w >= 0: matching_triggers.append("52W_HIGH")
        if dist_dc50 >= 0: matching_triggers.append("DC50_HIGH")
        if lvl.donchian_20_high > 0 and ltp >= lvl.donchian_20_high: matching_triggers.append("DC20_HIGH")
        if is_retraced:
            matching_triggers.append("RETRACED")
            if retrace_type:
                matching_triggers.append(f"{retrace_type}_RETRACED")
        if lvl.atl_low > 0 and ltp <= lvl.atl_low: matching_triggers.append("ATL")
        if lvl.low_52w > 0 and ltp <= lvl.low_52w: matching_triggers.append("52W_LOW")
        if lvl.donchian_50_low > 0 and ltp <= lvl.donchian_50_low: matching_triggers.append("DC50_LOW")
        if lvl.donchian_20_low > 0 and ltp <= lvl.donchian_20_low: matching_triggers.append("DC20_LOW")
        if lvl.st_daily_10_1_dir == 1: matching_triggers.append("ST_DAILY_10_1_BUY")
        else: matching_triggers.append("ST_DAILY_10_1_SELL")
        if lvl.st_daily_10_2_dir == 1: matching_triggers.append("ST_DAILY_10_2_BUY")
        else: matching_triggers.append("ST_DAILY_10_2_SELL")

        rows.append({
            "symbol": sym,
            "ltp": ltp,
            "p_change": p_change,
            "day_high": day_high,
            "ath_high": lvl.ath_high,
            "dist_ath": dist_ath,
            "high_52w": lvl.high_52w,
            "dist_52w": dist_52w,
            "donchian_50": lvl.donchian_50_high,
            "dist_dc50": dist_dc50,
            "donchian_20": lvl.donchian_20_high,
            "dist_dc20": round(((ltp - lvl.donchian_20_high) / lvl.donchian_20_high) * 100.0, 2) if lvl.donchian_20_high > 0 else -100.0,
            "rvol": rvol,
            "atr_20": lvl.atr_20d,
            "turnover_cr": turnover,
            "sector": lvl.sector if (lvl.sector and lvl.sector != "N/A") else get_stock_sector(sym),
            "status": status,
            "triggers": matching_triggers,
            "st_daily_10_1": lvl.st_daily_10_1_dir,
            "st_daily_10_2": lvl.st_daily_10_2_dir,
            "st_15m_10_1": lvl.st_15m_10_1_dir,
            "st_15m_10_2": lvl.st_15m_10_2_dir,
            "source": tick.source if tick else "CACHE"
        })

    # Default sort by distance to 52W descending
    rows.sort(key=lambda x: max(x["dist_ath"], x["dist_52w"], x["dist_dc50"]), reverse=True)
    return rows


@router.get("/subscriptions")
async def get_alert_subscriptions(authorized: bool = Depends(verify_token)) -> Dict[str, Any]:
    """Return all available screeners and current user subscription status."""
    return {
        "screeners": [
            {
                **s,
                "is_subscribed": state_manager.is_subscribed(s["id"])
            }
            for s in AVAILABLE_SCREENERS
        ],
        "active_count": len(state_manager.subscribed_triggers)
    }


@router.post("/subscriptions")
async def update_alert_subscriptions(
    payload: SubscriptionUpdateRequest,
    authorized: bool = Depends(verify_token)
) -> Dict[str, Any]:
    """Update active alert subscriptions."""
    valid_ids = {s["id"] for s in AVAILABLE_SCREENERS}
    filtered_subs = [s for s in payload.subscriptions if s in valid_ids]
    state_manager.set_subscriptions(filtered_subs)
    await repo.set_state("ALERT_SUBSCRIPTIONS", json.dumps(filtered_subs))
    return {
        "status": "success",
        "message": f"Updated subscriptions: {len(filtered_subs)} alerts active.",
        "active_subscriptions": filtered_subs
    }


@router.post("/scan")
async def trigger_manual_scan(authorized: bool = Depends(verify_token)) -> Dict[str, Any]:
    """Force an immediate real-time scan cycle across all F&O symbols."""
    import asyncio
    if state_manager.scan_callback:
        asyncio.create_task(state_manager.scan_callback(force_execution=True))
        return {
            "status": "scanning",
            "message": "Live scan triggered in background. Ticks will refresh in a few seconds."
        }
    return {"status": "error", "message": "Scanner callback not initialized."}


@router.post("/admin/pause")
async def pause_scanner(authorized: bool = Depends(verify_token)) -> Dict[str, str]:
    state_manager.is_paused = True
    await repo.set_state("SCANNER_PAUSED", "true")
    return {"status": "paused", "message": "Scanner has been paused."}


@router.post("/admin/resume")
async def resume_scanner(authorized: bool = Depends(verify_token)) -> Dict[str, str]:
    state_manager.is_paused = False
    await repo.set_state("SCANNER_PAUSED", "false")
    return {"status": "resumed", "message": "Scanner has been resumed."}


@router.get("/admin/settings")
async def get_system_settings(authorized: bool = Depends(verify_token)) -> Dict[str, Any]:
    """Return active system parameters and operational configuration."""
    return {
        "poll_interval_sec": settings.POLL_INTERVAL_SEC,
        "trigger_mode": settings.TRIGGER_MODE,
        "is_paused": state_manager.is_paused,
        "health_status": state_manager.health_status,
        "universe_size": len(state_manager.active_universe),
        "levels_loaded": len(state_manager.levels),
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "telegram_chats_count": len(settings.telegram_chat_ids),
        "indicators": {
            "52w_lookback_days": settings.HIGH_52W_LOOKBACK_DAYS,
            "dc_lookback_days": settings.DONCHIAN_LOOKBACK_DAYS,
            "supertrend_daily": ["(10, 1)", "(10, 2)"],
            "supertrend_15m": ["(10, 1)", "(10, 2)"]
        },
        "filters": {
            "min_rvol": settings.MIN_RVOL,
            "min_turnover_cr": settings.MIN_TURNOVER_CR,
            "near_breakout_pct": settings.NEAR_BREAKOUT_THRESHOLD_PCT,
            "re_alert_threshold_pct": settings.RE_ALERT_THRESHOLD_PCT
        }
    }

"""
Storage repository providing CRUD operations for stock levels,
alerts, watchlists, and system state.
"""

from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from storage.models import StockLevel, AlertLog, Watchlist, SystemState
from storage.database import AsyncSessionLocal


class Repository:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return AsyncSessionLocal()

    # --- STOCK LEVELS ---
    async def upsert_stock_level(self, level_data: Dict[str, Any]) -> StockLevel:
        async with AsyncSessionLocal() as session:
            symbol = level_data["symbol"]
            stmt = select(StockLevel).where(StockLevel.symbol == symbol)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                for k, v in level_data.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(existing)
                return existing
            else:
                level = StockLevel(**level_data)
                session.add(level)
                await session.commit()
                await session.refresh(level)
                return level

    async def bulk_upsert_stock_levels(self, levels_list: List[Dict[str, Any]]) -> None:
        async with AsyncSessionLocal() as session:
            for data in levels_list:
                symbol = data["symbol"]
                stmt = select(StockLevel).where(StockLevel.symbol == symbol)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    for k, v in data.items():
                        setattr(existing, k, v)
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(StockLevel(**data))
            await session.commit()

    async def get_all_stock_levels(self) -> List[StockLevel]:
        async with AsyncSessionLocal() as session:
            stmt = select(StockLevel)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_stock_level(self, symbol: str) -> Optional[StockLevel]:
        async with AsyncSessionLocal() as session:
            stmt = select(StockLevel).where(StockLevel.symbol == symbol)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # --- ALERT LOGS & DEDUPLICATION ---
    async def get_today_alerts_for_symbol(
        self, symbol: str, target_date: date
    ) -> List[AlertLog]:
        async with AsyncSessionLocal() as session:
            stmt = select(AlertLog).where(
                and_(
                    AlertLog.symbol == symbol,
                    AlertLog.alert_date == target_date
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def log_alert(self, alert_data: Dict[str, Any]) -> AlertLog:
        async with AsyncSessionLocal() as session:
            log_entry = AlertLog(**alert_data)
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)
            return log_entry

    async def get_alerts_by_date(self, target_date: date) -> List[AlertLog]:
        async with AsyncSessionLocal() as session:
            stmt = select(AlertLog).where(
                AlertLog.alert_date == target_date
            ).order_by(AlertLog.alert_time.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def clear_alerts_for_date(self, target_date: date) -> None:
        async with AsyncSessionLocal() as session:
            stmt = delete(AlertLog).where(AlertLog.alert_date == target_date)
            await session.execute(stmt)
            await session.commit()

    async def update_alert_confirmed_close(self, symbol: str, alert_date: date, confirmed: bool) -> None:
        async with AsyncSessionLocal() as session:
            stmt = update(AlertLog).where(
                and_(
                    AlertLog.symbol == symbol,
                    AlertLog.alert_date == alert_date
                )
            ).values(confirmed_close=confirmed)
            await session.execute(stmt)
            await session.commit()

    # --- WATCHLIST ---
    async def add_to_watchlist(self, symbol: str, added_by: str = "telegram") -> bool:
        async with AsyncSessionLocal() as session:
            stmt = select(Watchlist).where(Watchlist.symbol == symbol.upper())
            res = await session.execute(stmt)
            item = res.scalar_one_or_none()
            if item:
                item.is_active = True
                await session.commit()
                return True
            session.add(Watchlist(symbol=symbol.upper(), added_by=added_by, is_active=True))
            await session.commit()
            return True

    async def remove_from_watchlist(self, symbol: str) -> bool:
        async with AsyncSessionLocal() as session:
            stmt = select(Watchlist).where(Watchlist.symbol == symbol.upper())
            res = await session.execute(stmt)
            item = res.scalar_one_or_none()
            if item:
                item.is_active = False
                await session.commit()
                return True
            return False

    async def get_active_watchlist(self) -> List[str]:
        async with AsyncSessionLocal() as session:
            stmt = select(Watchlist.symbol).where(Watchlist.is_active == True)
            res = await session.execute(stmt)
            return [r[0] for r in res.all()]

    # --- SYSTEM STATE ---
    async def set_state(self, key: str, value: str) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(SystemState).where(SystemState.key == key)
            res = await session.execute(stmt)
            state = res.scalar_one_or_none()
            if state:
                state.value = value
                state.updated_at = datetime.utcnow()
            else:
                session.add(SystemState(key=key, value=value))
            await session.commit()

    async def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with AsyncSessionLocal() as session:
            stmt = select(SystemState).where(SystemState.key == key)
            res = await session.execute(stmt)
            state = res.scalar_one_or_none()
            return state.value if state else default

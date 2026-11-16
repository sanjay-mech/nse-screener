"""
SQLAlchemy models for persisting calculated levels, alerts history,
watchlist, and system state.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    DateTime,
    Boolean,
    Integer,
    Text,
    Index,
    Date
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StockLevel(Base):
    __tablename__ = "stock_levels"

    symbol = Column(String(32), primary_key=True, index=True)
    calculated_date = Column(Date, nullable=False, index=True)
    ath_high = Column(Float, nullable=False)
    ath_date = Column(String(32), nullable=True)
    high_52w = Column(Float, nullable=False)
    high_52w_date = Column(String(32), nullable=True)
    donchian_50_high = Column(Float, nullable=False)
    donchian_50_date = Column(String(32), nullable=True)
    donchian_20_high = Column(Float, default=0.0)
    donchian_20_high_date = Column(String(32), nullable=True)
    # Sell side levels
    atl_low = Column(Float, default=0.0)
    atl_date = Column(String(32), nullable=True)
    low_52w = Column(Float, default=0.0)
    low_52w_date = Column(String(32), nullable=True)
    donchian_50_low = Column(Float, default=0.0)
    donchian_50_low_date = Column(String(32), nullable=True)
    donchian_20_low = Column(Float, default=0.0)
    donchian_20_low_date = Column(String(32), nullable=True)
    avg_vol_20d = Column(Float, default=0.0)
    atr_20d = Column(Float, default=0.0)
    last_close = Column(Float, nullable=False)
    sector = Column(String(64), default="N/A")
    upper_circuit = Column(Float, nullable=True)
    lower_circuit = Column(Float, nullable=True)
    is_fno = Column(Boolean, default=True)
    # Supertrend (10, 1) and (10, 2) on Daily TF
    st_daily_10_1_val = Column(Float, default=0.0)
    st_daily_10_1_dir = Column(Integer, default=1)
    st_daily_10_2_val = Column(Float, default=0.0)
    st_daily_10_2_dir = Column(Integer, default=1)
    # Supertrend (10, 1) and (10, 2) on 15m TF
    st_15m_10_1_val = Column(Float, default=0.0)
    st_15m_10_1_dir = Column(Integer, default=1)
    st_15m_10_2_val = Column(Float, default=0.0)
    st_15m_10_2_dir = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_symbol_date", "symbol", "calculated_date"),
    )


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    alert_date = Column(Date, nullable=False, index=True)
    alert_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    side = Column(String(16), default="BUY")  # "BUY" or "SELL"
    trigger_types = Column(String(64), nullable=False)  # e.g., "ATH + 52W + DC50"
    trigger_mode = Column(String(32), default="ltp_above")
    ltp = Column(Float, nullable=False)
    pct_change = Column(Float, default=0.0)
    level_broken = Column(Float, nullable=False)
    pct_above = Column(Float, default=0.0)
    prior_high_date = Column(String(32), nullable=True)
    rvol = Column(Float, default=1.0)
    atr_20 = Column(Float, default=0.0)
    sector = Column(String(64), default="N/A")
    ban_status = Column(String(32), default="NORMAL")
    message_sent = Column(Text, nullable=True)
    confirmed_close = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_alert_symbol_date_trigger", "symbol", "alert_date", "trigger_types"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, unique=True, index=True)
    added_by = Column(String(64), default="system")
    added_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(String(256), nullable=True)
    is_active = Column(Boolean, default=True)


class SystemState(Base):
    __tablename__ = "system_state"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

"""
Application configuration and settings loader.
Merges YAML configuration with environment variables and Pydantic validation.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_YAML_PATH = BASE_DIR / "config" / "config.yaml"


def load_yaml_config() -> dict:
    if CONFIG_YAML_PATH.exists():
        with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml_cfg = load_yaml_config()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App
    APP_NAME: str = _yaml_cfg.get("app", {}).get("name", "NSE Breakout Quant Screener")
    APP_VERSION: str = _yaml_cfg.get("app", {}).get("version", "1.0.0")
    ENV: str = os.getenv("ENV", _yaml_cfg.get("app", {}).get("env", "production"))
    TIMEZONE: str = _yaml_cfg.get("app", {}).get("timezone", "Asia/Kolkata")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", _yaml_cfg.get("app", {}).get("log_level", "INFO"))

    # Database
    DATABASE_URL: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{BASE_DIR / 'screener.db'}"
        )
    )
    # Sync fallback url for scripts and migrations
    DATABASE_URL_SYNC: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL_SYNC",
            os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'screener.db'}").replace("+aiosqlite", "")
        )
    )

    # Telegram Alerting
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_IDS: str = ""
    TELEGRAM_CHAT_IDS_RAW: str = ""
    TELEGRAM_CHANNEL_ATH_52W: str = ""
    TELEGRAM_CHANNEL_DC_ST: str = ""
    ADMIN_CHAT_ID: str = ""
    DASHBOARD_TOKEN: str = ""

    # Scanner Timing & Interval
    POLL_INTERVAL_SEC: int = int(os.getenv("POLL_INTERVAL_SEC", _yaml_cfg.get("scanner", {}).get("poll_interval_sec", 45)))
    BATCH_CONCURRENCY: int = int(_yaml_cfg.get("scanner", {}).get("batch_concurrency", 12))
    REQUEST_TIMEOUT_SEC: float = float(_yaml_cfg.get("scanner", {}).get("request_timeout_sec", 10.0))
    CIRCUIT_BREAKER_ERROR_THRESHOLD: int = int(_yaml_cfg.get("scanner", {}).get("circuit_breaker_error_threshold", 5))
    CIRCUIT_BREAKER_COOLDOWN_SEC: int = int(_yaml_cfg.get("scanner", {}).get("circuit_breaker_cooldown_sec", 120))
    STALE_DATA_MAX_AGE_SEC: int = int(_yaml_cfg.get("scanner", {}).get("stale_data_max_age_sec", 300))
    RETRY_ATTEMPTS: int = int(_yaml_cfg.get("scanner", {}).get("retry_attempts", 3))
    RETRY_BACKOFF_SEC: float = float(_yaml_cfg.get("scanner", {}).get("retry_backoff_sec", 1.5))

    # Market Timing
    TRADING_START: str = _yaml_cfg.get("market", {}).get("trading_start", "09:15:00")
    TRADING_END: str = _yaml_cfg.get("market", {}).get("trading_end", "15:30:00")
    PRE_MARKET_TIME: str = _yaml_cfg.get("market", {}).get("pre_market_time", "09:10:00")
    EOD_SUMMARY_TIME: str = _yaml_cfg.get("market", {}).get("eod_summary_time", "15:45:00")
    HISTORY_REFRESH_TIME: str = _yaml_cfg.get("market", {}).get("history_refresh_time", "16:30:00")
    SKIP_HOLIDAYS: bool = bool(_yaml_cfg.get("market", {}).get("skip_holidays", True))

    # Signal Logic
    TRIGGER_MODE: str = os.getenv("TRIGGER_MODE", _yaml_cfg.get("signals", {}).get("trigger_mode", "ltp_above"))
    DONCHIAN_LOOKBACK_DAYS: int = int(_yaml_cfg.get("signals", {}).get("donchian_lookback_days", 50))
    HIGH_52W_LOOKBACK_DAYS: int = int(_yaml_cfg.get("signals", {}).get("high_52w_lookback_days", 252))
    EXCLUDE_TODAY_FROM_HISTORY: bool = bool(_yaml_cfg.get("signals", {}).get("exclude_today_from_history", True))
    MIN_PRICE: float = float(_yaml_cfg.get("signals", {}).get("min_price", 20.0))
    MAX_PRICE: float = float(_yaml_cfg.get("signals", {}).get("max_price", 150000.0))
    MIN_AVG_VOLUME_20D: float = float(_yaml_cfg.get("signals", {}).get("min_avg_volume_20d", 50000.0))
    MIN_TURNOVER_CR: float = float(_yaml_cfg.get("signals", {}).get("min_turnover_cr", 5.0))
    MIN_RVOL: float = float(_yaml_cfg.get("signals", {}).get("min_rvol", 1.0))
    MAX_DISTANCE_FROM_LEVEL_PCT: float = float(_yaml_cfg.get("signals", {}).get("max_distance_from_level_pct", 3.5))
    MIN_DISTANCE_ABOVE_LEVEL_PCT: float = float(_yaml_cfg.get("signals", {}).get("min_distance_above_level_pct", 0.05))
    REQUIRE_VOLUME_CONFIRMATION: bool = bool(_yaml_cfg.get("signals", {}).get("require_volume_confirmation", False))
    REQUIRE_SUPERTREND_BULLISH: bool = bool(_yaml_cfg.get("signals", {}).get("require_supertrend_bullish", False))

    # Validation
    ENABLE_CROSS_VALIDATION: bool = bool(_yaml_cfg.get("validation", {}).get("enable_cross_validation", True))
    MAX_LTP_DIVERGENCE_PCT: float = float(_yaml_cfg.get("validation", {}).get("max_ltp_divergence_pct", 1.0))
    CORPORATE_ACTION_GAP_THRESHOLD_PCT: float = float(_yaml_cfg.get("validation", {}).get("corporate_action_gap_threshold_pct", 20.0))

    # Alerts
    DEDUPLICATE_PER_DAY: bool = bool(_yaml_cfg.get("alerts", {}).get("deduplicate_per_day", True))
    ALLOW_RE_ALERT_ON_NEW_HIGH: bool = bool(_yaml_cfg.get("alerts", {}).get("allow_re_alert_on_new_high", True))
    RE_ALERT_THRESHOLD_PCT: float = float(_yaml_cfg.get("alerts", {}).get("re_alert_threshold_pct", 1.5))
    NEAR_BREAKOUT_THRESHOLD_PCT: float = float(_yaml_cfg.get("alerts", {}).get("near_breakout_threshold_pct", 1.0))
    MAX_TELEGRAM_RETRIES: int = int(_yaml_cfg.get("alerts", {}).get("max_telegram_retries", 4))
    RATE_LIMIT_PER_SECOND: int = int(_yaml_cfg.get("alerts", {}).get("rate_limit_per_second", 20))

    # Universe
    UNIVERSE_SOURCE_URL: str = _yaml_cfg.get("universe", {}).get("source_url", "https://archives.nseindia.com/content/fo/fo_mktlots.csv")
    CACHE_TTL_HOURS: int = int(_yaml_cfg.get("universe", {}).get("cache_ttl_hours", 24))

    @property
    def telegram_chat_ids(self) -> List[str]:
        chats = []
        if self.TELEGRAM_CHANNEL_ATH_52W and self.TELEGRAM_CHANNEL_ATH_52W.strip() not in chats:
            chats.append(self.TELEGRAM_CHANNEL_ATH_52W.strip())
        if self.TELEGRAM_CHANNEL_DC_ST and self.TELEGRAM_CHANNEL_DC_ST.strip() not in chats:
            chats.append(self.TELEGRAM_CHANNEL_DC_ST.strip())
        if self.ADMIN_CHAT_ID and self.ADMIN_CHAT_ID.strip() not in chats:
            chats.append(self.ADMIN_CHAT_ID.strip())
        raw = self.TELEGRAM_CHAT_IDS or self.TELEGRAM_CHAT_IDS_RAW or ""
        if raw:
            for cid in raw.split(","):
                c = cid.strip()
                if c and c not in chats:
                    chats.append(c)
        return chats

    def fix_database_url_for_async(self) -> str:
        url = self.DATABASE_URL
        # Normalize postgres:// to postgresql+asyncpg:// if on Render
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # SQLite async support
        elif url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url


settings = Settings()

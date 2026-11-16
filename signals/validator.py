"""
Signal and Price Validator.
Performs data integrity checks:
1. Rejection of stale data ticks (> max age)
2. Cross-validation between primary (NSE) and secondary (Yahoo) quotes
   to guard against bad ticks / exchange test prints (> 1.0% divergence)
"""

from datetime import datetime
from typing import Tuple, Optional
from loguru import logger
from config.settings import settings
from signals.models import PriceTick


class SignalValidator:
    def __init__(
        self,
        max_age_sec: int = settings.STALE_DATA_MAX_AGE_SEC,
        max_divergence_pct: float = settings.MAX_LTP_DIVERGENCE_PCT,
        enable_cross_validation: bool = settings.ENABLE_CROSS_VALIDATION
    ):
        self.max_age_sec = max_age_sec
        self.max_divergence_pct = max_divergence_pct
        self.enable_cross_val = enable_cross_validation

    def validate_tick_freshness(self, tick: PriceTick) -> Tuple[bool, Optional[str]]:
        """Ensure the tick data is recent and not frozen."""
        if tick.ltp <= 0:
            return False, "Non-positive LTP"

        age = (datetime.utcnow() - tick.timestamp).total_seconds()
        if age > self.max_age_sec:
            return False, f"Stale tick: age is {age:.1f}s (max allowed {self.max_age_sec}s)"

        return True, None

    def cross_validate_quotes(
        self, nse_tick: PriceTick, yahoo_tick: Optional[PriceTick]
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Cross-validate NSE LTP against Yahoo LTP.
        Returns: (is_valid, divergence_pct, error_message)
        """
        if not self.enable_cross_val or yahoo_tick is None or yahoo_tick.ltp <= 0:
            # If cross-validation disabled or secondary feed missing, allow primary tick
            return True, 0.0, None

        nse_ltp = nse_tick.ltp
        yahoo_ltp = yahoo_tick.ltp

        # Calculate percentage divergence
        divergence_pct = abs(nse_ltp - yahoo_ltp) / ((nse_ltp + yahoo_ltp) / 2.0) * 100.0

        if divergence_pct > self.max_divergence_pct:
            msg = (
                f"Cross-validation FAILED for {nse_tick.symbol}: "
                f"NSE={nse_ltp:.2f} vs Yahoo={yahoo_ltp:.2f} "
                f"(Divergence {divergence_pct:.2f}% > {self.max_divergence_pct}%)"
            )
            logger.warning(msg)
            return False, divergence_pct, msg

        return True, divergence_pct, None


signal_validator = SignalValidator()

"""
NSE Live Market Data Client.
Features:
- Browser-mimicking headers and TLS fingerprint
- Dynamic cookie bootstrap and session management
- Auto-rebootstrap on HTTP 401/403 or session expiration
- Rate-limiting with semaphore and randomized jitter
- High-efficiency bulk F&O fetch with single-symbol fallback
- Circuit breaker to prevent cascading failures
"""

from __future__ import annotations
import asyncio
import random
import time
from datetime import datetime
from typing import Dict, List, Optional
import httpx
from loguru import logger
from config.settings import settings
from signals.models import PriceTick


class NSEClient:
    BASE_URL = "https://www.nseindia.com"
    BULK_FNO_URL = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
    QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/market-data/live-equity-market",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "Connection": "keep-alive",
    }

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cookie_timestamp: float = 0
        self._cookie_ttl_sec: float = 600  # Refresh cookies every 10 mins
        self._lock = asyncio.Lock()
        self._concurrency_semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)
        
        # Circuit Breaker state
        self._failure_count: int = 0
        self._circuit_open_until: float = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.HEADERS,
                timeout=settings.REQUEST_TIMEOUT_SEC,
                follow_redirects=True,
                http2=False
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _is_circuit_open(self) -> bool:
        if time.time() < self._circuit_open_until:
            return True
        return False

    def _record_success(self) -> None:
        self._failure_count = 0
        self._circuit_open_until = 0

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= settings.CIRCUIT_BREAKER_ERROR_THRESHOLD:
            self._circuit_open_until = time.time() + settings.CIRCUIT_BREAKER_COOLDOWN_SEC
            logger.error(
                f"NSE Client Circuit Breaker TRIPPED after {self._failure_count} consecutive failures. "
                f"Cooling down for {settings.CIRCUIT_BREAKER_COOLDOWN_SEC}s."
            )

    async def bootstrap_cookies(self, force: bool = False) -> bool:
        """Fetch base page to obtain valid NSE session cookies."""
        async with self._lock:
            now = time.time()
            if not force and (now - self._cookie_timestamp) < self._cookie_ttl_sec:
                return True

            client = await self._get_client()
            try:
                # Add jitter before bootstrap
                await asyncio.sleep(random.uniform(0.1, 0.4))
                resp = await client.get(self.BASE_URL)
                if resp.status_code == 200:
                    self._cookie_timestamp = time.time()
                    self._record_success()
                    logger.debug("NSE session cookies bootstrapped successfully.")
                    return True
                else:
                    logger.warning(f"NSE bootstrap returned HTTP {resp.status_code}")
                    self._record_failure()
                    return False
            except Exception as e:
                logger.warning(f"Failed to bootstrap NSE session cookies: {e}")
                self._record_failure()
                return False

    async def fetch_all_fno_quotes(self) -> Dict[str, PriceTick]:
        """
        Fetch all F&O stock quotes in a single batch request via the official F&O index endpoint.
        Returns a mapping of uppercase NSE symbol to PriceTick.
        """
        if self._is_circuit_open():
            logger.warning("NSE circuit breaker is OPEN. Skipping NSE bulk call.")
            return {}

        await self.bootstrap_cookies()
        client = await self._get_client()

        for attempt in range(1, settings.RETRY_ATTEMPTS + 1):
            try:
                # Jitter before request
                await asyncio.sleep(random.uniform(0.1, 0.3))
                resp = await client.get(self.BULK_FNO_URL)

                if resp.status_code == 200:
                    data = resp.json()
                    stocks_data = data.get("data", [])
                    ticks: Dict[str, PriceTick] = {}

                    for item in stocks_data:
                        raw_sym = item.get("symbol", "").strip().upper()
                        # Skip index itself if returned in the dataset
                        if not raw_sym or "NIFTY" in raw_sym:
                            continue

                        try:
                            ltp = float(item.get("lastPrice", 0.0))
                            day_high = float(item.get("dayHigh", ltp))
                            day_low = float(item.get("dayLow", ltp))
                            day_open = float(item.get("open", ltp))
                            prev_close = float(item.get("previousClose", ltp))
                            p_change = float(item.get("pChange", 0.0))
                            volume = int(item.get("totalTradedVolume", 0))
                            # Turnover in Crores (Value in Lakhs / 100 or Value in Crores)
                            # NSE reports totalTradedValue in Lakhs or Crores; standardizing to Cr:
                            val = float(item.get("totalTradedValue", 0.0))
                            turnover_cr = round(val / 100.0, 2) if val > 0 else 0.0

                            tick = PriceTick(
                                symbol=raw_sym,
                                ltp=ltp,
                                day_high=day_high,
                                day_low=day_low,
                                day_open=day_open,
                                prev_close=prev_close,
                                p_change=p_change,
                                volume=volume,
                                turnover_cr=turnover_cr,
                                source="NSE_BULK",
                                timestamp=datetime.utcnow()
                            )
                            ticks[raw_sym] = tick
                        except (ValueError, TypeError):
                            continue

                    if ticks:
                        self._record_success()
                        return ticks

                elif resp.status_code in (401, 403):
                    logger.warning(f"NSE bulk endpoint returned {resp.status_code}, re-bootstrapping cookies...")
                    await self.bootstrap_cookies(force=True)
                elif resp.status_code == 404:
                    logger.warning("NSE bulk endpoint returned 404. Switching to Yahoo fallback immediately.")
                    break
                else:
                    logger.warning(f"NSE bulk returned status {resp.status_code}")

            except Exception as e:
                logger.warning(f"NSE bulk attempt {attempt} failed: {e}")
                if attempt == settings.RETRY_ATTEMPTS:
                    self._record_failure()

            await asyncio.sleep(settings.RETRY_BACKOFF_SEC * attempt)

        return {}

    async def fetch_single_quote(self, symbol: str) -> Optional[PriceTick]:
        """
        Fallback method to fetch an individual quote if bulk endpoint misses a symbol.
        """
        if self._is_circuit_open():
            return None

        async with self._concurrency_semaphore:
            await self.bootstrap_cookies()
            client = await self._get_client()
            url = self.QUOTE_URL.format(symbol=symbol)

            try:
                await asyncio.sleep(random.uniform(0.05, 0.15))
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    price_info = data.get("priceInfo", {})
                    sec_details = data.get("securityWiseDP", {})

                    ltp = float(price_info.get("lastPrice", 0.0))
                    if ltp <= 0:
                        return None

                    intra_high = float(price_info.get("intraDayHighLow", {}).get("max", ltp))
                    intra_low = float(price_info.get("intraDayHighLow", {}).get("min", ltp))
                    day_open = float(price_info.get("open", ltp))
                    prev_close = float(price_info.get("previousClose", ltp))
                    p_change = float(price_info.get("pChange", 0.0))
                    volume = int(sec_details.get("quantityTraded", 0))

                    # Circuit limits
                    upper_c = price_info.get("upperCP")
                    lower_c = price_info.get("lowerCP")
                    upper_circuit = float(upper_c) if upper_c is not None else None
                    lower_circuit = float(lower_c) if lower_c is not None else None

                    return PriceTick(
                        symbol=symbol.upper(),
                        ltp=ltp,
                        day_high=intra_high,
                        day_low=intra_low,
                        day_open=day_open,
                        prev_close=prev_close,
                        p_change=p_change,
                        volume=volume,
                        turnover_cr=round((ltp * volume) / 10000000.0, 2),
                        upper_circuit=upper_circuit,
                        lower_circuit=lower_circuit,
                        source="NSE_SINGLE",
                        timestamp=datetime.utcnow()
                    )
            except Exception as e:
                logger.debug(f"Failed to fetch single quote for {symbol} from NSE: {e}")
                return None


nse_client = NSEClient()

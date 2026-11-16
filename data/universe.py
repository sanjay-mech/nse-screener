"""
NSE F&O Universe Manager.
Pulls current equity derivatives stock list dynamically from NSE,
caches to disk with TTL, excludes indexes, and provides a verified fallback list.
"""

from __future__ import annotations
import csv
import json
import time
from pathlib import Path
from typing import List, Set
import httpx
from loguru import logger
from config.settings import settings, BASE_DIR

INDEX_SYMBOLS: Set[str] = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "NIFTYIT",
}

# Verified comprehensive NSE F&O Stock Universe fallback (~185 equities)
FALLBACK_FNO_STOCKS: List[str] = [
    "AARTIIND", "ABB", "ABBOTINDIA", "ABCAPITAL", "ABFRL", "ACC", "ADANIENT",
    "ADANIPORTS", "ALKEM", "AMBUJACEM", "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY",
    "ASIANPAINT", "ASTRAL", "ATUL", "AUBANK", "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA",
    "BATAINDIA", "BEL", "BERGEPAINT", "BHARATFORG", "BHARTIARTL", "BHEL", "BIOCON",
    "BOSCHLTD", "BPCL", "BRITANNIA", "BSOFT", "CANBK", "CANFINHOME", "CHAMBLFERT",
    "CHOLAFIN", "CIPLA", "COALINDIA", "COFORGE", "COLPAL", "CONCOR", "COROMANDEL",
    "CROMPTON", "CUB", "CUMMINSIND", "DABUR", "DALBHARAT", "DEEPAKNTR", "DIVISLAB",
    "DIXON", "DLF", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND", "FEDERALBNK",
    "GAIL", "GLENMARK", "GMRINFRA", "GNFC", "GODREJCP", "GODREJPROP", "GRANULES",
    "GRASIM", "GUJGASLTD", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK",
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDCOPPER", "HINDPETRO", "HINDUNILVR",
    "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDEA", "IDFC", "IDFCFIRSTB", "IEX",
    "IGL", "INDHOTEL", "INDIACEM", "INDIAMART", "INDIGO", "INDUSINDBK", "INDUSTOWER",
    "INFY", "IOC", "IPCALAB", "IRCTC", "ITC", "JINDALSTEL", "JKCEMENT",
    "JSWSTEEL", "JUBLFOOD", "KOTAKBANK", "L&TFH", "LALPATHLAB", "LAURUSLABS",
    "LICHSGFIN", "LT", "LTIM", "LTTS", "LUPIN", "M&M", "M&MFIN", "MANAPPURAM",
    "MARICO", "MARUTI", "MCDOWELL-N", "MCX", "METROPOLIS", "MFSL", "MGL",
    "MOTHERSON", "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAUKRI",
    "NAVINFLUOR", "NESTLEIND", "NMDC", "NTPC", "OBEROIRLTY", "OFSS", "ONGC",
    "PAGEIND", "PEL", "PERSISTENT", "PETRONET", "PFC", "PIDILITIND", "PIIND",
    "PNB", "POLYCAB", "POONAWALLA", "POWERGRID", "PVRINOX", "RAMCOCEM", "RBLBANK",
    "RECLTD", "RELIANCE", "SAIL", "SBICARD", "SBILIFE", "SBIN", "SHREECEM",
    "SHRIRAMFIN", "SIEMENS", "SRF", "SUNPHARMA", "SUNTV", "SYNGENE", "TATACHEM",
    "TATACOMM", "TATACONSUM", "TATAMOTORS", "TATAPOWER", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TORNTPHARM", "TRENT", "TVSMOTOR", "UBL", "ULTRACEMCO",
    "UPL", "VEDL", "VOLTAS", "WIPRO", "ZEEL", "ZYDUSLIFE"
]


class UniverseManager:
    def __init__(self):
        self.cache_file = BASE_DIR / "data" / "universe_cache.json"
        self._symbols: List[str] = []

    def load_cached_universe(self) -> List[str]:
        if not self.cache_file.exists():
            return []
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_time = data.get("timestamp", 0)
            ttl_seconds = settings.CACHE_TTL_HOURS * 3600
            if (time.time() - cached_time) < ttl_seconds:
                symbols = data.get("symbols", [])
                if symbols:
                    logger.info(f"Loaded {len(symbols)} F&O symbols from valid local cache.")
                    return symbols
        except Exception as e:
            logger.warning(f"Error reading universe cache: {e}")
        return []

    def save_universe_cache(self, symbols: List[str]) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.time(),
                    "count": len(symbols),
                    "symbols": sorted(symbols)
                }, f, indent=2)
            logger.info(f"Saved {len(symbols)} F&O symbols to cache file.")
        except Exception as e:
            logger.warning(f"Failed to write universe cache: {e}")

    async def fetch_universe_from_nse(self) -> List[str]:
        """
        Download official F&O securities list from NSE archives or NSE index F&O list.
        Validates content to prevent binary/PDF misinterpretation.
        """
        urls = [
            "https://archives.nseindia.com/content/fo/fo_mktlots.csv",
            "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for url in urls:
                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200 and len(resp.text) > 100:
                        # Reject if NSE returned a PDF or HTML error page
                        if resp.text.startswith("%PDF") or "<html" in resp.text.lower():
                            logger.warning(f"NSE URL {url} returned PDF or HTML instead of CSV. Skipping.")
                            continue

                        lines = resp.text.strip().splitlines()
                        symbols: Set[str] = set()
                        reader = csv.reader(lines)
                        header = next(reader, None)
                        for row in reader:
                            if not row:
                                continue
                            raw_sym = row[1].strip() if len(row) > 1 else row[0].strip()
                            clean_sym = raw_sym.upper()
                            # Validate strict NSE ticker format and exclude index contracts
                            if clean_sym and clean_sym not in INDEX_SYMBOLS and clean_sym != "SYMBOL" and "NIFTY" not in clean_sym and "BANKNIFTY" not in clean_sym:
                                if all(c.isalnum() or c in ("-", "&") for c in clean_sym) and 2 <= len(clean_sym) <= 12:
                                    symbols.add(clean_sym)
                        
                        # NSE F&O universe is always between 120 and 250 equities
                        if 100 <= len(symbols) <= 250:
                            sym_list = sorted(list(symbols))
                            logger.info(f"Dynamically fetched {len(sym_list)} F&O equities from {url}")
                            self.save_universe_cache(sym_list)
                            return sym_list
                        else:
                            logger.warning(f"Extracted {len(symbols)} symbols from {url}, out of expected range [100, 250].")
                except Exception as e:
                    logger.debug(f"Failed to fetch F&O universe from {url}: {e}")

        return []

    async def get_symbols(self, force_refresh: bool = False) -> List[str]:
        """
        Return the current F&O equity universe, refreshing if needed.
        """
        if not force_refresh:
            cached = self.load_cached_universe()
            if cached:
                self._symbols = cached
                return self._symbols

        logger.info("Refreshing NSE F&O universe...")
        live_symbols = await self.fetch_universe_from_nse()
        if live_symbols:
            self._symbols = live_symbols
            return self._symbols

        # Fallback to verified curated list
        logger.warning(f"Using built-in fallback universe of {len(FALLBACK_FNO_STOCKS)} F&O equities.")
        self._symbols = sorted(FALLBACK_FNO_STOCKS)
        self.save_universe_cache(self._symbols)
        return self._symbols


universe_manager = UniverseManager()

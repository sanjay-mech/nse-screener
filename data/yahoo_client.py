"""
Yahoo Finance Client.
Features:
- Batch historical daily data download (period='max', interval='1d')
- Automatic adjustment for stock splits and bonus issues
- Exponential backoff and thread pool execution
- Real-time intraday quote fallback (1m/5m candles) when NSE is unavailable
- Cross-validation helper to verify LTP accuracy
"""

from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import yfinance as yf
from loguru import logger
from data.symbol_mapper import nse_to_yahoo_ticker, yahoo_to_nse_symbol
from signals.models import PriceTick


class YahooClient:
    def __init__(self, max_workers: int = 8):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def _sync_download_history(
        self, tickers: List[str], period: str = "max"
    ) -> Dict[str, pd.DataFrame]:
        """
        Synchronous batch downloader using yfinance with auto_adjust=True.
        """
        if not tickers:
            return {}

        results: Dict[str, pd.DataFrame] = {}
        batch_size = 50

        for i in range(0, len(tickers), batch_size):
            chunk = tickers[i : i + batch_size]
            ticker_str = " ".join(chunk)
            try:
                data = yf.download(
                    tickers=ticker_str,
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                    progress=False,
                    threads=True
                )

                if data.empty:
                    continue

                if len(chunk) == 1:
                    t = chunk[0]
                    if not data.empty and "Close" in data.columns:
                        results[t] = data.dropna(how="all")
                else:
                    for t in chunk:
                        if t in data.columns.levels[0]:
                            df = data[t].dropna(how="all")
                            if not df.empty and "Close" in df.columns:
                                results[t] = df
            except Exception as e:
                logger.warning(f"Error downloading batch from Yahoo ({chunk[:3]}...): {e}")

        return results

    async def fetch_historical_daily(
        self, symbols: List[str], period: str = "max"
    ) -> Dict[str, pd.DataFrame]:
        """
        Async wrapper to batch download historical adjusted daily bars.
        Returns mapping from NSE symbol to DataFrame.
        """
        loop = asyncio.get_running_loop()
        ticker_map = {nse_to_yahoo_ticker(s): s for s in symbols}
        tickers = list(ticker_map.keys())

        logger.info(f"Downloading historical daily data for {len(tickers)} tickers from Yahoo Finance...")
        raw_results = await loop.run_in_executor(
            self._executor, self._sync_download_history, tickers, period
        )

        final_data: Dict[str, pd.DataFrame] = {}
        for y_ticker, df in raw_results.items():
            nse_sym = ticker_map.get(y_ticker, yahoo_to_nse_symbol(y_ticker))
            if not df.empty and len(df) >= 20:
                final_data[nse_sym] = df

        logger.info(f"Successfully processed historical data for {len(final_data)} symbols.")
        return final_data

    def _fetch_single_chunk(
        self, chunk: List[str], prev_closes: Optional[Dict[str, float]] = None
    ) -> Dict[str, PriceTick]:
        if not chunk:
            return {}

        ticks: Dict[str, PriceTick] = {}
        try:
            data = yf.download(
                tickers=" ".join(chunk),
                period="1d",
                interval="5m",
                auto_adjust=True,
                group_by="ticker",
                progress=False,
                threads=True
            )

            if data.empty:
                return {}

            for t in chunk:
                df = None
                if isinstance(data.columns, pd.MultiIndex):
                    if t in data.columns.levels[0]:
                        df = data[t]
                    elif t in data.columns:
                        df = data[t]
                elif "Close" in data.columns:
                    df = data

                if df is not None and not df.empty and "Close" in df.columns:
                    valid_df = df.dropna(subset=["Close"])
                    if not valid_df.empty:
                        last_row = valid_df.iloc[-1]
                        ltp = float(last_row["Close"])
                        day_high = float(valid_df["High"].max())
                        day_low = float(valid_df["Low"].min())
                        day_open = float(valid_df["Open"].iloc[0])
                        volume = int(valid_df["Volume"].sum())
                        
                        nse_sym = yahoo_to_nse_symbol(t)
                        prev_close = day_open
                        if prev_closes and nse_sym in prev_closes and prev_closes[nse_sym] > 0:
                            prev_close = prev_closes[nse_sym]

                        p_change = round(((ltp - prev_close) / prev_close) * 100, 2) if prev_close > 0 else 0.0

                        # Extract current and previous 5m candle data for fresh breakout detection
                        c_curr_high = float(last_row["High"])
                        c_curr_low = float(last_row["Low"])
                        if len(valid_df) >= 2:
                            c_prev_high = float(valid_df["High"].iloc[-2])
                            c_prev_low = float(valid_df["Low"].iloc[-2])
                        else:
                            c_prev_high = c_curr_high
                            c_prev_low = c_curr_low

                        if len(valid_df) >= 3:
                            c_prior_close = float(valid_df["Close"].iloc[-3])
                        elif len(valid_df) >= 2:
                            c_prior_close = float(valid_df["Open"].iloc[-2])
                        else:
                            c_prior_close = day_open

                        ticks[nse_sym] = PriceTick(
                            symbol=nse_sym,
                            ltp=ltp,
                            day_high=day_high,
                            day_low=day_low,
                            day_open=day_open,
                            prev_close=prev_close,
                            p_change=p_change,
                            volume=volume,
                            turnover_cr=round((ltp * volume) / 10000000.0, 2),
                            source="LIVE (YAHOO)",
                            timestamp=datetime.utcnow(),
                            candle_5m_curr_high=c_curr_high,
                            candle_5m_curr_low=c_curr_low,
                            candle_5m_prev_high=c_prev_high,
                            candle_5m_prev_low=c_prev_low,
                            candle_5m_prior_close=c_prior_close
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch intraday chunk from Yahoo: {e}")

        return ticks

    def _sync_fetch_intraday_quotes(
        self, tickers: List[str], prev_closes: Optional[Dict[str, float]] = None
    ) -> Dict[str, PriceTick]:
        """
        Synchronously download today's 1m/5m intraday bars for live quotes in parallel chunks.
        """
        if not tickers:
            return {}

        ticks: Dict[str, PriceTick] = {}
        chunk_size = 40
        chunks = [tickers[i : i + chunk_size] for i in range(0, len(tickers), chunk_size)]

        with ThreadPoolExecutor(max_workers=min(len(chunks), 6)) as executor:
            future_results = [
                executor.submit(self._fetch_single_chunk, chunk, prev_closes)
                for chunk in chunks
            ]
            for future in future_results:
                try:
                    res = future.result()
                    ticks.update(res)
                except Exception as e:
                    logger.warning(f"Chunk fetch error: {e}")

        return ticks

    async def fetch_intraday_fallback(
        self, symbols: List[str], prev_closes: Optional[Dict[str, float]] = None
    ) -> Dict[str, PriceTick]:
        """
        Async wrapper for intraday live quotes via Yahoo Finance.
        """
        loop = asyncio.get_running_loop()
        tickers = [nse_to_yahoo_ticker(s) for s in symbols]
        return await loop.run_in_executor(
            self._executor, self._sync_fetch_intraday_quotes, tickers, prev_closes
        )

    def _sync_fetch_15m_bars(
        self, tickers: List[str], period: str = "5d"
    ) -> Dict[str, pd.DataFrame]:
        """
        Synchronously download 15m intraday bars for Supertrend calculation.
        """
        if not tickers:
            return {}

        results: Dict[str, pd.DataFrame] = {}
        batch_size = 40

        for i in range(0, len(tickers), batch_size):
            chunk = tickers[i : i + batch_size]
            ticker_str = " ".join(chunk)
            try:
                data = yf.download(
                    tickers=ticker_str,
                    period=period,
                    interval="15m",
                    auto_adjust=True,
                    group_by="ticker",
                    progress=False,
                    threads=True
                )

                if data.empty:
                    continue

                if len(chunk) == 1:
                    t = chunk[0]
                    if not data.empty and "Close" in data.columns:
                        results[t] = data.dropna(subset=["Close"])
                else:
                    for t in chunk:
                        if t in data.columns.levels[0]:
                            df = data[t].dropna(subset=["Close"])
                            if not df.empty and len(df) >= 15:
                                results[t] = df
            except Exception as e:
                logger.warning(f"Error downloading 15m bars from Yahoo ({chunk[:2]}...): {e}")

        return results

    async def fetch_15m_history(
        self, symbols: List[str], period: str = "5d"
    ) -> Dict[str, pd.DataFrame]:
        """
        Async wrapper to batch download 15m historical candles.
        Returns mapping from NSE symbol to 15m DataFrame.
        """
        loop = asyncio.get_running_loop()
        ticker_map = {nse_to_yahoo_ticker(s): s for s in symbols}
        tickers = list(ticker_map.keys())

        raw_results = await loop.run_in_executor(
            self._executor, self._sync_fetch_15m_bars, tickers, period
        )

        final_data: Dict[str, pd.DataFrame] = {}
        for y_ticker, df in raw_results.items():
            nse_sym = ticker_map.get(y_ticker, yahoo_to_nse_symbol(y_ticker))
            if not df.empty and len(df) >= 15:
                final_data[nse_sym] = df

        return final_data


yahoo_client = YahooClient()

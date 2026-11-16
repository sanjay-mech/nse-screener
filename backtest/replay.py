"""
Historical Backtest and Replay Engine.
Replays breakout detection logic day-by-day across historical candles:
- Ensures strict zero look-ahead bias (level calculated on bars [t-lookback : t-1])
- Verifies ATH, 52W, and Donchian 50 breakout signals
- Computes forward returns (1D, 5D, 10D) and close-confirmation metrics
"""

from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from loguru import logger
import yfinance as yf

from data.symbol_mapper import nse_to_yahoo_ticker
from signals.level_calculator import compute_levels_for_symbol
from signals.breakout_detector import breakout_detector
from signals.models import PriceTick


class HistoricalReplay:
    def __init__(
        self,
        symbol: str,
        lookback_days: int = 500,
        min_rvol: float = 1.0
    ):
        self.symbol = symbol.upper()
        self.lookback_days = lookback_days
        self.min_rvol = min_rvol

    def fetch_history(self) -> pd.DataFrame:
        ticker = nse_to_yahoo_ticker(self.symbol)
        df = yf.download(
            tickers=ticker,
            period="max",
            interval="1d",
            auto_adjust=True,
            progress=False
        )
        if df.empty:
            raise ValueError(f"No historical data found for {ticker}")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()

    def run_replay(self) -> List[Dict[str, Any]]:
        """
        Walk forward through time bar-by-bar to detect breakouts.
        """
        df = self.fetch_history()
        if len(df) < 270:
            raise ValueError(f"Insufficient history for {self.symbol} (minimum 270 trading days needed)")

        signals_found: List[Dict[str, Any]] = []
        total_bars = len(df)
        start_idx = max(260, total_bars - self.lookback_days)

        logger.info(f"Replaying {self.symbol} from bar {start_idx} to {total_bars} ({total_bars - start_idx} sessions)...")

        for i in range(start_idx, total_bars):
            # Window strictly up to t-1
            history_window = df.iloc[:i]
            current_bar = df.iloc[i]
            current_date = current_bar.name.date() if hasattr(current_bar.name, "date") else current_bar.name

            # Compute levels strictly as of t-1 (excluding today)
            levels = compute_levels_for_symbol(
                symbol=self.symbol,
                df=history_window,
                as_of_date=current_date
            )
            if not levels:
                continue

            open_p = float(current_bar["Open"])
            high_p = float(current_bar["High"])
            low_p = float(current_bar["Low"])
            close_p = float(current_bar["Close"])
            vol = int(current_bar["Volume"])
            prev_close = float(history_window["Close"].iloc[-1])
            p_change = round(((close_p - prev_close) / prev_close) * 100.0, 2)

            tick = PriceTick(
                symbol=self.symbol,
                ltp=close_p,
                day_high=high_p,
                day_low=low_p,
                day_open=open_p,
                prev_close=prev_close,
                p_change=p_change,
                volume=vol,
                turnover_cr=round((close_p * vol) / 10000000.0, 2),
                timestamp=datetime.combine(current_date, datetime.min.time())
            )

            # Evaluate breakout
            signal = breakout_detector.evaluate_breakout(tick, levels)
            if signal:
                # Forward performance measurement
                fwd_5d_return = None
                fwd_10d_return = None
                if i + 5 < total_bars:
                    fwd_5d_return = round(((df["Close"].iloc[i + 5] - close_p) / close_p) * 100.0, 2)
                if i + 10 < total_bars:
                    fwd_10d_return = round(((df["Close"].iloc[i + 10] - close_p) / close_p) * 100.0, 2)

                signals_found.append({
                    "date": str(current_date),
                    "symbol": self.symbol,
                    "triggers": signal.trigger_label,
                    "breakout_level": signal.level_broken,
                    "close": close_p,
                    "pct_above": signal.pct_above,
                    "rvol": signal.rvol,
                    "close_confirmed": close_p > signal.level_broken,
                    "fwd_5d_return_pct": fwd_5d_return,
                    "fwd_10d_return_pct": fwd_10d_return
                })

        return signals_found


def main():
    parser = argparse.ArgumentParser(description="Replay breakout detection logic on historical data.")
    parser.add_argument("--symbol", type=str, default="RELIANCE", help="NSE Symbol (e.g. RELIANCE, TCS, INFY)")
    parser.add_argument("--days", type=int, default=500, help="Number of trading days to replay")
    args = parser.parse_args()

    replay = HistoricalReplay(symbol=args.symbol, lookback_days=args.days)
    results = replay.run_replay()

    print(f"\n{'='*75}")
    print(f"REPLAY RESULTS: {args.symbol} (Last {args.days} trading days)")
    print(f"{'='*75}")
    print(f"Total Breakout Signals Detected: {len(results)}\n")

    if results:
        headers = ["Date", "Triggers", "Level", "Close", "% Above", "RVOL", "5D Ret", "10D Ret"]
        print(f"{headers[0]:<12} {headers[1]:<18} {headers[2]:<10} {headers[3]:<10} {headers[4]:<9} {headers[5]:<6} {headers[6]:<9} {headers[7]:<9}")
        print("-" * 88)
        for r in results:
            f5 = f"{r['fwd_5d_return_pct']:+.2f}%" if r['fwd_5d_return_pct'] is not None else "N/A"
            f10 = f"{r['fwd_10d_return_pct']:+.2f}%" if r['fwd_10d_return_pct'] is not None else "N/A"
            print(f"{r['date']:<12} {r['triggers']:<18} Rs.{r['breakout_level']:<7.2f} Rs.{r['close']:<7.2f} +{r['pct_above']:<7.2f}% {r['rvol']:<6.1f}x {f5:<9} {f10:<9}")

        # Summary statistics
        fwd5 = [r["fwd_5d_return_pct"] for r in results if r["fwd_5d_return_pct"] is not None]
        if fwd5:
            win_rate = (len([x for x in fwd5 if x > 0]) / len(fwd5)) * 100.0
            avg_ret = float(np.mean(fwd5))
            print(f"\n5-Day Win Rate: {win_rate:.1f}% | Avg 5-Day Return: {avg_ret:+.2f}%")


if __name__ == "__main__":
    main()

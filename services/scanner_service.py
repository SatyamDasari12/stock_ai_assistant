from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd
import yfinance as yf

from features.indicators import add_indicators_to_ohlc
from utils.logging import logger


# Small, editable universe examples. Extend this list for broader coverage.
UNIVERSE_MAP: Dict[str, List[str]] = {
    "NIFTY 50": [
        "RELIANCE.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "INFY.NS",
        "TCS.NS",
        "LT.NS",
        "SBIN.NS",
        "ITC.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
        "BEL.NS",
    ],
    "NIFTY 100": [
        "RELIANCE.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "INFY.NS",
        "TCS.NS",
        "LT.NS",
        "SBIN.NS",
        "ITC.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
        "BEL.NS",
        "SUNPHARMA.NS",
        "TATAMOTORS.NS",
        "POWERGRID.NS",
        "ONGC.NS",
    ],
    "NIFTY 200 (slower)": [
        "RELIANCE.NS",
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "INFY.NS",
        "TCS.NS",
        "LT.NS",
        "SBIN.NS",
        "ITC.NS",
        "KOTAKBANK.NS",
        "AXISBANK.NS",
        "BEL.NS",
        "SUNPHARMA.NS",
        "TATAMOTORS.NS",
        "POWERGRID.NS",
        "ONGC.NS",
        "NTPC.NS",
        "COALINDIA.NS",
        "HCLTECH.NS",
        "WIPRO.NS",
    ],
}


def _compute_intraday_score(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0

    last = df.iloc[-1]
    score = 0.0

    rsi = last.get("RSI_14")
    if pd.notna(rsi) and 55 <= rsi <= 75:
        score += 2.0

    vol_spike = last.get("VOLUME_SPIKE", 0)
    if vol_spike:
        score += 2.0

    close = last.get("Close")
    vwap = last.get("VWAP")
    if pd.notna(close) and pd.notna(vwap):
        if close > vwap:
            score += 1.5

    macd_hist = last.get("MACD_HIST")
    if pd.notna(macd_hist) and macd_hist > 0:
        score += 1.0

    return float(score)


def scan_intraday_momentum_stocks(
    universe: str,
    top_n: int = 15,
) -> pd.DataFrame:
    symbols = UNIVERSE_MAP.get(universe, [])
    if not symbols:
        return pd.DataFrame()

    end = datetime.now().date()
    start = end - timedelta(days=60)

    rows = []
    for symbol in symbols:
        try:
            df = yf.download(
                symbol,
                start=start,
                end=end,
                interval="1d",
                progress=False,
                auto_adjust=False,
            )
            if df is None or df.empty:
                continue
            df = df.rename(
                columns={
                    "Open": "Open",
                    "High": "High",
                    "Low": "Low",
                    "Close": "Close",
                    "Adj Close": "AdjClose",
                    "Volume": "Volume",
                }
            )
            df = add_indicators_to_ohlc(df)
            score = _compute_intraday_score(df)
            last = df.iloc[-1]
            rows.append(
                {
                    "Symbol": symbol,
                    "Score": score,
                    "Close": float(last.get("Close", 0.0)),
                    "RSI_14": float(last.get("RSI_14", 0.0)),
                    "Volume": float(last.get("Volume", 0.0)),
                }
            )
        except Exception as exc:
            logger.exception(f"Intraday scan failed for {symbol}: {exc}")
            continue

    if not rows:
        return pd.DataFrame()

    df_all = pd.DataFrame(rows)
    df_all = df_all.sort_values("Score", ascending=False).head(top_n)
    return df_all.reset_index(drop=True)


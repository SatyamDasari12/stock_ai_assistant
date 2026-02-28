from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import pandas as pd
import yfinance as yf

from utils.logging import logger

UNDERLYING_SYMBOLS: List[str] = [
    "RELIANCE.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "TCS.NS",
    "SBIN.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "BEL.NS",
]


def _scan_calls_for_symbol(
    symbol: str,
    expiry: str,
) -> Optional[pd.DataFrame]:
    try:
        ticker = yf.Ticker(symbol)
        if expiry not in ticker.options:
            return None
        chain = ticker.option_chain(expiry)
        calls = chain.calls.copy()
        if calls is None or calls.empty:
            return None

        spot = float(
            ticker.history(period="5d", auto_adjust=False)["Close"].iloc[-1]
        )

        calls["Underlying"] = symbol
        calls["Moneyness"] = (calls["strike"] - spot) / spot
        calls["OI_Score"] = calls["openInterest"].fillna(0) / max(
            calls["openInterest"].max(), 1
        )
        calls["Volume_Score"] = calls["volume"].fillna(0) / max(
            calls["volume"].max(), 1
        )

        # Favor near-the-money, liquid contracts
        calls["BullishScore"] = (
            (1 - calls["Moneyness"].abs()).clip(lower=0) * 0.4
            + calls["OI_Score"] * 0.35
            + calls["Volume_Score"] * 0.25
        )

        useful_cols = [
            "Underlying",
            "contractSymbol",
            "strike",
            "lastPrice",
            "bid",
            "ask",
            "openInterest",
            "volume",
            "BullishScore",
        ]
        return calls[useful_cols]
    except Exception as exc:
        logger.exception(f"Options scan failed for {symbol} {expiry}: {exc}")
        return None


def scan_bullish_call_options(
    expiry: str,
    top_n: int = 15,
) -> pd.DataFrame:
    # Validate expiry format early
    try:
        datetime.strptime(expiry, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Expiry must be in YYYY-MM-DD format")

    frames: List[pd.DataFrame] = []
    for symbol in UNDERLYING_SYMBOLS:
        df_symbol = _scan_calls_for_symbol(symbol, expiry)
        if df_symbol is not None and not df_symbol.empty:
            frames.append(df_symbol)

    if not frames:
        return pd.DataFrame()

    all_calls = pd.concat(frames, ignore_index=True)
    all_calls = all_calls.sort_values("BullishScore", ascending=False).head(top_n)
    all_calls.reset_index(drop=True, inplace=True)
    return all_calls


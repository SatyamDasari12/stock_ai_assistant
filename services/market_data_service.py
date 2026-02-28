from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from models.types import Quote
from features.indicators import add_indicators_to_ohlc
from utils.logging import logger


def get_price_history(
    symbol: str,
    start: date,
    end: date,
) -> Optional[pd.DataFrame]:
    try:
        df = yf.download(
            symbol,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        logger.exception(f"Failed to download history for {symbol}: {exc}")
        return None

    if df is None or df.empty:
        return None

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
    return df


def get_history_with_indicators(
    symbol: str,
    start: date,
    end: date,
) -> Optional[pd.DataFrame]:
    df = get_price_history(symbol, start, end)
    if df is None:
        return None
    return add_indicators_to_ohlc(df)


def get_latest_quote(symbol: str) -> Optional[Quote]:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo", auto_adjust=False)
    except Exception as exc:
        logger.exception(f"Failed to fetch latest quote for {symbol}: {exc}")
        return None

    if hist is None or hist.empty:
        return None

    hist = hist.rename(
        columns={
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Adj Close": "AdjClose",
            "Volume": "Volume",
        }
    )
    hist = add_indicators_to_ohlc(hist)
    last_price = float(hist["Close"].iloc[-1])
    return Quote(symbol=symbol, last_price=last_price, history_df=hist)


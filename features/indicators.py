from __future__ import annotations

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange, BollingerBands


def add_indicators_to_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich an OHLCV dataframe with standard technical indicators.

    Expects columns: Open, High, Low, Close, Volume
    Index should be datetime.
    """
    if df.empty:
        return df

    o = df["Open"]
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    v = df.get("Volume")

    # Moving averages
    df["SMA_20"] = c.rolling(window=20, min_periods=10).mean()
    df["SMA_50"] = c.rolling(window=50, min_periods=25).mean()
    df["SMA_200"] = c.rolling(window=200, min_periods=100).mean()

    # RSI
    rsi = RSIIndicator(close=c, window=14)
    df["RSI_14"] = rsi.rsi()

    # MACD
    macd = MACD(close=c, window_slow=26, window_fast=12, window_sign=9)
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_HIST"] = macd.macd_diff()

    # ATR
    atr = AverageTrueRange(high=h, low=l, close=c, window=14)
    df["ATR_14"] = atr.average_true_range()

    # Bollinger Bands
    bb = BollingerBands(close=c, window=20, window_dev=2)
    df["BB_HIGH"] = bb.bollinger_hband()
    df["BB_LOW"] = bb.bollinger_lband()
    df["BB_WIDTH"] = (df["BB_HIGH"] - df["BB_LOW"]) / c

    # VWAP (daily approximation on end-of-day data)
    if v is not None:
        typical_price = (h + l + c) / 3.0
        cum_vp = (typical_price * v).cumsum()
        cum_v = v.cumsum().replace(0, np.nan)
        df["VWAP"] = cum_vp / cum_v

        vol_mean = v.rolling(window=20, min_periods=10).mean()
        df["VOLUME_SPIKE"] = (v > 1.5 * vol_mean).astype(int)

    return df


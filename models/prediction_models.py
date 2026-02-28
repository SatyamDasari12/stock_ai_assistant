from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from models.types import WeeklyPredictionResult


def _volatility_based_range(df: pd.DataFrame) -> tuple[float, float]:
    close = df["Close"]
    last = float(close.iloc[-1])
    returns = close.pct_change().dropna()
    if returns.empty:
        return last * 0.95, last * 1.05

    avg_daily_vol = returns.std()
    weekly_vol = avg_daily_vol * np.sqrt(5)
    low = last * (1 - weekly_vol)
    high = last * (1 + weekly_vol)
    return low, high


def _try_prophet_forecast(df: pd.DataFrame) -> Optional[tuple[float, float]]:
    try:
        from prophet import Prophet  # type: ignore
    except Exception:
        return None

    hist = df["Close"].reset_index()
    hist.columns = ["ds", "y"]
    if len(hist) < 60:
        return None

    try:
        m = Prophet(daily_seasonality=True)
        m.fit(hist)
        future = m.make_future_dataframe(periods=5, freq="D")
        forecast = m.predict(future).tail(5)
        low = float(forecast["yhat_lower"].min())
        high = float(forecast["yhat_upper"].max())
        return low, high
    except Exception:
        return None


def predict_weekly_movement(df: pd.DataFrame) -> WeeklyPredictionResult:
    """
    Lightweight ensemble-style weekly outlook.

    Tries Prophet for a distributional forecast; if unavailable,
    falls back to a simple volatility-based range.
    """
    last_close = float(df["Close"].iloc[-1])

    prophet_range = _try_prophet_forecast(df)
    vol_low, vol_high = _volatility_based_range(df)

    if prophet_range is not None:
        low, high = prophet_range
        low = 0.5 * low + 0.5 * vol_low
        high = 0.5 * high + 0.5 * vol_high
    else:
        low, high = vol_low, vol_high

    mid = (low + high) / 2
    if mid > last_close * 1.01:
        trend = "Bullish"
        probability = 0.6
    elif mid < last_close * 0.99:
        trend = "Bearish"
        probability = 0.6
    else:
        trend = "Sideways"
        probability = 0.5

    return WeeklyPredictionResult(
        trend=trend,
        probability=probability,
        expected_low=low,
        expected_high=high,
    )


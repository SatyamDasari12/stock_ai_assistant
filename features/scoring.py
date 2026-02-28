from __future__ import annotations

import pandas as pd

from models.types import StockScorecard


def build_scorecard_from_history(df: pd.DataFrame) -> StockScorecard | None:
    if df is None or df.empty:
        return None

    latest = df.iloc[-1]

    # --- Trend score (0–3) ---
    trend_score = 0
    close = latest.get("Close")
    ma20 = latest.get("SMA_20")
    ma50 = latest.get("SMA_50")
    ma200 = latest.get("SMA_200")

    if pd.notna(close) and pd.notna(ma20) and close > ma20:
        trend_score += 1
    if pd.notna(ma20) and pd.notna(ma50) and ma20 > ma50:
        trend_score += 1
    if pd.notna(ma50) and pd.notna(ma200) and ma50 > ma200:
        trend_score += 1

    # --- Momentum score (0–3) ---
    momentum_score = 0
    rsi = latest.get("RSI_14")
    macd = latest.get("MACD")
    macd_hist = latest.get("MACD_HIST")

    if pd.notna(rsi) and 55 <= rsi <= 70:
        momentum_score += 1
    if pd.notna(macd) and macd > 0:
        momentum_score += 1
    if pd.notna(macd_hist) and macd_hist > 0:
        momentum_score += 1

    # --- Volume score (0–2) ---
    volume_score = 0
    vol_spike = latest.get("VOLUME_SPIKE", 0)
    if vol_spike:
        volume_score += 1

    if "Volume" in df.columns:
        v = df["Volume"]
        vol_z = (v - v.rolling(20, min_periods=10).mean()) / (
            v.rolling(20, min_periods=10).std()
        )
        if abs(vol_z.iloc[-1]) > 1.0:
            volume_score += 1

    # --- Volatility score (0–2) ---
    volatility_score = 0
    if "BB_WIDTH" in df.columns:
        width = df["BB_WIDTH"]
        current_w = width.iloc[-1]
        base_w = width.rolling(50, min_periods=20).median().iloc[-1]
        if pd.notna(current_w) and pd.notna(base_w) and current_w > base_w * 1.2:
            volatility_score += 1
    if "ATR_14" in df.columns:
        atr = df["ATR_14"]
        atr_rel = atr / df["Close"]
        current_a = atr_rel.iloc[-1]
        base_a = atr_rel.rolling(50, min_periods=20).median().iloc[-1]
        if pd.notna(current_a) and pd.notna(base_a) and current_a > base_a * 1.1:
            volatility_score += 1

    return StockScorecard(
        trend_score=int(trend_score),
        momentum_score=int(momentum_score),
        volume_score=int(volume_score),
        volatility_score=int(volatility_score),
    )


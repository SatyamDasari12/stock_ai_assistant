from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
    "SUNPHARMA.NS",
    "TATAMOTORS.NS",
    "HAL.NS",
]


def get_nearest_expiries(symbol: str = "RELIANCE.NS", count: int = 3) -> List[str]:
    """
    Return the nearest N option expiry dates available for a given symbol.
    Falls back to computing approximate monthly expiries if yfinance fails.
    """
    try:
        ticker = yf.Ticker(symbol)
        all_expiries = ticker.options  # tuple of YYYY-MM-DD strings
        if all_expiries:
            today = datetime.now().date()
            future = [e for e in all_expiries if datetime.strptime(e, "%Y-%m-%d").date() >= today]
            return list(future[:count])
    except Exception as exc:
        logger.warning(f"Could not fetch expiries from yfinance: {exc}")

    # Fallback: compute last Thursday of next few months (NSE style)
    expiries = []
    today = datetime.now().date()
    for month_offset in range(3):
        year = today.year + (today.month + month_offset - 1) // 12
        month = (today.month + month_offset - 1) % 12 + 1
        # Last Thursday of the month
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        d = datetime(year, month, last_day)
        while d.weekday() != 3:  # 3 = Thursday
            d -= timedelta(days=1)
        if d.date() >= today:
            expiries.append(d.strftime("%Y-%m-%d"))
    return expiries[:count]


def compute_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    """
    Compute the max pain strike price.
    Max pain is the strike at which total option value (ITM loss for buyers) is minimised.
    """
    try:
        if calls.empty and puts.empty:
            return None

        strikes = sorted(
            set(calls["strike"].tolist() if not calls.empty else [])
            | set(puts["strike"].tolist() if not puts.empty else [])
        )
        if not strikes:
            return None

        pain_values: Dict[float, float] = {}
        for strike in strikes:
            total_pain = 0.0
            # Call pain at this strike: sum of (strike - K) * OI for all K < strike
            if not calls.empty:
                itm_calls = calls[calls["strike"] < strike]
                total_pain += float(
                    ((strike - itm_calls["strike"]) * itm_calls["openInterest"].fillna(0)).sum()
                )
            # Put pain at this strike: sum of (K - strike) * OI for all K > strike
            if not puts.empty:
                itm_puts = puts[puts["strike"] > strike]
                total_pain += float(
                    ((itm_puts["strike"] - strike) * itm_puts["openInterest"].fillna(0)).sum()
                )
            pain_values[strike] = total_pain

        max_pain_strike = min(pain_values, key=pain_values.get)
        return float(max_pain_strike)
    except Exception as exc:
        logger.warning(f"Max pain computation failed: {exc}")
        return None


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
        puts = chain.puts.copy()
        if calls is None or calls.empty:
            return None

        hist = ticker.history(period="5d", auto_adjust=False)
        if hist.empty:
            return None
        spot = float(hist["Close"].iloc[-1])

        # Max pain for this underlying
        max_pain = compute_max_pain(calls, puts)

        calls["Underlying"] = symbol
        calls["Spot"] = spot
        calls["MaxPain"] = max_pain
        calls["Moneyness"] = (calls["strike"] - spot) / spot
        calls["OI_Score"] = calls["openInterest"].fillna(0) / max(
            calls["openInterest"].max(), 1
        )
        calls["Volume_Score"] = calls["volume"].fillna(0) / max(
            calls["volume"].max(), 1
        )

        # Approximate PCR using put vs call OI at same strike
        if puts is not None and not puts.empty:
            put_oi_by_strike = (
                puts[["strike", "openInterest"]]
                .groupby("strike")["openInterest"]
                .sum()
            )
            calls["Put_OI"] = calls["strike"].map(put_oi_by_strike).fillna(0)
            calls["PCR"] = calls["Put_OI"] / calls["openInterest"].replace(0, 1)
            calls["PCR_Score"] = (
                1.0 - (calls["PCR"] - 0.8).abs() / 0.8
            ).clip(lower=0.0, upper=1.0)
        else:
            calls["PCR"] = 0.0
            calls["PCR_Score"] = 0.5

        # Favor near-the-money, liquid, bullish OI/PCR strikes
        calls["BullishScore"] = (
            (1 - calls["Moneyness"].abs()).clip(lower=0) * 0.35
            + calls["OI_Score"] * 0.30
            + calls["Volume_Score"] * 0.20
            + calls["PCR_Score"] * 0.15
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
            "PCR",
            "MaxPain",
            "BullishScore",
        ]
        available = [c for c in useful_cols if c in calls.columns]
        return calls[available]
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

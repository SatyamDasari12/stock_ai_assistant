"""
Options Analysis Service — NSE F&O Call Buying Strategy (Advanced)
===================================================================
Implements the full 6-layer strategy from NSE_FO_Call_Buying_Strategy_Advanced.md

Layer 1 — Hard Filters (pre-qualification):
  • Volume ≥ 1.2× 20-day average
  • Close > 20 DMA
  • ATR(14)/Price ≥ 1.5%
  • 3-day price gain ≤ 8%
  • IV rank in [25, 65]

Layer 2 — Indicator Normalization (0–100):
  A. Momentum Score     (5-day % gain, normalised)          → 25%
  B. Breakout Strength  (close vs. 10-day highest high)     → 15%
  C. Volume Expansion   (today vs 20-day avg)               → 15%
  D. OI Long Buildup    (OI change, price↑ required)        → 15%
  E. RSI Zone Score     (ideal 45–65)                       → 10%
  F. IV Sweet Spot      (ideal rank 30–60)                  → 10%
  G. Nifty Alignment    (NIFTY50 > its 20 DMA)              → 10%

Layer 3 — Final Composite Score (0–100), select Top-N.

Layer 4 — Contract Selection:
  • Strike where 0.40 ≤ BS-Delta ≤ 0.55
  • Daily Theta ≤ 0.5% of option premium
  • Reward/Risk ≥ 1.8 (reward = target×delta, risk = premium×0.30)

Layer 5 — Exit signals included in output.

Layer 6 — Enhancements:
  • Relative Strength vs Nifty (10-day): +5 pts if RS > 0
  • Nifty alignment bonus already in Layer 2.
"""
from __future__ import annotations

import calendar
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from utils.logging import logger

# ── Paths ─────────────────────────────────────────────────────────────────────
_DATA_DIR = "data"
_FNO_MASTER_FILE = os.path.join(_DATA_DIR, "fno_master.json")

# ── NSE API headers ───────────────────────────────────────────────────────────
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ── Nifty 50 historical cache ─────────────────────────────────────────────────
_nifty_hist_cache: Optional[pd.DataFrame] = None


def _get_nifty_hist() -> pd.DataFrame:
    global _nifty_hist_cache
    if _nifty_hist_cache is not None:
        return _nifty_hist_cache
    try:
        t = yf.Ticker("^NSEI")
        h = t.history(period="90d", auto_adjust=False)
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = [c[0] for c in h.columns]
        _nifty_hist_cache = h
        return h
    except Exception:
        return pd.DataFrame()


# ── Hardcoded fallback F&O list ───────────────────────────────────────────────
_HARDCODED_FNO_STOCKS: List[str] = [
    "360ONE", "ABB", "ABCAPITAL", "ADANIENT", "ADANIGREEN", "ADANIPORTS",
    "ALKEM", "AMBER", "AMBUJACEM", "ANGELONE", "APLAPOLLO", "APOLLOHOSP",
    "ASHOKLEY", "ASIANPAINT", "ASTRAL", "AUBANK", "AUROPHARMA", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE", "BANDHANBNK",
    "BANKBARODA", "BANKINDIA", "BDL", "BEL", "BHARATFORG", "BHARTIARTL",
    "BHEL", "BIOCON", "BLUESTARCO", "BOSCHLTD", "BPCL", "BRITANNIA", "BSE",
    "CAMS", "CANBK", "CDSL", "CGPOWER", "CHOLAFIN", "CIPLA", "COALINDIA",
    "COFORGE", "COLPAL", "CONCOR", "CROMPTON", "CUMMINSIND", "DABUR",
    "DALBHARAT", "DELHIVERY", "DIVISLAB", "DIXON", "DLF", "DMART", "DRREDDY",
    "EICHERMOT", "EXIDEIND", "FEDERALBNK", "FORTIS", "GAIL", "GLENMARK",
    "GMRAIRPORT", "GODREJCP", "GODREJPROP", "GRASIM", "HAL", "HAVELLS",
    "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDPETRO", "HINDUNILVR", "ICICIBANK", "ICICIGI", "ICICIPRULI",
    "IDBI", "IDFCFIRSTB", "IEX", "IGL", "INDHOTEL", "INDIGO", "INDUSINDBK",
    "INDUSTOWER", "INFY", "IOC", "IPCALAB", "IRCTC", "IRFC",
    "ITC", "JKCEMENT", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL",
    "KOTAKBANK", "L&TFH", "LALPATHLAB", "LT", "LTTS", "LUPIN",
    "M&M", "M&MFIN", "MARICO", "MARUTI", "MAXHEALTH",
    "MCDOWELL-N", "MCX", "METROPOLIS", "MFSL", "MOTHERSON",
    "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAUKRI",
    "NBCC", "NCC", "NESTLEIND", "NMDC", "NTPC", "OBEROIRLTY",
    "OFSS", "ONGC", "PAGEIND", "PEL", "PERSISTENT",
    "PFC", "PIDILITIND", "PNB", "POLYCAB", "POWERGRID",
    "PVRINOX", "RECLTD", "RELIANCE", "RVNL", "SAIL", "SBICARD",
    "SBILIFE", "SBIN", "SHRIRAMFIN", "SIEMENS", "SONACOMS",
    "SUNPHARMA", "SUNTV", "TATACHEM", "TATACOMM", "TATACONSUM",
    "TATAELXSI", "TATAMOTORS", "TATAPOWER", "TATASTEEL", "TCS",
    "TECHM", "TIINDIA", "TITAN", "TORNTPHARM", "TRENT",
    "TVSMOTOR", "UBL", "ULTRACEMCO", "UNIONBANK", "UPL",
    "VEDL", "VOLTAS", "WIPRO", "YESBANK", "ZOMATO", "ZYDUSLIFE",
    "ADANIENSOL", "APOLLOTYRE", "MAZDOCK", "IREDA", "HUDCO", "ETERNAL",
]

# ── In-memory cache ───────────────────────────────────────────────────────────
_fno_master_cache: Optional[List[Dict]] = None


def load_fno_master() -> List[Dict]:
    """
    Load NSE F&O master from data/fno_master.json.
    All returned entries are guaranteed to have exchange == "NSE".
    Falls back to NSE live API, then hardcoded list.
    BSE stocks are never included.
    """
    global _fno_master_cache
    if _fno_master_cache is not None:
        return _fno_master_cache

    if os.path.exists(_FNO_MASTER_FILE):
        try:
            with open(_FNO_MASTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 50:
                # ── NSE-only guard: drop any non-NSE entries ──────────────
                nse_only = [e for e in data if str(e.get("exchange", "NSE")).upper() == "NSE"]
                dropped = len(data) - len(nse_only)
                if dropped:
                    logger.warning(
                        f"Dropped {dropped} non-NSE entries from fno_master.json. "
                        "Re-run scripts/refresh_fno_master.py to fix the master."
                    )
                _fno_master_cache = nse_only
                logger.info(
                    f"F&O master loaded: {len(nse_only)} NSE stocks "
                    f"(from {_FNO_MASTER_FILE})"
                )
                return _fno_master_cache
        except Exception as exc:
            logger.warning(f"Failed to load fno_master.json: {exc}")

    # ── Live fallback: NSE Securities-in-F&O index ────────────────────────
    _nse_fo_url = (
        "https://www.nseindia.com/api/equity-stockIndices"
        "?index=SECURITIES%20IN%20F%26O"
    )
    for url in [_nse_fo_url, "https://www.nseindia.com/api/master-quote"]:
        try:
            r = requests.get(url, headers=_NSE_HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            payload = r.json()
            # Securities-in-F&O returns {data: [{symbol:...}, ...]}
            # master-quote returns ["SYM1", "SYM2", ...]
            if isinstance(payload, dict) and "data" in payload:
                symbols = sorted({
                    str(d["symbol"]).strip().upper()
                    for d in payload["data"]
                    if d.get("symbol") and d["symbol"] != "SECURITIES IN F&O"
                })
            elif isinstance(payload, list):
                symbols = sorted({str(s).strip().upper() for s in payload if s})
            else:
                continue
            if len(symbols) > 50:
                _fno_master_cache = [
                    {"symbol": s, "name": s, "lot_size": 0, "exchange": "NSE"}
                    for s in symbols
                ]
                logger.info(f"F&O master from live NSE API: {len(symbols)} stocks")
                return _fno_master_cache
        except Exception:
            continue

    # ── Ultimate hardcoded fallback ───────────────────────────────────────
    _fno_master_cache = [
        {"symbol": s, "name": s, "lot_size": 0, "exchange": "NSE"}
        for s in _HARDCODED_FNO_STOCKS
    ]
    logger.warning("F&O master using hardcoded fallback list")
    return _fno_master_cache


def get_fno_stock_list() -> List[str]:
    return [e["symbol"] for e in load_fno_master()]


def get_fno_master_map() -> Dict[str, Dict]:
    return {e["symbol"]: e for e in load_fno_master()}


# ── Month helpers ─────────────────────────────────────────────────────────────

def _last_thursday_of_month(year: int, month: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    while d.weekday() != 3:
        d -= timedelta(days=1)
    return d


def get_month_options() -> List[Tuple[str, int, int]]:
    now = datetime.now()
    result = []
    for offset in range(5):
        m = now.month + offset
        y = now.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        approx = _last_thursday_of_month(y, m)
        if approx.date() >= now.date():
            label = datetime(y, m, 1).strftime("%B %Y")
            result.append((label, y, m))
    return result


def _find_month_expiry(ticker: yf.Ticker, year: int, month: int) -> Optional[str]:
    try:
        all_opts = ticker.options
        if all_opts:
            matches = [
                e for e in all_opts
                if datetime.strptime(e, "%Y-%m-%d").year == year
                and datetime.strptime(e, "%Y-%m-%d").month == month
            ]
            if matches:
                return min(matches)
    except Exception:
        pass
    approx = _last_thursday_of_month(year, month)
    if approx.date() >= datetime.now().date():
        return approx.strftime("%Y-%m-%d")
    return None


# ── Strike / contract ─────────────────────────────────────────────────────────

def _strike_step(spot: float) -> float:
    if spot < 100:      return 5.0
    elif spot < 250:    return 10.0
    elif spot < 500:    return 25.0
    elif spot < 1000:   return 50.0
    elif spot < 2500:   return 100.0
    elif spot < 5000:   return 200.0
    elif spot < 10000:  return 500.0
    else:               return 1000.0


def _contract_name(symbol: str, expiry_str: str, strike: float, opt_type: str = "CE") -> str:
    dt = datetime.strptime(expiry_str, "%Y-%m-%d")
    month_abbr = dt.strftime("%b").upper()
    strike_str = f"{int(strike)}" if strike == int(strike) else f"{strike:.1f}"
    return f"{symbol} {month_abbr} {strike_str} {opt_type}"


# ── Black-Scholes (call price, delta, theta) ──────────────────────────────────

def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0.0)
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return max(S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2), 0.0)
    except Exception:
        return max(S - K, 0.0)


def _bs_greeks(S: float, K: float, T: float, r: float, sigma: float) -> Tuple[float, float, float]:
    """Returns (price, delta, daily_theta)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(S - K, 0.0), 1.0 if S > K else 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        # Theta (per year) → daily
        theta_annual = (
            -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
        )
        daily_theta = theta_annual / 365.0
        return max(price, 0.0), delta, daily_theta
    except Exception:
        return max(S - K, 0.0), 0.5, 0.0


def _estimate_volatility(hist: pd.DataFrame) -> float:
    try:
        closes = hist["Close"].dropna()
        if len(closes) < 5:
            return 0.30
        log_rets = (closes / closes.shift(1)).apply(math.log).dropna()
        return float(min(max(log_rets.std() * math.sqrt(252), 0.05), 2.5))
    except Exception:
        return 0.30


def _estimate_iv_rank(sigma: float, hist: pd.DataFrame) -> float:
    """
    Proxy IV Rank: compare current HV (30-day) against its 52-week range.
    Returns a 0-100 rank.
    """
    try:
        closes = hist["Close"].dropna()
        if len(closes) < 30:
            return 50.0
        # Rolling 10-day HV as proxy for option IV series
        log_rets = (closes / closes.shift(1)).apply(math.log)
        rolling_hv = log_rets.rolling(10).std() * math.sqrt(252)
        rolling_hv = rolling_hv.dropna()
        if len(rolling_hv) < 10:
            return 50.0
        hv_min = float(rolling_hv.min())
        hv_max = float(rolling_hv.max())
        current_hv = float(rolling_hv.iloc[-1])
        if hv_max == hv_min:
            return 50.0
        return round(((current_hv - hv_min) / (hv_max - hv_min)) * 100, 1)
    except Exception:
        return 50.0


# ── News sentiment ─────────────────────────────────────────────────────────────

_POSITIVE_WORDS = {
    "surge", "rally", "beats", "gain", "upgrade", "outperform", "record",
    "profit", "growth", "buy", "bullish", "strong", "positive", "win", "order",
    "contract", "expansion", "raised", "delivered", "milestone", "boost",
    "jump", "soar", "breakout", "target", "momentum",
}
_NEGATIVE_WORDS = {
    "fall", "drop", "crash", "miss", "downgrade", "underperform", "loss",
    "weak", "bearish", "sell", "concern", "risk", "fraud", "delay", "penalty",
    "fine", "lawsuit", "warning", "caution", "cut", "selloff", "probe",
    "decline", "slump", "below", "disappoint",
}


def _get_news_sentiment(symbol: str) -> Tuple[float, str]:
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        news = ticker.news
        if not news:
            return 0.0, ""
        scores = []
        headlines = []
        for article in news[:5]:
            content = article.get("content", article)
            title = (
                content.get("title", "") if isinstance(content, dict)
                else article.get("title", "")
            ).lower()
            if not title:
                continue
            headlines.append(title[:80])
            pos = sum(1 for w in _POSITIVE_WORDS if w in title)
            neg = sum(1 for w in _NEGATIVE_WORDS if w in title)
            scores.append(1.0 if pos > neg else (-1.0 if neg > pos else 0.0))
        avg = (sum(scores) / len(scores)) if scores else 0.0
        return round(avg, 2), headlines[0] if headlines else ""
    except Exception:
        return 0.0, ""


# ── NSE live option LTP ───────────────────────────────────────────────────────

_nse_session = requests.Session()
_nse_session_warmed = False


def _warm_nse_session() -> None:
    global _nse_session_warmed
    if _nse_session_warmed:
        return
    try:
        _nse_session.get(
            "https://www.nseindia.com/api/master-quote",
            headers=_NSE_HEADERS, timeout=6,
        )
        _nse_session_warmed = True
    except Exception:
        pass


def _fetch_live_option_ltp(
    symbol: str, expiry_str: str, strike: float, opt_type: str = "CE",
) -> Optional[float]:
    try:
        _warm_nse_session()
        h = {
            **_NSE_HEADERS,
            "Accept": "application/json",
            "Referer": f"https://www.nseindia.com/get-quotes/derivatives?symbol={symbol}",
        }
        r = _nse_session.get(
            f"https://www.nseindia.com/api/quote-derivative?symbol={symbol}",
            headers=h, timeout=6,
        )
        if r.status_code != 200 or len(r.text) < 50:
            return None
        data = r.json()
        stocks = data.get("stocks", [])
        if not stocks:
            return None
        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        # Windows doesn't support %-d; use lstrip("0") instead
        alt_expiry = expiry_dt.strftime("%d-%b-%Y")        # "27-Mar-2026"
        nse_expiry = alt_expiry.lstrip("0")                # "27-Mar-2026" (no leading zero)
        for entry in stocks:
            md = entry.get("metadata", {})
            e_expiry = str(md.get("expiryDate", "")).strip()
            e_strike = float(md.get("strikePrice", 0))
            e_type = str(md.get("optionType", "")).upper().strip()
            e_instr = str(md.get("instrumentType", "")).upper()
            if (
                "OPT" in e_instr
                and e_type == opt_type.upper()
                and abs(e_strike - strike) < 0.5
                and (e_expiry == nse_expiry or e_expiry == alt_expiry)
            ):
                ltp = md.get("lastPrice") or md.get("ltp")
                if ltp and str(ltp) not in ("-", "", "0"):
                    return float(str(ltp).replace(",", ""))
        return None
    except Exception as exc:
        logger.debug(f"NSE LTP fetch {symbol} {expiry_str} {strike}{opt_type}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1: HARD FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_hard_filters(hist: pd.DataFrame, spot: float) -> Tuple[bool, Dict]:
    """
    Returns (passes, filter_details).
    Checks:
      • Close > 20 DMA
      • Volume ≥ 1.2× 20-day avg volume
      • ATR(14)/Price ≥ 1.5%
      • 3-day price gain ≤ 8%
      • IV rank ∈ [25, 65]  (computed as HV rank proxy)
    """
    details: Dict = {}
    try:
        closes = hist["Close"].dropna()
        n = len(closes)
        last = float(closes.iloc[-1])

        # Close > 20 DMA
        sma20 = float(closes.tail(20).mean()) if n >= 20 else None
        above_sma20 = (sma20 is not None and last > sma20)
        details["Above 20DMA"] = above_sma20
        details["20DMA"] = round(sma20, 2) if sma20 else None

        # Volume ≥ 1.2× 20-day avg
        vol_ok = False
        if "Volume" in hist.columns:
            vols = hist["Volume"].dropna()
            if len(vols) >= 20:
                avg_vol = float(vols.tail(20).mean())
                today_vol = float(vols.iloc[-1])
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0
                vol_ok = vol_ratio >= 1.2
                details["Vol Ratio"] = round(vol_ratio, 2)
            else:
                vol_ok = True  # insufficient data — pass through
                details["Vol Ratio"] = None
        else:
            vol_ok = True
            details["Vol Ratio"] = None

        # ATR(14)/Price ≥ 1.5%
        try:
            hi = hist["High"].values[-15:]
            lo = hist["Low"].values[-15:]
            cl = closes.values[-15:]
            trs = [max(hi[i]-lo[i], abs(hi[i]-cl[i-1]), abs(lo[i]-cl[i-1]))
                   for i in range(1, len(hi))]
            atr = sum(trs[-14:]) / min(len(trs), 14) if trs else spot * 0.02
        except Exception:
            atr = spot * 0.02
        atr_pct = atr / last * 100
        atr_ok = atr_pct >= 1.5
        details["ATR%"] = round(atr_pct, 2)
        details["atr"] = round(atr, 2)

        # 3-day gain ≤ 8%
        gain3 = 0.0
        if n >= 4:
            gain3 = (last - float(closes.iloc[-4])) / float(closes.iloc[-4]) * 100
        gain3_ok = gain3 <= 8.0
        details["3d Gain%"] = round(gain3, 2)

        # IV Rank [25, 65]
        iv_rank = _estimate_iv_rank(_estimate_volatility(hist), hist)
        iv_ok = 25 <= iv_rank <= 65
        details["IV Rank"] = round(iv_rank, 1)

        passes = above_sma20 and vol_ok and atr_ok and gain3_ok
        # IV rank is a soft pre-filter — log but don't hard-exclude
        # (because HV-proxy may not exactly match option IV rank)
        details["PassedHardFilter"] = passes
        return passes, details

    except Exception as exc:
        logger.debug(f"Hard filter error: {exc}")
        return True, {}  # pass on error: don't exclude on bad data


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2: INDICATOR NORMALIZATION (0–100)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_composite_score(
    hist: pd.DataFrame,
    spot: float,
    iv_rank: float,
    nifty_hist: pd.DataFrame,
) -> Tuple[float, Dict]:
    """
    Computes the 7-factor composite score (0–100) and sub-scores.

    Returns (final_score_0_100, sub_scores_dict)
    """
    sub: Dict = {}
    try:
        closes = hist["Close"].dropna()
        n = len(closes)

        # ── A. Momentum Score (25%) ────────────────────────────────────────
        # Momentum = ((Close / Close_5daysAgo) - 1) × 100
        # Score = Min(100, Max(0, Momentum × 5))
        mom = 0.0
        if n >= 6:
            mom = (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100
        a_score = min(100.0, max(0.0, mom * 5))
        sub["A_Momentum"] = round(a_score, 1)
        sub["Momentum%"] = round(mom, 2)

        # ── B. Breakout Strength (15%) ─────────────────────────────────────
        # Score = 100 if Close > HighestHigh(10) else 0
        b_score = 0.0
        if n >= 11:
            highest10 = float(hist["High"].dropna().tail(11).iloc[:-1].max())
            b_score = 100.0 if spot > highest10 else 0.0
            sub["HighestHigh10"] = round(highest10, 2)
        sub["B_Breakout"] = b_score

        # ── C. Volume Expansion (15%) ──────────────────────────────────────
        # Volume_Score = Min(100, Volume_Ratio × 50)
        c_score = 50.0  # neutral default
        if "Volume" in hist.columns:
            vols = hist["Volume"].dropna()
            if len(vols) >= 20:
                avg_vol = float(vols.tail(20).mean())
                today_vol = float(vols.iloc[-1])
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0
                c_score = min(100.0, vol_ratio * 50)
                sub["VolRatio"] = round(vol_ratio, 2)
        sub["C_Volume"] = round(c_score, 1)

        # ── D. OI Long Buildup (15%) ───────────────────────────────────────
        # OI not available from yfinance for NSE → proxy: if price ↑ AND volume
        # expansion, treat as OI buildup. OI_Score = volume expansion bonus × 1.5
        # (since real OI unavailable; flag this in output)
        d_score = 0.0
        mom_positive = mom > 0
        if mom_positive and c_score > 50:
            # Proxy: price up + volume expanding = probable long buildup
            d_score = min(100.0, (c_score - 50) * 2)  # 0–100 when vol expands
        sub["D_OI_Proxy"] = round(d_score, 1)
        sub["OI_Proxy_Note"] = "Price↑+Vol proxy (live OI unavailable)"

        # ── E. RSI Zone Score (10%) ────────────────────────────────────────
        # 45–65 → 100, 65–72 → 60, >72 → 20, else → 40
        try:
            delta = closes.diff().dropna()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, float("inf"))
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        except Exception:
            rsi = 50.0
        if 45 <= rsi <= 65:
            e_score = 100.0
        elif 65 < rsi <= 72:
            e_score = 60.0
        elif rsi > 72:
            e_score = 20.0
        else:
            e_score = 40.0
        sub["E_RSI"] = round(e_score, 1)
        sub["RSI"] = round(rsi, 1)

        # ── F. IV Sweet Spot Score (10%) ───────────────────────────────────
        # Ideal rank 30–60 → 100, 20–30 or 60–70 → 60, else → 20
        if 30 <= iv_rank <= 60:
            f_score = 100.0
        elif (20 <= iv_rank < 30) or (60 < iv_rank <= 70):
            f_score = 60.0
        else:
            f_score = 20.0
        sub["F_IV"] = round(f_score, 1)
        sub["IV_Rank"] = round(iv_rank, 1)

        # ── G. Nifty Alignment (10%) ───────────────────────────────────────
        # NIFTY50 Close > its 20 DMA → 100 else 40
        g_score = 40.0
        if not nifty_hist.empty:
            nc = nifty_hist["Close"].dropna()
            if len(nc) >= 20:
                nifty_close = float(nc.iloc[-1])
                nifty_sma20 = float(nc.tail(20).mean())
                g_score = 100.0 if nifty_close > nifty_sma20 else 40.0
                sub["Nifty_Above20DMA"] = nifty_close > nifty_sma20
        sub["G_Nifty"] = g_score

        # ── Composite ──────────────────────────────────────────────────────
        composite = (
            0.25 * a_score
            + 0.15 * b_score
            + 0.15 * c_score
            + 0.15 * d_score
            + 0.10 * e_score
            + 0.10 * f_score
            + 0.10 * g_score
        )

        # ── Layer 6: Enhancements ──────────────────────────────────────────
        bonus = 0.0

        # Relative Strength vs Nifty (10-day)
        rs_10d = 0.0
        if not nifty_hist.empty and n >= 11:
            nc = nifty_hist["Close"].dropna()
            if len(nc) >= 11:
                stock_ret10 = (float(closes.iloc[-1]) / float(closes.iloc[-11]) - 1) * 100
                nifty_ret10 = (float(nc.iloc[-1]) / float(nc.iloc[-11]) - 1) * 100
                rs_10d = stock_ret10 - nifty_ret10
                if rs_10d > 0:
                    bonus += 5.0
        sub["RS_vs_Nifty_10d"] = round(rs_10d, 2)
        sub["RS_Bonus"] = bonus

        final = round(min(composite + bonus, 100.0), 2)
        sub["FinalScore"] = final

        return final, sub

    except Exception as exc:
        logger.debug(f"Composite score error: {exc}")
        return 50.0, {}


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4: SMART STRIKE SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _choose_strike_type(
    momentum_score: float,
    volume_ratio: float,
    iv_rank: float,
    iv_high_threshold: float = 60.0,
) -> Tuple[int, str]:
    """
    Deterministic 3-rule strike selection:

      Rule 1 (★ Aggressive):  Momentum_Score > 75 AND Volume_Ratio > 1.8
                               → OTM +1  (accelerating momentum, confirm with volume)

      Rule 2 (★ Conservative): IV Rank slightly high (> iv_high_threshold)
                               → ITM −1  (options are expensive; ITM lets us buy
                                          intrinsic value cheaply, theta is lower)

      Default:                 ATM       (balanced Delta ~0.50, strategy sweet spot)

    Returns (strike_offset, label)
      strike_offset: number of steps relative to ATM
                     0 = ATM, +1 = OTM +1, -1 = ITM -1
    """
    if momentum_score > 75 and volume_ratio > 1.8:
        return +1, "OTM +1"
    elif iv_rank > iv_high_threshold:
        return -1, "ITM -1"
    else:
        return 0, "ATM"


def _select_optimal_strike(
    spot: float,
    T: float,
    sigma: float,
    atr: float,
    momentum_score: float,
    volume_ratio: float,
    iv_rank: float,
    risk_free_rate: float = 0.067,
    min_rr_ratio: float = 1.8,
    max_theta_pct: float = 0.005,
) -> Optional[Dict]:
    """
    Select the single optimal option strike using the 3-rule logic, then
    compute Black-Scholes Greeks and validate Delta/Theta/R-R constraints.

    Strike Decision Rules
    ---------------------
    Rule 1 (Aggressive):   Momentum_Score > 75 AND Volume_Ratio > 1.8 → OTM +1
    Rule 2 (Conservative): IV Rank > 60                                → ITM -1
    Default:               ATM

    Greeks are computed for the selected strike and shown as advisory flags
    (not hard filters) — so no good stock is ever dropped due to Greeks alone.
    """
    step = _strike_step(spot)
    atm = round(spot / step) * step

    # ── Rule-based strike selection ────────────────────────────────────
    offset, strike_type_label = _choose_strike_type(momentum_score, volume_ratio, iv_rank)
    K = atm + offset * step
    if K <= 0:
        K = atm        # safety: never go below zero
        offset = 0
        strike_type_label = "ATM"

    # ── Compute Greeks for selected strike ────────────────────────────
    price, delta, daily_theta = _bs_greeks(spot, K, T, risk_free_rate, sigma)

    # If the selected strike gives a near-zero premium, fall back to ATM
    min_valid_premium = max(spot * 0.001, 0.50)
    if price < min_valid_premium and offset != 0:
        K = atm
        offset = 0
        strike_type_label = "ATM (fallback)"
        price, delta, daily_theta = _bs_greeks(spot, K, T, risk_free_rate, sigma)

    if price < min_valid_premium:
        return None  # even ATM has no tradeable premium (extremely illiquid / deep bear)

    # ── Advisory constraint checks (shown in UI, never hard-exclude) ────
    theta_pct = abs(daily_theta) / price if price > 0 else 1.0
    theta_ok = theta_pct <= max_theta_pct

    target_move = atr * 1.5
    reward = target_move * delta
    risk = price * 0.30
    rr_ratio = reward / risk if risk > 0 else 0.0
    rr_ok = rr_ratio >= min_rr_ratio

    # Delta advisory check
    in_target_delta = 0.40 <= delta <= 0.55

    return {
        "strike": K,
        "strike_type": strike_type_label,
        "strike_offset": offset,
        "bs_price": round(price, 2),
        "delta": round(delta, 3),
        "daily_theta": round(daily_theta, 4),
        "theta_pct": round(theta_pct * 100, 3),
        "rr_ratio": round(rr_ratio, 2),
        "theta_ok": theta_ok,
        "rr_ok": rr_ok,
        "in_target_delta": in_target_delta,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PER-SYMBOL SCAN
# ─────────────────────────────────────────────────────────────────────────────

def _scan_symbol_for_month(
    symbol: str,
    year: int,
    month: int,
    master_entry: Optional[Dict] = None,
    nifty_hist: Optional[pd.DataFrame] = None,
    risk_free_rate: float = 0.067,
) -> Optional[Dict]:
    """
    Full 6-layer analysis for one F&O stock.
    Returns a single result dict for the optimal contract, or None if filtered out.
    """
    ns_sym = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(ns_sym)
        expiry_str = _find_month_expiry(ticker, year, month)
        if not expiry_str:
            return None

        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        T = max((expiry_dt - datetime.now()).days / 365.0, 1 / 365.0)
        days_left = max((expiry_dt - datetime.now()).days, 1)

        hist = ticker.history(period="90d", auto_adjust=False)
        if hist is None or hist.empty or len(hist) < 10:
            return None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = [c[0] for c in hist.columns]

        spot = float(hist["Close"].iloc[-1])
        if spot <= 0:
            return None

        # ── Layer 1: Hard Filters ─────────────────────────────────────────
        passes, f_details = _compute_hard_filters(hist, spot)
        if not passes:
            return None

        atr = f_details.get("atr", spot * 0.02)
        iv_rank = f_details.get("IV Rank", 50.0)

        # ── Layer 2 & 3: Composite Score ──────────────────────────────────
        nifty = nifty_hist if nifty_hist is not None else pd.DataFrame()
        final_score, sub_scores = _compute_composite_score(hist, spot, iv_rank, nifty)
        rsi = sub_scores.get("RSI", 50.0)

        # ── Layer 4: Smart Strike Selection (3-Rule Logic) ───────────────
        sigma = _estimate_volatility(hist)
        # Pull the inputs that drive the strike rule
        momentum_score = sub_scores.get("A_Momentum", 0.0)
        volume_ratio   = sub_scores.get("VolRatio", 1.0)

        contract_info = _select_optimal_strike(
            spot=spot, T=T, sigma=sigma, atr=atr,
            momentum_score=momentum_score,
            volume_ratio=volume_ratio,
            iv_rank=iv_rank,
            risk_free_rate=risk_free_rate,
        )
        if contract_info is None:
            return None

        strike          = contract_info["strike"]
        strike_type     = contract_info["strike_type"]
        bs_price        = contract_info["bs_price"]
        delta_val       = contract_info["delta"]
        daily_theta     = contract_info["daily_theta"]
        theta_pct       = contract_info["theta_pct"]
        rr_ratio        = contract_info["rr_ratio"]

        # ── Live LTP (premium source) ─────────────────────────────────────
        live_ltp = _fetch_live_option_ltp(symbol, expiry_str, strike, "CE")
        if live_ltp and live_ltp > 0.01:
            current_premium = live_ltp
            price_source = "Live LTP"
        else:
            current_premium = bs_price
            price_source = "BS Model"

        # Skip near-zero premiums
        min_premium = max(spot * 0.001, 0.50)
        if current_premium < min_premium:
            return None

        # ── Lot size ──────────────────────────────────────────────────────
        lot_size = (master_entry or {}).get("lot_size", 0)
        if not lot_size or lot_size <= 0:
            lot_size = max(int(round(500000 / spot / 25)) * 25, 25)

        comp_name = (master_entry or {}).get("name", symbol)

        # ── Investment ────────────────────────────────────────────────────
        investment = current_premium * lot_size

        # ── Target price and expected premium ─────────────────────────────
        scale = math.sqrt(days_left / 21.0)
        bull_target = round(spot + atr * 1.5 * scale, 2)

        # Expected premium at target: BS at ~50% remaining time
        half_T = T * 0.5
        intrinsic = max(bull_target - strike, 0.0)
        bs_at_target = black_scholes_call(bull_target, strike, half_T, risk_free_rate, sigma * 0.85)
        exp_premium = round(max(intrinsic, bs_at_target), 2)

        gross_profit = round((exp_premium - current_premium) * lot_size, 0)
        ret_pct = round((gross_profit / investment * 100) if investment > 0 else 0.0, 1)

        # ── News sentiment ────────────────────────────────────────────────
        news_score, news_headline = _get_news_sentiment(symbol)

        # ── Layer 5: Exit signals ─────────────────────────────────────────
        closes = hist["Close"].dropna()
        ema5 = float(closes.ewm(span=5, adjust=False).mean().iloc[-1]) if len(closes) >= 5 else spot
        exit_signals = []
        if spot < ema5:
            exit_signals.append("⚠️ Below 5 EMA")
        if sub_scores.get("A_Momentum", 100) < 50:
            exit_signals.append("⚠️ Momentum < 50")

        # ── Final score normalization to 0-1 for display ──────────────────
        normalized_score = round(final_score / 100.0, 3)

        contract = _contract_name(symbol, expiry_str, strike, "CE")

        return {
            "Contract": contract,
            "Symbol": symbol,
            "Company": comp_name,
            "Expiry": expiry_str,
            "Days to Expiry": days_left,
            "Price Source": price_source,
            # ── Strike selection rule ───────────────────────────────────
            "Strike Type": strike_type,
            "Strike Rule": (
                f"OTM +1 (Mom {momentum_score:.0f}>75 & Vol {volume_ratio:.1f}x>1.8x)"
                if strike_type.startswith("OTM") else
                f"ITM -1 (IV Rank {iv_rank:.0f}>60, high IV)"
                if strike_type.startswith("ITM") else
                "ATM (default)"
            ),
            # ── Price / Strike ─────────────────────────────────────────────
            "Underlying Spot (₹)": round(spot, 2),
            "Strike (₹)": strike,
            "Moneyness%": round((strike - spot) / spot * 100, 1),
            # ── Premium / Investment ───────────────────────────────────────
            "Current Premium (₹)": round(current_premium, 2),
            "BS Fair Value (₹)": round(bs_price, 2),
            "Lot Size": lot_size,
            "Investment / Lot (₹)": round(investment, 0),
            # ── Greeks ────────────────────────────────────────────────────
            "Delta": delta_val,
            "Daily Theta (₹)": daily_theta,
            "Theta % of Premium": theta_pct,
            "Reward/Risk Ratio": rr_ratio,
            "Theta OK": "✅" if contract_info["theta_ok"] else "⚠️",
            "R/R OK": "✅" if contract_info["rr_ok"] else "⚠️",
            # ── Target & Profit ────────────────────────────────────────────
            "Target Spot Price (₹)": bull_target,
            "Expected Premium @ Target (₹)": exp_premium,
            "Est Profit / Lot (₹)": gross_profit,
            "Return%": ret_pct,
            # ── Composite Score (Layer 2 & 3) ──────────────────────────────
            "Final Score (0-100)": final_score,
            "BullishScore": normalized_score,  # kept for UI compat
            "A Momentum (25%)": sub_scores.get("A_Momentum", 0.0),
            "B Breakout (15%)": sub_scores.get("B_Breakout", 0.0),
            "C Volume (15%)": sub_scores.get("C_Volume", 0.0),
            "D OI Proxy (15%)": sub_scores.get("D_OI_Proxy", 0.0),
            "E RSI (10%)": sub_scores.get("E_RSI", 0.0),
            "F IV (10%)": sub_scores.get("F_IV", 0.0),
            "G Nifty (10%)": sub_scores.get("G_Nifty", 0.0),
            "RS vs Nifty 10d%": sub_scores.get("RS_vs_Nifty_10d", 0.0),
            "RS Bonus": sub_scores.get("RS_Bonus", 0.0),
            # ── Technical ─────────────────────────────────────────────────
            "RSI": rsi,
            "IV Rank": iv_rank,
            "Momentum%": sub_scores.get("Momentum%", 0.0),
            "Breakout": "✅" if sub_scores.get("B_Breakout", 0) == 100 else "❌",
            "Vol Ratio": sub_scores.get("VolRatio", 1.0),
            "ATR (₹)": atr,
            "Volatility (σ)": f"{sigma * 100:.1f}%",
            "5 EMA": round(ema5, 2),
            "Above 5 EMA": "✅" if spot >= ema5 else "❌",
            # ── Hard Filter Details ───────────────────────────────────────
            "Above 20DMA": "✅" if f_details.get("Above 20DMA") else "❌",
            "ATR% ≥ 1.5": "✅" if f_details.get("ATR%", 0) >= 1.5 else "❌",
            "3d Gain ≤ 8%": "✅" if f_details.get("3d Gain%", 0) <= 8 else "❌",
            "IV Range OK": "✅" if 25 <= iv_rank <= 65 else "⚠️",
            # ── News ──────────────────────────────────────────────────────
            "News Score": news_score,
            "Latest News": news_headline[:80] if news_headline else "—",
            # ── Exit Signals ──────────────────────────────────────────────
            "Exit Signals": " | ".join(exit_signals) if exit_signals else "None",
        }

    except Exception as exc:
        logger.debug(f"Scan failed for {symbol}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC SCAN FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def scan_fno_options_for_month(
    year: int,
    month: int,
    top_n: int = 10,
    max_workers: int = 14,
    min_score: float = 40.0,   # 0-100 scale
    strike_types: Optional[List[str]] = None,  # unused — kept for API compat
) -> pd.DataFrame:
    """
    Scan all NSE F&O stocks using the Advanced Call Buying Strategy.
    Returns a ranked DataFrame of top-N opportunities.

    Parameters
    ----------
    year, month   : Target expiry month.
    top_n         : Number of top stocks to return (strategy recommends 5).
    max_workers   : Thread pool size.
    min_score     : Minimum composite score (0-100) to include.
    """
    master_map = get_fno_master_map()
    fno_stocks = list(master_map.keys())
    nifty_hist = _get_nifty_hist()

    logger.info(
        f"Strategy scan: {len(fno_stocks)} F&O stocks | "
        f"{year}-{month:02d} | top_n={top_n}"
    )

    results: List[Dict] = []

    def _worker(sym: str) -> Optional[Dict]:
        return _scan_symbol_for_month(
            sym, year, month,
            master_entry=master_map.get(sym),
            nifty_hist=nifty_hist,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker, s): s for s in fno_stocks}
        for fut in as_completed(futures):
            try:
                row = fut.result()
                if row is not None and row["Final Score (0-100)"] >= min_score:
                    results.append(row)
            except Exception as exc:
                logger.debug(f"Worker error: {exc}")

    if not results:
        return pd.DataFrame()

    df = (
        pd.DataFrame(results)
        .sort_values("Final Score (0-100)", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    return df

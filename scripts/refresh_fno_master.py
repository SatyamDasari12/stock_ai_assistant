"""
Refresh F&O Master Data
========================
Downloads the live NSE F&O stock universe and enriches it with:
  - Company full name (from stock_master.json)
  - Approximate lot sizes (from NSE lot-sizes CSV or fallback table)
  - Exchange tag

Output: data/fno_master.json
Format: List of dicts — {symbol, name, lot_size, exchange}

Run manually to refresh:
    python scripts/refresh_fno_master.py
"""
import json
import os
import sys
import re
import requests
import pandas as pd
from io import StringIO

# ── Paths ─────────────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_THIS_DIR)
DATA_DIR = os.path.join(_ROOT_DIR, "data")
FNO_MASTER_FILE = os.path.join(DATA_DIR, "fno_master.json")
STOCK_MASTER_FILE = os.path.join(DATA_DIR, "stock_master.json")

# ── Known lot sizes (NSE-published, updated up to Mar 2026) ───────────────────
# Source: https://archives.nseindia.com/content/fo/fo_mktlots.csv (PDF not CSV)
# These are standard lot sizes; NSE revises them quarterly.
FALLBACK_LOT_SIZES: dict = {
    "360ONE": 150, "ABB": 50, "ABCAPITAL": 2200, "ADANIENT": 125,
    "ADANIGREEN": 250, "ADANIPORTS": 400, "ALKEM": 50, "AMBER": 50,
    "AMBUJACEM": 1000, "ANGELONE": 250, "APLAPOLLO": 175, "APOLLOHOSP": 125,
    "ASHOKLEY": 2500, "ASIANPAINT": 200, "ASTRAL": 200, "AUBANK": 1500,
    "AUROPHARMA": 650, "AXISBANK": 625, "BAJAJ-AUTO": 75, "BAJAJFINSV": 500,
    "BAJAJHLDNG": 50, "BAJFINANCE": 125, "BANDHANBNK": 3600, "BANKBARODA": 5850,
    "BANKINDIA": 3000, "BDL": 125, "BEL": 2250, "BHARATFORG": 575,
    "BHARTIARTL": 475, "BHEL": 2700, "BIOCON": 2200, "BLUESTARCO": 200,
    "BOSCHLTD": 25, "BPCL": 1800, "BRITANNIA": 100, "BSE": 400,
    "CAMS": 125, "CANBK": 3600, "CDSL": 1250, "CGPOWER": 750,
    "CHOLAFIN": 500, "CIPLA": 650, "COALINDIA": 2100, "COFORGE": 100,
    "COLPAL": 700, "CONCOR": 800, "CROMPTON": 1500, "CUMMINSIND": 150,
    "DABUR": 1250, "DALBHARAT": 150, "DELHIVERY": 2150, "DIVISLAB": 200,
    "DIXON": 70, "DLF": 1650, "DMART": 75, "DRREDDY": 125,
    "EICHERMOT": 175, "EXIDEIND": 2900, "FEDERALBNK": 5000, "FORTIS": 2000,
    "GAIL": 3825, "GLENMARK": 575, "GMRAIRPORT": 5250, "GODREJCP": 500,
    "GODREJPROP": 375, "GRASIM": 350, "HAL": 150, "HAVELLS": 500,
    "HCLTECH": 350, "HDFCAMC": 200, "HDFCBANK": 550, "HDFCLIFE": 1100,
    "HEROMOTOCO": 150, "HINDALCO": 1075, "HINDPETRO": 1450, "HINDUNILVR": 300,
    "ICICIBANK": 700, "ICICIGI": 125, "ICICIPRULI": 1000, "IDBI": 6400,
    "IDFCFIRSTB": 11250, "IEX": 3750, "IGL": 1375, "INDHOTEL": 1400,
    "INDIGO": 150, "INDUSINDBK": 600, "INDUSTOWER": 1400, "INFY": 400,
    "IOC": 5000, "IPCALAB": 425, "IRCTC": 1375, "IRFC": 4800,
    "ITC": 1600, "JKCEMENT": 125, "JSWSTEEL": 600, "JUBLFOOD": 250,
    "KALYANKJIL": 833, "KOTAKBANK": 400, "L&TFH": 3000, "LALPATHLAB": 200,
    "LT": 175, "LTTS": 125, "LUPIN": 300, "M&M": 350,
    "M&MFIN": 3000, "MARICO": 1200, "MARUTI": 75, "MAXHEALTH": 700,
    "MCDOWELL-N": 250, "MCX": 200, "METROPOLIS": 250, "MFSL": 700,
    "MOTHERSON": 4350, "MPHASIS": 175, "MRF": 15, "MUTHOOTFIN": 375,
    "NATIONALUM": 3500, "NAUKRI": 100, "NBCC": 5000, "NCC": 2500,
    "NESTLEIND": 100, "NMDC": 3750, "NTPC": 2250, "OBEROIRLTY": 500,
    "OFSS": 100, "ONGC": 1925, "PAGEIND": 15, "PEL": 250,
    "PERSISTENT": 125, "PFC": 2250, "PIDILITIND": 250, "PNB": 8000,
    "POLYCAB": 125, "POWERGRID": 2900, "PVRINOX": 375, "RECLTD": 1500,
    "RELIANCE": 250, "RVNL": 1900, "SAIL": 7100, "SBICARD": 750,
    "SBILIFE": 375, "SBIN": 750, "SHRIRAMFIN": 300, "SIEMENS": 175,
    "SONACOMS": 750, "SUNPHARMA": 350, "SUNTV": 700, "TATACHEM": 550,
    "TATACOMM": 400, "TATACONSUM": 900, "TATAELXSI": 100, "TATAMOTORS": 1925,
    "TATAPOWER": 2700, "TATASTEEL": 2850, "TCS": 175, "TECHM": 400,
    "TIINDIA": 125, "TITAN": 375, "TORNTPHARM": 150, "TRENT": 350,
    "TVSMOTOR": 350, "UBL": 350, "ULTRACEMCO": 100, "UNIONBANK": 5700,
    "UPL": 1300, "VEDL": 1750, "VOLTAS": 375, "WIPRO": 1500,
    "YESBANK": 40000, "ZOMATO": 3000, "ZYDUSLIFE": 700,
    # Additional
    "ADANIENSOL": 500, "APOLLOTYRE": 1500, "MAZDOCK": 50,
    "IREDA": 2500, "HUDCO": 3250, "CGPOWER": 750,
}

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def _load_stock_name_map() -> dict:
    """Load {symbol: company_name} from existing stock_master.json."""
    if not os.path.exists(STOCK_MASTER_FILE):
        return {}
    try:
        with open(STOCK_MASTER_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        # entries is list of [symbol, name, exchange]
        name_map = {}
        for e in entries:
            sym = str(e[0]).strip().upper()
            name = str(e[1]).strip() if len(e) > 1 else sym
            if sym not in name_map:
                name_map[sym] = name
        print(f"  Loaded {len(name_map)} names from stock_master.json")
        return name_map
    except Exception as ex:
        print(f"  Warning: could not load stock_master.json: {ex}")
        return {}


def _fetch_fno_symbols() -> list:
    """Fetch the live NSE F&O stock symbol list."""
    try:
        r = requests.get(
            "https://www.nseindia.com/api/master-quote",
            headers=NSE_HEADERS,
            timeout=10,
        )
        if r.status_code == 200 and r.text.strip().startswith("["):
            stocks = r.json()
            if isinstance(stocks, list) and len(stocks) > 50:
                print(f"  Fetched {len(stocks)} F&O symbols from NSE live API")
                return sorted(stocks)
    except Exception as ex:
        print(f"  Warning: NSE API failed: {ex}")

    # Fallback: use the keys from the hardcoded lot-size table
    fallback = sorted(FALLBACK_LOT_SIZES.keys())
    print(f"  Using hardcoded fallback: {len(fallback)} symbols")
    return fallback


def _try_fetch_lot_sizes_csv() -> dict:
    """
    Try to fetch NSE F&O lot sizes from the archives CSV.
    Returns {SYMBOL: lot_size} or empty dict on failure.
    """
    url = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
    try:
        r = requests.get(url, headers=NSE_HEADERS, timeout=10)
        if r.status_code == 200 and "," in r.text and not r.text.startswith("%PDF"):
            df = pd.read_csv(StringIO(r.text))
            # Typical columns: SYMBOL, JAN 2026, FEB 2026, MAR 2026, ...
            # Take the first month column after SYMBOL
            df.columns = [str(c).strip() for c in df.columns]
            sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
            num_cols = [c for c in df.columns if c != sym_col]
            if sym_col and num_cols:
                result = {}
                for _, row in df.iterrows():
                    sym = str(row[sym_col]).strip().upper()
                    for nc in num_cols:
                        try:
                            val = int(str(row[nc]).replace(",", "").strip())
                            if val > 0:
                                result[sym] = val
                                break
                        except Exception:
                            continue
                print(f"  Fetched {len(result)} lot sizes from NSE CSV")
                return result
    except Exception as ex:
        print(f"  NSE lot-size CSV fetch failed: {ex}")
    return {}


def refresh():
    print("=" * 60)
    print("  NSE F&O Master Refresh")
    print("=" * 60)

    os.makedirs(DATA_DIR, exist_ok=True)

    print("\n[1] Loading stock name map from stock_master.json...")
    name_map = _load_stock_name_map()

    print("\n[2] Fetching NSE F&O symbol list...")
    symbols = _fetch_fno_symbols()

    print("\n[3] Fetching lot sizes from NSE CSV...")
    live_lots = _try_fetch_lot_sizes_csv()
    # Merge: live CSV takes priority, fallback for missing
    lot_map = {**FALLBACK_LOT_SIZES, **live_lots}

    print("\n[4] Building F&O master entries...")
    entries = []
    missing_name = 0
    missing_lot = 0

    for sym in symbols:
        sym_up = sym.strip().upper()

        # Try to get company name
        name = name_map.get(sym_up)
        if not name:
            # Try some common variations (BAJAJ-AUTO might be stored as BAJAJAUTO)
            alt = sym_up.replace("-", "").replace("&", "")
            name = name_map.get(alt, sym_up)
            if name == sym_up:
                missing_name += 1

        lot = lot_map.get(sym_up)
        if not lot:
            missing_lot += 1
            # Estimate: ~1 lot ≈ ₹5L notional (rough NSE guideline)
            lot = 0  # mark as unknown — will show as "N/A" in UI

        entries.append({
            "symbol": sym_up,
            "name": name,
            "lot_size": lot,
            "exchange": "NSE",
        })

    entries.sort(key=lambda x: x["symbol"])

    print(f"\n  Total entries     : {len(entries)}")
    print(f"  Missing names     : {missing_name}")
    print(f"  Missing lot sizes : {missing_lot}")

    print(f"\n[5] Saving to {FNO_MASTER_FILE}...")
    with open(FNO_MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print(f"\n✅  F&O master saved: {len(entries)} stocks")


if __name__ == "__main__":
    refresh()

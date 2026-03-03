from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import List

import pytz

import plotly.graph_objs as go
import streamlit as st

from services.options_service import scan_bullish_call_options

IST = pytz.timezone("Asia/Kolkata")


def _now_ist() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")


def _get_last_thursday(year: int, month: int) -> str:
    """Return the last Thursday of a given year/month in YYYY-MM-DD format (NSE expiry convention)."""
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day)
    while d.weekday() != 3:  # 3 = Thursday
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _get_expiry_month_options(months_ahead: int = 4) -> List[tuple[str, str]]:
    """Return list of (display_label, YYYY-MM-DD expiry_date) for next N months."""
    now = datetime.now(IST)
    options = []
    for offset in range(months_ahead):
        year = now.year + (now.month + offset - 1) // 12
        month = (now.month + offset - 1) % 12 + 1
        expiry_date = _get_last_thursday(year, month)
        month_label = datetime(year, month, 1).strftime("%B %Y")
        # Mark if already past this month's expiry
        expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        if expiry_dt >= now.date():
            options.append((f"{month_label}  (Last Thu: {expiry_dt.strftime('%d %b')})", expiry_date))
    return options


def render_options_scanner_page() -> None:
    st.title("📊 Options Scanner")
    st.caption(
        f"Bullish CE opportunities using Open Interest, PCR, max pain, and trend | "
        f"All times in IST | {_now_ist()}"
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        expiry_options = _get_expiry_month_options(months_ahead=4)
        if expiry_options:
            labels = [label for label, _ in expiry_options]
            selected_label = st.selectbox(
                "Select Expiry Month",
                options=labels,
                help="Select expiry month — expiry date is auto-calculated to the last Thursday (NSE convention).",
            )
            expiry = dict(expiry_options).get(selected_label, "")
            if expiry:
                st.caption(f"📅 Resolved expiry date: **{expiry}** (last Thursday of selected month)")
        else:
            expiry = st.text_input(
                "Expiry (YYYY-MM-DD)",
                help="Example: 2026-03-27",
            )
    with col2:
        top_n = st.slider("Number of option ideas", 5, 50, 15, 5)

    if st.button("🔍 Scan CE Options", type="primary"):
        if not expiry:
            st.error("Please select an expiry month.")
            return

        with st.spinner(f"Scanning option chains for bullish CE opportunities (expiry: {expiry})…"):
            df = scan_bullish_call_options(expiry=expiry, top_n=top_n)

        if df is None or df.empty:
            st.warning(
                "No CE opportunities found for this expiry. "
                "The date may be too far out, or options data is not available via yfinance for Indian markets on all symbols."
            )
            return

        # Strip .NS/.BO from Underlying column before display
        if "Underlying" in df.columns:
            df["Underlying"] = df["Underlying"].str.replace(r"\.(NS|BO)$", "", regex=True)

        # Strip contract symbol suffix for readability
        if "contractSymbol" in df.columns:
            df["Contract"] = df["contractSymbol"].str.replace(r"\.NS", "", regex=True)

        st.subheader(f"🏆 Top CE Opportunities — Expiry: {expiry}")
        st.caption(f"Data scanned at {_now_ist()}")

        # Max Pain info (show per underlying)
        if "MaxPain" in df.columns and "Underlying" in df.columns:
            st.markdown("**📍 Max Pain Levels by Underlying**")
            max_pain_data = (
                df[["Underlying", "MaxPain"]]
                .drop_duplicates()
                .dropna(subset=["MaxPain"])
                .sort_values("Underlying")
            )
            if not max_pain_data.empty:
                cols = st.columns(min(len(max_pain_data), 5))
                for i, (_, row) in enumerate(max_pain_data.iterrows()):
                    cols[i % len(cols)].metric(
                        row["Underlying"],
                        f"₹{row['MaxPain']:.0f}",
                        delta="Max Pain",
                    )

        st.markdown("---")

        # Score bar chart
        st.subheader("📈 Bullish Score Comparison")
        x_labels = df["Contract"] if "Contract" in df.columns else df.index.astype(str)
        fig_score = go.Figure(
            go.Bar(
                x=x_labels,
                y=df["BullishScore"],
                marker_color=[
                    "#26a69a" if s >= 0.6 else ("#ffa726" if s >= 0.4 else "#ef5350")
                    for s in df["BullishScore"]
                ],
                text=df["BullishScore"].round(3),
                textposition="outside",
            )
        )
        fig_score.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=10, b=80),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickangle=-45, tickfont=dict(size=9), color="#8b949e"),
            yaxis=dict(title="Bullish Score", gridcolor="rgba(128,128,128,0.15)", color="#8b949e"),
        )
        st.plotly_chart(fig_score, use_container_width=True)

        # Data table
        st.subheader("📋 Full Results")
        display_cols = [
            c for c in [
                "Underlying", "Contract", "strike", "lastPrice",
                "bid", "ask", "openInterest", "volume", "PCR", "MaxPain", "BullishScore"
            ] if c in df.columns
        ]
        st.dataframe(
            df[display_cols].reset_index(drop=True),
            use_container_width=True,
        )

        st.caption(
            "Signals favour strikes with OI build-up, healthy PCR (≈0.8), and "
            "underlying bullish trend. Max Pain shows where option sellers want price to expire. "
            "Use this as a starting point, not investment advice."
        )

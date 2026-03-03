from datetime import date, timedelta
from typing import Optional

import plotly.graph_objs as go
import streamlit as st

from services.analysis_service import (
    analyze_stock_for_week,
    build_stock_scorecard,
    get_stock_history_with_indicators,
)
from services.market_data_service import (
    compute_support_resistance,
    get_dynamic_interval,
    get_rangebreaks,
    resolve_symbol,
)
from rag.news_rag_service import get_symbol_news_summaries
from features.stock_master import load_combined_stock_master, build_all_labels, load_nse_stock_master


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------

def render_stock_analysis_page() -> None:
    st.title("📈 Stock Analysis")
    st.caption("Weekly trend prediction, technical indicators, news sentiment, and AI reasoning")

    # ── Inputs ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2.5, 1, 1, 1])


    # ── Load combined NSE + BSE equity list (cached 24 h) ────────────────
    _entries   = load_combined_stock_master()
    _all_labels = build_all_labels(_entries)
    # Quick name-lookup: {symbol: name} from the combined list
    _name_map  = {sym: name for sym, name, _ in _entries}

    with col1:
        # ── Typeahead selectbox — Google-style search ─────────────────
        _selected_label = st.selectbox(
            "Search Stock",
            options=_all_labels,
            index=None,
            placeholder="Type symbol or company name: BEL, Bharat Elec, DLINKINDIA…",
            help=(
                "Cross-listed stocks appear as separate [NSE] and [BSE] entries. "
                "Start typing — suggestions update live."
            ),
            key="stock_search_selectbox",
        )

        if _selected_label:
            # Parse: 'SYMBOL — Company Name [NSE]'
            raw_symbol   = _selected_label.split(" — ")[0].strip()
            _exch_tag    = "NSE" if "[NSE]" in _selected_label else "BSE"
            _full_name   = _name_map.get(raw_symbol, raw_symbol)
            # Save to session state so button-click rerun has the right values
            st.session_state["_confirmed_symbol"] = raw_symbol
            st.session_state["_confirmed_exchange"] = _exch_tag
            # Color-coded exchange badge
            _badge_color = "#1a7f37" if _exch_tag == "NSE" else "#b45309"
            _badge_bg    = "#1a7f3722" if _exch_tag == "NSE" else "#b4530922"
            st.markdown(
                f"<div style='margin-top:4px; font-size:0.88rem; color:#c9d1d9;'>"
                f"<b>{raw_symbol}</b> &mdash; {_full_name} &nbsp;"
                f"<span style='background:{_badge_bg}; color:{_badge_color}; "
                f"border:1px solid {_badge_color}88; padding:2px 9px; "
                f"border-radius:12px; font-size:0.76rem; font-weight:700;'>{_exch_tag}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            # On button-click rerun, selectbox momentarily returns None
            raw_symbol = st.session_state.get("_confirmed_symbol", "")
            _exch_tag  = st.session_state.get("_confirmed_exchange", "NSE")


    # Default range = last 2 months
    default_start = date.today() - timedelta(days=60)
    with col2:
        start_date = st.date_input("From", value=default_start)
    with col3:
        end_date = st.date_input("To", value=date.today())

    with col4:
        st.markdown("<div style='margin-bottom: -5px;'><small style='color:#8b949e; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;'>Chart Indicators</small></div>", unsafe_allow_html=True)
        show_vwap = st.checkbox("VWAP", value=True)
        show_bb   = st.checkbox("Bollinger", value=True)

    if not raw_symbol or not raw_symbol.strip():
        st.info("Enter a stock symbol to begin (e.g. **BEL**, **TCS**, **RELIANCE**).")
        return

    if st.button("🔍 Run Analysis", type="primary"):

        # ── Resolve exchange ────────────────────────────────────────────
        # Since we use a curated list with [NSE]/[BSE] tags, we don't need to probe.
        suffix = ".NS" if _exch_tag == "NSE" else ".BO"
        resolved_symbol = raw_symbol.upper() + suffix
        exchange = _exch_tag

        # Full display name — use combined name map
        display_name = _name_map.get(raw_symbol.upper(), raw_symbol.upper())

        # ── Dynamic interval ────────────────────────────────────────────
        interval, interval_label = get_dynamic_interval(start_date, end_date)
        range_days = (end_date - start_date).days

        # Warn if intraday but date is too old for yfinance limits
        start_age  = (date.today() - start_date).days
        interval_warning = None
        if interval in ("5m", "15m") and start_age > 59:
            interval_warning = (
                "⚠️ **Intraday (5m/15m) data is only available for the last 60 days.** "
                "Falling back to daily bars for this date range."
            )
            interval = "1d"
            interval_label = "Daily"
        elif interval == "1h" and start_age > 729:
            interval_warning = (
                "⚠️ **1-hour data is only available for the last 730 days.** "
                "Falling back to weekly bars."
            )
            interval = "1wk"
            interval_label = "Weekly"

        if interval_warning:
            st.warning(interval_warning)

        rangebreaks = get_rangebreaks(interval)

        st.caption(
            f"📊 Chart resolution: **{interval_label}** bars | "
            f"Range: **{range_days} days** | Interval: `{interval}`"
        )

        # ── Fetch data ───────────────────────────────────────────────────
        with st.spinner(f"Fetching {interval_label} data and running analysis…"):
            history_df = get_stock_history_with_indicators(
                symbol=resolved_symbol,
                start=start_date,
                end=end_date,
                interval=interval,
            )

            if history_df is None or history_df.empty:
                st.error(
                    f"Could not fetch price data for **{display_name}**. "
                    "The symbol may not exist or no data is available for this range/interval."
                )
                return

            prediction     = analyze_stock_for_week(resolved_symbol, history_df)
            scorecard      = build_stock_scorecard(history_df)
            sr_levels      = compute_support_resistance(history_df)

            # Fetch News for LLM Summary context
            news_summaries = get_symbol_news_summaries(raw_symbol)

        # ── 1) Top Level AI Summary ────────────────────────────────────
        st.subheader("🔮 AI Summary & Prediction")
        if prediction:
            p_col1, p_col2, p_col3 = st.columns(3)
            p_col1.metric("Predicted Trend", prediction.trend)
            p_col2.metric("Probability", f"{prediction.probability:.1%}")
            p_col3.metric("Expected Range", f"₹{prediction.expected_low:.1f} - ₹{prediction.expected_high:.1f}")

            from services.llm_service import explain_weekly_outlook
            with st.spinner("Generating AI explanation..."):
                weekly_summary = explain_weekly_outlook(
                    symbol=display_name,
                    scorecard=scorecard,
                    prediction=prediction,
                    news_summaries=news_summaries,
                )

            with st.container(border=True):
                st.write(weekly_summary)
        else:
            st.warning("Not enough data to run weekly prediction (need at least 20 bars).")

        st.markdown("---")

        # ── 2) Render charts ───────────────────────────────────────────────
        st.subheader(f"Price Action | Interval: {interval}")
        _render_price_chart(
            history_df,
            symbol=display_name,
            interval=interval,
            interval_label=interval_label,
            show_bb=show_bb,
            show_vwap=show_vwap,
            rangebreaks=rangebreaks,
        )
        _render_indicator_panels(history_df)
        _render_scorecard(scorecard, sr_levels)
        _render_news_section(raw_symbol, display_name)


# ---------------------------------------------------------------------------
# Price chart
# ---------------------------------------------------------------------------

def _render_price_chart(
    history_df,
    symbol: str,
    interval: str,
    interval_label: str,
    show_bb: bool = True,
    show_vwap: bool = True,
    rangebreaks: Optional[list] = None,
) -> None:
    st.subheader("📊 Price Chart")

    fig = go.Figure()

    # Candlestick (use Bar/OHLC for very short intraday ranges with few bars)
    n_bars = len(history_df)
    if n_bars < 3:
        st.warning("Not enough bars in the selected range to draw a chart.")
        return

    fig.add_trace(
        go.Candlestick(
            x=history_df.index,
            open=history_df["Open"],
            high=history_df["High"],
            low=history_df["Low"],
            close=history_df["Close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            whiskerwidth=0.5,
        )
    )

    # Moving averages — only meaningful for daily+ intervals with enough bars
    if interval in ("1d", "1wk") and n_bars >= 20:
        ma_styles = [
            ("SMA_20",  "SMA 20",  "rgba(255,152,0,0.85)",   1.5),
            ("SMA_50",  "SMA 50",  "rgba(33,150,243,0.85)",  1.5),
            ("SMA_200", "SMA 200", "rgba(76,175,80,0.85)",   1.5),
        ]
        for col, name, color, lw in ma_styles:
            if col in history_df.columns:
                fig.add_trace(go.Scatter(
                    x=history_df.index, y=history_df[col],
                    name=name, line=dict(color=color, width=lw), opacity=0.9,
                ))

    # Bollinger Bands
    if show_bb and "BB_HIGH" in history_df.columns and "BB_LOW" in history_df.columns:
        fig.add_trace(go.Scatter(
            x=history_df.index, y=history_df["BB_HIGH"],
            name="BB Upper",
            line=dict(color="rgba(156,39,176,0.5)", width=1, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=history_df.index, y=history_df["BB_LOW"],
            name="BB Lower",
            line=dict(color="rgba(156,39,176,0.5)", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(156,39,176,0.05)",
        ))

    # VWAP
    if show_vwap and "VWAP" in history_df.columns:
        fig.add_trace(go.Scatter(
            x=history_df.index, y=history_df["VWAP"],
            name="VWAP",
            line=dict(color="rgba(255,235,59,0.9)", width=1.5, dash="dash"),
        ))

    xaxis_cfg = dict(
        gridcolor="rgba(128,128,128,0.12)",
        showgrid=True,
        zeroline=False,
    )
    if rangebreaks:
        xaxis_cfg["rangebreaks"] = rangebreaks

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=560,
        margin=dict(l=10, r=10, t=44, b=10),
        legend=dict(orientation="h", y=-0.14, font=dict(size=11)),
        title=dict(
            text=f"{symbol} — {interval_label} bars",
            font=dict(size=15, color="#c9d1d9"),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=xaxis_cfg,
        yaxis=dict(gridcolor="rgba(128,128,128,0.12)", zeroline=False, side="right"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Volume chart
    if "Volume" in history_df.columns:
        vol_colors = [
            "#26a69a" if float(c) >= float(o) else "#ef5350"
            for c, o in zip(history_df["Close"], history_df["Open"])
        ]
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(
            x=history_df.index,
            y=history_df["Volume"],
            name="Volume",
            marker_color=vol_colors,
            opacity=0.75,
        ))
        vol_xaxis = dict(gridcolor="rgba(128,128,128,0.12)", showgrid=False)
        if rangebreaks:
            vol_xaxis["rangebreaks"] = rangebreaks

        fig_vol.update_layout(
            height=160,
            margin=dict(l=10, r=10, t=6, b=10),
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=vol_xaxis,
            yaxis=dict(
                gridcolor="rgba(128,128,128,0.12)",
                title="Volume",
                side="right",
            ),
        )
        st.plotly_chart(fig_vol, use_container_width=True)


# ---------------------------------------------------------------------------
# Indicator metrics panel
# ---------------------------------------------------------------------------

def _render_indicator_panels(history_df) -> None:
    st.subheader("📉 Technical Indicators")

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        rsi_val = _safe_last(history_df, "RSI_14")
        rsi_delta = _safe_delta(history_df, "RSI_14")
        status = "🟢" if 50 < rsi_val < 70 else ("🔴" if rsi_val >= 70 else "🟡")
        st.metric(f"{status} RSI (14)", _fmt(rsi_val, ".1f"), delta=_fmt(rsi_delta, "+.1f") if rsi_delta is not None else None)

    with col2:
        macd_val   = _safe_last(history_df, "MACD")
        macd_delta = _safe_delta(history_df, "MACD")
        st.metric("📊 MACD", _fmt(macd_val, ".2f"), delta=_fmt(macd_delta, "+.2f") if macd_delta is not None else None)

    with col3:
        atr_val   = _safe_last(history_df, "ATR_14")
        close_val = _safe_last(history_df, "Close")
        atr_pct   = (atr_val / close_val * 100) if close_val > 0 else 0.0
        st.metric("🌊 ATR (14)", _fmt(atr_val, ".2f"), delta=f"{atr_pct:.1f}% of price")

    with col4:
        vwap_val = _safe_last(history_df, "VWAP")
        above = "↑ Above" if close_val > vwap_val else "↓ Below"
        st.metric("📍 VWAP", _fmt(vwap_val, ".2f"), delta=above if vwap_val > 0 else None)

    with col5:
        vol_val   = _safe_last(history_df, "Volume")
        vol_spike = bool(int(_safe_last(history_df, "VOLUME_SPIKE")))
        st.metric("📦 Volume", f"{vol_val:,.0f}", delta="⚡ Spike!" if vol_spike else None)

    with col6:
        hist_val   = _safe_last(history_df, "MACD_HIST")
        hist_delta = _safe_delta(history_df, "MACD_HIST")
        st.metric("📈 MACD Hist", _fmt(hist_val, ".2f"), delta=_fmt(hist_delta, "+.2f") if hist_delta is not None else None)


def _safe_last(df, col: str) -> float:
    if col in df.columns:
        v = df[col].iloc[-1]
        try:
            return float(v)
        except Exception:
            pass
    return 0.0


def _safe_delta(df, col: str):
    if col in df.columns and len(df) > 1:
        try:
            return float(df[col].iloc[-1]) - float(df[col].iloc[-2])
        except Exception:
            pass
    return None


def _fmt(val: float, spec: str) -> str:
    try:
        return format(val, spec)
    except Exception:
        return str(val)


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def _render_scorecard(scorecard, sr_levels: dict) -> None:
    st.subheader("🎯 Signal Scorecard & Key Levels")

    col1, col2 = st.columns(2)
    with col1:
        if scorecard is not None:
            total = scorecard.total_score
            icon  = "🟢" if total >= 7 else ("🟡" if total >= 5 else "🔴")
            st.markdown(f"**Technical Score: {icon} {total}/10**")
            st.progress(total / 10.0)
            sc = st.columns(4)
            sc[0].metric("Trend",     f"{scorecard.trend_score}/3")
            sc[1].metric("Momentum",  f"{scorecard.momentum_score}/3")
            sc[2].metric("Volume",    f"{scorecard.volume_score}/2")
            sc[3].metric("Volatility",f"{scorecard.volatility_score}/2")
            st.caption(scorecard.interpretation)
        else:
            st.info("Not enough data to compute scorecard.")

    with col2:
        if sr_levels:
            st.markdown("**📐 Key Levels**")
            lc = st.columns(3)
            lc[0].metric("Support",    f"₹{sr_levels.get('support',    0):.2f}")
            lc[1].metric("Pivot",      f"₹{sr_levels.get('pivot',      0):.2f}")
            lc[2].metric("Resistance", f"₹{sr_levels.get('resistance', 0):.2f}")
            pc = st.columns(2)
            pc[0].metric("S1", f"₹{sr_levels.get('s1', 0):.2f}")
            pc[1].metric("R1", f"₹{sr_levels.get('r1', 0):.2f}")


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def _render_news_section(symbol: str, display_name: str = "") -> None:
    st.subheader("📰 News Sentiment")
    label = display_name if display_name else symbol
    with st.spinner(f"Fetching latest news for {label}…"):
        news = get_symbol_news_summaries(symbol, top_k=5)

    if not news:
        st.info(f"No recent news found for **{label}**.")
        return

    for i, item in enumerate(news):
        label_text = item[:90] + "…" if len(item) > 90 else item
        with st.expander(f"📄 News {i + 1}: {label_text}"):
            st.write(item)

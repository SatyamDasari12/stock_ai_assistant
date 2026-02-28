from datetime import date, timedelta

import plotly.graph_objs as go
import streamlit as st

from services.analysis_service import (
    analyze_stock_for_week,
    build_stock_scorecard,
    get_stock_history_with_indicators,
)


def render_stock_analysis_page() -> None:
    st.title("📈 Stock Analysis")
    st.caption("Weekly trend, indicators, news sentiment, and AI explanation")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        symbol = st.text_input("Stock symbol (NSE, e.g. BEL.NS)", value="BEL.NS")
    with col2:
        start_date = st.date_input(
            "From",
            value=date.today() - timedelta(days=180),
        )
    with col3:
        end_date = st.date_input("To", value=date.today())

    if not symbol:
        st.info("Enter a stock symbol to begin (e.g. **BEL.NS**, **TCS.NS**).")
        return

    if st.button("Run Analysis", type="primary"):
        with st.spinner("Fetching data and running analysis..."):
            history_df = get_stock_history_with_indicators(
                symbol=symbol,
                start=start_date,
                end=end_date,
            )

            if history_df is None or history_df.empty:
                st.error("Could not fetch price history for this symbol.")
                return

            prediction = analyze_stock_for_week(symbol, history_df)
            scorecard = build_stock_scorecard(history_df)

        _render_price_chart(history_df, symbol)
        _render_indicator_panels(history_df)
        _render_scorecard_and_prediction(scorecard, prediction)


def _render_price_chart(history_df, symbol: str) -> None:
    st.subheader("Price & Volume")
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=history_df.index,
            open=history_df["Open"],
            high=history_df["High"],
            low=history_df["Low"],
            close=history_df["Close"],
            name="Price",
        )
    )
    if "SMA_20" in history_df.columns:
        fig.add_trace(
            go.Scatter(
                x=history_df.index,
                y=history_df["SMA_20"],
                name="SMA 20",
                line=dict(color="orange", width=1),
            )
        )
    if "SMA_50" in history_df.columns:
        fig.add_trace(
            go.Scatter(
                x=history_df.index,
                y=history_df["SMA_50"],
                name="SMA 50",
                line=dict(color="blue", width=1),
            )
        )
    if "SMA_200" in history_df.columns:
        fig.add_trace(
            go.Scatter(
                x=history_df.index,
                y=history_df["SMA_200"],
                name="SMA 200",
                line=dict(color="green", width=1),
            )
        )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=500,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=-0.2),
        title=f"{symbol} price action",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_indicator_panels(history_df) -> None:
    st.subheader("Technical Indicators")
    latest = history_df.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("RSI", f"{latest.get('RSI_14', float('nan')):.1f}")
    with col2:
        st.metric("MACD", f"{latest.get('MACD', float('nan')):.2f}")
    with col3:
        st.metric("ATR", f"{latest.get('ATR_14', float('nan')):.2f}")
    with col4:
        st.metric("Volume", f"{latest.get('Volume', 0):,.0f}")


def _render_scorecard_and_prediction(scorecard, prediction) -> None:
    st.subheader("Signal Scorecard & Weekly Outlook")

    col1, col2 = st.columns(2)
    with col1:
        if scorecard is not None:
            st.markdown("**Technical Scores (0–10)**")
            st.progress(scorecard.total_score / 10.0)
            st.write(
                f"**Trend:** {scorecard.trend_score}/3  |  "
                f"**Momentum:** {scorecard.momentum_score}/3  |  "
                f"**Volume:** {scorecard.volume_score}/2  |  "
                f"**Volatility:** {scorecard.volatility_score}/2"
            )
            st.caption(scorecard.interpretation)
        else:
            st.info("Not enough data to compute scorecard.")

    with col2:
        if prediction is not None:
            st.markdown("**Weekly Prediction**")
            st.write(
                f"**Trend:** {prediction.trend}  \n"
                f"**Probability:** {prediction.probability:.0%}  \n"
                f"**Expected Range:** {prediction.expected_low:.2f} – "
                f"{prediction.expected_high:.2f}"
            )
            if prediction.reasoning:
                with st.expander("Model rationale"):
                    st.write(prediction.reasoning)
        else:
            st.info("Prediction model did not return an output.")


import streamlit as st

from services.analysis_service import build_stock_scorecard
from services.market_data_service import get_latest_quote, compute_support_resistance, resolve_symbol
from services.portfolio_service import build_portfolio_recommendation
from services.llm_service import explain_portfolio_advice
from rag.news_rag_service import get_symbol_news_summaries
from features.tickers import VALID_TICKERS, TICKER_NAMES, TICKER_NAMES


def render_portfolio_advisor_page() -> None:
    st.title("🧺 Portfolio Advisor")
    st.caption("Position-level buy / sell / hold guidance with risk metrics and AI reasoning")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_ticker = st.selectbox(
            "Stock symbol",
            options=VALID_TICKERS + ["Custom..."],
            index=None,
            format_func=lambda x: f"{x} - {TICKER_NAMES.get(x, x)}" if x in TICKER_NAMES else x,
            help="Select a symbol or choose 'Custom...' to enter a different one."
        )
        if selected_ticker == "Custom...":
            raw_symbol = st.text_input("Enter Custom Symbol", value="", help="No need to add .NS or .BO — the app detects the exchange.")
        elif selected_ticker is None:
            raw_symbol = ""
        else:
            raw_symbol = selected_ticker
    with col2:
        buy_price = st.number_input("Buy price (₹)", min_value=0.0, value=440.0, step=0.5)
    with col3:
        quantity = st.number_input("Quantity", min_value=1, value=10, step=1)

    if st.button("📊 Get Advice", type="primary"):
        if not raw_symbol.strip():
            st.error("Enter a stock symbol.")
            return

        with st.spinner("Detecting exchange & evaluating position..."):
            symbol, exchange = resolve_symbol(raw_symbol)
            st.info(f"📡 Detected Exchange: **{exchange}**")
            quote = get_latest_quote(symbol)
            if quote is None:
                st.error("Could not fetch live quote for this symbol. Check symbol format (e.g. BEL.NS).")
                return

            scorecard = build_stock_scorecard(quote.history_df)
            atr = (
                float(quote.history_df["ATR_14"].iloc[-1])
                if "ATR_14" in quote.history_df.columns
                else None
            )
            rec = build_portfolio_recommendation(
                symbol=symbol,
                buy_price=buy_price,
                quantity=quantity,
                latest_price=quote.last_price,
                scorecard=scorecard,
                atr=atr,
            )
            sr_levels = compute_support_resistance(quote.history_df)

            # Fetch news for LLM context
            news_summaries = get_symbol_news_summaries(symbol, top_k=3)

            # LLM-enhanced explanation
            llm_explanation = explain_portfolio_advice(
                symbol=symbol,
                buy_price=buy_price,
                quantity=quantity,
                latest_price=quote.last_price,
                recommendation_action=rec.action,
                recommendation_reason=rec.reason,
                scorecard=scorecard,
                news_summaries=news_summaries,
            )

        # P&L Summary
        pnl_abs = (quote.last_price - buy_price) * quantity
        pnl_pct = (quote.last_price - buy_price) / buy_price * 100 if buy_price > 0 else 0.0
        invested_value = buy_price * quantity
        current_value = quote.last_price * quantity

        st.subheader("💰 Position Summary")
        pnl_cols = st.columns(4)
        pnl_cols[0].metric("Invested", f"₹{invested_value:,.0f}")
        pnl_cols[1].metric("Current Value", f"₹{current_value:,.0f}", delta=f"₹{pnl_abs:+,.0f}")
        pnl_cols[2].metric("P&L %", f"{pnl_pct:+.1f}%")
        pnl_cols[3].metric("Current Price", f"₹{quote.last_price:.2f}")

        # Recommendation
        action_color = {
            "HOLD": "green",
            "SELL": "red",
            "REDUCE / EXIT": "red",
            "HOLD / TIGHTEN SL": "orange",
            "AVOID FRESH ADDITIONS": "orange",
        }.get(rec.action, "blue")

        st.subheader("🎯 Recommendation")
        st.markdown(
            f"<div style='padding: 12px; border-radius: 8px; background: rgba(0,0,0,0.1); "
            f"border-left: 4px solid {action_color};'>"
            f"<span style='color:{action_color}; font-size:1.5em; font-weight:700'>{rec.action}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.write(f"**Rationale:** {rec.reason}")

        if rec.target_price is not None and rec.stop_loss is not None:
            level_cols = st.columns(4)
            level_cols[0].metric("🎯 Target", f"₹{rec.target_price:.2f}")
            level_cols[1].metric("🛑 Stop Loss", f"₹{rec.stop_loss:.2f}")
            if rec.risk_reward is not None:
                level_cols[2].metric("⚖️ Risk/Reward", f"{rec.risk_reward:.2f}:1")
            if rec.atr_percent is not None:
                level_cols[3].metric("🌊 ATR Volatility", f"{rec.atr_percent:.1f}%")

        if rec.holding_period:
            st.write(f"**Suggested Holding Period:** {rec.holding_period}")

        # Support / Resistance
        if sr_levels:
            st.subheader("📐 Key Price Levels")
            sr_cols = st.columns(5)
            sr_cols[0].metric("Support", f"₹{sr_levels.get('support', 0):.2f}")
            sr_cols[1].metric("S1", f"₹{sr_levels.get('s1', 0):.2f}")
            sr_cols[2].metric("Pivot", f"₹{sr_levels.get('pivot', 0):.2f}")
            sr_cols[3].metric("R1", f"₹{sr_levels.get('r1', 0):.2f}")
            sr_cols[4].metric("Resistance", f"₹{sr_levels.get('resistance', 0):.2f}")

        # Scorecard
        if scorecard is not None:
            st.subheader("📊 Technical Scorecard")
            score_color = "🟢" if scorecard.total_score >= 7 else ("🟡" if scorecard.total_score >= 5 else "🔴")
            st.markdown(f"**Score: {score_color} {scorecard.total_score}/10** — {scorecard.interpretation}")
            sc_cols = st.columns(4)
            sc_cols[0].metric("Trend", f"{scorecard.trend_score}/3")
            sc_cols[1].metric("Momentum", f"{scorecard.momentum_score}/3")
            sc_cols[2].metric("Volume", f"{scorecard.volume_score}/2")
            sc_cols[3].metric("Volatility", f"{scorecard.volatility_score}/2")

        # LLM Reasoning
        if llm_explanation:
            st.subheader("🤖 AI Analysis")
            st.info(llm_explanation)

        # News
        if news_summaries:
            st.subheader("📰 Recent News")
            for i, item in enumerate(news_summaries):
                with st.expander(f"News {i+1}: {item[:70]}..." if len(item) > 70 else f"News {i+1}: {item}"):
                    st.write(item)

        st.caption(
            "⚠️ This is an AI-generated view based on technical structure and basic risk metrics. "
            "Always consider your own risk tolerance and consult a SEBI-registered advisor before trading."
        )

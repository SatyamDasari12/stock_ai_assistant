import streamlit as st

from services.analysis_service import build_stock_scorecard
from services.market_data_service import get_latest_quote
from services.portfolio_service import build_portfolio_recommendation


def render_portfolio_advisor_page() -> None:
    st.title("🧺 Portfolio Advisor")
    st.caption("Position‑level buy / sell / hold guidance")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Stock symbol (e.g. BEL.NS)")
    with col2:
        buy_price = st.number_input("Buy price", min_value=0.0, value=440.0, step=0.5)
    with col3:
        quantity = st.number_input("Quantity", min_value=1, value=1, step=1)

    if st.button("Get Advice", type="primary"):
        if not symbol:
            st.error("Enter a stock symbol.")
            return

        with st.spinner("Evaluating position..."):
            quote = get_latest_quote(symbol)
            if quote is None:
                st.error("Could not fetch live quote for this symbol.")
                return

            scorecard = build_stock_scorecard(quote.history_df)
            rec = build_portfolio_recommendation(
                symbol=symbol,
                buy_price=buy_price,
                quantity=quantity,
                latest_price=quote.last_price,
                scorecard=scorecard,
            )

        st.subheader("Recommendation")
        st.write(f"**Action:** {rec.action}")
        st.write(f"**Rationale:** {rec.reason}")
        if rec.target_price is not None and rec.stop_loss is not None:
            st.write(
                f"**Target:** {rec.target_price:.2f}  |  "
                f"**Stop Loss:** {rec.stop_loss:.2f}"
            )
        if rec.holding_period is not None:
            st.write(f"**Holding Period:** {rec.holding_period}")

        st.caption(
            "This is an AI‑generated view based on technical structure and risk profile. "
            "Always consider your own risk tolerance and consult a SEBI‑registered advisor."
        )


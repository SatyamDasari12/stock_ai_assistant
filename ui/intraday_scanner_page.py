import streamlit as st

from services.scanner_service import scan_intraday_momentum_stocks


def render_intraday_scanner_page() -> None:
    st.title("⚡ Intraday Scanner")
    st.caption("Volume spikes, RSI/VWAP breakouts, momentum ranking")

    universe_choice = st.selectbox(
        "Universe",
        ["NIFTY 50", "NIFTY 100", "NIFTY 200 (slower)"],
        index=0,
    )

    top_n = st.slider("Number of ideas", min_value=5, max_value=50, value=15, step=5)

    if st.button("Scan Market", type="primary"):
        with st.spinner("Scanning intraday opportunities..."):
            results = scan_intraday_momentum_stocks(
                universe=universe_choice,
                top_n=top_n,
            )

        if not results:
            st.warning("No intraday opportunities detected (or data not available).")
            return

        st.subheader("Top Momentum Candidates")
        st.dataframe(
            results,
            use_container_width=True,
        )

        st.caption(
            "Signals combine volume spikes, RSI/MACD momentum, and price vs VWAP. "
            "Always validate signals on your broker charts before trading."
        )


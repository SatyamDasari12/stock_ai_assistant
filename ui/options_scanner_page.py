import streamlit as st

from services.options_service import scan_bullish_call_options


def render_options_scanner_page() -> None:
    st.title("📊 Options Scanner")
    st.caption("Bullish CE opportunities using OI, PCR, and trend")

    expiry = st.text_input(
        "Expiry (YYYY-MM-DD, exchange format)",
        help="Example: 2024-03-28. Actual format depends on broker/NSE API.",
    )
    top_n = st.slider("Number of option ideas", 5, 50, 15, 5)

    if st.button("Scan CE Options", type="primary"):
        if not expiry:
            st.error("Please enter an expiry date.")
            return

        with st.spinner("Scanning option chains..."):
            df = scan_bullish_call_options(expiry=expiry, top_n=top_n)

        if df is None or df.empty:
            st.warning("No suitable CE opportunities found (or data unavailable).")
            return

        st.subheader("Top CE Opportunities")
        st.dataframe(df, use_container_width=True)

        st.caption(
            "Signals favor strikes with OI build‑up, healthy PCR, and "
            "underlying bullish trend. Use this as a starting point, not advice."
        )


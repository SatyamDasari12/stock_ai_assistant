import streamlit as st

from ui.stock_analysis_page import render_stock_analysis_page
from ui.intraday_scanner_page import render_intraday_scanner_page
from ui.options_scanner_page import render_options_scanner_page
from ui.portfolio_advisor_page import render_portfolio_advisor_page


PAGES = {
    "📈 Stock Analysis": render_stock_analysis_page,
    "⚡ Intraday Scanner": render_intraday_scanner_page,
    "📊 Options Scanner": render_options_scanner_page,
    "🧺 Portfolio Advisor": render_portfolio_advisor_page,
}


def main() -> None:
    st.set_page_config(
        page_title="AI Stock Assistant (NSE/BSE)",
        page_icon="📈",
        layout="wide",
    )

    st.sidebar.title("AI Stock Assistant")
    st.sidebar.caption("NSE/BSE personal trading co‑pilot")

    selected_page = st.sidebar.radio(
        "Navigation",
        list(PAGES.keys()),
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "Models: **Prophet, Random Forest, Gradient Boosting, Llama 3 (Groq)**"
    )

    render_fn = PAGES[selected_page]
    render_fn()


if __name__ == "__main__":
    main()


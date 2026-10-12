import streamlit as st

from connectors.etoro_service import EtoroService
from ui.components import section_header


@st.fragment
def _render_market_news_fragment() -> None:
    """Render cached market news inside an isolated fragment at bottom of investments page."""
    with section_header("Market News", "Latest market news from eToro feed"):
        etoro = EtoroService()
        news = etoro.fetch_news(limit=10)
        is_configured = etoro.is_configured()

        if news:
            with st.container(height=300, border=True):
                for item in news:
                    c1, c2 = st.columns([1, 15])
                    with c1:
                        if item.get("avatar"):
                            st.image(item["avatar"], width=24)
                        else:
                            st.write("👤")
                    with c2:
                        text = item.get("text", "")
                        if len(text) > 200:
                            text = text[:200] + "..."
                        username = item.get("username", "eToro")
                        created = (item.get("created") or "")[:10]
                        st.markdown(
                            f"**@{username}** <span style='color: gray; font-size: 0.8em;'>• {created}</span><br/>"
                            f"<span style='font-size: 0.9em;'>{text}</span>",
                            unsafe_allow_html=True,
                        )
                    st.divider()
        else:
            if not is_configured:
                st.info("Connect eToro in Settings to view market news.")
            else:
                st.info("No news available right now.")

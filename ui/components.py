import streamlit as st


def kpi_card(
    title: str,
    value_str: str,
    delta_str: str | None = None,
    is_positive: bool = True,
    subtext: str | None = None,
) -> None:
    st.metric(label=title, value=value_str, delta=delta_str, help=subtext)


def section_header(title: str, subtitle: str | None = None, badge: str | None = None) -> None:
    badge_text = f" `{badge}`" if badge else ""
    st.subheader(f"{title}{badge_text}")
    if subtitle:
        st.caption(subtitle)


def empty_state(title: str, message: str) -> None:
    st.info(f"### 📊 {title}\n\n{message}")

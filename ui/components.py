import re
import streamlit as st


def is_hidden() -> bool:
    return bool(st.session_state.get("hide_amounts", False))


def format_money(val: float | int | None, symbol: str = "€", decimals: int = 2) -> str:
    if is_hidden():
        return f"{symbol}****"
    if val is None:
        return f"{symbol}0.00"
    if decimals == 0:
        return f"{symbol}{val:,.0f}"
    return f"{symbol}{val:,.{decimals}f}"


def mask_if_hidden(text: str | None) -> str:
    if not text:
        return ""
    if not is_hidden():
        return str(text)
    # Mask any currency amount (e.g. €123.45, +€1,000, -$50.00) with symbol + ****
    return re.sub(r'([+\-]?)(\$|€|£|TRY\s*)[0-9,]+(\.[0-9]+)?', r'\1\2****', str(text))


def status_badge(text: str, kind: str = "success") -> str:
    return f"<div class='status-dot status-dot-{kind}' title='{text}'></div>"


def kpi_card(
    title: str,
    value_str: str,
    delta_str: str | None = None, subtext: str | None = None,
) -> None:
    if is_hidden():
        value_str = mask_if_hidden(value_str)
        if delta_str and any(c in delta_str for c in ["€", "$", "£"]):
            delta_str = mask_if_hidden(delta_str)
        if subtext:
            subtext = mask_if_hidden(subtext)
    st.metric(label=title, value=value_str, delta=delta_str, help=subtext)


def section_header(title: str, subtitle: str | None = None, badge: str | None = None) -> None:
    badge_text = f" `{badge}`" if badge else ""
    st.subheader(f"{title}{badge_text}")
    if subtitle:
        st.caption(subtitle)


def empty_state(title: str, message: str) -> None:
    st.info(f"### 📊 {title}\n\n{message}")

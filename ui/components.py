import re
import streamlit as st


def is_hidden() -> bool:
    return bool(st.session_state.get("hide_amounts", False))


def _on_privacy_toggle() -> None:
    st.session_state["hide_amounts"] = bool(
        st.session_state.get("global_privacy_toggle", False)
    )


def render_privacy_toggle() -> None:
    st.toggle(
        "Hide values",
        key="global_privacy_toggle",
        on_change=_on_privacy_toggle,
    )



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
    s = re.sub(r'([+\-]?)(\$|€|£|TRY\s*)[0-9,]+(\.[0-9]+)?', r'\1\2****', str(text))
    # Mask percentage values (e.g. 12.5%, +12.5%, -5.0%, **%) with symbol + ****%
    s = re.sub(r'([+\-]?)(\d+(?:,\d+)*(?:\.\d+)?|\*+)\s*%', r'\1****%', s)
    # Mask asset counts and quote delayed counts in metrics/tooltips
    s = re.sub(r'(\b\d+\b)\s+assets', r'**** assets', s)
    s = re.sub(r'(\b\d+\b)\s+quote delayed', r'**** quote delayed', s)
    return s


def status_badge(text: str, kind: str = "success") -> str:
    return f"<div class='status-dot status-dot-{kind}' title='{text}'></div>"


def kpi_card(
    title: str,
    value_str: str,
    delta_str: str | None = None, subtext: str | None = None,
) -> None:
    if is_hidden():
        value_str = mask_if_hidden(value_str)
        if delta_str:
            delta_str = mask_if_hidden(delta_str)
        if subtext:
            subtext = mask_if_hidden(subtext)
    st.metric(label=title, value=value_str, delta=delta_str, help=subtext)


import contextlib


@contextlib.contextmanager
def finance_card(title: str | None = None, subtitle: str | None = None):
    """Semantic card container pattern using CSS variables and standard spacing."""
    with st.container(border=True):
        if title:
            if subtitle:
                st.markdown(
                    f"<div style='margin-bottom: var(--space-sm);'><strong>{title}</strong>"
                    f"<div style='color: var(--text-muted); font-size: var(--font-size-sm);'>{subtitle}</div></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"**{title}**")
        yield


def metric_callout(
    label: str,
    value: str,
    delta: str | None = None,
    subtext: str | None = None,
) -> None:
    """Standardized metric callout helper respecting privacy mask and tabular figures."""
    kpi_card(title=label, value_str=value, delta_str=delta, subtext=subtext)


def section_divider() -> None:
    """Render a clean semantic section divider matching theme tokens."""
    st.markdown("<hr class='section-divider'/>", unsafe_allow_html=True)


@contextlib.contextmanager
def section_header(title: str, subtitle: str | None = None, badge: str | None = None):
    with st.container(border=True):
        badge_text = f" `{badge}`" if badge else ""
        sub = mask_if_hidden(subtitle) if is_hidden() and subtitle else subtitle
        st.subheader(f"{title}{badge_text}", help=sub)
        yield


def empty_state(title: str, message: str) -> None:
    st.info(f"### 📊 {title}\n\n{message}")


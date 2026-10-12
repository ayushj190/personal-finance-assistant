import re
from typing import Any
import streamlit as st
from money import Money
from ui import state


def is_hidden() -> bool:
    return bool(state.get(state.K.PRIVACY_HIDDEN, False))


def _on_privacy_toggle() -> None:
    state.set(
        state.K.PRIVACY_HIDDEN,
        bool(state.get(state.K.GLOBAL_PRIVACY_TOGGLE, False)),
    )


def render_privacy_toggle() -> None:
    st.toggle(
        "Hide values",
        key=state.K.GLOBAL_PRIVACY_TOGGLE,
        on_change=_on_privacy_toggle,
    )



def format_money(
    val: float | int | Any | None,
    symbol: str = "€",
    decimals: int = 2,
) -> str:
    from money import Money

    if not isinstance(val, Money):
        # Convert incoming primitive to Money for uniform representation
        val = Money.from_major(val) if val is not None else Money.from_cents(0)

    curr_map = {"EUR": "€", "USD": "$", "GBP": "£", "TRY": "TRY "}
    sym = curr_map.get(val.currency, symbol) if symbol == "€" else symbol
    if is_hidden():
        return f"{sym}****"
    amount = val.to_major()
    if decimals == 0:
        return f"{sym}{amount:,.0f}"
    return f"{sym}{amount:,.{decimals}f}"


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


def render_section_header(
    title: str,
    subtitle: str | None = None,
    badge: str | None = None,
) -> None:
    """Render a semantic section title + subtitle directly inside an existing panel or column."""
    badge_text = f" `{badge}`" if badge else ""
    sub = mask_if_hidden(subtitle) if is_hidden() and subtitle else subtitle
    st.markdown(
        f"<div style='margin-bottom: var(--space-xs, 4px);'>"
        f"<h3 style='margin: 0; font-size: 1.15rem; font-weight: 600; color: var(--text-color);'>{title}{badge_text}</h3>"
        + (f"<div style='color: var(--text-muted); font-size: 0.85rem; margin-top: 2px;'>{sub}</div>" if sub else "")
        + "</div>",
        unsafe_allow_html=True,
    )


@contextlib.contextmanager
def section_header(title: str, subtitle: str | None = None, badge: str | None = None):
    with st.container(border=True):
        badge_text = f" `{badge}`" if badge else ""
        sub = mask_if_hidden(subtitle) if is_hidden() and subtitle else subtitle
        st.subheader(f"{title}{badge_text}", help=sub)
        yield


def empty_state(
    title: str = "",
    body: str = "",
    icon: str = "📊",
    action_label: str | None = None,
) -> bool:
    """Standard empty state component matching AC-10."""
    with st.container(border=True):
        st.markdown(
            f"<div class='empty-state-card'>"
            f"<div class='empty-state-icon'>{icon}</div>"
            f"<h3 class='empty-state-title'>{title}</h3>"
            f"<p class='empty-state-body'>{body}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if action_label:
            return bool(st.button(action_label, key=f"btn_empty_{title.lower().replace(' ', '_')}"))
        return False


def skeleton(rows: int = 3) -> None:
    """Render skeleton placeholder rows matching theme token height and pulses (AC-10)."""
    bars = "".join("<div class='skeleton-bar'></div>" for _ in range(rows))
    st.markdown(f"<div class='skeleton-container'>{bars}</div>", unsafe_allow_html=True)


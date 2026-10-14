"""Shared Copilot page panel: one figure panel per page, keyed by page id.

The turn's captured figure and the data tool's headline render as a dedicated panel
at the top of the destination page, masked with the shared helpers, and scrolled
into view with `st.iframe` and a pinned selector (AC-3, AC-4, AC-9).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import state
from ui.components import mask_if_hidden
from ui.theme import render_chart

_PANEL_SELECTOR = "copilot_page_panel"


def set_panel(page: str, figure: Any, headline: str | None = None) -> None:
    """Commit the turn's figure and headline as the panel for `page` (AC-3)."""
    state.set(
        state.K.COPILOT_PAGE_PANEL,
        {"page": page, "figure": figure, "headline": headline},
    )


def clear_panel() -> None:
    """Drop the panel (Clear Chat, manual navigation, or a new turn)."""
    state.delete(state.K.COPILOT_PAGE_PANEL)


def _figure_title(figure: Any) -> str | None:
    title = getattr(getattr(figure, "layout", None), "title", None)
    text = getattr(title, "text", None) if title is not None else None
    return str(text) if text else None


def render_page_panel(page_id: str) -> None:
    """Render the Copilot panel when it belongs to this page and scroll it into view (AC-3, AC-4)."""
    panel = state.get(state.K.COPILOT_PAGE_PANEL)
    if not panel or panel.get("page") != page_id:
        return
    figure = panel.get("figure")
    if figure is None:
        return

    headline = panel.get("headline") or _figure_title(figure)
    if headline:
        headline = mask_if_hidden(str(headline))

    with st.container(key=_PANEL_SELECTOR):
        st.markdown("##### 🤖 Copilot")
        if headline:
            st.markdown(f"**{headline}**")
        render_chart(figure, width="stretch")
    _scroll_into_view()


def _scroll_into_view() -> None:
    """Scroll the pinned panel into view; if the script cannot run the top placement stands (AC-4)."""
    try:
        from ui.theme import script_iframe

        script_iframe(
            f"""
            <script>
              (function() {{
                var doc = window.parent.document;
                var el = doc.querySelector('.st-key-{_PANEL_SELECTOR}');
                if (el && el.scrollIntoView) {{
                  el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                }}
              }})();
            </script>
            """
        )
    except Exception:
        pass

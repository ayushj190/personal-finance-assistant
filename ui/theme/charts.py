from typing import Any
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from ui.theme.tokens import (
    COLOR_PALETTE,
    COLOR_UNCATEGORIZED,
    FONT_FAMILY_SANS,
    SEMANTIC_FINANCIAL_COLORS,
)

# Semantic financial color mapping for chart series and categories (AC-2, AC-6)
FINANCIAL_COLOR_MAP = SEMANTIC_FINANCIAL_COLORS


def hex_to_rgba(hex_code: str, alpha: float = 1.0) -> str:
    """Convert hex color (#RRGGBB) to rgba string with transparency."""
    cleaned = hex_code.lstrip("#")
    if len(cleaned) == 6:
        r, g, b = (int(cleaned[i : i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r}, {g}, {b}, {alpha})"
    return hex_code


def get_financial_color(category_or_signal: str, default: str = COLOR_UNCATEGORIZED) -> str:
    """Retrieve standardized semantic financial color for an asset class or expense bucket."""
    normalized = category_or_signal.strip().lower() if category_or_signal else ""
    return FINANCIAL_COLOR_MAP.get(normalized, default)


def register_plotly_theme() -> None:
    """Register the custom PFA Plotly theme template without monkey patching st.plotly_chart."""
    current_theme = (
        st.session_state.get("theme", "dark")
        if hasattr(st, "session_state")
        else "dark"
    )
    template = go.layout.Template()
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.colorway = COLOR_PALETTE

    chart_font_family = FONT_FAMILY_SANS.replace('"', "")

    template.layout.margin = dict(l=55, r=25, t=40, b=40)

    if current_theme == "light":
        template.layout.font = dict(
            family=chart_font_family,
            color="#0F172A",
            size=13,
        )
        template.layout.xaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.25)",
            zerolinecolor="rgba(148, 163, 184, 0.35)",
            tickfont=dict(color="#475569", size=11),
            title=dict(font=dict(color="#0F172A", size=12)),
            showgrid=True,
            automargin=True,
        )
        template.layout.yaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.25)",
            zerolinecolor="rgba(148, 163, 184, 0.35)",
            tickfont=dict(color="#475569", size=11),
            title=dict(font=dict(color="#0F172A", size=12)),
            showgrid=True,
            automargin=True,
        )
        template.layout.legend = dict(
            font=dict(color="#334155"),
            bgcolor="rgba(255, 255, 255, 0.9)",
            bordercolor="rgba(148, 163, 184, 0.35)",
            borderwidth=1,
        )
    else:
        template.layout.font = dict(
            family=chart_font_family,
            color="#F8FAFC",
            size=13,
        )
        template.layout.xaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.12)",
            zerolinecolor="rgba(148, 163, 184, 0.2)",
            tickfont=dict(color="#94A3B8", size=11),
            title=dict(font=dict(color="#F8FAFC", size=12)),
            showgrid=True,
            automargin=True,
        )
        template.layout.yaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.12)",
            zerolinecolor="rgba(148, 163, 184, 0.2)",
            tickfont=dict(color="#94A3B8", size=11),
            title=dict(font=dict(color="#F8FAFC", size=12)),
            showgrid=True,
            automargin=True,
        )
        template.layout.legend = dict(
            font=dict(color="#CBD5E1"),
            bgcolor="rgba(15, 23, 42, 0.65)",
            bordercolor="rgba(148, 163, 184, 0.2)",
            borderwidth=1,
        )

    pio.templates["pfa_theme"] = template
    pio.templates.default = "pfa_theme"


def render_chart(figure_or_data: Any, *args: Any, **kwargs: Any) -> Any:
    """Standardized Plotly chart renderer replacing runtime monkey patching."""
    if "theme" not in kwargs:
        kwargs["theme"] = None
    if "use_container_width" not in kwargs:
        kwargs["use_container_width"] = True
    if "config" not in kwargs or kwargs["config"] is None:
        kwargs["config"] = {}
    kwargs["config"]["displayModeBar"] = False

    if hasattr(figure_or_data, "layout"):
        if not figure_or_data.layout.paper_bgcolor:
            figure_or_data.layout.paper_bgcolor = "rgba(0,0,0,0)"
        if not figure_or_data.layout.plot_bgcolor:
            figure_or_data.layout.plot_bgcolor = "rgba(0,0,0,0)"
        if not figure_or_data.layout.template:
            figure_or_data.layout.template = "pfa_theme"
        if hasattr(figure_or_data.layout, "xaxis") and figure_or_data.layout.xaxis.automargin is None:
            figure_or_data.layout.xaxis.automargin = True
        if hasattr(figure_or_data.layout, "yaxis") and figure_or_data.layout.yaxis.automargin is None:
            figure_or_data.layout.yaxis.automargin = True

    return st.plotly_chart(figure_or_data, *args, **kwargs)


from typing import Any
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from ui.theme.tokens import COLOR_PALETTE


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

    if current_theme == "light":
        template.layout.font = dict(
            family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            color="#0F172A",
            size=13,
        )
        template.layout.xaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.25)",
            zerolinecolor="rgba(148, 163, 184, 0.35)",
            tickfont=dict(color="#475569", size=11),
            title=dict(font=dict(color="#0F172A", size=12)),
            showgrid=True,
        )
        template.layout.yaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.25)",
            zerolinecolor="rgba(148, 163, 184, 0.35)",
            tickfont=dict(color="#475569", size=11),
            title=dict(font=dict(color="#0F172A", size=12)),
            showgrid=True,
        )
        template.layout.legend = dict(
            font=dict(color="#334155"),
            bgcolor="rgba(255, 255, 255, 0.9)",
            bordercolor="rgba(148, 163, 184, 0.35)",
            borderwidth=1,
        )
    else:
        template.layout.font = dict(
            family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
            color="#F8FAFC",
            size=13,
        )
        template.layout.xaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.12)",
            zerolinecolor="rgba(148, 163, 184, 0.2)",
            tickfont=dict(color="#94A3B8", size=11),
            title=dict(font=dict(color="#F8FAFC", size=12)),
            showgrid=True,
        )
        template.layout.yaxis = dict(
            gridcolor="rgba(148, 163, 184, 0.12)",
            zerolinecolor="rgba(148, 163, 184, 0.2)",
            tickfont=dict(color="#94A3B8", size=11),
            title=dict(font=dict(color="#F8FAFC", size=12)),
            showgrid=True,
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

    return st.plotly_chart(figure_or_data, *args, **kwargs)

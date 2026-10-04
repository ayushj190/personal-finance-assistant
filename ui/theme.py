import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

TEAL = "#2DD4BF"
VIOLET = "#A78BFA"
AMBER = "#FBBF24"
ROSE = "#FB7185"
SKY = "#38BDF8"
EMERALD = "#34D399"
SLATE = "#94A3B8"

COLOR_PALETTE = [TEAL, VIOLET, AMBER, ROSE, SKY, EMERALD, "#F472B6", "#818CF8", "#A3E635", SLATE]


def register_plotly_theme() -> None:
    template = go.layout.Template()
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.font = dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#F8FAFC", size=13)
    template.layout.colorway = COLOR_PALETTE
    template.layout.xaxis = dict(
        gridcolor="rgba(148, 163, 184, 0.12)",
        zerolinecolor="rgba(148, 163, 184, 0.2)",
        showgrid=True,
    )
    template.layout.yaxis = dict(
        gridcolor="rgba(148, 163, 184, 0.12)",
        zerolinecolor="rgba(148, 163, 184, 0.2)",
        showgrid=True,
    )
    template.layout.legend = dict(
        font=dict(color="#CBD5E1"),
        bgcolor="rgba(15, 23, 42, 0.6)",
        bordercolor="rgba(148, 163, 184, 0.2)",
        borderwidth=1,
    )
    pio.templates["pfa_dark"] = template
    pio.templates.default = "pfa_dark"


from textwrap import dedent

def inject_custom_css() -> None:
    st.markdown(
        dedent(
            """
            <style>
        /* Modern Glass UI Elements */
        .glass-card, div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.75) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 14px;
            padding: 16px 20px;
            box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.25);
            transition: all 0.2s ease-in-out;
            margin-bottom: 8px;
        }
        .glass-card:hover, div[data-testid="stMetric"]:hover {
            border-color: rgba(45, 212, 191, 0.4);
            transform: translateY(-2px);
            box-shadow: 0 8px 30px 0 rgba(0, 0, 0, 0.35);
        }

        /* Bordered Containers */
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: rgba(15, 23, 42, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
            border-radius: 12px;
            padding: 16px;
            transition: border-color 0.2s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
            border-color: rgba(45, 212, 191, 0.3) !important;
        }

        /* Buttons Styling */
        button[kind="primary"] {
            background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 10px rgba(20, 184, 166, 0.25);
            transition: all 0.2s ease !important;
        }
        button[kind="primary"]:hover {
            background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%) !important;
            box-shadow: 0 4px 16px rgba(20, 184, 166, 0.4);
            transform: translateY(-1px);
        }
        button[kind="secondary"] {
            background: rgba(30, 41, 59, 0.5) !important;
            border: 1px solid rgba(148, 163, 184, 0.25) !important;
            color: #E2E8F0 !important;
            border-radius: 8px !important;
            transition: all 0.2s ease !important;
        }
        button[kind="secondary"]:hover {
            border-color: rgba(45, 212, 191, 0.5) !important;
            color: #2DD4BF !important;
            background: rgba(30, 41, 59, 0.8) !important;
            transform: translateY(-1px);
        }

        .kpi-title {
            color: #94A3B8;
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 6px;
        }
        .kpi-value {
            color: #F8FAFC;
            font-size: 1.85rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .kpi-delta-positive {
            display: inline-block;
            background: rgba(52, 211, 153, 0.15);
            color: #34D399;
            font-size: 0.82rem;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
            margin-top: 6px;
        }
        .kpi-delta-negative {
            display: inline-block;
            background: rgba(251, 113, 133, 0.15);
            color: #FB7185;
            font-size: 0.82rem;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 6px;
            margin-top: 6px;
        }
        .badge-pill {
            display: inline-block;
            padding: 3px 10px;
            font-size: 0.78rem;
            font-weight: 600;
            border-radius: 9999px;
            background: rgba(45, 212, 191, 0.15);
            color: #2DD4BF;
            border: 1px solid rgba(45, 212, 191, 0.3);
        }
        </style>
        """
        ).strip(),
        unsafe_allow_html=True,
    )

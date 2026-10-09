import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from textwrap import dedent

TEAL = "#2DD4BF"
VIOLET = "#A78BFA"
AMBER = "#FBBF24"
ROSE = "#FB7185"
SKY = "#38BDF8"
EMERALD = "#34D399"
SLATE = "#94A3B8"

COLOR_PALETTE = [TEAL, VIOLET, AMBER, ROSE, SKY,
                 EMERALD, "#F472B6", "#818CF8", "#A3E635", SLATE]

COLOR_INCOME = EMERALD
COLOR_FIXED = ROSE
COLOR_DISCRETIONARY = AMBER
COLOR_SAVINGS = TEAL
COLOR_CASH = TEAL
COLOR_INVESTMENT = SKY
COLOR_LIABILITY = ROSE
COLOR_UNCATEGORIZED = SLATE


def _patch_plotly_chart() -> None:
    """Ensure st.plotly_chart defaults to theme=None and transparent background."""
    if getattr(st, "_pfa_plotly_chart_patched", False):
        return
    orig_plotly_chart = st.plotly_chart

    def themed_plotly_chart(figure_or_data, *args, **kwargs):
        if "theme" not in kwargs:
            kwargs["theme"] = None
        if "use_container_width" not in kwargs:
            kwargs["use_container_width"] = True
        if "config" not in kwargs:
            kwargs["config"] = {}
        kwargs["config"]["displayModeBar"] = False

        if hasattr(figure_or_data, "layout"):
            if not figure_or_data.layout.paper_bgcolor:
                figure_or_data.layout.paper_bgcolor = "rgba(0,0,0,0)"
            if not figure_or_data.layout.plot_bgcolor:
                figure_or_data.layout.plot_bgcolor = "rgba(0,0,0,0)"
            if not figure_or_data.layout.template:
                figure_or_data.layout.template = "pfa_theme"

        return orig_plotly_chart(figure_or_data, *args, **kwargs)

    st.plotly_chart = themed_plotly_chart
    st._pfa_plotly_chart_patched = True


def register_plotly_theme() -> None:
    current_theme = st.session_state.get(
        "theme", "dark") if hasattr(st, "session_state") else "dark"
    template = go.layout.Template()
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.colorway = COLOR_PALETTE

    if current_theme == "light":
        template.layout.font = dict(
            family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#0F172A", size=13)
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
            family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#F8FAFC", size=13)
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
    _patch_plotly_chart()


def inject_custom_css() -> None:
    current_theme = st.session_state.get(
        "theme", "dark") if hasattr(st, "session_state") else "dark"
    if current_theme == "light":
        css_theme = """
        :root, .stApp {
            --background-color: #F8FAFC !important;
            --secondary-background-color: #FFFFFF !important;
            --text-color: #0F172A !important;
            --primary-color: #0D9488 !important;
            --tab-border: #E2E8F0 !important;
            --tab-inactive-bg: #F1F5F9 !important;
            --button-border: #CBD5E1 !important;
            --button-bg: #FFFFFF !important;
            --text-muted: #334155 !important;
            background-color: #F8FAFC !important;
            color: #0F172A !important;
        }

        /* Sidebar in Light Mode */
        section[data-testid="stSidebar"] {
            border-right: 1px solid #E2E8F0 !important;
        }
        section[data-testid="stSidebar"],
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
        }
        section[data-testid="stSidebar"] * {
            color: #0F172A !important;
        }
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown span,
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] .stCaption * {
            color: #334155 !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #0F172A !important;
        }
        section[data-testid="stSidebar"] hr {
            border-color: #E2E8F0 !important;
        }

        /* Metric Cards & Glass Cards */
        .glass-card, div[data-testid="stMetric"] {
            background: #FFFFFF !important;
            backdrop-filter: none !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 14px !important;
            padding: 16px 20px !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 4px 12px 0 rgba(0, 0, 0, 0.03) !important;
            transition: all 0.2s ease-in-out !important;
            min-height: 115px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            box-sizing: border-box !important;
        }
        .glass-card:hover, div[data-testid="stMetric"]:hover {
            border-color: rgba(13, 148, 136, 0.6) !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 18px 0 rgba(0, 0, 0, 0.08) !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            color: #334155 !important;
            opacity: 1 !important;
            font-weight: 600 !important;
        }
        [data-testid="stMetricLabel"] svg {
            fill: #334155 !important;
            color: #334155 !important;
            opacity: 0.9 !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            color: #0F172A !important;
            font-weight: 700 !important;
            opacity: 1 !important;
        }
        .kpi-title { color: #334155 !important; opacity: 1 !important; }
        .kpi-value { color: #0F172A !important; opacity: 1 !important; }

        /* Bordered Containers */
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 12px !important;
            padding: 16px !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04) !important;
            backdrop-filter: none !important;
            color: #0F172A !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
            border-color: rgba(13, 148, 136, 0.4) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div * {
            color: #0F172A;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption,
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption * {
            color: #334155 !important;
        }

        /* Tabs in Light Mode */
        div[data-baseweb="tab-list"],
        div[data-testid="stTabs"] [role="tablist"] {
            background-color: transparent !important;
            border-bottom: 2px solid #E2E8F0 !important;
            gap: 8px !important;
        }
        [role="tab"],
        [data-baseweb="tab"],
        [data-testid="stTab"],
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] div[role="tab"] {
            background-color: transparent !important;
            border: none !important;
            border-radius: 6px 6px 0 0 !important;
            padding: 8px 16px !important;
            color: #334155 !important;
            opacity: 1 !important;
            transition: all 0.15s ease-in-out !important;
            cursor: pointer !important;
        }
        [role="tab"] *,
        [data-baseweb="tab"] *,
        [data-testid="stTab"] *,
        div[data-testid="stTabs"] button *,
        div[data-testid="stTabs"] div[role="tab"] * {
            color: #334155 !important;
            font-size: 0.92rem !important;
            font-weight: 600 !important;
            opacity: 1 !important;
        }
        [role="tab"]:hover,
        [role="tab"]:hover *,
        [data-baseweb="tab"]:hover,
        [data-baseweb="tab"]:hover *,
        [data-testid="stTab"]:hover,
        [data-testid="stTab"]:hover * {
            color: #0F172A !important;
            opacity: 1 !important;
        }
        [role="tab"][aria-selected="true"],
        [role="tab"][aria-selected="true"] *,
        [data-baseweb="tab"][aria-selected="true"],
        [data-baseweb="tab"][aria-selected="true"] *,
        [data-testid="stTab"][aria-selected="true"],
        [data-testid="stTab"][aria-selected="true"] * {
            color: #0D9488 !important;
            font-weight: 700 !important;
            opacity: 1 !important;
        }
        div[data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: #0D9488 !important;
            height: 3px !important;
            border-radius: 2px !important;
        }
        div[data-baseweb="tab-border"] {
            background-color: #E2E8F0 !important;
        }

        /* Secondary Buttons & Popovers */
        button[kind="secondary"],
        button[data-testid="baseButton-secondary"],
        div[data-testid="stPopover"] > button {
            background: #FFFFFF !important;
            border: 1px solid #CBD5E1 !important;
            color: #334155 !important;
            border-radius: 8px !important;
            min-height: 38px !important;
            height: 38px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
        }
        button[kind="secondary"]:hover,
        button[data-testid="baseButton-secondary"]:hover,
        div[data-testid="stPopover"] > button:hover {
            border-color: #0D9488 !important;
            color: #0D9488 !important;
            background: #F8FAFC !important;
            transform: translateY(-1px) !important;
        }

        /* Inputs, Selects, Expanders */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
            border-color: #CBD5E1 !important;
        }
        div[data-testid="stExpander"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 10px !important;
        }
        div[data-testid="stExpander"] details summary,
        div[data-testid="stExpander"] details summary span,
        div[data-testid="stExpander"] details summary p {
            color: #0F172A !important;
            font-weight: 600 !important;
        }
        div[data-testid="stPopoverBody"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            color: #0F172A !important;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1) !important;
        }
        div[data-testid="stChatMessage"] {
            background-color: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 10px !important;
            color: #0F172A !important;
        }
        div[data-testid="stRadio"] label p,
        div[data-testid="stCheckbox"] label p {
            color: #0F172A !important;
        }
        """
    else:
        css_theme = """
        :root, .stApp {
            --background-color: #1E1E1E !important;
            --secondary-background-color: #252526 !important;
            --text-color: #D4D4D4 !important;
            --primary-color: #007ACC !important;
            --tab-border: #3C3C3C !important;
            --tab-inactive-bg: #2D2D2D !important;
            --button-border: #3C3C3C !important;
            --button-bg: #333333 !important;
            --text-muted: #858585 !important;
            background-color: #1E1E1E !important;
            color: #D4D4D4 !important;
        }

        /* Sidebar in Dark Mode */
        section[data-testid="stSidebar"] {
            border-right: 1px solid #3C3C3C !important;
        }
        section[data-testid="stSidebar"],
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {
            background-color: #252526 !important;
            color: #D4D4D4 !important;
        }
        section[data-testid="stSidebar"] * {
            color: #D4D4D4;
        }
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown span,
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] .stCaption * {
            color: #858585 !important;
        }
        section[data-testid="stSidebar"] hr {
            border-color: #3C3C3C !important;
        }

        /* Metric Cards & Glass Cards */
        .glass-card, div[data-testid="stMetric"] {
            background: #252526 !important;
            backdrop-filter: none !important;
            border: 1px solid #3C3C3C !important;
            border-radius: 4px !important;
            padding: 16px 20px !important;
            box-shadow: none !important;
            transition: all 0.2s ease-in-out !important;
            min-height: 115px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            box-sizing: border-box !important;
        }
        .glass-card:hover, div[data-testid="stMetric"]:hover {
            border-color: #007ACC !important;
            transform: translateY(-2px) !important;
            box-shadow: none !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            color: #94A3B8 !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            color: #F8FAFC !important;
        }
        .kpi-title { color: #94A3B8 !important; }
        .kpi-value { color: #F8FAFC !important; }

        /* Bordered Containers */
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: #252526 !important;
            backdrop-filter: none !important;
            border: 1px solid #3C3C3C !important;
            border-radius: 4px !important;
            padding: 16px !important;
            box-sizing: border-box !important;
            box-shadow: none !important;
            transition: border-color 0.2s ease, transform 0.2s ease !important;
            color: #D4D4D4 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
            border-color: #007ACC !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div * {
            color: #F8FAFC;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption,
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption * {
            color: #94A3B8 !important;
        }

        /* Tabs in Dark Mode */
        div[data-baseweb="tab-list"],
        div[data-testid="stTabs"] [role="tablist"] {
            background-color: transparent !important;
            border-bottom: 2px solid rgba(148, 163, 184, 0.18) !important;
            gap: 8px !important;
        }
        [role="tab"],
        [data-baseweb="tab"],
        [data-testid="stTab"],
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] div[role="tab"] {
            background-color: transparent !important;
            border: none !important;
            border-radius: 6px 6px 0 0 !important;
            padding: 8px 16px !important;
            transition: all 0.15s ease-in-out !important;
            cursor: pointer !important;
        }
        [role="tab"] *,
        [data-baseweb="tab"] *,
        [data-testid="stTab"] *,
        div[data-testid="stTabs"] button *,
        div[data-testid="stTabs"] div[role="tab"] * {
            color: #94A3B8 !important;
            font-size: 0.92rem !important;
            font-weight: 500 !important;
        }
        [role="tab"]:hover,
        [role="tab"]:hover *,
        [data-baseweb="tab"]:hover,
        [data-baseweb="tab"]:hover *,
        [data-testid="stTab"]:hover,
        [data-testid="stTab"]:hover * {
            color: #F8FAFC !important;
        }
        [role="tab"][aria-selected="true"],
        [role="tab"][aria-selected="true"] *,
        [data-baseweb="tab"][aria-selected="true"],
        [data-baseweb="tab"][aria-selected="true"] *,
        [data-testid="stTab"][aria-selected="true"],
        [data-testid="stTab"][aria-selected="true"] * {
            color: #2DD4BF !important;
            font-weight: 700 !important;
        }
        div[data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: #2DD4BF !important;
            height: 3px !important;
            border-radius: 2px !important;
        }
        div[data-baseweb="tab-border"] {
            background-color: rgba(148, 163, 184, 0.18) !important;
        }

        /* Secondary Buttons & Popovers */
        button[kind="secondary"],
        button[data-testid="baseButton-secondary"],
        div[data-testid="stPopover"] > button {
            background: rgba(30, 41, 59, 0.5) !important;
            border: 1px solid rgba(148, 163, 184, 0.25) !important;
            color: #E2E8F0 !important;
            border-radius: 8px !important;
            min-height: 38px !important;
            height: 38px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
        }
        button[kind="secondary"]:hover,
        button[data-testid="baseButton-secondary"]:hover,
        div[data-testid="stPopover"] > button:hover {
            border-color: rgba(45, 212, 191, 0.5) !important;
            color: #2DD4BF !important;
            background: rgba(30, 41, 59, 0.8) !important;
            transform: translateY(-1px) !important;
        }

        /* Inputs, Selects, Expanders */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input {
            background-color: #1E293B !important;
            color: #F8FAFC !important;
            border-color: rgba(148, 163, 184, 0.2) !important;
        }
        div[data-testid="stExpander"] {
            background-color: rgba(15, 23, 42, 0.45) !important;
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
            border-radius: 10px !important;
        }
        div[data-testid="stExpander"] details summary,
        div[data-testid="stExpander"] details summary span,
        div[data-testid="stExpander"] details summary p {
            color: #F8FAFC !important;
            font-weight: 600 !important;
        }
        div[data-testid="stPopoverBody"] {
            background-color: #0F172A !important;
            border: 1px solid rgba(148, 163, 184, 0.25) !important;
            color: #F8FAFC !important;
        }
        /* Chat UI */
        div[data-testid="stChatMessage"] {
            background-color: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin-bottom: 1rem !important;
            display: flex !important;
        }

        /* User Messages (Right Aligned) */
        div[data-testid="stChatMessage"]:has([alt="user avatar"]), 
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            flex-direction: row-reverse !important;
        }
        div[data-testid="stChatMessage"]:has([alt="user avatar"]) .stMarkdown,
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown {
            background-color: #007ACC !important;
            color: #FFFFFF !important;
            border-radius: 18px 18px 4px 18px !important;
            padding: 12px 16px !important;
            max-width: 80% !important;
            margin-right: 12px !important;
            margin-left: auto !important;
        }

        /* Assistant Messages (Left Aligned) */
        div[data-testid="stChatMessage"]:has([alt="assistant avatar"]), 
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            flex-direction: row !important;
        }
        div[data-testid="stChatMessage"]:has([alt="assistant avatar"]) .stMarkdown,
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) .stMarkdown {
            background-color: #333333 !important;
            color: #D4D4D4 !important;
            border-radius: 18px 18px 18px 4px !important;
            padding: 12px 16px !important;
            max-width: 85% !important;
            margin-left: 12px !important;
            margin-right: auto !important;
        }
        div[data-testid="stRadio"] label p,
        div[data-testid="stCheckbox"] label p {
            color: #F8FAFC !important;
        }
        """

    raw_css = """
        <style>
        __CSS_THEME__

        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }

        /* Move main h1 titles into the top gap */
        .block-container h1 {
            margin-top: -1.5rem !important;
            padding-top: 0 !important;
        }
        /* Push sidebar content up slightly to fill gap */
        [data-testid="stSidebarContent"] {
            padding-top: 0rem !important;
        }

        header[data-testid="stHeader"] {
            background-color: transparent !important;
            pointer-events: none !important;
        }
        header[data-testid="stHeader"] * {
            pointer-events: auto !important;
        }
        
        /* Ensure the sidebar button can be seen outside, but keep inner contents clipped */
        [data-testid="stSidebar"] {
            overflow: visible !important;
        }
        [data-testid="stSidebarUserContent"] {
            overflow-x: hidden !important;
            overflow-y: hidden !important;
        }
        
        /* Hide sidebar collapse button so it cannot be closed */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }


        /* ------------------------------------------ */

        [data-testid="stMetricLabel"] {
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
            margin-bottom: 4px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.75rem !important;
            font-weight: 700 !important;
            line-height: 1.2 !important;
        }

        /* Standardized Primary Buttons */
        button[kind="primary"], button[data-testid="baseButton-primary"] {
            background: #007ACC !important;
            color: #FFFFFF !important;
            border: none !important;
            font-weight: 500 !important;
            border-radius: 2px !important;
            min-height: 32px !important;
            height: 32px !important;
            box-shadow: none !important;
            transition: background-color 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
            background: #005999 !important;
            box-shadow: none !important;
            transform: none !important;
        }
        div[data-testid="stPopover"] {
            width: 100% !important;
        }

        .kpi-title {
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 6px;
        }
        .kpi-value {
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
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            font-size: 0.72rem;
            font-weight: 600;
            border-radius: 9999px;
            background: rgba(45, 212, 191, 0.12);
            color: #2DD4BF;
            border: 1px solid rgba(45, 212, 191, 0.28);
            white-space: nowrap;
        }
        .badge-success {
            background: rgba(52, 211, 153, 0.12);
            color: #34D399;
            border-color: rgba(52, 211, 153, 0.28);
        }
        .badge-warning {
            background: rgba(251, 191, 36, 0.12);
            color: #FBBF24;
            border-color: rgba(251, 191, 36, 0.28);
        }
        .badge-neutral {
            background: rgba(148, 163, 184, 0.12);
            color: #94A3B8;
            border-color: rgba(148, 163, 184, 0.28);
        }

        /* Status Dots */
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        .status-dot-success { background-color: #34D399; box-shadow: 0 0 8px #34D399; }
        .status-dot-warning { background-color: #FBBF24; box-shadow: 0 0 8px #FBBF24; }
        .status-dot-danger { background-color: #FB7185; box-shadow: 0 0 8px #FB7185; }
        .status-dot-neutral { background-color: #94A3B8; box-shadow: 0 0 4px #94A3B8; }



        /* Hide Top Right Default Elements & Header */
        [data-testid="stToolbar"] { display: none !important; }
        .stDeployButton { display: none !important; }
        [data-testid="stAppMetaInfo"] { display: none !important; }







        /* Hide Scrollbars */
        ::-webkit-scrollbar {
            width: 0px !important;
            background: transparent !important;
        }
        * {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }

        </style>
        """

    st.markdown(
        dedent(raw_css.replace("__CSS_THEME__", css_theme)).strip(),
        unsafe_allow_html=True,
    )

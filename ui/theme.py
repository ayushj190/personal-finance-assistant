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
        
        section[data-testid="stSidebar"] .st-key-sticky_sidebar_header {
            background-color: #FFFFFF !important;
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
            gap: 0px !important;
            justify-content: flex-start !important;
            padding-left: 0 !important;
            margin-left: 0 !important;
            width: 100% !important;
        }
        [role="tab"],
        [data-baseweb="tab"],
        [data-testid="stTab"],
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] div[role="tab"] {
            background-color: transparent !important;
            border: 1px solid transparent !important;
            border-bottom: none !important;
            border-radius: 8px 8px 0 0 !important;
            padding: 10px 16px !important;
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
            --background-color: #0a110d !important;
            --secondary-background-color: #101c15 !important;
            --text-color: #ecfdf5 !important;
            --primary-color: #10b981 !important;
            --tab-border: #162a1f !important;
            --tab-inactive-bg: #0d1711 !important;
            --button-border: #1e3325 !important;
            --button-bg: #101c15 !important;
            --text-muted: #94a3b8 !important;
            background-color: #0a110d !important;
            color: #ecfdf5 !important;
            font-family: 'Inter', sans-serif !important;
        }

        /* Sidebar in Dark Mode */
        section[data-testid="stSidebar"] {
            border-right: 1px solid #162a1f !important;
        }
        section[data-testid="stSidebar"],
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {
            background-color: #101c15 !important;
            color: #ecfdf5 !important;
        }
        
        section[data-testid="stSidebar"] .st-key-sticky_sidebar_header {
            background-color: #101c15 !important;
        }
        section[data-testid="stSidebar"] * {
            color: #ecfdf5;
        }
        section[data-testid="stSidebar"] .stMarkdown p,
        section[data-testid="stSidebar"] .stMarkdown span,
        section[data-testid="stSidebar"] .stCaption,
        section[data-testid="stSidebar"] .stCaption * {
            color: #94a3b8 !important;
        }
        section[data-testid="stSidebar"] hr {
            border-color: #1e3325 !important;
        }

        /* Metric Cards & Glass Cards */
        .glass-card, div[data-testid="stMetric"] {
            background: #101c15 !important;
            backdrop-filter: none !important;
            border: 1px solid #1e3325 !important;
            border-radius: 12px !important;
            padding: 16px 20px !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
            transition: all 0.2s ease-in-out !important;
            min-height: 115px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            box-sizing: border-box !important;
        }
        .glass-card:hover, div[data-testid="stMetric"]:hover {
            border-color: #10b981 !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 24px rgba(16, 185, 129, 0.15) !important;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] * {
            color: #94a3b8 !important;
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] * {
            color: #ecfdf5 !important;
        }
        .kpi-title { color: #94a3b8 !important; }
        .kpi-value { color: #ecfdf5 !important; }

        /* Bordered Containers */
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            background: #101c15 !important;
            backdrop-filter: none !important;
            border: 1px solid #1e3325 !important;
            border-radius: 12px !important;
            padding: 16px !important;
            box-sizing: border-box !important;
            box-shadow: none !important;
            transition: border-color 0.2s ease, transform 0.2s ease !important;
            color: #ecfdf5 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
            border-color: #10b981 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div * {
            color: #ecfdf5;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption,
        div[data-testid="stVerticalBlockBorderWrapper"] > div .stCaption * {
            color: #94a3b8 !important;
        }

        /* Tabs in Dark Mode */
        div[data-baseweb="tab-list"],
        div[data-testid="stTabs"] [role="tablist"] {
            background-color: transparent !important;
            border-bottom: 2px solid #1e3325 !important;
            gap: 0px !important;
            justify-content: flex-start !important;
            padding-left: 0 !important;
            margin-left: 0 !important;
            width: 100% !important;
        }
        [role="tab"],
        [data-baseweb="tab"],
        [data-testid="stTab"],
        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] div[role="tab"] {
            background-color: transparent !important;
            border: 1px solid transparent !important;
            border-bottom: none !important;
            border-radius: 8px 8px 0 0 !important;
            padding: 10px 16px !important;
            transition: all 0.15s ease-in-out !important;
            cursor: pointer !important;
        }
        [role="tab"] *,
        [data-baseweb="tab"] *,
        [data-testid="stTab"] *,
        div[data-testid="stTabs"] button *,
        div[data-testid="stTabs"] div[role="tab"] * {
            color: #94a3b8 !important;
            font-size: 0.92rem !important;
            font-weight: 500 !important;
        }
        [role="tab"]:hover,
        [role="tab"]:hover *,
        [data-baseweb="tab"]:hover,
        [data-baseweb="tab"]:hover *,
        [data-testid="stTab"]:hover,
        [data-testid="stTab"]:hover * {
            color: #ecfdf5 !important;
        }
        [role="tab"][aria-selected="true"],
        [role="tab"][aria-selected="true"] *,
        [data-baseweb="tab"][aria-selected="true"],
        [data-baseweb="tab"][aria-selected="true"] *,
        [data-testid="stTab"][aria-selected="true"],
        [data-testid="stTab"][aria-selected="true"] * {
            color: #10b981 !important;
            font-weight: 700 !important;
        }
        div[data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: #10b981 !important;
            height: 3px !important;
            border-radius: 2px !important;
        }
        div[data-baseweb="tab-border"] {
            background-color: #1e3325 !important;
        }

        /* Secondary Buttons & Popovers */
        button[kind="secondary"],
        button[data-testid="baseButton-secondary"],
        div[data-testid="stPopover"] > button {
            background: #101c15 !important;
            border: 1px solid #1e3325 !important;
            color: #ecfdf5 !important;
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
            border-color: #10b981 !important;
            color: #10b981 !important;
            background: #162a1f !important;
            transform: translateY(-1px) !important;
        }

        /* Inputs, Selects, Expanders */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input {
            background-color: #0d1711 !important;
            color: #ecfdf5 !important;
            border-color: #1e3325 !important;
        }
        div[data-testid="stExpander"] {
            background-color: #101c15 !important;
            border: 1px solid #1e3325 !important;
            border-radius: 10px !important;
        }
        div[data-testid="stExpander"] details summary,
        div[data-testid="stExpander"] details summary span,
        div[data-testid="stExpander"] details summary p {
            color: #ecfdf5 !important;
            font-weight: 600 !important;
        }
        div[data-testid="stPopoverBody"] {
            background-color: #0a110d !important;
            border: 1px solid #1e3325 !important;
            color: #ecfdf5 !important;
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
            background-color: #10b981 !important;
            color: #0a110d !important;
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
            background-color: #162a1f !important;
            color: #ecfdf5 !important;
            border-radius: 18px 18px 18px 4px !important;
            padding: 12px 16px !important;
            max-width: 85% !important;
            margin-left: 12px !important;
            margin-right: auto !important;
        }
        div[data-testid="stRadio"] label p,
        div[data-testid="stCheckbox"] label p {
            color: #ecfdf5 !important;
        }
        """

    raw_css = """
        <style>
        __CSS_THEME__

        .block-container,
        div[data-testid="stMainBlockContainer"] {
            padding: 1rem 2rem 2rem 2rem !important;
            max-width: 100% !important;
        }

        /* Top App Bar Sticky Header Container */
        div.st-key-top_app_bar {
            position: sticky !important;
            top: 0px !important;
            z-index: 99999 !important;
            background-color: var(--background-color) !important;
            border-bottom: 1px solid var(--tab-border) !important;
            margin-left: -2rem !important;
            margin-right: -2rem !important;
            margin-top: -1rem !important;
            margin-bottom: 1.25rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            padding-top: 0.65rem !important;
            padding-bottom: 0.55rem !important;
            width: calc(100% + 4rem) !important;
            box-sizing: border-box !important;
        }

        /* Top App Bar Inner Layout */
        div.st-key-top_app_bar > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"],
        div.st-key-top_app_bar div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0px !important;
        }

        /* Tabs Row Columns */
        div.st-key-top_app_bar div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] {
            align-items: flex-end !important;
            gap: 0px !important;
        }

        /* Individual Tab Links */
        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"] {
            background-color: transparent !important;
            border: 1px solid transparent !important;
            border-bottom: none !important;
            border-radius: 8px 8px 0 0 !important;
            padding: 10px 16px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-decoration: none !important;
            color: var(--text-muted) !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            white-space: nowrap !important;
            width: 100% !important;
            min-height: 42px !important;
            height: 42px !important;
            box-sizing: border-box !important;
            transition: all 0.15s ease-in-out !important;
            position: relative !important;
            top: 1px !important; /* to overlap the bottom border */
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"]:hover {
            background-color: var(--tab-inactive-bg) !important;
            color: var(--text-color) !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"][aria-current="page"] {
            background-color: var(--background-color) !important;
            border: 1px solid var(--tab-border) !important;
            border-bottom: 1px solid var(--background-color) !important;
            color: var(--primary-color) !important;
            font-weight: 600 !important;
            box-shadow: none !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"] * {
            color: var(--text-muted) !important;
            font-size: 0.84rem !important;
            font-weight: inherit !important;
            white-space: nowrap !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"]:hover * {
            color: var(--text-color) !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"][aria-current="page"] * {
            color: var(--primary-color) !important;
            font-weight: 600 !important;
        }

        /* Right Column: Hide values toggle alignment */
        div.st-key-top_app_bar > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {
            display: flex !important;
            justify-content: flex-end !important;
            align-items: center !important;
        }

        div.st-key-top_app_bar div[data-testid="stToggle"],
        div.st-key-top_app_bar div[data-testid="stCheckbox"] {
            margin-bottom: 0 !important;
            margin-top: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            width: 100% !important;
        }

        div.st-key-top_app_bar div[data-testid="stToggle"] label,
        div.st-key-top_app_bar div[data-testid="stCheckbox"] label {
            margin-bottom: 0 !important;
            margin-top: 0 !important;
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
            cursor: pointer !important;
            justify-content: flex-end !important;
        }

        div.st-key-top_app_bar div[data-testid="stToggle"] label p,
        div.st-key-top_app_bar div[data-testid="stCheckbox"] label p {
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            color: var(--text-muted) !important;
            margin: 0 !important;
            white-space: nowrap !important;
        }

        /* Remove Small gap for the rest of the main content */

        header[data-testid="stHeader"] {
            background-color: transparent !important;
            pointer-events: none !important;
        }
        header[data-testid="stHeader"] * {
            pointer-events: auto !important;
        }
        
        /* Sidebar styling to start at the top */
        [data-testid="stSidebar"] {
            top: 0 !important;
            height: 100vh !important;
            padding-top: 0 !important;
            overflow: visible !important;
        }
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        [data-testid="stSidebarContent"] {
            padding-top: 0 !important;
            gap: 0 !important;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0 !important;
            margin-top: -4.5rem !important; /* Forcefully pull up to kill the un-hideable gap */
            height: calc(100vh + 4.5rem) !important;
            overflow: hidden !important; /* Use flexbox for internal scrolling */
            display: flex !important;
            flex-direction: column !important;
        }
        
        /* Middle Chat History Container */
        [data-testid="stSidebarUserContent"] > div.element-container:nth-child(2) {
            flex-grow: 1 !important;
            overflow-y: auto !important; /* ONLY this scrolls! */
            padding-bottom: 1rem !important;
            padding-right: 0.5rem !important;
        }
        
        /* Bottom Chat Input */
        div[data-testid="stChatInput"] {
            position: relative !important;
            bottom: auto !important;
            flex-shrink: 0 !important;
            padding-bottom: 1rem !important;
        }
        
        /* Hide sidebar collapse button so it cannot be closed */
        [data-testid="stSidebarCollapseButton"],
        [data-testid="collapsedControl"] {
            display: none !important;
        }

        /* Sleek DataFrames */
        [data-testid="stDataFrame"] {
            border-radius: 12px !important;
            overflow: hidden !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
            border: 1px solid var(--tab-border) !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease !important;
        }
        [data-testid="stDataFrame"]:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 24px rgba(13, 148, 136, 0.15) !important;
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
            background: #10b981 !important;
            color: #0a110d !important;
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
            background: #059669 !important;
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

        /* Sticky Sidebar Header */
        div[data-testid="stSidebarUserContent"] .st-key-sticky_sidebar_header {
            flex-shrink: 0 !important;
            padding-top: 1.5rem !important;
            padding-bottom: 1rem !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            border-bottom: 1px solid var(--tab-border) !important;
        }

        /* Subtle Micro-Animations */
        @keyframes subtleFadeUp {
            from {
                opacity: 0.92;
                transform: translateY(3px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .glass-card, 
        div[data-testid="stMetric"],
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s ease !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"] {
            transition: background-color 0.18s ease, color 0.18s ease, transform 0.15s ease !important;
        }

        div.st-key-top_app_bar a[data-testid="stPageLink-NavLink"]:hover {
            transform: translateY(-1px) !important;
        }

        button[kind="secondary"],
        button[data-testid="baseButton-secondary"],
        div[data-testid="stPopover"] > button {
            transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.18s ease, box-shadow 0.18s ease !important;
        }

        /* Prevent Streamlit from dimming the screen during re-runs */
        [data-stale="true"],
        .stApp [data-stale="true"],
        div[data-testid="stMain"] [data-stale="true"],
        div[data-testid="stSidebar"] [data-stale="true"],
        .element-container[data-stale="true"] {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
        }

        [data-testid="stAppViewContainer"] > .main {
            opacity: 1 !important;
            filter: none !important;
        }

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

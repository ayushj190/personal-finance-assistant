from pathlib import Path
import streamlit as st

from ui.theme.tokens import (
    COLOR_CASH,
    COLOR_DISCRETIONARY,
    COLOR_FIXED,
    COLOR_INCOME,
    COLOR_INVESTMENT,
    COLOR_LIABILITY,
    COLOR_PALETTE,
    COLOR_SAVINGS,
    COLOR_UNCATEGORIZED,
    SEMANTIC_FINANCIAL_COLORS,
    AMBER,
    EMERALD,
    INDIGO,
    LIME,
    PINK,
    ROSE,
    SKY,
    SLATE,
    TEAL,
    VIOLET,
    SPACE_XS,
    SPACE_SM,
    SPACE_MD,
    SPACE_LG,
    SPACE_XL,
    SPACE_2XL,
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    FONT_FAMILY_SANS,
    FONT_FAMILY_MONO,
    FONT_SIZE_XS,
    FONT_SIZE_SM,
    FONT_SIZE_BASE,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
    FONT_SIZE_2XL,
)
from ui.theme.charts import (
    FINANCIAL_COLOR_MAP,
    get_financial_color,
    hex_to_rgba,
    mask_chart_if_hidden,
    register_plotly_theme,
    render_chart,
)

THEME_DIR = Path(__file__).resolve().parent
COMMON_CSS_FILE = THEME_DIR / "common.css"
LIGHT_CSS_FILE = THEME_DIR / "light.css"
DARK_CSS_FILE = THEME_DIR / "dark.css"


def inject_custom_css() -> None:
    """Inject custom design system CSS based on current active theme."""
    current_theme = (
        st.session_state.get("theme", "dark")
        if hasattr(st, "session_state")
        else "dark"
    )

    theme_css = ""
    target_theme_file = LIGHT_CSS_FILE if current_theme == "light" else DARK_CSS_FILE
    if target_theme_file.exists():
        theme_css = target_theme_file.read_text(encoding="utf-8")

    common_css = ""
    if COMMON_CSS_FILE.exists():
        common_css = COMMON_CSS_FILE.read_text(encoding="utf-8")

    css = f"<style>\n{theme_css}\n{common_css}\n</style>"
    st.markdown(css, unsafe_allow_html=True)


__all__ = [
    "TEAL",
    "VIOLET",
    "AMBER",
    "ROSE",
    "SKY",
    "EMERALD",
    "SLATE",
    "PINK",
    "INDIGO",
    "LIME",
    "COLOR_PALETTE",
    "COLOR_INCOME",
    "COLOR_FIXED",
    "COLOR_DISCRETIONARY",
    "COLOR_SAVINGS",
    "COLOR_CASH",
    "COLOR_INVESTMENT",
    "COLOR_LIABILITY",
    "COLOR_UNCATEGORIZED",
    "SEMANTIC_FINANCIAL_COLORS",
    "SPACE_XS",
    "SPACE_SM",
    "SPACE_MD",
    "SPACE_LG",
    "SPACE_XL",
    "SPACE_2XL",
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
    "FONT_FAMILY_SANS",
    "FONT_FAMILY_MONO",
    "FONT_SIZE_XS",
    "FONT_SIZE_SM",
    "FONT_SIZE_BASE",
    "FONT_SIZE_LG",
    "FONT_SIZE_XL",
    "FONT_SIZE_2XL",
    "FINANCIAL_COLOR_MAP",
    "get_financial_color",
    "hex_to_rgba",
    "register_plotly_theme",
    "render_chart",
    "mask_chart_if_hidden",
    "inject_custom_css",
]

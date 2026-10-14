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

# Copilot sidebar drag range. Streamlit clamps its own resize handle at 600px
# (~41% of a 1446px window), so the handle is re-driven here to reach half the
# window. `SIDEBAR_RESIZE_BRIDGE_KEY` names the zero size component that carries
# the script, hidden by `common.css`.
SIDEBAR_MIN_WIDTH_PX = 260
SIDEBAR_MAX_WIDTH_RATIO = 0.5
SIDEBAR_WIDTH_STORAGE_KEY = "pfa_sidebar_width"
SIDEBAR_RESIZE_BRIDGE_KEY = "sidebar_resize_bridge"

_SIDEBAR_RESIZE_JS = """
<script>
  (function () {
    var MIN_PX = __MIN_PX__;
    var MAX_RATIO = __MAX_RATIO__;
    var STORAGE_KEY = "__STORAGE_KEY__";
    var doc = window.parent;
    var d = doc.document;
    var dragging = false;

    function sidebar() {
      return d.querySelector('[data-testid="stSidebar"]');
    }

    function clamp(px) {
      var widest = doc.innerWidth * MAX_RATIO;
      return Math.max(MIN_PX, Math.min(widest, px));
    }

    function apply(px) {
      var el = sidebar();
      if (!el) return;
      if (doc.innerWidth < 768) {
        el.style.removeProperty('width');
        el.style.removeProperty('max-width');
        el.style.removeProperty('min-width');
        return;
      }
      var width = clamp(px);
      el.style.setProperty('width', width + 'px', 'important');
      el.style.setProperty('max-width', (MAX_RATIO * 100) + 'vw', 'important');
      el.style.setProperty('min-width', MIN_PX + 'px', 'important');
    }

    function inHandle(target) {
      return !!(target && target.closest &&
        target.closest('[data-testid="stSidebarResizeHandle"]'));
    }

    function onDown(e) {
      if (!inHandle(e.target)) return;
      // Take the drag over from Streamlit so it does not snap back to its own ceiling.
      dragging = true;
      e.preventDefault();
      e.stopPropagation();
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      d.body.style.userSelect = 'none';
    }

    function onMove(e) {
      if (!dragging) return;
      e.preventDefault();
      apply(e.clientX);
    }

    function onUp() {
      if (!dragging) return;
      dragging = false;
      d.body.style.userSelect = '';
      var el = sidebar();
      if (!el) return;
      try {
        doc.localStorage.setItem(STORAGE_KEY, String(Math.round(el.getBoundingClientRect().width)));
      } catch (err) {}
    }

    d.addEventListener('pointerdown', onDown, true);
    d.addEventListener('mousedown', onDown, true);
    d.addEventListener('pointermove', onMove, true);
    d.addEventListener('mousemove', onMove, true);
    d.addEventListener('pointerup', onUp, true);
    d.addEventListener('mouseup', onUp, true);
    d.addEventListener('pointercancel', onUp, true);
    doc.addEventListener('blur', onUp);

    // Re-assert the remembered width when the window is resized back to a wide
    // layout (the narrow layout is left to Streamlit's own overlay sidebar).
    doc.addEventListener('resize', function () {
      var saved = null;
      try {
        saved = doc.localStorage.getItem(STORAGE_KEY);
      } catch (err) {}
      if (saved) apply(parseInt(saved, 10));
    });

    var attempts = 0;
    (function restore() {
      var saved = null;
      try {
        saved = doc.localStorage.getItem(STORAGE_KEY);
      } catch (err) {}
      if (saved) apply(parseInt(saved, 10));
      if (!sidebar() && ++attempts < 40) doc.setTimeout(restore, 250);
    })();
  })();
</script>
"""
_SIDEBAR_RESIZE_JS = (
    _SIDEBAR_RESIZE_JS
    .replace("__MIN_PX__", str(SIDEBAR_MIN_WIDTH_PX))
    .replace("__MAX_RATIO__", str(SIDEBAR_MAX_WIDTH_RATIO))
    .replace("__STORAGE_KEY__", SIDEBAR_WIDTH_STORAGE_KEY)
)


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


def script_iframe(html: str) -> None:
    """Run a browser script from an effectively zero size, same origin iframe.

    `st.iframe` is the current element (it rejects a height of 0, so 1px is the
    minimum and the bridge CSS hides it). `st.components.v1.html` is deprecated
    and logs a warning on every run, so it is only the fallback.
    """
    if hasattr(st, "iframe"):
        st.iframe(html, height=1)
        return
    import streamlit.components.v1 as components  # pragma: no cover - older Streamlit

    components.html(html, height=1)


def inject_sidebar_resize() -> None:
    """Let the Copilot sidebar be dragged out to half the window width.

    Streamlit's own handle stops at its frontend ceiling, so the drag is driven
    from a zero size bridge component and the width is remembered in the browser.
    """
    try:
        with st.container(key=SIDEBAR_RESIZE_BRIDGE_KEY):
            script_iframe(_SIDEBAR_RESIZE_JS)
    except Exception:
        pass


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
    "inject_sidebar_resize",
    "script_iframe",
]

import pathlib
import shutil
from typing import Any
import plotly
import plotly.graph_objects as go
import streamlit.components.v1 as components

COMPONENT_DIR = pathlib.Path(__file__).parent.resolve()

# Auto-copy plotly.min.js from installed plotly package if not already present
_dest_js = COMPONENT_DIR / "plotly.min.js"
if not _dest_js.exists():
    try:
        _src_js = pathlib.Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
        if _src_js.exists():
            shutil.copyfile(_src_js, _dest_js)
    except Exception:
        pass

_sankey_chart = components.declare_component(
    "interactive_sankey_chart",
    path=str(COMPONENT_DIR),
)


def render_interactive_sankey(
    fig: go.Figure,
    drilldown: str = "Full Flow",
    key: str = "interactive_sankey",
) -> dict[str, Any] | None:
    """Render interactive Sankey diagram that emits node click events back to Streamlit."""
    fig_json = fig.to_plotly_json() if hasattr(fig, "to_plotly_json") else fig
    return _sankey_chart(
        figure=fig_json,
        drilldown=drilldown,
        key=key,
        default=None,
    )

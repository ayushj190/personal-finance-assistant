from typing import Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_chart(df: pd.DataFrame, chart_spec: dict[str, Any] | None) -> go.Figure | None:
    if df.empty or not chart_spec:
        return None

    chart_type = chart_spec.get("type", "table")
    title = chart_spec.get("title", "")
    x = chart_spec.get("x")
    y = chart_spec.get("y")
    color = chart_spec.get("color")
    names = chart_spec.get("names")
    values = chart_spec.get("values")

    cols = set(df.columns)

    try:
        if chart_type == "bar":
            if x in cols and y in cols:
                color_col = color if color in cols else None
                fig = px.bar(df, x=x, y=y, color=color_col, title=title, template="pfa_theme")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                return fig
        elif chart_type == "line":
            if x in cols and y in cols:
                color_col = color if color in cols else None
                fig = px.line(df, x=x, y=y, color=color_col, title=title, markers=True, template="pfa_theme")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                return fig
        elif chart_type == "area":
            if x in cols and y in cols:
                color_col = color if color in cols else None
                fig = px.area(df, x=x, y=y, color=color_col, title=title, template="pfa_theme")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                return fig
        elif chart_type == "pie":
            name_col = names or x
            val_col = values or y
            if name_col in cols and val_col in cols:
                fig = px.pie(df, names=name_col, values=val_col, title=title, hole=0.4, template="pfa_theme")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                return fig
    except Exception:
        pass

    return None

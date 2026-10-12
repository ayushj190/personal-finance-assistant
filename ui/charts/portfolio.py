import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ui import state
from ui.components import is_hidden
from ui.theme import mask_chart_if_hidden
from ui.charts.common import SECTOR_RGBA_COLORS


def wrap_treemap_label(text: str, max_chars: int = 14) -> str:
    """Wrap category/asset labels with <br> for multi-line treemap rendering."""
    if not text or len(text) <= max_chars or "<br>" in text:
        return text
    words = text.split()
    if len(words) <= 1:
        return text
    lines: list[str] = []
    current_line: list[str] = []
    current_len = 0
    for w in words:
        if current_line and (current_len + len(w) + 1 > max_chars):
            lines.append(" ".join(current_line))
            current_line = [w]
            current_len = len(w)
        else:
            current_line.append(w)
            current_len += len(w) + (1 if len(current_line) > 1 else 0)
    if current_line:
        lines.append(" ".join(current_line))
    return "<br>".join(lines)


def clean_treemap_tile_label(display_label: str, ticker: str = "") -> str:
    """Produce a concise, recognizable tile name for treemaps so names fit neatly without clipping."""
    if not display_label or pd.isna(display_label):
        return str(ticker).strip() if ticker and not pd.isna(ticker) else "Asset"

    text = str(display_label).strip()
    tick = str(ticker).strip() if ticker and not pd.isna(ticker) else ""

    if len(text) <= 12 and "<br>" not in text:
        return text

    cleaned = re.sub(
        r"\s+(?:UCITS\s+ETF|UCITS|ETF|ETC|Acc|Dist|\(Acc\)|\(Dist\)|USD\s+Hedged|Hedged)\b",
        "",
        text,
        flags=re.I,
    )
    cleaned = re.sub(
        r"^(?:SS\s+SPDR|SPDR|iShares\s+VII\s+PLC\s+-\s+iShares|iShares\s+Core|iShares\s+Edge|iShares)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"[\s,]+(?:Inc\.?|Corp\.?|Corporation|Ltd\.?|Group\s+plc|plc|AG|NV|SA|S/A|SE|Co\.?|Holdings?)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s*-\s*(?:ADR|SPONS\s+ADR)\b", "", cleaned, flags=re.I).rstrip(" .,-")

    if not cleaned:
        return tick if tick else text

    if len(cleaned) > 18 and tick and not tick.startswith(("ID_", "COPY:")) and len(tick) <= 8:
        return tick

    return cleaned


def build_investments_market_carpet(
    consolidated_df: pd.DataFrame,
    height: int = 350,
) -> go.Figure:
    """Build a market carpet (treemap heatmap) of investment sector and theme exposures with translucent glassmorphic tiles."""
    if consolidated_df.empty:
        return go.Figure()

    df = consolidated_df.copy()
    if "sector" not in df.columns:
        df["sector"] = "Other"
    df["sector"] = df["sector"].fillna("Other")

    if "display_label" not in df.columns:
        df["display_label"] = df.get("name", df.get("ticker", "Asset"))
    df["display_label"] = df["display_label"].fillna("Asset")

    ticker_series = df["ticker"] if "ticker" in df.columns else pd.Series([""] * len(df), index=df.index)
    df["display_label_cleaned"] = [
        clean_treemap_tile_label(str(label), str(tick))
        for label, tick in zip(df["display_label"], ticker_series)
    ]

    df["sector_wrapped"] = df["sector"].map(lambda s: wrap_treemap_label(str(s), 14))
    df["display_label_wrapped"] = df["display_label_cleaned"].map(lambda l: wrap_treemap_label(str(l), 14))

    grouped = (
        df.groupby(["sector_wrapped", "display_label_wrapped"], as_index=False)["value_eur"]
        .sum()
        .sort_values(by="value_eur", ascending=False)
    )
    grouped = grouped[grouped["value_eur"] > 0]
    if grouped.empty:
        return go.Figure()

    color_map = {**SECTOR_RGBA_COLORS}
    for k, v in SECTOR_RGBA_COLORS.items():
        color_map[wrap_treemap_label(k, 14)] = v

    fig = px.treemap(
        grouped,
        path=["sector_wrapped", "display_label_wrapped"],
        values="value_eur",
        color="sector_wrapped",
        color_discrete_map=color_map,
    )

    marker_line = dict(width=2, color="rgba(255, 255, 255, 0.28)")
    font_spec = dict(size=12, family="Inter, -apple-system, sans-serif", color="#ffffff")
    header_pad = dict(t=26, l=4, r=4, b=4)
    if is_hidden():
        fig.update_traces(
            textinfo="label",
            texttemplate="<b>%{label}</b><br>€****",
            textfont=font_spec,
            insidetextfont=font_spec,
            outsidetextfont=font_spec,
            hovertemplate="Censored<extra></extra>",
            marker=dict(cornerradius=8, line=marker_line, pad=header_pad),
            tiling=dict(pad=6, packing="squarify"),
            opacity=0.85,
        )
    else:
        fig.update_traces(
            textinfo="label+value",
            texttemplate="<b>%{label}</b><br>€%{value:,.0f}",
            textfont=font_spec,
            insidetextfont=font_spec,
            outsidetextfont=font_spec,
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Sector / Theme: %{parent}<br>"
                "Value: €%{value:,.2f}<br>"
                "Weight: %{percentRoot:.1%}<extra></extra>"
            ),
            marker=dict(cornerradius=8, line=marker_line, pad=header_pad),
            tiling=dict(pad=6, packing="squarify"),
            opacity=0.85,
        )

    current_theme = state.get(state.K.THEME, "dark")
    if current_theme == "light":
        hoverlabel_cfg = dict(
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="rgba(148, 163, 184, 0.4)",
            font=dict(family="Inter, -apple-system, sans-serif", size=12, color="#0f172a"),
        )
    else:
        hoverlabel_cfg = dict(
            bgcolor="rgba(16, 28, 21, 0.95)",
            bordercolor="rgba(45, 212, 191, 0.4)",
            font=dict(family="Inter, -apple-system, sans-serif", size=12, color="#ecfdf5"),
        )

    fig.update_layout(
        height=height,
        margin=dict(t=25, l=10, r=10, b=15),
        showlegend=False,
        font=dict(color="#ffffff", family="Inter, -apple-system, sans-serif"),
        uniformtext=dict(minsize=10, mode=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        transition=dict(duration=450, easing="cubic-in-out"),
        hoverlabel=hoverlabel_cfg,
    )
    mask_chart_if_hidden(fig)
    return fig

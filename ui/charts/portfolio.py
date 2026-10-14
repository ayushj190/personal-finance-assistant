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
    group_col: str = "sector",
    height: int = 350,
) -> go.Figure:
    """Build a market carpet (treemap heatmap) of investment exposures grouped by dimension (AC-6, AC-15)."""
    if consolidated_df.empty:
        return go.Figure()

    col = str(group_col or "sector").lower().strip()
    if col in ("nature", "asset_nature", "commodities"):
        col = "nature"
    elif col in ("region", "country", "geography"):
        col = "region"
    elif col in ("currency", "currencies"):
        col = "currency"
    else:
        col = "sector"

    df = consolidated_df.copy()
    if col not in df.columns:
        df[col] = "Other"
    df[col] = df[col].fillna("Other")

    if "display_label" not in df.columns:
        df["display_label"] = df.get("name", df.get("ticker", "Asset"))
    df["display_label"] = df["display_label"].fillna("Asset")

    ticker_series = df["ticker"] if "ticker" in df.columns else pd.Series([""] * len(df), index=df.index)
    df["display_label_cleaned"] = [
        clean_treemap_tile_label(str(label), str(tick))
        for label, tick in zip(df["display_label"], ticker_series)
    ]

    group_wrapped_col = f"{col}_wrapped"
    df[group_wrapped_col] = df[col].map(lambda s: wrap_treemap_label(str(s), 14))
    df["display_label_wrapped"] = df["display_label_cleaned"].map(lambda l: wrap_treemap_label(str(l), 14))

    grouped = (
        df.groupby([group_wrapped_col, "display_label_wrapped"], as_index=False)["value_eur"]
        .sum()
        .sort_values(by="value_eur", ascending=False)
    )
    grouped = grouped[grouped["value_eur"] > 0]
    if grouped.empty:
        return go.Figure()

    color_map = None
    if col == "sector":
        color_map = {**SECTOR_RGBA_COLORS}
        for k, v in SECTOR_RGBA_COLORS.items():
            color_map[wrap_treemap_label(k, 14)] = v

    fig = px.treemap(
        grouped,
        path=[group_wrapped_col, "display_label_wrapped"],
        values="value_eur",
        color=group_wrapped_col,
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
        dim_title = col.title()
        fig.update_traces(
            textinfo="label+value",
            texttemplate="<b>%{label}</b><br>€%{value:,.0f}",
            textfont=font_spec,
            insidetextfont=font_spec,
            outsidetextfont=font_spec,
            hovertemplate=(
                "<b>%{label}</b><br>"
                f"{dim_title}: %{{parent}}<br>"
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


def build_equity_curve(
    snapshot_rows: list[dict[str, Any]],
    range_filter: str = "3M",
    height: int = 320,
) -> go.Figure:
    """Build the portfolio equity curve: value line with stepped cost basis line (AC-9).

    If snapshot_rows is empty, displays an honest empty state stating history builds from today.
    """
    if not snapshot_rows:
        fig = go.Figure()
        fig.add_annotation(
            text="Portfolio history builds from today onwards as daily snapshots accumulate.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color="#94a3b8"),
        )
        fig.update_layout(
            height=height,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, l=20, r=20, b=20),
        )
        return fig

    from datetime import date, timedelta
    df = pd.DataFrame(snapshot_rows)
    if "snapshot_date" not in df.columns or df.empty:
        return go.Figure()

    # Filter date range
    today = date.today()
    days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    if range_filter in days_map:
        cutoff = (today - timedelta(days=days_map[range_filter])).isoformat()
        df = df[df["snapshot_date"] >= cutoff]

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text=f"No snapshots recorded in the selected {range_filter} range.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color="#94a3b8"),
        )
        fig.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig

    df = df.sort_values(by="snapshot_date")
    fig = go.Figure()

    hidden = is_hidden()
    val_hover = "Censored<extra></extra>" if hidden else "%{x}<br>Portfolio Value: €%{y:,.2f}<extra></extra>"
    cost_hover = "Censored<extra></extra>" if hidden else "%{x}<br>Cost Basis: €%{y:,.2f}<extra></extra>"

    # Cost basis stepped line
    fig.add_trace(
        go.Scatter(
            x=df["snapshot_date"],
            y=df["cost_basis_eur"],
            mode="lines",
            name="Cost Basis",
            line=dict(shape="hv", color="#94a3b8", width=1.5, dash="dot"),
            hovertemplate=cost_hover,
        )
    )

    # Portfolio Value line
    fig.add_trace(
        go.Scatter(
            x=df["snapshot_date"],
            y=df["market_value_eur"],
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color="#10b981", width=2.5),
            marker=dict(size=4, color="#10b981"),
            hovertemplate=val_hover,
        )
    )

    fig.update_layout(
        height=height,
        margin=dict(t=25, l=45, r=15, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="", showgrid=True, gridcolor="rgba(148, 163, 184, 0.1)"),
        yaxis=dict(title="", showgrid=True, gridcolor="rgba(148, 163, 184, 0.1)", tickprefix="€"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color="#e2e8f0"),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_sector_performance_heat(
    live_rows_df: pd.DataFrame,
    height: int = 240,
) -> go.Figure:
    """Build sector performance heatmap/bars coloured by weighted day move (AC-11)."""
    if live_rows_df.empty or "sector" not in live_rows_df.columns:
        return go.Figure()

    is_p = live_rows_df["is_priced"] if "is_priced" in live_rows_df.columns else pd.Series([True] * len(live_rows_df))
    priced = live_rows_df[is_p & (live_rows_df["day_change_pct"].notna())].copy()
    if priced.empty:
        return go.Figure()

    sector_moves = []
    for sec, group in priced.groupby("sector"):
        total_w = float(group["weight_pct"].sum() or 0.0)
        if total_w > 0:
            weighted_move = float((group["day_change_pct"] * group["weight_pct"]).sum()) / total_w
        else:
            weighted_move = float(group["day_change_pct"].mean() or 0.0)
        sec_val = float(group["value_eur"].sum() or 0.0)
        sector_moves.append({
            "sector": sec,
            "weighted_move_pct": weighted_move,
            "value_eur": sec_val,
        })

    sdf = pd.DataFrame(sector_moves).sort_values(by="weighted_move_pct", ascending=True)
    if sdf.empty:
        return go.Figure()

    colors = ["#10b981" if m >= 0 else "#ef4444" for m in sdf["weighted_move_pct"]]
    text_labels = [f"{m:+.2f}%" for m in sdf["weighted_move_pct"]]

    fig = go.Figure(
        go.Bar(
            x=sdf["weighted_move_pct"],
            y=sdf["sector"],
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=text_labels,
            textposition="auto",
            hovertemplate="<b>%{y}</b><br>Weighted Move: %{x:+.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=height,
        margin=dict(t=20, l=110, r=20, b=25),
        xaxis=dict(title="Weighted Move (%)", zeroline=True, zerolinecolor="rgba(148, 163, 184, 0.4)"),
        yaxis=dict(title=""),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color="#e2e8f0"),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_pnl_contribution_chart(
    live_rows_df: pd.DataFrame,
    height: int = 320,
) -> go.Figure:
    """Build ranked P&L contribution bar chart of each holding's unrealized profit or loss (AC-11)."""
    if live_rows_df.empty or "unrealized_pnl_eur" not in live_rows_df.columns:
        return go.Figure()

    df = live_rows_df.sort_values(by="unrealized_pnl_eur", ascending=True).copy()
    if df.empty:
        return go.Figure()

    colors = ["#10b981" if v >= 0 else "#ef4444" for v in df["unrealized_pnl_eur"]]
    hidden = is_hidden()

    if hidden:
        text_labels = ["€****" for _ in df["unrealized_pnl_eur"]]
        hover = "Censored<extra></extra>"
    else:
        text_labels = [f"{'+' if v >= 0 else ''}€{v:,.0f}" for v in df["unrealized_pnl_eur"]]
        hover = "<b>%{y}</b><br>Unrealized P&L: €%{x:,.2f}<extra></extra>"

    labels = df["name_with_ticker"] if "name_with_ticker" in df.columns else df["ticker"]
    fig = go.Figure(
        go.Bar(
            x=df["unrealized_pnl_eur"],
            y=labels,
            orientation="h",
            marker=dict(color=colors, cornerradius=4),
            text=text_labels,
            textposition="auto",
            hovertemplate=hover,
        )
    )
    fig.update_layout(
        height=max(height, min(600, len(df) * 28)),
        margin=dict(t=20, l=140, r=30, b=25),
        xaxis=dict(title="Unrealized P&L (€)", zeroline=True, zerolinecolor="rgba(148, 163, 184, 0.4)"),
        yaxis=dict(title="", automargin=True),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, sans-serif", color="#e2e8f0"),
    )
    mask_chart_if_hidden(fig)
    return fig


import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ui.theme import (
    COLOR_PALETTE,
    COLOR_FIXED,
    COLOR_DISCRETIONARY,
    COLOR_UNCATEGORIZED,
    mask_chart_if_hidden,
)


def build_spending_donut(df: pd.DataFrame, drilldown_category: str | None = None) -> go.Figure:
    if df.empty:
        return go.Figure()

    cat_col = "parent_category" if "parent_category" in df.columns else "category"

    if drilldown_category:
        filtered_df = df[df[cat_col] == drilldown_category]
        if filtered_df.empty and "category" in df.columns:
            filtered_df = df[df["category"] == drilldown_category]

        if not filtered_df.empty and "category" in filtered_df.columns and filtered_df["category"].nunique() > 1:
            df_grouped = filtered_df.groupby("category", as_index=False)["amount_eur"].sum()
            names_col = "category"
        else:
            df_grouped = filtered_df.groupby("merchant", as_index=False)["amount_eur"].sum()
            names_col = "merchant"
    else:
        df_grouped = df.groupby(cat_col, as_index=False)["amount_eur"].sum()
        names_col = cat_col

    pull_values = [0.02] * len(df_grouped)

    # With many slices the inside labels crowd each other (spec 0016 nit), so the
    # names move to the legend and the slices keep only the percentage.
    crowded = len(df_grouped) > 6
    show_labels = not drilldown_category and not crowded

    fig = px.pie(
        df_grouped,
        names=names_col,
        values="amount_eur",
        hole=0.55,
        color_discrete_sequence=COLOR_PALETTE,
    )

    fig.update_traces(
        textinfo="percent+label" if show_labels else "percent",
        textposition="inside",
        pull=pull_values,
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Spent: €%{value:,.2f}<br>"
            "Share: %{percent}<extra></extra>"
        ),
        marker=dict(line=dict(color="#0F172A", width=2)),
    )

    fig.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=25, b=25),
        showlegend=bool(drilldown_category) or crowded,
        transition=dict(duration=500, easing="cubic-in-out"),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_monthly_spending_bar(monthly_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if monthly_df.empty:
        return fig

    df_sorted = monthly_df.sort_values(by="month", ascending=True)
    months = df_sorted["month"].tolist()

    fig.add_trace(
        go.Bar(
            x=months,
            y=df_sorted["fixed_spent"].tolist(),
            name="Fixed",
            marker_color=COLOR_FIXED,
        )
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=df_sorted["disc_spent"].tolist(),
            name="Discretionary",
            marker_color=COLOR_DISCRETIONARY,
        )
    )
    if "uncat_spent" in df_sorted.columns and df_sorted["uncat_spent"].sum() > 0:
        fig.add_trace(
            go.Bar(
                x=months,
                y=df_sorted["uncat_spent"].tolist(),
                name="Uncategorized",
                marker_color=COLOR_UNCATEGORIZED,
            )
        )

    fig.update_layout(
        height=350,
        barmode="stack",
        hovermode="x unified",
        margin=dict(l=55, r=20, t=25, b=25),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
        yaxis=dict(
            title="Expenses (€)",
            tickprefix="€",
            tickformat="~s",
            automargin=True,
        ),
        xaxis=dict(title="Month", automargin=True),
    )
    mask_chart_if_hidden(fig)
    return fig

from typing import Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    COLOR_PALETTE,
    COLOR_INCOME,
    COLOR_FIXED,
    COLOR_DISCRETIONARY,
    COLOR_SAVINGS,
    COLOR_CASH,
    COLOR_INVESTMENT,
    COLOR_LIABILITY,
    COLOR_UNCATEGORIZED,
)


def build_net_worth_area_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig

    # Group by date and asset_class
    pivoted = df.pivot_table(
        index="date", columns="asset_class", values="value_eur", aggfunc="sum").fillna(0)

    dates = pivoted.index.tolist()
    cash = pivoted.get("cash", pd.Series(0, index=dates)).tolist()
    investments = pivoted.get("investment", pd.Series(0, index=dates)).tolist()
    liabilities = pivoted.get("liability", pd.Series(0, index=dates)).tolist()

    net_worth = [c + i - abs(l)
                 for c, i, l in zip(cash, investments, liabilities)]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cash,
            mode="lines",
            name="Cash",
            stackgroup="positive",
            line=dict(width=0.5, color=COLOR_CASH),
            fillcolor="rgba(45, 212, 191, 0.4)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=investments,
            mode="lines",
            name="Investments",
            stackgroup="positive",
            line=dict(width=0.5, color=COLOR_INVESTMENT),
            fillcolor="rgba(56, 189, 248, 0.4)",
        )
    )
    if any(l > 0 for l in liabilities):
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=[-abs(l) for l in liabilities],
                mode="lines",
                name="Liabilities",
                line=dict(width=1, color=COLOR_LIABILITY, dash="dash"),
                fillcolor="rgba(251, 113, 133, 0.2)",
            )
        )

    current_theme = st.session_state.get(
        "theme", "dark") if hasattr(st, "session_state") else "dark"
    nw_color = "#0F172A" if current_theme == "light" else "#F8FAFC"

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=net_worth,
            mode="lines+markers",
            name="Net Worth",
            line=dict(width=3, color=nw_color),
            marker=dict(size=5),
        )
    )

    fig.update_layout(
        height=350,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1),
    )
    return fig




def build_spending_donut(df: pd.DataFrame, drilldown_category: str | None = None) -> go.Figure:
    if df.empty:
        return go.Figure()

    if drilldown_category:
        filtered_df = df[df["category"] == drilldown_category]
        df_grouped = filtered_df.groupby("merchant", as_index=False)["amount_eur"].sum()
        names_col = "merchant"
    else:
        df_grouped = df.groupby("category", as_index=False)["amount_eur"].sum()
        names_col = "category"

    pull_values = [0.02] * len(df_grouped)

    fig = px.pie(
        df_grouped,
        names=names_col,
        values="amount_eur",
        hole=0.55,
        color_discrete_sequence=COLOR_PALETTE
    )
    
    fig.update_traces(
        textinfo="percent+label" if not drilldown_category else "percent",
        textposition="inside",
        pull=pull_values,
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Spent: €%{value:,.2f}<br>"
            "Share: %{percent}<extra></extra>"
        ),
        marker=dict(line=dict(color='#0F172A', width=2))
    )
    
    fig.update_layout(
        height=350, 
        margin=dict(l=10, r=10, t=20, b=20),
        showlegend=True if drilldown_category else False,
        transition=dict(duration=500, easing="cubic-in-out")
    )
    return fig


def build_drift_bar_chart(drift_data: list[dict[str, Any]], drift_band_pct: float = 5.0) -> go.Figure:
    fig = go.Figure()
    if not drift_data:
        return fig

    buckets = [d["bucket"] for d in drift_data]
    actuals = [d["actual_pct"] for d in drift_data]
    targets = [d["target_pct"] for d in drift_data]

    fig.add_trace(go.Bar(x=buckets, y=actuals, name="Current %", marker_color=COLOR_INVESTMENT, text=[f"{a:.1f}%" for a in actuals], textposition="auto"))
    fig.add_trace(go.Bar(x=buckets, y=targets, name="Target %", marker_color=COLOR_SAVINGS, text=[f"{t:.1f}%" for t in targets], textposition="auto"))

    fig.update_layout(
        height=350,
        barmode='group',
        yaxis_title="Allocation (%)",
        margin=dict(l=10, r=10, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def build_mortgage_amortization_chart(schedule_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if schedule_df.empty:
        return fig

    dates = schedule_df["due_date"].tolist()
    balance = (schedule_df["balance_minor"] / 100.0).tolist()
    cum_principal = (schedule_df["principal_minor"].cumsum() / 100.0).tolist()

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=balance,
            mode="lines",
            name="Remaining Balance",
            line=dict(color=COLOR_LIABILITY, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(251, 113, 133, 0.15)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cum_principal,
            mode="lines",
            name="Cumulative Principal Paid",
            line=dict(color=COLOR_INCOME, width=2.5),
        )
    )

    fig.update_layout(
        height=350,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1),
    )
    return fig


def build_mortgage_interest_principal_bar(schedule_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if schedule_df.empty:
        return fig

    dates = schedule_df["due_date"].tolist()
    interest = (schedule_df["interest_minor"] / 100.0).tolist()
    principal = (schedule_df["principal_minor"] / 100.0).tolist()

    fig.add_trace(go.Bar(x=dates, y=principal,
                  name="Principal", marker_color=COLOR_SAVINGS))
    fig.add_trace(go.Bar(x=dates, y=interest, name="Interest",
                  marker_color=COLOR_LIABILITY))

    fig.update_layout(
        height=350,
        barmode="stack",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1),
    )
    return fig


def build_monthly_spending_bar(monthly_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if monthly_df.empty:
        return fig

    df_sorted = monthly_df.sort_values(by="month", ascending=True)
    months = df_sorted["month"].tolist()

    fig.add_trace(go.Bar(x=months, y=df_sorted["fixed_spent"].tolist(
    ), name="Fixed", marker_color=COLOR_FIXED))
    fig.add_trace(go.Bar(x=months, y=df_sorted["disc_spent"].tolist(
    ), name="Discretionary", marker_color=COLOR_DISCRETIONARY))
    if "uncat_spent" in df_sorted.columns and df_sorted["uncat_spent"].sum() > 0:
        fig.add_trace(go.Bar(x=months, y=df_sorted["uncat_spent"].tolist(
        ), name="Uncategorized", marker_color=COLOR_UNCATEGORIZED))

    fig.update_layout(
        height=350,
        barmode="stack",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Expenses (€)"),
        xaxis=dict(title="Month"),
    )
    return fig

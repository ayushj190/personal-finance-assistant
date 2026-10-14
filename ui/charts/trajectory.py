from typing import Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.money import Money
from ui.theme import (
    COLOR_CASH,
    COLOR_INVESTMENT,
    COLOR_LIABILITY,
    COLOR_SAVINGS,
    COLOR_INCOME,
    hex_to_rgba,
    mask_chart_if_hidden,
)
from ui import state


def build_net_worth_area_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return fig

    # Group by date and asset_class
    pivoted = df.pivot_table(
        index="date", columns="asset_class", values="value_eur", aggfunc="sum"
    ).fillna(0)

    dates = pivoted.index.tolist()
    cash = pivoted.get("cash", pd.Series(0, index=dates)).tolist()
    investments = pivoted.get("investment", pd.Series(0, index=dates)).tolist()
    liabilities = pivoted.get("liability", pd.Series(0, index=dates)).tolist()

    net_worth = [c + i - abs(l) for c, i, l in zip(cash, investments, liabilities)]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=cash,
            mode="lines",
            name="Cash",
            stackgroup="positive",
            line=dict(width=0.5, color=COLOR_CASH),
            fillcolor=hex_to_rgba(COLOR_CASH, 0.4),
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
            fillcolor=hex_to_rgba(COLOR_INVESTMENT, 0.4),
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
                fillcolor=hex_to_rgba(COLOR_LIABILITY, 0.2),
            )
        )

    current_theme = state.get(state.K.THEME, "dark")
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
        margin=dict(l=55, r=20, t=25, b=25),
        yaxis=dict(
            title="Net Worth (€)",
            tickprefix="€",
            tickformat="~s",
            automargin=True,
        ),
        xaxis=dict(automargin=True),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_drift_bar_chart(drift_data: list[dict[str, Any]], drift_band_pct: float = 5.0) -> go.Figure:
    fig = go.Figure()
    if not drift_data:
        return fig

    buckets = [d["bucket"] for d in drift_data]
    actuals = [d["actual_pct"] for d in drift_data]
    targets = [d["target_pct"] for d in drift_data]

    fig.add_trace(
        go.Bar(
            x=buckets,
            y=actuals,
            name="Current %",
            marker_color=COLOR_INVESTMENT,
            text=[f"{a:.1f}%" for a in actuals],
            textposition="auto",
        )
    )
    fig.add_trace(
        go.Bar(
            x=buckets,
            y=targets,
            name="Target %",
            marker_color=COLOR_SAVINGS,
            text=[f"{t:.1f}%" for t in targets],
            textposition="auto",
        )
    )

    fig.update_layout(
        height=350,
        barmode="group",
        margin=dict(l=55, r=20, t=25, b=25),
        yaxis=dict(
            title="Allocation (%)",
            ticksuffix="%",
            automargin=True,
        ),
        xaxis=dict(automargin=True),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_mortgage_amortization_chart(schedule_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if schedule_df.empty:
        return fig

    dates = schedule_df["due_date"].tolist()
    balance = [Money.from_cents(m).to_major() for m in schedule_df["balance_minor"]]
    cum_principal = [Money.from_cents(m).to_major() for m in schedule_df["principal_minor"].cumsum()]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=balance,
            mode="lines",
            name="Remaining Balance",
            line=dict(color=COLOR_LIABILITY, width=2.5),
            fill="tozeroy",
            fillcolor=hex_to_rgba(COLOR_LIABILITY, 0.15),
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
        margin=dict(l=55, r=20, t=25, b=25),
        yaxis=dict(
            title="Amount (€)",
            tickprefix="€",
            tickformat="~s",
            automargin=True,
        ),
        xaxis=dict(automargin=True),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    mask_chart_if_hidden(fig)
    return fig


def build_mortgage_interest_principal_bar(schedule_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if schedule_df.empty:
        return fig

    dates = schedule_df["due_date"].tolist()
    interest = [Money.from_cents(m).to_major() for m in schedule_df["interest_minor"]]
    principal = [Money.from_cents(m).to_major() for m in schedule_df["principal_minor"]]

    fig.add_trace(
        go.Bar(x=dates, y=principal, name="Principal", marker_color=COLOR_SAVINGS)
    )
    fig.add_trace(
        go.Bar(x=dates, y=interest, name="Interest", marker_color=COLOR_LIABILITY)
    )

    fig.update_layout(
        height=350,
        barmode="stack",
        hovermode="x unified",
        margin=dict(l=55, r=20, t=25, b=25),
        yaxis=dict(
            title="Monthly Payment (€)",
            tickprefix="€",
            tickformat="~s",
            automargin=True,
        ),
        xaxis=dict(automargin=True),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
    )
    mask_chart_if_hidden(fig)
    return fig

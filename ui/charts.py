import sqlite3
from typing import Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.pages.tax import calculate_box1_tax
from ui.components import is_hidden
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
    hex_to_rgba,
    render_chart,
)


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

    current_theme = (
        st.session_state.get("theme", "dark")
        if hasattr(st, "session_state")
        else "dark"
    )
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
    return fig


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

    fig = px.pie(
        df_grouped,
        names=names_col,
        values="amount_eur",
        hole=0.55,
        color_discrete_sequence=COLOR_PALETTE,
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
        marker=dict(line=dict(color="#0F172A", width=2)),
    )

    fig.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=25, b=25),
        showlegend=True if drilldown_category else False,
        transition=dict(duration=500, easing="cubic-in-out"),
    )
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
    return fig


def build_mortgage_interest_principal_bar(schedule_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if schedule_df.empty:
        return fig

    dates = schedule_df["due_date"].tolist()
    interest = (schedule_df["interest_minor"] / 100.0).tolist()
    principal = (schedule_df["principal_minor"] / 100.0).tolist()

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
    return fig


# ── Interactive Non-Crossing Cash Flow Sankey ──────────────────────────


def prepare_cash_flow_sankey_data(
    conn: sqlite3.Connection,
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    display_df: pd.DataFrame | None = None,
    salary_day: int = 25,
) -> dict[str, Any]:
    """Extract and calculate income, tax, expense buckets, and category breakdowns for Sankey flow."""
    # 1. Income & Savings cash flow query
    if start_date and end_date:
        date_cond = "t.booking_date >= ? AND t.booking_date <= ?"
        params: tuple[Any, ...] = (start_date, end_date)
    else:
        date_cond = f"t.booking_date >= date('now', '-{days} days')"
        params = ()

    cf_row = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 as inc,
            SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as sav
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.is_internal_transfer = 0
          AND {date_cond}
        """,
        params,
    ).fetchone()

    inc = float(cf_row["inc"] or 0.0) if cf_row else 0.0
    sav = float(cf_row["sav"] or 0.0) if cf_row else 0.0

    # 2. Estimate gross salary & taxes from tax profile or transactions
    profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
    annual_gross = (
        float(profile["gross_annual_income"])
        if profile and profile["gross_annual_income"]
        else 0.0
    )
    eff_tax_rate = 0.3697
    if annual_gross > 0:
        b1 = calculate_box1_tax(annual_gross)
        if b1.get("total_tax", 0) > 0:
            eff_tax_rate = min(0.52, max(0.18, b1["total_tax"] / annual_gross))

    if inc > 0:
        gross_salary = inc / (1.0 - eff_tax_rate)
        taxes = gross_salary - inc
        net_salary = inc
    elif annual_gross > 0:
        factor = (days / 365.0) if not (start_date and end_date) else 1.0 / 12.0
        gross_salary = annual_gross * factor
        taxes = gross_salary * eff_tax_rate
        net_salary = gross_salary - taxes
    else:
        gross_salary = 0.0
        taxes = 0.0
        net_salary = 0.0

    # 3. Itemized category expenses from transactions
    if display_df is not None and not display_df.empty:
        fixed_df = display_df[display_df.get("is_fixed", False)] if "is_fixed" in display_df.columns else pd.DataFrame()
        disc_df = display_df[display_df.get("is_disc", False)] if "is_disc" in display_df.columns else pd.DataFrame()
        uncat_df = display_df[display_df.get("is_uncat", False)] if "is_uncat" in display_df.columns else pd.DataFrame()

        fixed_spent = float(fixed_df["amount_eur"].sum()) if not fixed_df.empty else 0.0
        disc_spent = float(disc_df["amount_eur"].sum()) if not disc_df.empty else 0.0
        uncat_spent = float(uncat_df["amount_eur"].sum()) if not uncat_df.empty else 0.0

        fixed_cats = fixed_df.groupby("parent_category")["amount_eur"].sum().to_dict() if not fixed_df.empty else {}
        disc_cats = disc_df.groupby("parent_category")["amount_eur"].sum().to_dict() if not disc_df.empty else {}
    else:
        # Fetch directly from DB
        spend_rows = conn.execute(
            f"""
            SELECT
                COALESCE(p.name, c.name, 'Uncategorized') as parent_cat,
                COALESCE(c.kind, 'discretionary') as cat_kind,
                SUM(-t.amount_eur_minor) / 100.0 as spent_eur
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN categories p ON p.id = c.parent_id
            WHERE t.is_internal_transfer = 0
              AND t.amount_eur_minor < 0
              AND {date_cond}
            GROUP BY parent_cat, cat_kind
            ORDER BY spent_eur DESC
            """,
            params,
        ).fetchall()

        fixed_spent = 0.0
        disc_spent = 0.0
        uncat_spent = 0.0
        fixed_cats = {}
        disc_cats = {}

        for r in spend_rows:
            p_cat = r["parent_cat"]
            k = r["cat_kind"]
            amt = float(r["spent_eur"] or 0.0)
            if p_cat == "Uncategorized" or k not in ("fixed", "discretionary", "savings"):
                uncat_spent += amt
            elif k == "fixed":
                fixed_spent += amt
                fixed_cats[p_cat] = fixed_cats.get(p_cat, 0.0) + amt
            elif k == "discretionary":
                disc_spent += amt
                disc_cats[p_cat] = disc_cats.get(p_cat, 0.0) + amt

    total_out = fixed_spent + disc_spent + sav + uncat_spent
    if gross_salary == 0.0 and total_out > 0:
        gross_salary = total_out
        net_salary = total_out

    drawdown = max(0.0, total_out - net_salary)
    unallocated = max(0.0, net_salary - total_out)

    return {
        "gross_salary": gross_salary,
        "taxes": taxes,
        "net_salary": net_salary,
        "drawdown": drawdown,
        "fixed_spent": fixed_spent,
        "disc_spent": disc_spent,
        "sav": sav,
        "uncat_spent": uncat_spent,
        "unallocated": unallocated,
        "fixed_cats": {k: round(v, 2) for k, v in sorted(fixed_cats.items(), key=lambda x: -x[1]) if v > 0.01},
        "disc_cats": {k: round(v, 2) for k, v in sorted(disc_cats.items(), key=lambda x: -x[1]) if v > 0.01},
    }


def build_cash_flow_sankey(
    data: dict[str, Any],
    drilldown_flow: str = "Full Flow",
) -> go.Figure:
    """Build a non-crossing, drill-down enabled Sankey diagram."""
    gross_salary = float(data.get("gross_salary", 0.0))
    taxes = float(data.get("taxes", 0.0))
    net_salary = float(data.get("net_salary", 0.0))
    drawdown = float(data.get("drawdown", 0.0))
    fixed_spent = float(data.get("fixed_spent", 0.0))
    disc_spent = float(data.get("disc_spent", 0.0))
    sav = float(data.get("sav", 0.0))
    uncat_spent = float(data.get("uncat_spent", 0.0))
    unallocated = float(data.get("unallocated", 0.0))
    fixed_cats = data.get("fixed_cats", {})
    disc_cats = data.get("disc_cats", {})

    labels: list[str] = []
    colors: list[str] = []
    x_coords: list[float] = []
    y_coords: list[float] = []
    node_idx: dict[str, int] = {}

    def add_node(name: str, color: str, x: float, y: float) -> int:
        if name not in node_idx:
            idx = len(labels)
            node_idx[name] = idx
            labels.append(name)
            colors.append(color)
            x_coords.append(round(x, 4))
            y_coords.append(round(y, 4))
        return node_idx[name]

    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    link_colors: list[str] = []

    def add_flow(src_name: str, dst_name: str, val: float, src_color: str, _dst_color: str = ""):
        if val > 0.05 and src_name in node_idx and dst_name in node_idx:
            sources.append(node_idx[src_name])
            targets.append(node_idx[dst_name])
            values.append(round(val, 2))
            link_colors.append(hex_to_rgba(src_color, 0.35))

    # Palettes
    fixed_palette = ["#F43F5E", "#E11D48", "#BE123C", "#FB7185", "#FDA4AF", "#9F1239"]
    disc_palette = ["#F59E0B", "#D97706", "#B45309", "#FBBF24", "#FCD34D", "#92400E", "#78350F"]

    drill = (drilldown_flow or "Full Flow").strip()

    if drill == "Fixed Expenses":
        # Upstream is hidden. Fixed Expenses -> child categories
        add_node("Fixed Expenses", "#FB7185", x=0.02, y=0.5)
        num_f = max(1, len(fixed_cats))
        for i, (cat, val) in enumerate(fixed_cats.items()):
            c_col = fixed_palette[i % len(fixed_palette)]
            y_pos = (i + 0.5) / num_f
            add_node(cat, c_col, x=0.98, y=y_pos)
            add_flow("Fixed Expenses", cat, val, "#FB7185", c_col)

    elif drill == "Discretionary":
        # Upstream is hidden. Discretionary -> child categories
        add_node("Discretionary", "#FBBF24", x=0.02, y=0.5)
        num_d = max(1, len(disc_cats))
        for i, (cat, val) in enumerate(disc_cats.items()):
            c_col = disc_palette[i % len(disc_palette)]
            y_pos = (i + 0.5) / num_d
            add_node(cat, c_col, x=0.98, y=y_pos)
            add_flow("Discretionary", cat, val, "#FBBF24", c_col)

    elif drill == "Taxes & Net":
        # Gross -> Taxes & Net
        add_node("Gross Salary", "#10B981", x=0.02, y=0.5)
        add_node("Taxes (Box 1)", "#EF4444", x=0.98, y=0.2)
        add_node("Net Income", "#06B6D4", x=0.98, y=0.7)
        if taxes > 0:
            add_flow("Gross Salary", "Taxes (Box 1)", taxes, "#10B981", "#EF4444")
        if net_salary > 0:
            add_flow("Gross Salary", "Net Income", net_salary, "#10B981", "#06B6D4")

    elif drill == "Savings":
        # Net Income / Savings -> Savings
        add_node("Savings & Investments", "#38BDF8", x=0.02, y=0.5)
        add_node("Emergency & Reserves", "#0284C7", x=0.98, y=0.3)
        add_node("Portfolio Wealth", "#38BDF8", x=0.98, y=0.7)
        if sav > 0:
            add_flow("Savings & Investments", "Emergency & Reserves", sav * 0.4, "#38BDF8", "#0284C7")
            add_flow("Savings & Investments", "Portfolio Wealth", sav * 0.6, "#38BDF8", "#38BDF8")

    else:
        # Full Cash Flow (Non-crossing 4-column layout)
        # Stage 0 (x=0.01): Inflows
        if gross_salary > 0:
            add_node("Gross Salary", "#10B981", x=0.01, y=0.35)
        if drawdown > 0:
            add_node("Savings Drawdown", "#F43F5E", x=0.01, y=0.85)

        # Stage 1 (x=0.28): Tax (top) & Net Income (below)
        if taxes > 0:
            add_node("Taxes (Box 1)", "#EF4444", x=0.28, y=0.06)
        if net_salary > 0:
            add_node("Net Income", "#06B6D4", x=0.28, y=0.55)

        # Stage 2 (x=0.62): Buckets ordered vertically to match terminal categories
        # 1. Fixed Expenses (top)
        # 2. Discretionary (middle)
        # 3. Savings & Investments (lower)
        # 4. Uncategorized (bottom)
        # 5. Unallocated (bottom-most)
        if fixed_spent > 0:
            add_node("Fixed Expenses", "#FB7185", x=0.62, y=0.18)
        if disc_spent > 0:
            add_node("Discretionary", "#FBBF24", x=0.62, y=0.55)
        if sav > 0:
            add_node("Savings & Investments", "#38BDF8", x=0.62, y=0.82)
        if uncat_spent > 0:
            add_node("Uncategorized", "#94A3B8", x=0.62, y=0.92)
        if unallocated > 0:
            add_node("Unallocated Cash", "#A78BFA", x=0.62, y=0.98)

        # Stage 3 (x=0.98): Terminal Categories
        # Top half: Fixed categories
        num_f = max(1, len(fixed_cats))
        for i, (cat, val) in enumerate(fixed_cats.items()):
            c_col = fixed_palette[i % len(fixed_palette)]
            y_pos = 0.02 + (i / max(1, num_f - 1)) * 0.32 if num_f > 1 else 0.16
            add_node(cat, c_col, x=0.98, y=y_pos)

        # Bottom half: Discretionary categories
        num_d = max(1, len(disc_cats))
        for j, (cat, val) in enumerate(disc_cats.items()):
            c_col = disc_palette[j % len(disc_palette)]
            y_pos = 0.42 + (j / max(1, num_d - 1)) * 0.48 if num_d > 1 else 0.65
            add_node(cat, c_col, x=0.98, y=y_pos)

        # Add Flows (strictly connecting adjacent vertical ranks)
        if gross_salary > 0:
            if taxes > 0:
                add_flow("Gross Salary", "Taxes (Box 1)", taxes, "#10B981", "#EF4444")
            if net_salary > 0:
                add_flow("Gross Salary", "Net Income", net_salary, "#10B981", "#06B6D4")

        if drawdown > 0 and "Net Income" in node_idx:
            add_flow("Savings Drawdown", "Net Income", drawdown, "#F43F5E", "#06B6D4")

        if fixed_spent > 0 and "Net Income" in node_idx:
            add_flow("Net Income", "Fixed Expenses", fixed_spent, "#06B6D4", "#FB7185")
        if disc_spent > 0 and "Net Income" in node_idx:
            add_flow("Net Income", "Discretionary", disc_spent, "#06B6D4", "#FBBF24")
        if sav > 0 and "Net Income" in node_idx:
            add_flow("Net Income", "Savings & Investments", sav, "#06B6D4", "#38BDF8")
        if uncat_spent > 0 and "Net Income" in node_idx:
            add_flow("Net Income", "Uncategorized", uncat_spent, "#06B6D4", "#94A3B8")
        if unallocated > 0 and "Net Income" in node_idx:
            add_flow("Net Income", "Unallocated Cash", unallocated, "#06B6D4", "#A78BFA")

        for cat, val in fixed_cats.items():
            add_flow("Fixed Expenses", cat, val, "#FB7185", "#FB7185")

        for cat, val in disc_cats.items():
            add_flow("Discretionary", cat, val, "#FBBF24", "#FBBF24")

    if not values:
        return go.Figure()

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node=dict(
                    pad=22,
                    thickness=18,
                    line=dict(color="#0F172A", width=0.8),
                    label=labels,
                    color=colors,
                    x=x_coords,
                    y=y_coords,
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    color=link_colors,
                ),
            )
        ]
    )

    title_map = {
        "Full Flow": "🌊 Full Cash Flow (Income → Net → Expense Buckets → Categories)",
        "Fixed Expenses": "🔒 Fixed Expenses Breakdown (Committed Outflows)",
        "Discretionary": "🛍️ Discretionary Spend Breakdown (Flexible Outflows)",
        "Taxes & Net": "🏛️ Gross Salary & Dutch Box 1 Tax Allocation",
        "Savings": "📈 Savings & Investment Allocations",
    }
    title_text = title_map.get(drill, f"Flow: {drill}")

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14)),
        font=dict(size=12),
        height=450,
        margin=dict(t=40, l=15, r=15, b=20),
    )

    if is_hidden():
        fig.update_traces(
            node=dict(hovertemplate="Censored<extra></extra>"),
            link=dict(hovertemplate="Censored<extra></extra>"),
        )
    else:
        fig.update_traces(
            node=dict(hovertemplate="<b>%{label}</b><br>Total: €%{value:,.2f}<extra></extra>"),
            link=dict(
                hovertemplate="<b>%{source.label} → %{target.label}</b><br>Flow: €%{value:,.2f}<extra></extra>"
            ),
        )

    return fig


def render_cash_flow_sankey(
    conn: sqlite3.Connection,
    key_prefix: str = "sankey",
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    display_df: pd.DataFrame | None = None,
    salary_day: int = 25,
) -> None:
    """Render interactive non-crossing Sankey diagram with direct diagram click-to-drilldown."""
    drill_key = f"{key_prefix}_drilldown_state"
    last_ts_key = f"{key_prefix}_last_click_ts"
    if drill_key not in st.session_state:
        st.session_state[drill_key] = "Full Flow"

    current_drill = st.session_state[drill_key]

    sankey_data = prepare_cash_flow_sankey_data(
        conn,
        days=days,
        start_date=start_date,
        end_date=end_date,
        display_df=display_df,
        salary_day=salary_day,
    )

    if (
        sankey_data["gross_salary"] <= 0
        and sankey_data["fixed_spent"] <= 0
        and sankey_data["disc_spent"] <= 0
    ):
        st.info("No expense or income transactions recorded for this period to display flow topology.")
        return

    fig = build_cash_flow_sankey(sankey_data, drilldown_flow=current_drill)

    # Render diagram with direct click-to-drilldown (no separate buttons)
    try:
        from ui.sankey_component.component import render_interactive_sankey

        click_event = render_interactive_sankey(
            fig,
            drilldown=current_drill,
            key=f"{key_prefix}_interactive_widget",
        )
        if click_event and isinstance(click_event, dict) and "clicked" in click_event:
            ts = click_event.get("ts")
            if ts and ts != st.session_state.get(last_ts_key):
                st.session_state[last_ts_key] = ts
                clicked = str(click_event["clicked"]).strip()
                target_drill = current_drill

                if clicked == "RESET":
                    target_drill = "Full Flow"
                elif current_drill != "Full Flow" and (
                    clicked == current_drill
                    or (current_drill == "Fixed Expenses" and clicked == "Fixed Expenses")
                    or (current_drill == "Discretionary" and clicked == "Discretionary")
                    or (current_drill == "Savings" and clicked == "Savings & Investments")
                    or (current_drill == "Taxes & Net" and clicked in ("Gross Salary", "Taxes (Box 1)", "Net Income"))
                ):
                    # Clicking the active root node in a drilled-down view toggles back to Full Flow
                    target_drill = "Full Flow"
                elif clicked == "Fixed Expenses" or clicked in sankey_data.get("fixed_cats", {}):
                    target_drill = "Fixed Expenses"
                elif clicked == "Discretionary" or clicked in sankey_data.get("disc_cats", {}):
                    target_drill = "Discretionary"
                elif clicked in ("Savings & Investments", "Emergency & Reserves", "Portfolio Wealth", "Savings"):
                    target_drill = "Savings"
                elif clicked in ("Gross Salary", "Taxes (Box 1)", "Net Income", "Taxes & Net"):
                    target_drill = "Taxes & Net"

                if target_drill != current_drill:
                    st.session_state[drill_key] = target_drill
                    st.rerun(scope="fragment")
    except Exception:
        render_chart(
            fig,
            use_container_width=True,
            key=f"{key_prefix}_chart_widget",
        )

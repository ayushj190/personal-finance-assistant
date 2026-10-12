import sqlite3
from typing import Any
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from money import Money
from ui.pages.tax import calculate_box1_tax
from ui.theme import hex_to_rgba, mask_chart_if_hidden
import ui.charts


def prepare_cash_flow_sankey_data(
    conn: sqlite3.Connection,
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    display_df: pd.DataFrame | None = None,
    salary_day: int = 25,
) -> dict[str, Any]:
    """Extract and calculate income, tax, expense buckets, and category breakdowns for Sankey flow."""
    if start_date and end_date:
        date_cond = "t.booking_date >= ? AND t.booking_date <= ?"
        params: tuple[Any, ...] = (start_date, end_date)
    else:
        date_cond = f"t.booking_date >= date('now', '-{days} days')"
        params = ()

    cf_row = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) as inc_minor,
            SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) as sav_minor
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.is_internal_transfer = 0
          AND {date_cond}
        """,
        params,
    ).fetchone()

    inc = Money.from_cents(cf_row["inc_minor"]).to_major() if cf_row else 0.0
    sav = Money.from_cents(cf_row["sav_minor"]).to_major() if cf_row else 0.0

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
        spend_rows = conn.execute(
            f"""
            SELECT
                COALESCE(p.name, c.name, 'Uncategorized') as parent_cat,
                COALESCE(c.kind, 'discretionary') as cat_kind,
                SUM(-t.amount_eur_minor) as spent_minor
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN categories p ON p.id = c.parent_id
            WHERE t.is_internal_transfer = 0
              AND t.amount_eur_minor < 0
              AND {date_cond}
            GROUP BY parent_cat, cat_kind
            ORDER BY spent_minor DESC
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
            amt = Money.from_cents(r["spent_minor"]).to_major()
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
    height: int = 450,
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

    fixed_palette = ["#F43F5E", "#E11D48", "#BE123C", "#FB7185", "#FDA4AF", "#9F1239"]
    disc_palette = ["#F59E0B", "#D97706", "#B45309", "#FBBF24", "#FCD34D", "#92400E", "#78350F"]
    drill = (drilldown_flow or "Full Flow").strip()

    if drill == "Net Income":
        add_node("Net Income", "#06B6D4", x=0.01, y=0.5)
        if drawdown > 0:
            add_node("Savings Drawdown", "#F43F5E", x=0.01, y=0.85)

        if fixed_spent > 0:
            add_node("Fixed Expenses", "#FB7185", x=0.50, y=0.18)
        if disc_spent > 0:
            add_node("Discretionary", "#FBBF24", x=0.50, y=0.55)
        if sav > 0:
            add_node("Savings & Investments", "#38BDF8", x=0.50, y=0.82)
        if uncat_spent > 0:
            add_node("Uncategorized", "#94A3B8", x=0.50, y=0.92)
        if unallocated > 0:
            add_node("Unallocated Cash", "#A78BFA", x=0.50, y=0.98)

        num_f = max(1, len(fixed_cats))
        for i, (cat, val) in enumerate(fixed_cats.items()):
            c_col = fixed_palette[i % len(fixed_palette)]
            y_pos = 0.02 + (i / max(1, num_f - 1)) * 0.32 if num_f > 1 else 0.16
            add_node(cat, c_col, x=0.98, y=y_pos)

        num_d = max(1, len(disc_cats))
        for j, (cat, val) in enumerate(disc_cats.items()):
            c_col = disc_palette[j % len(disc_palette)]
            y_pos = 0.42 + (j / max(1, num_d - 1)) * 0.48 if num_d > 1 else 0.65
            add_node(cat, c_col, x=0.98, y=y_pos)

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

    elif drill == "Fixed Expenses":
        add_node("Fixed Expenses", "#FB7185", x=0.02, y=0.5)
        num_f = max(1, len(fixed_cats))
        for i, (cat, val) in enumerate(fixed_cats.items()):
            c_col = fixed_palette[i % len(fixed_palette)]
            y_pos = (i + 0.5) / num_f
            add_node(cat, c_col, x=0.98, y=y_pos)
            add_flow("Fixed Expenses", cat, val, "#FB7185", c_col)

    elif drill == "Discretionary":
        add_node("Discretionary", "#FBBF24", x=0.02, y=0.5)
        num_d = max(1, len(disc_cats))
        for i, (cat, val) in enumerate(disc_cats.items()):
            c_col = disc_palette[i % len(disc_palette)]
            y_pos = (i + 0.5) / num_d
            add_node(cat, c_col, x=0.98, y=y_pos)
            add_flow("Discretionary", cat, val, "#FBBF24", c_col)

    elif drill == "Taxes & Net":
        add_node("Gross Salary", "#10B981", x=0.02, y=0.5)
        add_node("Taxes (Box 1)", "#EF4444", x=0.98, y=0.2)
        add_node("Net Income", "#06B6D4", x=0.98, y=0.7)
        if taxes > 0:
            add_flow("Gross Salary", "Taxes (Box 1)", taxes, "#10B981", "#EF4444")
        if net_salary > 0:
            add_flow("Gross Salary", "Net Income", net_salary, "#10B981", "#06B6D4")

    elif drill == "Savings":
        add_node("Savings & Investments", "#38BDF8", x=0.02, y=0.5)
        add_node("Emergency & Reserves", "#0284C7", x=0.98, y=0.3)
        add_node("Portfolio Wealth", "#38BDF8", x=0.98, y=0.7)
        if sav > 0:
            add_flow("Savings & Investments", "Emergency & Reserves", sav * 0.4, "#38BDF8", "#0284C7")
            add_flow("Savings & Investments", "Portfolio Wealth", sav * 0.6, "#38BDF8", "#38BDF8")

    else:
        if gross_salary > 0:
            add_node("Gross Salary", "#10B981", x=0.01, y=0.35)
        if drawdown > 0:
            add_node("Savings Drawdown", "#F43F5E", x=0.01, y=0.85)

        if taxes > 0:
            add_node("Taxes (Box 1)", "#EF4444", x=0.28, y=0.06)
        if net_salary > 0:
            add_node("Net Income", "#06B6D4", x=0.28, y=0.55)

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

        num_f = max(1, len(fixed_cats))
        for i, (cat, val) in enumerate(fixed_cats.items()):
            c_col = fixed_palette[i % len(fixed_palette)]
            y_pos = 0.02 + (i / max(1, num_f - 1)) * 0.32 if num_f > 1 else 0.16
            add_node(cat, c_col, x=0.98, y=y_pos)

        num_d = max(1, len(disc_cats))
        for j, (cat, val) in enumerate(disc_cats.items()):
            c_col = disc_palette[j % len(disc_palette)]
            y_pos = 0.42 + (j / max(1, num_d - 1)) * 0.48 if num_d > 1 else 0.65
            add_node(cat, c_col, x=0.98, y=y_pos)

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
        "Net Income": "💸 Net Income Outflows (Gross Salary & Taxes Hidden • Click Net Income to restore)",
        "Fixed Expenses": "🔒 Fixed Expenses Breakdown (Committed Outflows)",
        "Discretionary": "🛍️ Discretionary Spend Breakdown (Flexible Outflows)",
        "Taxes & Net": "🏛️ Gross Salary & Dutch Box 1 Tax Allocation",
        "Savings": "📈 Savings & Investment Allocations",
    }
    title_text = title_map.get(drill, f"Flow: {drill}")

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14)),
        font=dict(size=12),
        height=height,
        margin=dict(t=40, l=15, r=15, b=20),
    )

    if ui.charts.is_hidden():
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

    mask_chart_if_hidden(fig)
    return fig


def render_cash_flow_sankey(
    conn: sqlite3.Connection,
    key_prefix: str = "sankey",
    days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    display_df: pd.DataFrame | None = None,
    salary_day: int = 25,
    height: int = 450,
) -> None:
    """Render interactive non-crossing Sankey diagram."""
    drill_key = f"{key_prefix}_drilldown_state"
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

    fig = build_cash_flow_sankey(sankey_data, drilldown_flow=current_drill, height=height)
    ui.charts.render_chart(
        fig,
        use_container_width=True,
        key=f"{key_prefix}_chart_widget",
    )


@st.dialog("Expenses — Fullscreen Flow", width="large")
def open_sankey_fullscreen_dialog(
    start_date: str | None = None,
    end_date: str | None = None,
    drilldown_flow: str | None = None,
) -> None:
    """Open full screen modal dialog displaying the high-resolution cash flow Sankey diagram."""
    from config import DB_PATH
    from db import database

    if drilldown_flow:
        st.session_state["fullscreen_sankey_drilldown_state"] = drilldown_flow
    elif "dashboard_sankey_drilldown_state" in st.session_state:
        st.session_state["fullscreen_sankey_drilldown_state"] = st.session_state["dashboard_sankey_drilldown_state"]
    elif "spending_sankey_drilldown_state" in st.session_state:
        st.session_state["fullscreen_sankey_drilldown_state"] = st.session_state["spending_sankey_drilldown_state"]

    dlg_conn = database.connect(DB_PATH)
    try:
        render_cash_flow_sankey(
            dlg_conn,
            key_prefix="fullscreen_sankey",
            start_date=start_date,
            end_date=end_date,
            height=620,
        )
    finally:
        dlg_conn.close()

from typing import Any
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import DB_PATH
from db import database
from money import Money
from services.analytics import (
    aggregate_top_merchants,
    calculate_current_net_worth,
    detect_recurring_charges,
    get_merchant_context,
)
from services.budget_service import (
    calculate_12_month_runway_forecast,
    calculate_3_month_historical_burn_rate,
    calculate_budget_variance,
)
from services.fiscal_service import (
    format_fiscal_month_label,
    get_fiscal_month_for_date,
    get_fiscal_month_range,
    get_fiscal_salary_day,
)
from ui.charts import build_monthly_spending_bar, build_spending_donut, render_cash_flow_sankey
from ui.components import format_money, is_hidden, kpi_card, section_header
from ui.theme import mask_chart_if_hidden, render_chart
from ui.dialogs import assign_mortgage_dialog, set_category_budget_dialog
from ui.filters import build_where_clause, render_filters
from services.date_scope import spending_view_for_scope


def _fetch_spending_df(conn, filters) -> pd.DataFrame:
    """Fetch detailed spending transactions and classify with strict non-overlapping rules."""
    where_sql, params = build_where_clause(filters, table_alias="t")
    where_parts = []
    if where_sql:
        where_parts.append(where_sql.replace("WHERE ", "", 1))
    where_parts.append("t.amount_eur_minor < 0")
    where_parts.append("t.is_internal_transfer = 0")
    where_parts.append("(c.kind IS NULL OR c.kind NOT IN ('savings', 'transfer', 'income'))")
    base_where = "WHERE " + " AND ".join(where_parts)

    detail_query = f"""
    SELECT t.id,
           t.booking_date,
           t.merchant_normalized AS merchant,
           t.category_id,
           COALESCE(c.name, 'Uncategorized') AS category,
           COALESCE(p.name, c.name, 'Uncategorized') AS parent_category,
           c.kind AS category_kind,
           t.amount_eur_minor,
           -t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {base_where}
    ORDER BY t.booking_date DESC
    """
    df = pd.read_sql_query(detail_query, conn, params=params)
    if not df.empty:
        # AC-2: Prevent uncategorized expenses from leaking into discretionary totals.
        is_uncat = df["category_id"].isna() | (df["category"] == "Uncategorized")
        is_fixed = (~is_uncat) & (df["category_kind"] == "fixed")
        is_disc = (~is_uncat) & (~is_fixed)

        df["is_uncat"] = is_uncat
        df["is_fixed"] = is_fixed
        df["is_disc"] = is_disc
        df["expense_kind"] = np.where(
            is_uncat, "uncategorized", np.where(is_fixed, "fixed", "discretionary")
        )
    return df


def _calculate_monthly_summary(df_all: pd.DataFrame, salary_day: int) -> pd.DataFrame:
    """Aggregate monthly summary using integer cents to guarantee summation invariants."""
    df_all["fiscal_month"] = df_all["booking_date"].apply(
        lambda d: get_fiscal_month_for_date(d, salary_day)
    )

    monthly_rows = []
    for fm, grp in df_all.groupby("fiscal_month"):
        tot_minor = int(grp["amount_eur_minor"].abs().sum())
        fix_minor = int(grp[grp["is_fixed"]]["amount_eur_minor"].abs().sum())
        disc_minor = int(grp[grp["is_disc"]]["amount_eur_minor"].abs().sum())
        unc_minor = int(grp[grp["is_uncat"]]["amount_eur_minor"].abs().sum())

        # AC-1, AC-7: Enforce exact integer identity
        assert tot_minor == fix_minor + disc_minor + unc_minor, (
            f"Sum mismatch: {tot_minor} != {fix_minor} + {disc_minor} + {unc_minor}"
        )

        monthly_rows.append({
            "month": fm,
            "tx_count": len(grp),
            "tot_minor": tot_minor,
            "fix_minor": fix_minor,
            "disc_minor": disc_minor,
            "unc_minor": unc_minor,
            "total_spent": Money.from_cents(tot_minor).to_major(),
            "fixed_spent": Money.from_cents(fix_minor).to_major(),
            "disc_spent": Money.from_cents(disc_minor).to_major(),
            "uncat_spent": Money.from_cents(unc_minor).to_major(),
        })
    return pd.DataFrame(monthly_rows).sort_values(by="month", ascending=False)


def _render_kpi_ribbon(
    total_spent: float,
    fixed_spent: float,
    disc_spent: float,
    uncat_spent: float,
    header_title: str,
) -> None:
    """Render top 4-KPI ribbon satisfying Total = Fixed + Discretionary + Uncategorized."""
    c1, c2, c3, c4 = st.columns(4)
    if is_hidden():
        with c1:
            kpi_card("Total Expenses", "€****", subtext=header_title)
        with c2:
            kpi_card("Fixed Expenses", "€****", subtext="****% of total")
        with c3:
            kpi_card("Discretionary", "€****", subtext="****% of total")
        with c4:
            kpi_card("Uncategorized", "€****", subtext="****% of total")
    else:
        fixed_pct = (fixed_spent / total_spent * 100) if total_spent > 0 else 0.0
        disc_pct = (disc_spent / total_spent * 100) if total_spent > 0 else 0.0
        uncat_pct = (uncat_spent / total_spent * 100) if total_spent > 0 else 0.0

        with c1:
            kpi_card("Total Expenses", f"€{total_spent:,.2f}", subtext=header_title)
        with c2:
            kpi_card(
                "Fixed Expenses",
                f"€{fixed_spent:,.2f}",
                subtext=f"{fixed_pct:.1f}% of total",
            )
        with c3:
            kpi_card(
                "Discretionary",
                f"€{disc_spent:,.2f}",
                subtext=f"{disc_pct:.1f}% of total",
            )
        with c4:
            kpi_card(
                "Uncategorized",
                f"€{uncat_spent:,.2f}",
                subtext=f"{uncat_pct:.1f}% of total",
            )


# Shared fixed height so the two top panels align top and bottom (AC-4).
_SPENDING_PANEL_HEIGHT = 420


@st.fragment
def _render_analytics_fragment(
    display_df: pd.DataFrame,
    selected_scope: str,
    conn: Any,
) -> None:
    """Isolated fragment for the matched-height donut and subscription panels."""
    with section_header(
        f"Expense Breakdown ({selected_scope})",
        "Hierarchical spending across categories and merchants",
    ):
        if display_df.empty:
            st.info("No expense data available for this scope.")
            return

        col_left, col_right = st.columns([1, 1])

        with col_left:
            with st.container(border=True, height=_SPENDING_PANEL_HEIGHT):
                st.markdown("##### 🍩 Spending by Category")
                drill_key = f"donut_drilldown_{selected_scope}"
                if drill_key not in st.session_state:
                    st.session_state[drill_key] = None

                if st.session_state[drill_key]:
                    if st.button("← Back to Categories", key=f"btn_back_donut_{selected_scope}"):
                        st.session_state[drill_key] = None
                        st.rerun()

                fig = build_spending_donut(display_df, drilldown_category=st.session_state[drill_key])
                selection = st.plotly_chart(
                    fig,
                    width="stretch",
                    theme=None,
                    on_select="rerun",
                    selection_mode="points",
                    key=f"donut_chart_{selected_scope}",
                )

                if selection and hasattr(selection, "selection") and selection.selection.get("points"):
                    clicked_point = selection.selection["points"][0]
                    clicked_label = clicked_point.get("label") or clicked_point.get("x")
                    if st.session_state[drill_key] is None and clicked_label:
                        st.session_state[drill_key] = clicked_label
                        st.rerun()
                elif selection and isinstance(selection, dict) and selection.get("selection", {}).get("points"):
                    clicked_point = selection["selection"]["points"][0]
                    clicked_label = clicked_point.get("label") or clicked_point.get("x")
                    if st.session_state[drill_key] is None and clicked_label:
                        st.session_state[drill_key] = clicked_label
                        st.rerun()

        with col_right:
            with st.container(border=True, height=_SPENDING_PANEL_HEIGHT):
                st.markdown("##### 🔁 Subscription Leak Detector")
                st.caption("Recurring services and annual commitments")
                all_tx_rows = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM v_transactions ORDER BY booking_date DESC"
                    ).fetchall()
                ]
                recurring = detect_recurring_charges(all_tx_rows)
                if recurring:
                    rec_df = pd.DataFrame(recurring)[
                        ["merchant", "cadence", "amount_eur", "annual_cost_eur"]
                    ]
                    rec_df.columns = [
                        "Merchant",
                        "Cadence",
                        "Cost / Cycle",
                        "Annual Cost (€)",
                    ]
                    if is_hidden():
                        rec_df["Merchant"] = "****"
                        rec_df["Cost / Cycle"] = rec_df["Cost / Cycle"].map(
                            lambda x: format_money(x)
                        )
                        rec_df["Annual Cost (€)"] = rec_df["Annual Cost (€)"].map(
                            lambda x: format_money(x)
                        )
                        cost_cfg = st.column_config.TextColumn("Cost / Cycle", disabled=True)
                        ann_cfg = st.column_config.TextColumn("Annual Cost (€)", disabled=True)
                    else:
                        cost_cfg = st.column_config.NumberColumn(
                            "Cost / Cycle", format="€%.2f", disabled=True
                        )
                        ann_cfg = st.column_config.NumberColumn(
                            "Annual Cost (€)", format="€%.2f", disabled=True
                        )

                    st.dataframe(
                        rec_df,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                            "Cost / Cycle": cost_cfg,
                            "Annual Cost (€)": ann_cfg,
                        },
                    )
                else:
                    st.caption("No subscriptions detected.")


def _merchant_category_label(row: dict[str, Any]) -> str:
    """Category with its parent shown when the two differ."""
    category = row.get("category") or "Uncategorized"
    parent = row.get("parent")
    if parent and str(parent) != str(category):
        return f"{parent} / {category}"
    return str(category)


def _render_top_merchants(merchant_data: dict[str, Any] | None, selected_scope: str) -> None:
    """AC-5, AC-6, AC-7: full width merchant table with location gated on IBAN data."""
    with section_header("Top Merchants", f"Highest spending in {selected_scope}"):
        data = merchant_data or {}
        rows = data.get("rows") or []
        if not rows:
            st.caption("No merchant data available for this scope.")
            return

        has_location = bool(data.get("has_location"))
        hidden = is_hidden()

        if hidden:
            avg_col = ["€****"] * len(rows)
            total_col = ["€****"] * len(rows)
            share_col = ["****%"] * len(rows)
        else:
            avg_col = [f"€{r['avg_eur']:,.2f}" for r in rows]
            total_col = [f"€{r['total_eur']:,.2f}" for r in rows]
            share_col = [f"{r['share_pct']:.1f}%" for r in rows]

        disp = pd.DataFrame(
            {
                "Merchant": [r["merchant"] for r in rows],
                "Category": [_merchant_category_label(r) for r in rows],
                "Transactions": [r["transactions"] for r in rows],
                "Avg per Visit (€)": avg_col,
                "Total Spent (€)": total_col,
                "Share (%)": share_col,
                "Last Transaction": [r["last_date"] for r in rows],
                "Accounts": [r["accounts"] for r in rows],
            }
        )
        if has_location:
            disp.insert(1, "Location", [r.get("location") or "—" for r in rows])

        column_config = {
            "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
            "Transactions": st.column_config.NumberColumn("Transactions", format="%d"),
            "Last Transaction": st.column_config.TextColumn("Last Transaction"),
            "Accounts": st.column_config.TextColumn("Accounts", width="medium"),
            "Avg per Visit (€)": st.column_config.TextColumn("Avg per Visit (€)", disabled=True),
            "Total Spent (€)": st.column_config.TextColumn("Total Spent (€)", disabled=True),
            "Share (%)": st.column_config.TextColumn("Share (%)", disabled=True),
        }
        st.dataframe(
            disp,
            width="stretch",
            hide_index=True,
            column_config=column_config,
        )

        if has_location and data.get("location_totals"):
            loc_df = pd.DataFrame(data["location_totals"])
            loc_df.columns = ["Location", "Spent (€)"]
            loc_fig = px.bar(
                loc_df,
                x="Location",
                y="Spent (€)",
                title="Spending by Location",
                color_discrete_sequence=["#2DD4BF"],
            )
            loc_fig.update_layout(
                margin=dict(t=35, l=55, r=20, b=25),
                xaxis=dict(title="Location", automargin=True),
                yaxis=dict(title="Spent (€)", tickprefix="€", automargin=True),
            )
            if hidden:
                loc_fig.update_traces(hovertemplate="Censored<extra></extra>")
            with st.container(border=True):
                render_chart(loc_fig, width="stretch")


@st.fragment
def _render_budget_tracker_fragment(
    conn: Any,
    selected_scope: str,
    start_d_str: str | None,
    end_d_str: str | None,
    monthly_df: pd.DataFrame,
) -> None:
    """AC-3, AC-4: Category budget rollup metrics and 12-month runway trajectory."""
    with section_header(
        "Category Budget Tracker & Variance",
        "Track monthly targets and branch rollups without double counting",
    ):
        b_data = calculate_budget_variance(
            conn,
            year_month=selected_scope if selected_scope != "All Months (Monthly Average)" else None,
            start_date=start_d_str,
            end_date=end_d_str,
        )

        b1, b2, b3 = st.columns(3)
        with b1:
            tot_b_str = "€****" if is_hidden() else f"€{b_data['total_budget_eur']:,.2f}"
            kpi_card("Monthly Budget", tot_b_str, subtext="Target cap across category branches")
        with b2:
            tot_s_str = "€****" if is_hidden() else f"€{b_data['total_spent_eur']:,.2f}"
            kpi_card("Current Spend", tot_s_str, subtext=f"Total spent in {b_data['month']}")
        with b3:
            var_val = b_data["variance_eur"]
            var_sub = "Within budget" if var_val >= 0 else "Over budget"
            var_str = (
                "€****"
                if is_hidden()
                else f"€{abs(var_val):,.2f} {'left' if var_val >= 0 else 'deficit'}"
            )
            kpi_card("Budget Variance", var_str, subtext=var_sub)

        cat_df = b_data["categories_df"]
        if not cat_df.empty:
            disp_filter = cat_df["is_parent"] | (cat_df["budget_eur"] > 0) | (cat_df["spent_eur"] > 0)
            disp_df_sub = cat_df[disp_filter].copy() if any(disp_filter) else cat_df.copy()
            disp_b = disp_df_sub[
                ["category", "kind", "budget_eur", "spent_eur", "remaining_eur", "pct_used", "status"]
            ].copy()
            disp_b.columns = [
                "Category",
                "Type",
                "Budget (€)",
                "Spent (€)",
                "Remaining (€)",
                "% Used",
                "Status",
            ]
            if is_hidden():
                disp_b["Budget (€)"] = "€****"
                disp_b["Spent (€)"] = "€****"
                disp_b["Remaining (€)"] = "€****"
                disp_b["% Used"] = "****%"
                disp_b["Category"] = "****"
            else:
                disp_b["Budget (€)"] = disp_b["Budget (€)"].map(
                    lambda x: f"€{x:,.2f}" if x > 0 else "—"
                )
                disp_b["Spent (€)"] = disp_b["Spent (€)"].map(lambda x: f"€{x:,.2f}")
                disp_b["Remaining (€)"] = disp_b["Remaining (€)"].map(
                    lambda x: f"€{x:,.2f}" if x != 0 else "—"
                )
                disp_b["% Used"] = disp_b["% Used"].map(
                    lambda x: f"{x:.0f}%" if x > 0 else "0%"
                )
            st.dataframe(disp_b, width="stretch", hide_index=True)

        # 12-Month Runway Projection Chart (AC-3: Baseline uses 3-month historical burn rate)
        st.markdown("#### 📈 12-Month Financial Trajectory Projection")
        nw_data = calculate_current_net_worth(conn)
        liq_cash = nw_data["liquid_cash"]

        inc_row = conn.execute(
            """
            SELECT AVG(monthly_inc) as avg_inc FROM (
                SELECT SUM(amount_eur) as monthly_inc
                FROM v_transactions
                WHERE category_kind = 'income' AND is_internal_transfer = 0
                GROUP BY strftime('%Y-%m', booking_date)
                ORDER BY strftime('%Y-%m', booking_date) DESC
                LIMIT 6
            )
            """
        ).fetchone()
        avg_income = float(inc_row["avg_inc"] or 0.0) if inc_row else 0.0

        # Calculate 3-month historical burn rate for stabilized trajectory
        burn_3m_data = calculate_3_month_historical_burn_rate(conn)
        cur_burn = float(burn_3m_data["avg_burn_eur"])
        if cur_burn <= 0 and not monthly_df.empty:
            cur_burn = float(monthly_df["total_spent"].iloc[0])

        bud_burn = float(b_data["total_budget_eur"]) if b_data["total_budget_eur"] > 0 else cur_burn

        forecast_data = calculate_12_month_runway_forecast(
            liquid_cash=liq_cash,
            projected_monthly_income=avg_income,
            current_burn_rate=cur_burn,
            budgeted_burn_rate=bud_burn,
            horizon_months=12,
        )

        # Cash Runway KPI badge calculation (AC-3)
        net_burn = cur_burn - avg_income
        if net_burn <= 0:
            runway_str = "Sustainable (Net Positive)"
            runway_sub = f"+€{abs(net_burn):,.2f}/mo net cashflow"
        else:
            runway_months = liq_cash / net_burn if net_burn > 0 else float("inf")
            if runway_months >= 120:
                runway_str = "> 10 Years"
            else:
                runway_str = f"{runway_months:.1f} Months"
            runway_sub = f"€{net_burn:,.2f}/mo net deficit"

        k_col1, k_col2, k_col3 = st.columns(3)
        with k_col1:
            kpi_card(
                "3-Month Avg Burn",
                f"€{cur_burn:,.2f}",
                subtext=f"Fixed €{burn_3m_data.get('fixed_burn_eur', 0):,.2f} | Disc €{burn_3m_data.get('disc_burn_eur', 0):,.2f}",
            )
        with k_col2:
            kpi_card(
                "Projected Income",
                f"€{avg_income:,.2f}",
                subtext="6-mo avg net income",
            )
        with k_col3:
            kpi_card(
                "Cash Runway",
                runway_str,
                subtext=runway_sub,
            )

        if forecast_data:
            f_df = pd.DataFrame(forecast_data)
            f_fig = go.Figure()
            f_fig.add_trace(
                go.Scatter(
                    x=f_df["month_label"],
                    y=f_df["current_spend_balance_eur"],
                    mode="lines+markers",
                    name="3-Mo Historical Burn Trajectory",
                    line=dict(color="#FB7185", width=2.5),
                )
            )
            f_fig.add_trace(
                go.Scatter(
                    x=f_df["month_label"],
                    y=f_df["budgeted_spend_balance_eur"],
                    mode="lines+markers",
                    name="Budgeted Target Trajectory",
                    line=dict(color="#2DD4BF", width=2.5, dash="dash"),
                )
            )
            f_fig.update_layout(
                xaxis=dict(title="Timeline", automargin=True),
                yaxis=dict(title="Projected Cash Balance (€)", tickprefix="€", tickformat="~s", automargin=True),
                margin=dict(t=35, l=55, r=20, b=25),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            with st.container(border=True):
                st.markdown("##### 📈 12-Month Cash Buffer Trajectory (3-Mo Burn vs Target Budget)")
                render_chart(f_fig, width="stretch")


def _render_uncategorized_triage(
    conn: Any,
    where_sql: str,
    params: list,
    selected_scope: str,
    start_d_str: str | None,
    end_d_str: str | None,
) -> None:
    """AC-5: Streamlined uncategorized triage table and modal action launcher."""
    with section_header(
        "Top Uncategorized Expenses",
        "Review and categorize transactions, or link directly to a mortgage liability",
    ):
        scope_choice = "All Filtered Months"
        if selected_scope != "All Months (Monthly Average)":
            col_sc1, _ = st.columns([2, 3])
            with col_sc1:
                scope_choice = st.radio(
                    "Uncategorized Scope",
                    options=[f"Selected Month ({selected_scope})", "All Filtered Months"],
                    horizontal=True,
                    key="uncat_spending_scope_toggle",
                )

        uncat_where_parts = []
        if where_sql:
            uncat_where_parts.append(where_sql.replace("WHERE ", "", 1))
        uncat_where_parts.append(
            "(t.category_id IS NULL OR t.category_id = (SELECT id FROM categories WHERE name = 'Uncategorized' LIMIT 1))"
        )
        uncat_where_parts.append("t.amount_eur_minor < 0")
        uncat_where_parts.append("t.is_internal_transfer = 0")

        uncat_params = list(params)
        if scope_choice.startswith("Selected Month") and selected_scope != "All Months (Monthly Average)":
            if start_d_str and end_d_str:
                uncat_where_parts.append("t.booking_date >= ? AND t.booking_date <= ?")
                uncat_params.extend([start_d_str, end_d_str])
            else:
                uncat_where_parts.append("strftime('%Y-%m', t.booking_date) = ?")
                uncat_params.append(selected_scope)

        uncat_query = f"""
        SELECT t.id,
               t.booking_date,
               a.name AS account,
               COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
               -t.amount_eur_minor / 100.0 AS amount_eur,
               t.description_raw
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE {" AND ".join(uncat_where_parts)}
        ORDER BY abs(t.amount_eur_minor) DESC
        LIMIT 10
        """
        uncat_df = pd.read_sql_query(uncat_query, conn, params=uncat_params)

        if uncat_df.empty:
            st.success("🎉 No uncategorized expenses found in this scope!")
            return

        cat_rows = conn.execute(
            "SELECT id, name FROM categories WHERE name != 'Uncategorized' ORDER BY name ASC"
        ).fetchall()
        cat_names = [r["name"] for r in cat_rows]
        cat_name_to_id = {r["name"]: r["id"] for r in cat_rows}

        st.caption(
            f"Showing top {len(uncat_df)} uncategorized expenses. Assign categories inline below, "
            "or click **🏠 Link Mortgage** in the action bar to connect directly to loan schedules."
        )

        edit_df = uncat_df[["id", "booking_date", "account", "merchant", "amount_eur"]].copy()
        edit_df["category"] = None

        if is_hidden():
            edit_df_display = edit_df.copy()
            edit_df_display["amount_eur"] = edit_df_display["amount_eur"].map(
                lambda x: format_money(x)
            )
            amount_col_cfg = st.column_config.TextColumn("Amount (€)", disabled=True)
        else:
            edit_df_display = edit_df
            amount_col_cfg = st.column_config.NumberColumn(
                "Amount (€)", format="€%.2f", disabled=True
            )

        edited_uncat = st.data_editor(
            edit_df_display,
            column_config={
                "id": None,
                "booking_date": st.column_config.DateColumn("Date", disabled=True),
                "account": st.column_config.TextColumn("Account", disabled=True),
                "merchant": st.column_config.TextColumn("Merchant / Description", width="medium", disabled=True),
                "amount_eur": amount_col_cfg,
                "category": st.column_config.SelectboxColumn("Assign Category", options=cat_names, required=False),
            },
            disabled=["id", "booking_date", "account", "merchant", "amount_eur"],
            width="stretch",
            hide_index=True,
            key="spending_uncat_editor",
        )

        col_save, col_link_mort = st.columns([1, 2])
        with col_save:
            if st.button("Save Categorizations", type="primary", key="btn_save_uncat"):
                saved_count = 0
                for idx, row in edited_uncat.iterrows():
                    new_cat = row["category"]
                    if new_cat and new_cat in cat_name_to_id:
                        new_cat_id = cat_name_to_id[new_cat]
                        tx_id = int(uncat_df.loc[idx, "id"])
                        merchant = str(uncat_df.loc[idx, "merchant"])
                        with conn:
                            conn.execute(
                                "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                                (new_cat_id, tx_id),
                            )
                            if merchant:
                                database.upsert_category_rule(conn, merchant, new_cat_id, source="user")
                            if new_cat == "Mortgage":
                                conn.execute(
                                    "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = (SELECT id FROM liabilities LIMIT 1)",
                                    (merchant,),
                                )
                        saved_count += 1

                if saved_count > 0:
                    st.success(f"Successfully categorized {saved_count} transaction(s) and updated rules!")
                    st.rerun()

        with col_link_mort:
            if st.button("🏠 Assign Top Item to Mortgage", key="btn_link_top_mortgage"):
                top_tx_id = int(uncat_df.iloc[0]["id"])
                assign_mortgage_dialog(tx_id=top_tx_id)


def _render_sankey_flow(
    conn: Any,
    display_df: pd.DataFrame,
    selected_scope: str,
    months: list[str],
    salary_day: int,
    fixed_spent: float,
    disc_spent: float,
    uncat_spent: float,
    start_d_str: str | None,
    end_d_str: str | None,
) -> None:
    """AC-6: Render non-crossing cash flow Sankey diagram with interactive drill-down."""
    render_cash_flow_sankey(
        conn=conn,
        key_prefix="spending_sankey",
        start_date=start_d_str,
        end_date=end_d_str,
        display_df=display_df,
        salary_day=salary_day,
    )


def _render_monthly_trend(monthly_df: pd.DataFrame) -> None:
    """Render month-by-month spending trends and breakdown table."""
    with section_header(
        "Monthly Expenses Trend", "Month-by-month spending broken down by expense kind"
    ):
        col_chart, col_tbl = st.columns([2, 3])
        with col_chart:
            st.plotly_chart(
                build_monthly_spending_bar(monthly_df),
                width="stretch",
                theme=None,
            )
        with col_tbl:
            tbl_df = monthly_df[
                ["month", "total_spent", "fixed_spent", "disc_spent", "uncat_spent"]
            ].copy()

            tbl_df["prev_total"] = tbl_df["total_spent"].shift(-1)
            tbl_df["MoM Change (%)"] = np.where(
                tbl_df["prev_total"] == 0,
                0,
                ((tbl_df["total_spent"] - tbl_df["prev_total"]) / tbl_df["prev_total"] * 100),
            )

            tot = tbl_df["total_spent"].mask(tbl_df["total_spent"] == 0, 1)
            tbl_df["Fixed (%)"] = (tbl_df["fixed_spent"] / tot * 100).fillna(0)
            tbl_df["Disc. (%)"] = (tbl_df["disc_spent"] / tot * 100).fillna(0)

            tbl_df = tbl_df[
                ["month", "total_spent", "MoM Change (%)", "Fixed (%)", "Disc. (%)", "uncat_spent"]
            ]
            tbl_df.columns = [
                "Month",
                "Total (€)",
                "MoM Change (%)",
                "Fixed (%)",
                "Disc. (%)",
                "Uncategorized (€)",
            ]

            if is_hidden():
                for col in ["Total (€)", "Uncategorized (€)"]:
                    tbl_df[col] = tbl_df[col].map(lambda x: format_money(x))
                for col in ["MoM Change (%)", "Fixed (%)", "Disc. (%)"]:
                    tbl_df[col] = tbl_df[col].map(lambda x: "****%")
                st.dataframe(tbl_df, width="stretch", hide_index=True)
            else:
                st.dataframe(
                    tbl_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Total (€)": st.column_config.NumberColumn("Total (€)", format="€%.2f"),
                        "MoM Change (%)": st.column_config.NumberColumn(
                            "MoM Change (%)", format="%+.1f%%"
                        ),
                        "Fixed (%)": st.column_config.NumberColumn("Fixed (%)", format="%.1f%%"),
                        "Disc. (%)": st.column_config.NumberColumn("Disc. (%)", format="%.1f%%"),
                        "Uncategorized (€)": st.column_config.NumberColumn(
                            "Uncategorized (€)", format="€%.2f"
                        ),
                    },
                )


def render():
    col_filt, col_scope, col_budgets, col_mortgage = st.columns(
        [1.2, 2.2, 1.3, 1.3], vertical_alignment="bottom"
    )
    with col_filt:
        filters = render_filters()

    conn = database.connect(DB_PATH)
    salary_day = get_fiscal_salary_day(conn)

    where_sql, params = build_where_clause(filters, table_alias="t")
    df_all = _fetch_spending_df(conn, filters)

    if df_all.empty:
        conn.close()
        st.info("No spending transactions found for the selected filter criteria.")
        return

    monthly_df = _calculate_monthly_summary(df_all, salary_day)

    months = monthly_df["month"].tolist() if not monthly_df.empty else []
    month_options = months + ["All Months (Monthly Average)"]

    fiscal_tooltip = (
        f"Fiscal cycle runs from Day {salary_day} to Day {salary_day - 1}. Change payday in Settings."
        if salary_day > 1
        else "Fiscal cycle aligns with standard calendar months (Day 1 to month end)."
    )

    mapped = spending_view_for_scope(filters.get("resolved", {}), salary_day)
    desired_scope = mapped["option"]
    if desired_scope not in month_options:
        desired_scope = month_options[0] if month_options else "All Months (Monthly Average)"
    resolved_scope = filters.get("resolved", {})
    _scope_key = (
        resolved_scope.get("start_iso"),
        resolved_scope.get("end_iso"),
        resolved_scope.get("preset"),
    )
    if (
        resolved_scope.get("requested")
        and "spending_view_scope" in st.session_state
        and st.session_state.get("_spending_scope_applied") != _scope_key
    ):
        st.session_state["spending_view_scope"] = desired_scope
    st.session_state["_spending_scope_applied"] = _scope_key
    if "spending_view_scope" not in st.session_state:
        st.session_state["spending_view_scope"] = desired_scope

    with col_scope:
        selected_scope = st.selectbox(
            "View Scope",
            options=month_options,
            key="spending_view_scope",
            help=fiscal_tooltip,
            format_func=lambda m: format_fiscal_month_label(m, salary_day)
            if m != "All Months (Monthly Average)"
            else m,
        )
        if mapped.get("caption"):
            st.caption(f"🗓️ {mapped['caption']}")
    with col_budgets:
        if st.button("✏️ Set Budgets", width="stretch", key="btn_open_budget_dialog"):
            set_category_budget_dialog()
    with col_mortgage:
        if st.button("🏠 Link Mortgage", width="stretch", key="btn_open_mortgage_dialog"):
            assign_mortgage_dialog()

    # Calculate exact scope KPIs
    month_divisor = 1
    if selected_scope == "All Months (Monthly Average)":
        display_df = df_all.copy()
        n_months = max(1, len(months))
        month_divisor = n_months
        # AC-7: Sum in minor units, divide by count, ensure exact equality
        avg_tot_minor = round(monthly_df["tot_minor"].sum() / n_months)
        avg_fix_minor = round(monthly_df["fix_minor"].sum() / n_months)
        avg_disc_minor = round(monthly_df["disc_minor"].sum() / n_months)
        avg_unc_minor = avg_tot_minor - avg_fix_minor - avg_disc_minor

        total_spent = Money.from_cents(avg_tot_minor).to_major()
        fixed_spent = Money.from_cents(avg_fix_minor).to_major()
        disc_spent = Money.from_cents(avg_disc_minor).to_major()
        uncat_spent = Money.from_cents(avg_unc_minor).to_major()
        header_title = f"Average Monthly Expenses ({n_months} fiscal months)"
        start_d_str, end_d_str = None, None
    else:
        display_df = df_all[df_all["fiscal_month"] == selected_scope].copy()
        month_row = monthly_df[monthly_df["month"] == selected_scope].iloc[0]
        total_spent = float(month_row["total_spent"])
        fixed_spent = float(month_row["fixed_spent"])
        disc_spent = float(month_row["disc_spent"])
        uncat_spent = float(month_row["uncat_spent"])
        header_title = f"Monthly Expenses ({format_fiscal_month_label(selected_scope, salary_day)})"
        y, m = map(int, selected_scope.split("-"))
        s_d, e_d = get_fiscal_month_range(y, m, salary_day)
        start_d_str, end_d_str = s_d.isoformat(), e_d.isoformat()

    # AC-1: Top 4 KPI Ribbon
    _render_kpi_ribbon(total_spent, fixed_spent, disc_spent, uncat_spent, header_title)

    # AC-5, AC-6, AC-7: Top Merchants aggregation over the scope
    merchant_context = get_merchant_context(
        conn,
        list(display_df["merchant"].dropna().unique()),
        where_sql=where_sql,
        params=params,
        start_date=start_d_str,
        end_date=end_d_str,
    )
    merchant_data = aggregate_top_merchants(
        display_df,
        merchant_context,
        scope_total_eur=total_spent,
        month_divisor=month_divisor,
    )

    # Analytics Section inside isolated Streamlit fragment
    _render_analytics_fragment(display_df, selected_scope, conn)

    # AC-5: Top Merchants is its own panel spanning the full content width
    _render_top_merchants(merchant_data, selected_scope)

    # AC-3, AC-4: Category Budget Tracker inside isolated Streamlit fragment
    _render_budget_tracker_fragment(conn, selected_scope, start_d_str, end_d_str, monthly_df)

    # AC-5: Uncategorized Quick Triage Table
    _render_uncategorized_triage(
        conn, where_sql, params, selected_scope, start_d_str, end_d_str
    )

    # AC-6: Collapsible Cash Flow Sankey Container
    with st.expander("🌊 Cash Flow Topology (Sankey)", expanded=False):
        _render_sankey_flow(
            conn,
            display_df,
            selected_scope,
            months,
            salary_day,
            fixed_spent,
            disc_spent,
            uncat_spent,
            start_d_str,
            end_d_str,
        )

    # Monthly Trend & Summary Table
    _render_monthly_trend(monthly_df)

    conn.close()

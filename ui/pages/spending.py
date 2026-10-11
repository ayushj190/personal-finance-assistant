import pandas as pd
import streamlit as st
import numpy as np
import plotly.graph_objects as go

from config import DB_PATH
from db import database
from services.analytics import detect_recurring_charges, calculate_current_net_worth, calculate_burn_and_runway
from services.budget_service import calculate_budget_variance, set_category_budget, calculate_12_month_runway_forecast
from services.fiscal_service import (
    get_fiscal_salary_day,
    get_fiscal_month_for_date,
    get_fiscal_month_range,
    format_fiscal_month_label,
)
from ui.charts import build_monthly_spending_bar, build_spending_donut
from ui.components import format_money, is_hidden, kpi_card, section_header, status_badge
from ui.filters import build_where_clause, render_filters
from ui.pages.tax import calculate_box1_tax



def render():
    filters = render_filters()

    conn = database.connect(DB_PATH)
    salary_day = get_fiscal_salary_day(conn)

    where_sql, params = build_where_clause(filters, table_alias="t")

    # Strictly exclude internal transfers, savings/investments, and inflows from spending
    where_parts = []
    if where_sql:
        where_parts.append(where_sql.replace("WHERE ", "", 1))
    where_parts.append("t.amount_eur_minor < 0")
    where_parts.append("t.is_internal_transfer = 0")
    where_parts.append(
        "(c.kind IS NULL OR c.kind NOT IN ('savings', 'transfer', 'income'))")

    base_where = "WHERE " + " AND ".join(where_parts)

    # 1. Fetch Detailed Spending Transactions
    detail_query = f"""
    SELECT t.id,
           t.booking_date,
           t.merchant_normalized AS merchant,
           COALESCE(c.name, 'Uncategorized') AS category,
           COALESCE(p.name, c.name, 'Uncategorized') AS parent_category,
           COALESCE(c.kind, 'discretionary') AS category_kind,
           -t.amount_eur_minor / 100.0 AS amount_eur
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN categories p ON p.id = c.parent_id
    {base_where}
    ORDER BY t.booking_date DESC
    """
    df_all = pd.read_sql_query(detail_query, conn, params=params)

    if df_all.empty:
        conn.close()
        st.info("No spending transactions found for the selected filter criteria.")
        return

    # Assign fiscal month based on user's salary payday
    df_all["fiscal_month"] = df_all["booking_date"].apply(lambda d: get_fiscal_month_for_date(d, salary_day))

    # Aggregate monthly summary using fiscal months
    monthly_rows = []
    for fm, grp in df_all.groupby("fiscal_month"):
        tot = float(grp["amount_eur"].sum())
        fix = float(grp[grp["category_kind"] == "fixed"]["amount_eur"].sum())
        disc = float(grp[grp["category_kind"] == "discretionary"]["amount_eur"].sum())
        unc = float(grp[grp["category"] == "Uncategorized"]["amount_eur"].sum())
        monthly_rows.append({
            "month": fm,
            "tx_count": len(grp),
            "total_spent": tot,
            "fixed_spent": fix,
            "disc_spent": disc,
            "uncat_spent": unc,
        })
    monthly_df = pd.DataFrame(monthly_rows).sort_values(by="month", ascending=False)

    # 2. Monthly Scope Selector
    months = monthly_df["month"].tolist() if not monthly_df.empty else []
    month_options = months + ["All Months (Monthly Average)"]

    col_sel, col_salary_info = st.columns([2, 3])
    with col_sel:
        selected_scope = st.selectbox(
            "View Scope",
            options=month_options,
            index=0,
            format_func=lambda m: format_fiscal_month_label(m, salary_day) if m != "All Months (Monthly Average)" else m,
        )
    with col_salary_info:
        if salary_day > 1:
            st.caption(f"🗓️ Fiscal cycle runs Day {salary_day} to Day {salary_day - 1}. Change payday in **Settings**.")

    # Filter data according to selected scope and determine date bounds
    if selected_scope == "All Months (Monthly Average)":
        display_df = df_all.copy()
        n_months = max(1, len(months))
        total_spent = monthly_df["total_spent"].sum() / n_months
        fixed_spent = monthly_df["fixed_spent"].sum() / n_months
        disc_spent = monthly_df["disc_spent"].sum() / n_months
        uncat_spent = monthly_df["uncat_spent"].sum() / n_months
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

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Expenses",
                 f"€{total_spent:,.2f}", subtext=header_title)
    with c2:
        fixed_pct = (fixed_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Fixed Expenses",
                 f"€{fixed_spent:,.2f}", subtext=f"{fixed_pct:.1f}% of total")
    with c3:
        disc_pct = (disc_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Discretionary", f"€{disc_spent:,.2f}",
                 subtext=f"{disc_pct:.1f}% of total")
    with c4:
        uncat_pct = (uncat_spent / total_spent * 100) if total_spent > 0 else 0
        kpi_card("Uncategorized", f"€{uncat_spent:,.2f}",
                 subtext=f"{uncat_pct:.1f}% of total")

    # --- CASH FLOW SANKEY DIAGRAM ---
    if selected_scope == "All Months (Monthly Average)":
        all_inflows, all_savings = [], []
        for m_str in months:
            y_i, m_i = map(int, m_str.split("-"))
            s_d_i, e_d_i = get_fiscal_month_range(y_i, m_i, salary_day)
            cf_row = conn.execute("""
                SELECT SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 as inc,
                       SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as sav
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.is_internal_transfer = 0
                  AND t.booking_date >= ? AND t.booking_date <= ?
            """, (s_d_i.isoformat(), e_d_i.isoformat())).fetchone()
            all_inflows.append(float(cf_row["inc"] or 0.0) if cf_row else 0.0)
            all_savings.append(float(cf_row["sav"] or 0.0) if cf_row else 0.0)
        n_m = max(1, len(months))
        inc = sum(all_inflows) / n_m if all_inflows else 0.0
        sav = sum(all_savings) / n_m if all_savings else 0.0
    else:
        cf_row = conn.execute("""
            SELECT SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 as inc,
                   SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 as sav
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.is_internal_transfer = 0
              AND t.booking_date >= ? AND t.booking_date <= ?
        """, (start_d_str, end_d_str)).fetchone()
        inc = float(cf_row["inc"] or 0.0) if cf_row else 0.0
        sav = float(cf_row["sav"] or 0.0) if cf_row else 0.0

    fix = fixed_spent
    disc = disc_spent

    # Calculate Gross Salary and Taxes
    profile = conn.execute("SELECT * FROM tax_profile WHERE id = 1").fetchone()
    annual_gross = float(profile["gross_annual_income"]) if profile and profile["gross_annual_income"] else 0.0
    eff_tax_rate = 0.3697
    if annual_gross > 0:
        b1 = calculate_box1_tax(annual_gross)
        if b1["total_tax"] > 0:
            eff_tax_rate = min(0.52, max(0.20, b1["total_tax"] / annual_gross))

    if inc > 0:
        gross_salary = inc / (1.0 - eff_tax_rate)
        taxes = gross_salary - inc
        net_salary = inc
    elif annual_gross > 0:
        gross_salary = annual_gross / 12.0
        taxes = gross_salary * eff_tax_rate
        net_salary = gross_salary - taxes
    else:
        gross_salary = fix + disc + sav
        taxes = 0.0
        net_salary = gross_salary

    # Consolidated category spending for breakdown
    fixed_items = display_df[display_df["category_kind"] == "fixed"]
    if selected_scope == "All Months (Monthly Average)":
        fixed_cats = (fixed_items.groupby("parent_category")["amount_eur"].sum() / max(1, len(months))).to_dict()
    else:
        fixed_cats = fixed_items.groupby("parent_category")["amount_eur"].sum().to_dict()

    disc_items = display_df[(display_df["category_kind"] == "discretionary") & (display_df["category"] != "Uncategorized")]
    if selected_scope == "All Months (Monthly Average)":
        disc_cats = (disc_items.groupby("parent_category")["amount_eur"].sum() / max(1, len(months))).to_dict()
    else:
        disc_cats = disc_items.groupby("parent_category")["amount_eur"].sum().to_dict()

    total_out = fix + disc + sav + uncat_spent
    drawdown = max(0.0, total_out - net_salary)
    unallocated = max(0.0, net_salary - total_out)

    # Build Sankey Topology
    labels, colors, node_idx = [], [], {}

    def get_or_add_node(name: str, color: str) -> int:
        if name not in node_idx:
            node_idx[name] = len(labels)
            labels.append(name)
            colors.append(color)
        return node_idx[name]

    sources, targets, values = [], [], []

    def add_flow(src_name: str, dst_name: str, val: float, src_color: str, dst_color: str):
        if val > 0.05:
            s_i = get_or_add_node(src_name, src_color)
            d_i = get_or_add_node(dst_name, dst_color)
            sources.append(s_i)
            targets.append(d_i)
            values.append(round(val, 2))

    # Gross Salary -> Taxes & Net Income
    if gross_salary > 0:
        add_flow("Gross Salary", "Taxes (Box 1)", taxes, "#10B981", "#EF4444")
        add_flow("Gross Salary", "Net Income", net_salary, "#10B981", "#06B6D4")

    if drawdown > 0:
        add_flow("Savings Drawdown", "Net Income", drawdown, "#F43F5E", "#06B6D4")

    # Net Income -> Major Buckets
    if fix > 0:
        add_flow("Net Income", "Fixed Expenses", fix, "#06B6D4", "#FB7185")
    if disc > 0:
        add_flow("Net Income", "Discretionary", disc, "#06B6D4", "#FBBF24")
    if sav > 0:
        add_flow("Net Income", "Savings & Investments", sav, "#06B6D4", "#38BDF8")
    if uncat_spent > 0:
        add_flow("Net Income", "Uncategorized", uncat_spent, "#06B6D4", "#94A3B8")
    if unallocated > 0:
        add_flow("Net Income", "Unallocated Cash", unallocated, "#06B6D4", "#A78BFA")

    # Fixed Expenses -> Spending categories (Mortgage & Rent, Utility Bills, Insurances, Subscriptions)
    fixed_palette = ["#F43F5E", "#E11D48", "#BE123C", "#9F1239", "#FDA4AF", "#FB7185"]
    for idx_f, (cat_name, cat_val) in enumerate(sorted(fixed_cats.items(), key=lambda x: -x[1])):
        f_col = fixed_palette[idx_f % len(fixed_palette)]
        add_flow("Fixed Expenses", cat_name, cat_val, "#FB7185", f_col)

    # Discretionary -> Spending categories (Groceries, Food & Restaurants, Sports & Leisure, etc.)
    disc_palette = ["#F59E0B", "#D97706", "#B45309", "#92400E", "#FCD34D", "#FBBF24", "#78350F"]
    for idx_d, (cat_name, cat_val) in enumerate(sorted(disc_cats.items(), key=lambda x: -x[1])):
        d_col = disc_palette[idx_d % len(disc_palette)]
        add_flow("Discretionary", cat_name, cat_val, "#FBBF24", d_col)

    if values:
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=18,
                thickness=20,
                line=dict(color="#0F172A", width=0.5),
                label=labels,
                color=colors,
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
            ),
        )])
        fig.update_layout(
            title_text="Cash Flow Overview (Gross Salary → Taxes → Net Income → Category Breakdown)",
            font_size=12,
            height=460,
            margin=dict(t=40, l=10, r=10, b=10),
        )
        if is_hidden():
            fig.update_traces(hovertemplate="Censored<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

    # 5. Expense Breakdown & Top Merchants
    with section_header(f"Expense Breakdown ({selected_scope})",
                   "Hierarchical spending across categories and merchants"):
        if not display_df.empty:
            col_left, col_right = st.columns([1, 1])
        
            with col_left:
                drill_key = f"donut_drilldown_{selected_scope}"
                if drill_key not in st.session_state:
                    st.session_state[drill_key] = None

                if st.session_state[drill_key]:
                    if st.button("← Back to Categories"):
                        st.session_state[drill_key] = None
                        st.rerun()

                fig = build_spending_donut(display_df, drilldown_category=st.session_state[drill_key])
            
                selection = st.plotly_chart(
                    fig, 
                    use_container_width=True, 
                    theme=None, 
                    on_select="rerun", 
                    selection_mode="points"
                )

                if selection and hasattr(selection, "selection") and selection.selection.get("points"):
                    clicked_point = selection.selection["points"][0]
                    clicked_label = clicked_point.get("label") or clicked_point.get("x")
                
                    # Only drill down if we are at the top level
                    if st.session_state[drill_key] is None and clicked_label:
                        st.session_state[drill_key] = clicked_label
                        st.rerun()
                elif selection and isinstance(selection, dict) and selection.get("selection", {}).get("points"):
                    clicked_point = selection["selection"]["points"][0]
                    clicked_label = clicked_point.get("label") or clicked_point.get("x")
                
                    if st.session_state[drill_key] is None and clicked_label:
                        st.session_state[drill_key] = clicked_label
                        st.rerun()
            
                with section_header("Top Merchants",
                               f"Highest spending in {selected_scope}"):
                    top_merchants = display_df.groupby(
                        "merchant")["amount_eur"].sum().reset_index()
                    top_merchants = top_merchants.sort_values(
                        by="amount_eur", ascending=False).head(10)
                    top_merchants.columns = ["Merchant", "Spent (€)"]
                    if is_hidden():
                        top_merchants["Spent (€)"] = top_merchants["Spent (€)"].map(
                            lambda x: format_money(x))
                        spent_cfg = st.column_config.TextColumn(
                            "Spent (€)", disabled=True)
                    else:
                        spent_cfg = st.column_config.NumberColumn(
                            "Spent (€)", format="€%.2f", disabled=True)
                    st.dataframe(
                        top_merchants,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                            "Spent (€)": spent_cfg
                        }
                    )

            with col_right:
                with section_header("Subscription Leak Detector",
                               "Recurring services and annual commitments"):
                    all_tx_rows = [dict(r) for r in conn.execute(
                        "SELECT * FROM v_transactions ORDER BY booking_date DESC").fetchall()]
                    recurring = detect_recurring_charges(all_tx_rows)
                    if recurring:
                        rec_df = pd.DataFrame(recurring)[
                            ["merchant", "cadence", "amount_eur", "annual_cost_eur"]]
                        rec_df.columns = ["Merchant", "Cadence",
                                          "Cost / Cycle", "Annual Cost (€)"]
                        if is_hidden():
                            rec_df["Cost / Cycle"] = rec_df["Cost / Cycle"].map(
                                lambda x: format_money(x))
                            rec_df["Annual Cost (€)"] = rec_df["Annual Cost (€)"].map(
                                lambda x: format_money(x))
                            cost_cfg = st.column_config.TextColumn(
                                "Cost / Cycle", disabled=True)
                            ann_cfg = st.column_config.TextColumn(
                                "Annual Cost (€)", disabled=True)
                        else:
                            cost_cfg = st.column_config.NumberColumn(
                                "Cost / Cycle", format="€%.2f", disabled=True)
                            ann_cfg = st.column_config.NumberColumn(
                                "Annual Cost (€)", format="€%.2f", disabled=True)

                        st.dataframe(
                            rec_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Merchant": st.column_config.TextColumn("Merchant", width="medium"),
                                "Cost / Cycle": cost_cfg,
                                "Annual Cost (€)": ann_cfg
                            }
                        )
                    else:
                        st.caption("No subscriptions detected.")

            # 6. Top Uncategorized Expenses & Mortgage Assignment
    with section_header("Top Uncategorized Expenses",
                   "Review, categorize, or assign your largest uncategorized expenses to mortgage"):

        # Scope selection toggle: allow viewing for current month scope or across all months
        scope_choice = "All Filtered Months"
        if selected_scope != "All Months (Monthly Average)":
            col_sc1, _ = st.columns([2, 3])
            with col_sc1:
                scope_choice = st.radio(
                    "Uncategorized Scope",
                    options=[
                        f"Selected Month ({selected_scope})", "All Filtered Months"],
                    horizontal=True,
                    key="uncat_spending_scope_toggle",
                )

        uncat_where_parts = []
        if where_sql:
            uncat_where_parts.append(where_sql.replace("WHERE ", "", 1))
        uncat_where_parts.append("t.category_id IS NULL")
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
        else:
            cat_rows = conn.execute(
                "SELECT id, name FROM categories ORDER BY name ASC").fetchall()
            cat_names = [r["name"] for r in cat_rows]
            cat_name_to_id = {r["name"]: r["id"] for r in cat_rows}

            st.caption(
                f"Showing top {len(uncat_df)} uncategorized expenses by amount. Select a category below and click **Save Categorizations**, or use the Mortgage Assignment tool.")

            edit_df = uncat_df[["id", "booking_date",
                                "account", "merchant", "amount_eur"]].copy()
            edit_df["category"] = None

            if is_hidden():
                edit_df_display = edit_df.copy()
                edit_df_display["amount_eur"] = edit_df_display["amount_eur"].map(
                    lambda x: format_money(x))
                amount_col_cfg = st.column_config.TextColumn(
                    "Amount (€)", disabled=True)
            else:
                edit_df_display = edit_df
                amount_col_cfg = st.column_config.NumberColumn(
                    "Amount (€)", format="€%.2f", disabled=True)

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
                disabled=["id", "booking_date",
                          "account", "merchant", "amount_eur"],
                use_container_width=True,
                hide_index=True,
                key="spending_uncat_editor",
            )

            col_save, _ = st.columns([1, 3])
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
                                    database.upsert_category_rule(
                                        conn, merchant, new_cat_id, source="user")
                                if new_cat == "Mortgage":
                                    conn.execute(
                                        "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = (SELECT id FROM liabilities LIMIT 1)",
                                        (merchant,),
                                    )
                            saved_count += 1

                    if saved_count > 0:
                        st.success(
                            f"Successfully categorized {saved_count} transaction(s) and updated rules!")
                        st.rerun()

            # Dedicated Mortgage Assignment Tool
            liabilities = conn.execute("SELECT * FROM liabilities").fetchall()
            with st.expander("🏠 Assign Transaction to Mortgage Details & Tab Info", expanded=True):
                st.markdown(
                    "Link an uncategorized payment directly to your mortgage schedule and details. "
                    "This assigns the transaction to the **Mortgage** category, records it against your loan liability, "
                    "and updates the **Mortgage** tab info."
                )

                tx_options = []
                tx_lookup = {}
                for _, r in uncat_df.iterrows():
                    lbl = f"{r['booking_date']} — {format_money(r['amount_eur'])} — {r['merchant'][:45]}"
                    tx_options.append(lbl)
                    tx_lookup[lbl] = r

                cm1, cm2, cm3 = st.columns([2, 1, 1])
                with cm1:
                    chosen_tx_lbl = st.selectbox(
                        "Select Uncategorized Transaction", options=tx_options, key="mortgage_tx_select")
                    chosen_tx = tx_lookup[chosen_tx_lbl]
                with cm2:
                    if liabilities:
                        lib_map = {
                            f"{lib['name']} ({lib['lender']})": lib for lib in liabilities}
                        chosen_lib_lbl = st.selectbox("Mortgage Liability", options=list(
                            lib_map.keys()), key="mortgage_lib_select")
                        chosen_lib = lib_map[chosen_lib_lbl]
                    else:
                        chosen_lib = None
                        st.warning(
                            "No mortgage loan configured yet. Set one up in Settings or Mortgage tab.")
                with cm3:
                    payment_kind = st.selectbox(
                        "Payment Assignment",
                        options=["Monthly Installment",
                                 "Extra Repayment (Boetevrij)"],
                        key="mortgage_assign_kind",
                    )

                recalc_strat = "lower_payment"
                if payment_kind == "Extra Repayment (Boetevrij)":
                    recalc_strat = st.selectbox(
                        "Recalculation Benefit",
                        options=["lower_payment", "shorter_term"],
                        format_func=lambda x: "Lower Monthly Payment" if x == "lower_payment" else "Shorten Loan Term",
                        key="mortgage_recalc_strat",
                    )

                if st.button("Confirm Mortgage Assignment", type="primary", key="btn_confirm_mortgage_assign", disabled=chosen_lib is None):
                    mortgage_cat_id = cat_name_to_id.get("Mortgage")
                    if not mortgage_cat_id:
                        st.error("Category 'Mortgage' not found. Please create it first.")
                        return
                    
                    tx_id = int(chosen_tx["id"])
                    tx_date = str(chosen_tx["booking_date"])
                    tx_amount_minor = int(round(chosen_tx["amount_eur"] * 100))
                    tx_merchant = str(chosen_tx["merchant"])

                    with conn:
                        # 1. Update transaction category to Mortgage
                        conn.execute(
                            "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE id = ?",
                            (mortgage_cat_id, tx_id),
                        )
                        # 2. Update merchant category rule
                        if tx_merchant:
                            database.upsert_category_rule(
                                conn, tx_merchant, mortgage_cat_id, source="user")

                        # 3. Save payment match pattern on liability if unset
                        conn.execute(
                            "UPDATE liabilities SET payment_match_pattern = COALESCE(payment_match_pattern, ?) WHERE id = ?",
                            (tx_merchant, chosen_lib["id"]),
                        )

                        # 4. If extra repayment, record in liability_extra_payments
                        if payment_kind == "Extra Repayment (Boetevrij)":
                            conn.execute(
                                """
                                INSERT INTO liability_extra_payments (liability_id, paid_date, amount_minor, recalc)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(liability_id, paid_date) DO UPDATE SET
                                    amount_minor = excluded.amount_minor,
                                    recalc = excluded.recalc
                                """,
                                (chosen_lib["id"], tx_date,
                                 tx_amount_minor, recalc_strat),
                            )

                    # Resync schedule if extra payment
                    if payment_kind == "Extra Repayment (Boetevrij)":
                        from services.mortgage import sync_liability_schedule
                        sync_liability_schedule(conn, chosen_lib["id"])

                    st.success(
                        f"Successfully assigned {format_money(chosen_tx['amount_eur'])} on {tx_date} to {chosen_lib['name']}! "
                        f"View detailed breakdown on the Mortgage tab."
                    )
                    st.rerun()

        # --- Monthly Trend Chart & Summary Table (Moved to bottom) ---
    with section_header("Monthly Expenses Trend",
                   "Month-by-month spending broken down by expense kind"):
        col_chart, col_tbl = st.columns([2, 3])
        with col_chart:
            st.plotly_chart(build_monthly_spending_bar(monthly_df),
                            use_container_width=True, theme=None)
        with col_tbl:
            tbl_df = monthly_df[["month", "total_spent",
                                 "fixed_spent", "disc_spent", "uncat_spent"]].copy()
        
            # Add MoM change and percentages
            tbl_df["prev_total"] = tbl_df["total_spent"].shift(-1)
        
            tbl_df["MoM Change (%)"] = np.where(
                tbl_df["prev_total"] == 0, 
                0, 
                ((tbl_df["total_spent"] - tbl_df["prev_total"]) / tbl_df["prev_total"] * 100)
            )
        
            tot = tbl_df["total_spent"].mask(tbl_df["total_spent"] == 0, 1)
            tbl_df["Fixed (%)"] = (tbl_df["fixed_spent"] / tot * 100).fillna(0)
            tbl_df["Disc. (%)"] = (tbl_df["disc_spent"] / tot * 100).fillna(0)
        
            tbl_df = tbl_df[["month", "total_spent", "MoM Change (%)", "Fixed (%)", "Disc. (%)", "uncat_spent"]]
            tbl_df.columns = [
                "Month", "Total (€)", "MoM Change (%)", "Fixed (%)", "Disc. (%)", "Uncategorized (€)"]
        
            if is_hidden():
                for col in ["Total (€)", "Uncategorized (€)"]:
                    tbl_df[col] = tbl_df[col].map(lambda x: format_money(x))
                for col in ["MoM Change (%)", "Fixed (%)", "Disc. (%)"]:
                    tbl_df[col] = tbl_df[col].map(lambda x: "***")
                st.dataframe(tbl_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(
                    tbl_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Total (€)": st.column_config.NumberColumn("Total (€)", format="€%.2f"),
                        "MoM Change (%)": st.column_config.NumberColumn("MoM Change (%)", format="%+.1f%%"),
                        "Fixed (%)": st.column_config.NumberColumn("Fixed (%)", format="%.1f%%"),
                        "Disc. (%)": st.column_config.NumberColumn("Disc. (%)", format="%.1f%%"),
                        "Uncategorized (€)": st.column_config.NumberColumn("Uncategorized (€)", format="€%.2f"),
                    }
                )

        # --- Category Budgeting & Variance Section ---
    with section_header("Category Budget Tracker & Variance", "Track monthly targets and spending discipline"):
        b_data = calculate_budget_variance(
            conn,
            year_month=selected_scope if selected_scope != "All Months (Monthly Average)" else None,
            start_date=start_d_str,
            end_date=end_d_str,
        )

        b1, b2, b3 = st.columns(3)
        with b1:
            tot_b_str = "€****" if is_hidden() else f"€{b_data['total_budget_eur']:,.2f}"
            kpi_card("Monthly Budget", tot_b_str, subtext="Target cap across categories")
        with b2:
            tot_s_str = "€****" if is_hidden() else f"€{b_data['total_spent_eur']:,.2f}"
            kpi_card("Current Spend", tot_s_str, subtext=f"Total spent in {b_data['month']}")
        with b3:
            var_val = b_data['variance_eur']
            var_sub = "Within budget" if var_val >= 0 else "Over budget"
            var_str = "€****" if is_hidden() else f"€{abs(var_val):,.2f} {'left' if var_val >= 0 else 'deficit'}"
            kpi_card("Budget Variance", var_str, subtext=var_sub)

        col_b_tbl, col_b_edit = st.columns([3, 1])
        with col_b_tbl:
            cat_df = b_data["categories_df"]
            if not cat_df.empty:
                disp_filter = cat_df["is_parent"] | (cat_df["budget_eur"] > 0) | (cat_df["spent_eur"] > 0)
                disp_df_sub = cat_df[disp_filter].copy() if any(disp_filter) else cat_df.copy()
                disp_b = disp_df_sub[["category", "kind", "budget_eur", "spent_eur", "remaining_eur", "pct_used", "status"]].copy()
                disp_b.columns = ["Category", "Type", "Budget (€)", "Spent (€)", "Remaining (€)", "% Used", "Status"]
                if is_hidden():
                    disp_b["Budget (€)"] = "€****"
                    disp_b["Spent (€)"] = "€****"
                    disp_b["Remaining (€)"] = "€****"
                    disp_b["% Used"] = "***"
                    disp_b["Category"] = "****"
                else:
                    disp_b["Budget (€)"] = disp_b["Budget (€)"].map(lambda x: f"€{x:,.2f}" if x > 0 else "—")
                    disp_b["Spent (€)"] = disp_b["Spent (€)"].map(lambda x: f"€{x:,.2f}")
                    disp_b["Remaining (€)"] = disp_b["Remaining (€)"].map(lambda x: f"€{x:,.2f}" if x != 0 else "—")
                    disp_b["% Used"] = disp_b["% Used"].map(lambda x: f"{x:.0f}%" if x > 0 else "0%")
                st.dataframe(disp_b, use_container_width=True, hide_index=True)

        with col_b_edit:
            with st.popover("✏️ Set Category Budgets", use_container_width=True):
                st.caption("Update monthly spending caps")
                with st.form("set_cat_budget_form"):
                    parent_cats = conn.execute(
                        "SELECT id, name FROM categories WHERE parent_id IS NULL AND kind IN ('fixed', 'discretionary') ORDER BY name ASC"
                    ).fetchall()
                    sub_cats = conn.execute(
                        "SELECT id, name FROM categories WHERE parent_id IS NOT NULL AND kind IN ('fixed', 'discretionary') ORDER BY name ASC"
                    ).fetchall()
                    cat_options = {}
                    for p in parent_cats:
                        cat_options[p["id"]] = f"⭐ {p['name']} (Main Category)"
                    for s in sub_cats:
                        cat_options[s["id"]] = f"   ↳ {s['name']}"

                    selected_cat_id = st.selectbox(
                        "Category",
                        options=list(cat_options.keys()),
                        format_func=lambda x: cat_options[x],
                    )
                    curr_bud = 0.0
                    if selected_cat_id:
                        matched = cat_df[cat_df["category_id"] == selected_cat_id]
                        if not matched.empty:
                            curr_bud = float(matched["budget_eur"].iloc[0])
                    new_limit = st.number_input(
                        "Monthly Limit (€)",
                        min_value=0.0,
                        value=curr_bud,
                        step=50.0,
                        format="%.2f",
                    )
                    if st.form_submit_button("Save Budget", type="primary"):
                        set_category_budget(conn, selected_cat_id, new_limit)
                        st.success(f"Updated budget for {cat_options[selected_cat_id]}!")
                        st.rerun()

        # --- 12-Month Runway Projection Chart ---
        st.markdown("#### 📈 12-Month Financial Trajectory Projection")
        nw_data = calculate_current_net_worth(conn)
        liq_cash = nw_data["liquid_cash"]
    
        # Estimate income and burn
        inc_row = conn.execute(
            "SELECT AVG(monthly_inc) as avg_inc FROM (SELECT SUM(amount_eur) as monthly_inc FROM v_transactions WHERE category_kind = 'income' AND is_internal_transfer = 0 GROUP BY strftime('%Y-%m', booking_date) ORDER BY strftime('%Y-%m', booking_date) DESC LIMIT 6)"
        ).fetchone()
        avg_income = float(inc_row["avg_inc"] or 0.0) if inc_row else 0.0

        cur_burn = float(monthly_df["total_spent"].iloc[0]) if not monthly_df.empty else 0.0
        bud_burn = float(b_data["total_budget_eur"]) if b_data["total_budget_eur"] > 0 else cur_burn

        forecast_data = calculate_12_month_runway_forecast(
            liquid_cash=liq_cash,
            projected_monthly_income=avg_income,
            current_burn_rate=cur_burn,
            budgeted_burn_rate=bud_burn,
            horizon_months=12,
        )

        if forecast_data:
            f_df = pd.DataFrame(forecast_data)
            f_fig = go.Figure()
            f_fig.add_trace(go.Scatter(
                x=f_df["month_label"],
                y=f_df["current_spend_balance_eur"],
                mode="lines+markers",
                name="Current Burn Trajectory",
                line=dict(color="#FB7185", width=2.5),
            ))
            f_fig.add_trace(go.Scatter(
                x=f_df["month_label"],
                y=f_df["budgeted_spend_balance_eur"],
                mode="lines+markers",
                name="Budgeted Target Trajectory",
                line=dict(color="#2DD4BF", width=2.5, dash="dash"),
            ))
            f_fig.update_layout(
                title="12-Month Cash Buffer Trajectory (Current vs Target Budget)",
                xaxis_title="Timeline",
                yaxis_title="Projected Cash Balance (€)",
                margin=dict(t=35, l=10, r=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            if is_hidden():
                f_fig.update_traces(hovertemplate="Censored<extra></extra>")
            st.plotly_chart(f_fig, use_container_width=True)

        conn.close()


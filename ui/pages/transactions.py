import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from ui.filters import build_where_clause, render_filters


def render():
    filters = render_filters()

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

    # Filter toggles
    c_f1, c_f2 = st.columns([1, 2])
    with c_f1:
        only_uncategorized = st.checkbox(
            "Review Uncategorized Only", value=False)
    with c_f2:
        search_query = st.text_input(
            "Search merchant or description", placeholder="Filter by text...")

    extra_clauses = []
    if only_uncategorized:
        extra_clauses.append("t.category_id IS NULL")
    if search_query.strip():
        extra_clauses.append(
            "(t.merchant_normalized LIKE ? OR t.description_raw LIKE ?)")
        params.extend([f"%{search_query.strip()}%",
                      f"%{search_query.strip()}%"])

    if extra_clauses:
        prefix = "WHERE " if not where_sql else f"{where_sql} AND "
        where_sql = prefix + " AND ".join(extra_clauses)

    query = f"""
    SELECT t.id, t.booking_date, a.name AS account,
           t.amount_eur_minor / 100.0 AS amount_eur,
           COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
           c.name AS category,
           t.is_internal_transfer
    FROM transactions t
    JOIN accounts a ON a.id = t.account_id
    LEFT JOIN categories c ON c.id = t.category_id
    {where_sql}
    ORDER BY t.booking_date DESC
    LIMIT 200
    """

    df = pd.read_sql_query(query, conn, params=params)

    # Categories list for dropdown
    cat_rows = conn.execute(
        "SELECT id, name FROM categories ORDER BY name ASC").fetchall()
    cat_names = [r["name"] for r in cat_rows]
    cat_name_to_id = {r["name"]: r["id"] for r in cat_rows}

    st.markdown(
        f"**Showing {len(df)} transactions** (editing category updates rules for merchant)")

    # Data Editor with Privacy Mode support
    from ui.components import format_money, is_hidden

    df_display = df.copy()
    if not df_display.empty:
        df_display.insert(0, "select", False)

    if is_hidden():
        df_display["amount_eur"] = df_display["amount_eur"].map(
            lambda x: format_money(x))
        df_display["merchant"] = "****"
        amount_col_cfg = st.column_config.TextColumn(
            "Amount (€)", disabled=True)
    else:
        amount_col_cfg = st.column_config.NumberColumn(
            "Amount (€)", format="€%.2f", disabled=True)

    edited_df = st.data_editor(
        df_display,
        column_config={
            "select": st.column_config.CheckboxColumn("Select", help="Check to select transaction to delete", default=False),
            "id": None,
            "booking_date": st.column_config.DateColumn("Transaction Date"),
            "account": st.column_config.TextColumn("Account / Card", disabled=True),
            "amount_eur": amount_col_cfg,
            "merchant": st.column_config.TextColumn("Merchant / Payee", width="medium", disabled=True),
            "category": st.column_config.SelectboxColumn("Category", options=cat_names, required=True),
            "is_internal_transfer": st.column_config.CheckboxColumn("Internal Transfer"),
        },
        disabled=["id", "booking_date", "account", "amount_eur", "merchant"],
        use_container_width=True,
        hide_index=True,
        key="tx_editor",
    )

    # Check for selected rows to delete
    selected_ids = []
    if not edited_df.empty and "select" in edited_df.columns:
        selected_mask = edited_df["select"] == True
        if selected_mask.any():
            selected_ids = [int(i) for i in edited_df.loc[selected_mask, "id"].tolist()]

    col_save, col_del, _ = st.columns([1, 1, 2])
    with col_save:
        save_pressed = st.button("Save Changes", type="primary")
    with col_del:
        if selected_ids:
            delete_pressed = st.button(
                f"🗑️ Delete Selected ({len(selected_ids)})",
                type="secondary",
                help="Delete checked transactions from database"
            )
        else:
            delete_pressed = False

    if delete_pressed and selected_ids:
        deleted_count = database.delete_transactions(conn, selected_ids)
        st.success(f"Successfully deleted {deleted_count} transaction(s)!")
        st.rerun()

    # Check for edits
    if save_pressed:
        # Compare original df with edited_df
        updated_rules = 0
        for idx, row in edited_df.iterrows():
            orig_cat = df.loc[idx, "category"]
            new_cat = row["category"]
            merchant = df.loc[idx, "merchant"]

            if new_cat and new_cat != orig_cat and merchant:
                new_cat_id = cat_name_to_id.get(new_cat)
                if new_cat_id:
                    # 1. Upsert user rule for this merchant
                    database.upsert_category_rule(
                        conn, merchant, new_cat_id, source="user", confidence=1.0)
                    # 2. Update all past transactions for this merchant
                    with conn:
                        conn.execute(
                            "UPDATE transactions SET category_id = ?, category_source = 'user' WHERE merchant_normalized = ?",
                            (new_cat_id, merchant),
                        )
                    updated_rules += 1

        if updated_rules > 0:
            st.success(
                f"Successfully updated categories and saved {updated_rules} merchant rules!")
            st.rerun()

    conn.close()

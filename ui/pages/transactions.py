import pandas as pd
import streamlit as st

from config import DB_PATH
from db import database
from ui.components import format_money, is_hidden
from ui.dialogs import confirm_delete_transactions_dialog
from ui.filters import build_where_clause, render_filters


def render():
    col_filt, col_uncat, col_search = st.columns([1, 1.4, 2.6], vertical_alignment="bottom")
    with col_filt:
        filters = render_filters()
    with col_uncat:
        only_uncategorized = st.checkbox(
            "Review Uncategorized Only", value=False)
    with col_search:
        search_query = st.text_input(
            "Search merchant or description", placeholder="Filter by text...", label_visibility="collapsed")

    conn = database.connect(DB_PATH)
    where_sql, params = build_where_clause(filters, table_alias="t")

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

    col_count, col_sel_all, col_clear_all = st.columns([4, 1.2, 1.2], vertical_alignment="center")
    with col_count:
        st.markdown(
            f"**Showing {len(df)} transactions** (editing category updates rules for merchant)"
        )
    with col_sel_all:
        if st.button("Select All", key="tx_select_all_btn", use_container_width=True):
            st.session_state["tx_select_all_flag"] = True
            st.session_state["tx_editor_version"] = st.session_state.get("tx_editor_version", 0) + 1
            st.rerun()
    with col_clear_all:
        if st.button("Clear All", key="tx_clear_all_btn", use_container_width=True):
            st.session_state["tx_select_all_flag"] = False
            st.session_state["tx_editor_version"] = st.session_state.get("tx_editor_version", 0) + 1
            st.rerun()

    df_display = df.copy()
    if not df_display.empty:
        default_select = st.session_state.get("tx_select_all_flag", False)
        df_display.insert(0, "select", default_select)

    if is_hidden():
        df_display["amount_eur"] = df_display["amount_eur"].map(
            lambda x: format_money(x))
        df_display["merchant"] = "****"
        amount_col_cfg = st.column_config.TextColumn(
            "Amount (€)", disabled=True)
    else:
        amount_col_cfg = st.column_config.NumberColumn(
            "Amount (€)", format="€%.2f", disabled=True)

    editor_key = f"tx_editor_{st.session_state.get('tx_editor_version', 0)}"
    edited_df = st.data_editor(
        df_display,
        column_config={
            "select": st.column_config.CheckboxColumn("Select", help="Check to select transactions for bulk actions", default=False),
            "id": None,
            "booking_date": st.column_config.DateColumn("Transaction Date"),
            "account": st.column_config.TextColumn("Account / Card", disabled=True),
            "amount_eur": amount_col_cfg,
            "merchant": st.column_config.TextColumn("Merchant / Payee", width="medium", disabled=True),
            "category": st.column_config.SelectboxColumn("Category", options=cat_names, required=True),
            "is_internal_transfer": None,
        },
        disabled=["id", "booking_date", "account", "amount_eur", "merchant"],
        use_container_width=True,
        hide_index=True,
        key=editor_key,
    )

    # Check for selected rows
    selected_ids = []
    if not edited_df.empty and "select" in edited_df.columns:
        selected_mask = edited_df["select"] == True
        if selected_mask.any():
            selected_ids = [int(i) for i in edited_df.loc[selected_mask, "id"].tolist()]

    # Persistent bottom action bar when rows are selected
    if selected_ids:
        st.markdown("---")
        st.markdown(f"#### ⚡ Batch Actions ({len(selected_ids)} selected)")
        col_tf1, col_tf2, col_cat_picker, col_cat_rule, col_cat_btn, col_del = st.columns(
            [1.3, 1.3, 2.2, 1.8, 1.0, 1.4], vertical_alignment="bottom"
        )
        with col_tf1:
            if st.button("🔄 Mark Transfer", use_container_width=True, help="Mark selected rows as internal transfers and assign Transfer category"):
                count = database.set_transactions_internal_transfer(conn, selected_ids, is_transfer=True)
                st.success(f"Marked {count} transaction(s) as internal transfers.")
                st.rerun()
        with col_tf2:
            if st.button("↩️ Unmark Transfer", use_container_width=True, help="Revert selected rows internal transfer flag to 0"):
                count = database.set_transactions_internal_transfer(conn, selected_ids, is_transfer=False)
                st.success(f"Unmarked {count} transaction(s) from internal transfers.")
                st.rerun()
        with col_cat_picker:
            selected_category = st.selectbox(
                "Bulk Category",
                options=cat_names,
                label_visibility="collapsed",
                placeholder="Choose category...",
                key="bulk_cat_select",
            )
        with col_cat_rule:
            upsert_rules = st.checkbox("Update rules", value=True, help="Upsert merchant category rules for future imports", key="bulk_cat_rules")
        with col_cat_btn:
            if st.button("Apply", type="primary", use_container_width=True, key="bulk_cat_apply"):
                if selected_category and selected_category in cat_name_to_id:
                    target_cat_id = cat_name_to_id[selected_category]
                    count = database.bulk_categorize_transactions(
                        conn,
                        selected_ids,
                        target_cat_id,
                        source="user",
                        update_rules=upsert_rules,
                    )
                    st.success(f"Updated category for {count} transaction(s).")
                    st.rerun()
        with col_del:
            if st.button(f"🗑️ Delete ({len(selected_ids)})", type="secondary", use_container_width=True, key="bulk_del_btn"):
                confirm_delete_transactions_dialog(selected_ids)
    else:
        st.caption("💡 Select rows using checkboxes to mark internal transfers, bulk categorize, or delete.")

    col_save, _ = st.columns([1.5, 4.5])
    with col_save:
        save_pressed = st.button("Save Inline Edits", type="secondary", key="btn_save_tx_inline")

    # Check for edits
    if save_pressed:
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


"""Copilot confirm gated write tools (AC-8).

Each tool's first call returns a proposal and a stateless confirmation token (a
hash of the exact proposed arguments, the allocation delete pattern) and changes
nothing. On your yes the model calls the tool again with that token to perform the
write; a token whose arguments no longer match is refused. Writes happen only
inside these named, validated functions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from config import DB_PATH
from db import database
from db.repositories import TransactionRepository
from services.budget_service import set_category_budget


def _args_token(name: str, *parts: Any) -> str:
    """Deterministic token over the exact proposed arguments (AC-8)."""
    payload = json.dumps([name, *parts], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _refused() -> dict[str, Any]:
    return {
        "success": False,
        "message": (
            "That confirmation token no longer matches the proposed change, so nothing "
            "was changed. Ask me again and I will show the current proposal."
        ),
    }


def _resolve_category_id(conn: Any, category: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) LIMIT 1",
        (str(category or "").strip(),),
    ).fetchone()
    if not row:
        return None
    return int(row["id"]) if isinstance(row, dict) or hasattr(row, "keys") else int(row[0])


def _resolve_target_ids(conn: Any, transaction_ids: Any, tx_filter: Any) -> list[int]:
    if transaction_ids:
        return sorted(int(i) for i in transaction_ids)
    if not isinstance(tx_filter, dict):
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if tx_filter.get("uncategorized"):
        clauses.append("category_id IS NULL")
    if tx_filter.get("merchant"):
        clauses.append("merchant_normalized LIKE ?")
        params.append(f"%{tx_filter['merchant']}%")
    if tx_filter.get("category"):
        clauses.append(
            "category_id = (SELECT id FROM categories WHERE LOWER(name) = LOWER(?) LIMIT 1)"
        )
        params.append(tx_filter["category"])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT id FROM transactions {where} ORDER BY booking_date DESC LIMIT 500", params
    ).fetchall()
    return sorted(
        int(r["id"]) if hasattr(r, "keys") else int(r[0]) for r in rows
    )


def tool_categorize_transactions(
    category: str,
    transaction_ids: Iterable[int] | None = None,
    tx_filter: dict[str, Any] | None = None,
    confirm_token: str = "",
) -> dict[str, Any]:
    """Categorize transactions after confirmation (AC-8)."""
    clean_category = str(category or "").strip()
    if not clean_category:
        return {"success": False, "message": "A category name is required."}

    conn = database.connect(DB_PATH)
    try:
        cat_id = _resolve_category_id(conn, clean_category)
        if cat_id is None:
            return {
                "success": False,
                "message": f"Unknown category '{clean_category}'. Ask for the category list first.",
            }
        ids = _resolve_target_ids(conn, transaction_ids, tx_filter)
        if not ids:
            return {
                "success": False,
                "message": "No transactions matched, so there is nothing to categorize.",
            }
        token = _args_token("categorize_transactions", clean_category, ids)
        if not confirm_token:
            return {
                "success": True,
                "proposal": {"category": clean_category, "count": len(ids), "transaction_ids": ids},
                "confirm_token": token,
                "message": (
                    f"I will set the category of {len(ids)} transaction(s) to "
                    f"'{clean_category}'. Reply to confirm and I will call "
                    f"categorize_transactions again with confirm_token='{token}'."
                ),
            }
        if confirm_token != token:
            return _refused()
        updated = database.bulk_categorize_transactions(
            conn, ids, cat_id, source="user", update_rules=True
        )
    finally:
        conn.close()

    return {
        "success": True,
        "updated": updated,
        "category": clean_category,
        "message": f"Categorized {updated} transaction(s) as '{clean_category}'.",
    }


def tool_mark_as_transfer(
    transaction_ids: Iterable[int],
    confirm_token: str = "",
) -> dict[str, Any]:
    """Mark transactions as internal transfers after confirmation (AC-8)."""
    ids = sorted(int(i) for i in (transaction_ids or []))
    if not ids:
        return {"success": False, "message": "At least one transaction id is required."}
    token = _args_token("mark_as_transfer", ids)
    if not confirm_token:
        return {
            "success": True,
            "proposal": {"count": len(ids), "transaction_ids": ids},
            "confirm_token": token,
            "message": (
                f"I will mark {len(ids)} transaction(s) as internal transfers. Reply to "
                f"confirm and I will call mark_as_transfer again with confirm_token='{token}'."
            ),
        }
    if confirm_token != token:
        return _refused()

    conn = database.connect(DB_PATH)
    try:
        updated = database.set_transactions_internal_transfer(conn, ids, is_transfer=True)
    finally:
        conn.close()
    return {
        "success": True,
        "updated": updated,
        "message": f"Marked {updated} transaction(s) as internal transfers.",
    }


def tool_edit_transaction(
    transaction_id: int,
    category: str | None = None,
    description: str | None = None,
    confirm_token: str = "",
) -> dict[str, Any]:
    """Edit one transaction's category or description after confirmation (AC-8)."""
    try:
        tid = int(transaction_id)
    except (TypeError, ValueError):
        return {"success": False, "message": f"Invalid transaction id '{transaction_id}'."}
    clean_category = str(category).strip() if category else None
    clean_description = str(description).strip() if description else None
    if not clean_category and not clean_description:
        return {"success": False, "message": "Provide a category or a description to change."}

    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM transactions WHERE id = ?", (tid,)
        ).fetchone()
        if not row:
            return {"success": False, "message": f"No transaction with id {tid}."}
        cat_id = None
        if clean_category:
            cat_id = _resolve_category_id(conn, clean_category)
            if cat_id is None:
                return {
                    "success": False,
                    "message": f"Unknown category '{clean_category}'.",
                }

        token = _args_token("edit_transaction", tid, clean_category, clean_description)
        if not confirm_token:
            return {
                "success": True,
                "proposal": {
                    "transaction_id": tid,
                    "category": clean_category,
                    "description": clean_description,
                },
                "confirm_token": token,
                "message": (
                    f"I will update transaction {tid}. Reply to confirm and I will call "
                    f"edit_transaction again with confirm_token='{token}'."
                ),
            }
        if confirm_token != token:
            return _refused()

        if cat_id is not None:
            database.bulk_categorize_transactions(conn, [tid], cat_id, source="user")
        if clean_description:
            with conn:
                conn.execute(
                    "UPDATE transactions SET description_raw = ? WHERE id = ?",
                    (clean_description, tid),
                )
    finally:
        conn.close()
    return {
        "success": True,
        "transaction_id": tid,
        "message": f"Updated transaction {tid}.",
    }


def tool_delete_transaction(
    transaction_id: int,
    confirm_token: str = "",
) -> dict[str, Any]:
    """Delete one transaction after confirmation (AC-8)."""
    try:
        tid = int(transaction_id)
    except (TypeError, ValueError):
        return {"success": False, "message": f"Invalid transaction id '{transaction_id}'."}

    token = _args_token("delete_transaction", tid)
    if not confirm_token:
        conn = database.connect(DB_PATH)
        try:
            row = conn.execute(
                """
                SELECT t.id, t.booking_date, COALESCE(NULLIF(t.merchant_normalized, ''), t.description_raw) AS merchant,
                       -t.amount_eur_minor / 100.0 AS amount_eur
                FROM transactions t WHERE t.id = ?
                """,
                (tid,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return {"success": False, "message": f"No transaction with id {tid}."}
        proposal = {
            "transaction_id": tid,
            "date": str(row["booking_date"])[:10],
            "merchant": row["merchant"],
            "amount_eur": round(float(row["amount_eur"] or 0.0), 2),
        }
        return {
            "success": True,
            "proposal": proposal,
            "confirm_token": token,
            "message": (
                f"I will delete '{proposal['merchant']}' on {proposal['date']} for "
                f"€{proposal['amount_eur']:,.2f}. Reply to confirm and I will call "
                f"delete_transaction again with confirm_token='{token}'."
            ),
        }
    if confirm_token != token:
        return _refused()

    conn = database.connect(DB_PATH)
    try:
        ok = TransactionRepository.delete_transaction(conn, tid)
    finally:
        conn.close()
    return {
        "success": True,
        "deleted": bool(ok),
        "message": (
            f"Deleted transaction {tid}." if ok else f"Transaction {tid} was already gone."
        ),
    }


def tool_set_budget_cap(
    category: str,
    cap_eur: float,
    confirm_token: str = "",
) -> dict[str, Any]:
    """Set a category monthly budget cap after confirmation (AC-8)."""
    clean_category = str(category or "").strip()
    if not clean_category:
        return {"success": False, "message": "A category name is required."}
    try:
        cap = round(float(cap_eur), 2)
    except (TypeError, ValueError):
        return {"success": False, "message": f"Invalid cap '{cap_eur}'."}
    if cap < 0:
        return {"success": False, "message": "A budget cap cannot be negative."}

    conn = database.connect(DB_PATH)
    try:
        cat_id = _resolve_category_id(conn, clean_category)
        if cat_id is None:
            return {"success": False, "message": f"Unknown category '{clean_category}'."}

        token = _args_token("set_budget_cap", clean_category, cap)
        if not confirm_token:
            return {
                "success": True,
                "proposal": {"category": clean_category, "cap_eur": cap},
                "confirm_token": token,
                "message": (
                    f"I will set the monthly budget for '{clean_category}' to €{cap:,.2f}. "
                    f"Reply to confirm and I will call set_budget_cap again with "
                    f"confirm_token='{token}'."
                ),
            }
        if confirm_token != token:
            return _refused()
        set_category_budget(conn, cat_id, cap)
    finally:
        conn.close()
    return {
        "success": True,
        "category": clean_category,
        "cap_eur": cap,
        "message": f"Set the monthly budget for '{clean_category}' to €{cap:,.2f}.",
    }

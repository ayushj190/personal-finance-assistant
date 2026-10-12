from datetime import date
from typing import Any
import streamlit as st

from config import DB_PATH
from db import database
from money import Money
from services.analytics import calculate_current_net_worth
from ui import state


def tool_get_current_net_worth() -> dict[str, Any]:
    """Calculate and return the user's real-time net worth, including liquid cash, investments, and home equity."""
    conn = database.connect_readonly(DB_PATH)
    try:
        nw_data = calculate_current_net_worth(conn)
        acc_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        if acc_count == 0 and nw_data["net_worth"] == 0:
            guidance = (
                "No financial accounts configured yet. Import a bank or broker statement via "
                "'📎 Import' in the sidebar or add manual accounts on the Dashboard."
            )
            return {
                "success": True,
                "liquid_cash_eur": 0.0,
                "investments_eur": 0.0,
                "home_equity_eur": 0.0,
                "net_worth_eur": 0.0,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"Your current net worth is €0.00. {guidance}",
            }
        return {
            "success": True,
            "liquid_cash_eur": nw_data["liquid_cash"],
            "investments_eur": nw_data["invested"],
            "home_equity_eur": nw_data["home_equity"],
            "net_worth_eur": nw_data["net_worth"],
            "message": f"Your current net worth is €{nw_data['net_worth']:,.2f}.",
        }
    finally:
        conn.close()


def tool_toggle_privacy_mode(enable: bool | None = None) -> dict[str, Any]:
    """Toggle or set privacy mode (hide or show financial amounts)."""
    current = bool(state.get(state.K.PRIVACY_HIDDEN, False))
    new_val = not current if enable is None else bool(enable)
    state.set(state.K.PRIVACY_HIDDEN, new_val)
    state.set(state.K.GLOBAL_PRIVACY_TOGGLE, new_val)
    state_str = "ENABLED (Amounts hidden)" if new_val else "DISABLED (Amounts visible)"
    return {"success": True, "message": f"Privacy mode is now {state_str}."}


def tool_set_theme(theme: str) -> dict[str, Any]:
    """Set app theme to 'dark' or 'light'."""
    clean_theme = theme.lower().strip()
    if clean_theme not in ("dark", "light"):
        return {"success": False, "message": "Theme must be either 'dark' or 'light'."}
    state.set(state.K.THEME, clean_theme)
    state.set("global_theme_toggle", (clean_theme == "light"))
    return {"success": True, "message": f"App theme switched to {clean_theme} mode."}


def tool_update_savings_rate(
    institution_or_name: str,
    apy_pct: float,
    balance_eur: float | None = None,
) -> dict[str, Any]:
    """Update Annual Percentage Yield (APY) interest rate or balance for a savings/cash account."""
    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT id, institution, name, apy FROM accounts
            WHERE asset_class = 'cash' AND (LOWER(institution) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?))
            LIMIT 1
            """,
            (f"%{institution_or_name.strip()}%", f"%{institution_or_name.strip()}%"),
        ).fetchone()

        if not row:
            accounts = conn.execute(
                "SELECT institution, name FROM accounts WHERE asset_class = 'cash'"
            ).fetchall()
            names = [f"{a['institution']} - {a['name']}" for a in accounts]
            return {
                "success": False,
                "message": f"Cash account '{institution_or_name}' not found. Available cash accounts: {', '.join(names)}",
            }

        acc_id = row["id"]
        with conn:
            conn.execute("UPDATE accounts SET apy = ? WHERE id = ?", (apy_pct, acc_id))
            if balance_eur is not None:
                b_minor = Money.from_major(balance_eur).cents
                database.upsert_snapshots(
                    conn,
                    [{
                        "account_id": acc_id,
                        "snapshot_date": date.today().isoformat(),
                        "balance_minor": b_minor,
                        "balance_eur_minor": b_minor,
                    }],
                )

        msg = f"Updated {row['institution']} ({row['name']}) APY to {apy_pct:.2f}%."
        if balance_eur is not None:
            msg += f" Current balance recorded as €{balance_eur:,.2f}."
        return {"success": True, "message": msg}
    finally:
        conn.close()


def tool_request_profile_form(form_type: str) -> dict[str, Any]:
    """Request the UI to render an interactive form for the user to fill out. Valid form_types: 'tax_profile', 'risk_profile'"""
    return {
        "success": True,
        "form_request": form_type,
        "message": f"Displaying the {form_type.replace('_', ' ')} form..."
    }

import json
from typing import Any
import pandas as pd

from config import DB_PATH
from db import database
from db.repositories import AccountRepository, HoldingRepository
from money import Money
from services.allocation_service import (
    create_allocation_profile,
    delete_allocation_profile,
    list_allocation_profiles,
)
from services.portfolio import calculate_drift, get_consolidated_holdings_df


def tool_set_active_allocation_profile(profile_name: str) -> dict[str, Any]:
    """Set the active investment asset allocation profile by name."""
    conn = database.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id, name, dimension, drift_band_pct FROM allocation_profiles WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{profile_name.strip()}%",),
        ).fetchone()
        if not row:
            profiles = conn.execute("SELECT name FROM allocation_profiles").fetchall()
            available = [p["name"] for p in profiles]
            return {
                "success": False,
                "message": f"Profile '{profile_name}' not found. Available profiles: {', '.join(available)}",
            }

        with conn:
            conn.execute("UPDATE allocation_profiles SET is_active = 0")
            conn.execute("UPDATE allocation_profiles SET is_active = 1 WHERE id = ?", (row["id"],))

        return {
            "success": True,
            "message": f"Active allocation profile set to '{row['name']}' (Dimension: {row['dimension']}, Tolerance: ±{row['drift_band_pct']}pp).",
        }
    finally:
        conn.close()


def tool_save_risk_profile(
    risk_score: int,
    risk_tolerance: str,
    notes: str = "",
    answers: dict[str, str] | None = None,
    investment_horizon_years: int | None = None,
    liquidity_needs: str | None = None,
    investment_experience: str | None = None,
) -> dict[str, Any]:
    """Save user investment risk assessment profile to the database."""
    conn = database.connect(DB_PATH)
    try:
        score = max(1, min(10, int(risk_score))) if risk_score is not None else 5
        risk_tolerance = risk_tolerance.strip() if risk_tolerance else "Moderate"
        notes = notes.strip() if notes else ""
        p_id = database.save_risk_profile(
            conn,
            risk_score=score,
            risk_tolerance=risk_tolerance.strip(),
            notes=notes.strip(),
            answers=answers or {},
            investment_horizon_years=investment_horizon_years,
            liquidity_needs=liquidity_needs,
            investment_experience=investment_experience,
        )
        return {
            "success": True,
            "profile_id": p_id,
            "risk_score": score,
            "risk_tolerance": risk_tolerance.strip(),
            "message": f"Risk profile successfully saved: Score {score}/10 ({risk_tolerance}).",
        }
    finally:
        conn.close()


def tool_get_risk_profile() -> dict[str, Any]:
    """Retrieve the latest saved investment risk tolerance profile."""
    conn = database.connect_readonly(DB_PATH)
    try:
        profile = database.get_latest_risk_profile(conn)
        if not profile:
            guidance = "No risk profile has been established yet. You can complete the questionnaire by clicking '🎯 Assess Risk' in the sidebar."
            return {
                "success": False,
                "empty_dataset": True,
                "guidance": guidance,
                "message": f"No risk profile has been established yet. {guidance}",
            }
        return {"success": True, "profile": profile}
    finally:
        conn.close()


def tool_analyze_investments() -> dict[str, Any]:
    """Analyze current portfolio asset allocation against the active target profile and user risk profile."""
    conn = database.connect_readonly(DB_PATH)
    try:
        # Net worth breakdown by asset class
        nw_rows = conn.execute(
            """
            SELECT a.asset_class, SUM(s.balance_eur_minor) AS value_eur_minor
            FROM account_snapshots s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM account_snapshots WHERE account_id = s.account_id)
            GROUP BY a.asset_class
            """
        ).fetchall()
        asset_classes = {
            r["asset_class"]: Money.from_cents(r["value_eur_minor"]).to_major()
            for r in nw_rows
            if r["value_eur_minor"] is not None
        }

        # Liquid cash balance in EUR
        cash_balance_eur = round(float(AccountRepository.get_total_cash_balance(conn)), 2)

        # Single source of truth: consolidated holdings resolving direct holdings and copy trade mirrors
        consolidated_df = get_consolidated_holdings_df(conn)

        positions: list[dict[str, Any]] = []
        if not consolidated_df.empty and "value_eur" in consolidated_df.columns:
            total_portfolio_value_eur = round(float(consolidated_df["value_eur"].sum()), 2)
            holdings_by_nature = {
                str(k): round(float(v), 2)
                for k, v in consolidated_df.groupby("nature")["value_eur"].sum().to_dict().items()
            }
            # AC-8/AC-9: one entry per distinct asset, summed across lots.
            for ticker, group in consolidated_df.groupby("ticker", sort=False):
                val = float(group["value_eur"].sum() or 0.0)
                first = group.iloc[0]
                positions.append({
                    "ticker": str(ticker),
                    "name": str(first.get("name", "")),
                    "display_label": str(first.get("display_label", "")),
                    "value_eur": round(val, 2),
                    "value_eur_formatted": f"€{val:,.2f}",
                    "asset_class": str(first.get("asset_class", "investment")),
                    "nature": str(first.get("nature", "")),
                    "region": str(first.get("region", "")),
                    "sector": str(first.get("sector", "")),
                    "currency": str(first.get("currency", "EUR")),
                    "source": str(first.get("source", "Direct Holdings")),
                })
        else:
            total_portfolio_value_eur = 0.0
            holdings_by_nature = {}

        # Active allocation profile & targets
        profiles = HoldingRepository.get_allocation_profiles(conn)
        active_profile = next((p for p in profiles if p.get("is_active")), profiles[0] if profiles else None)
        targets_dict: dict[str, float] = {}
        targets_list: list[dict[str, Any]] = []
        drift_data: list[dict[str, Any]] = []

        if active_profile:
            targets_dict = HoldingRepository.get_allocation_targets(conn, active_profile["id"])
            targets_list = [{"bucket": b, "target_pct": pct} for b, pct in targets_dict.items()]

            dimension = active_profile.get("dimension") or "nature"
            include_cash = bool(active_profile.get("include_cash", 0))
            drift_band_pct = float(active_profile.get("drift_band_pct", 5.0))

            current_values: dict[str, float] = {}
            if not consolidated_df.empty:
                col_to_use = dimension if dimension in consolidated_df.columns else "nature"
                for _, row in consolidated_df.iterrows():
                    b_key = str(row.get(col_to_use) or "other")
                    current_values[b_key] = current_values.get(b_key, 0.0) + float(row.get("value_eur", 0.0) or 0.0)

            if include_cash and cash_balance_eur > 0:
                current_values["cash"] = cash_balance_eur

            drift_data = calculate_drift(
                current_values=current_values,
                targets=targets_dict,
                drift_band_pct=drift_band_pct,
            )

        risk_prof = database.get_latest_risk_profile(conn)

        # Graceful empty state handling (AC-6)
        if consolidated_df.empty and not asset_classes:
            guidance = (
                "No portfolio holdings or investment accounts recorded yet. "
                "Import an eToro or broker statement via the '📎 Import' button in the sidebar "
                "or from the Investments page."
            )
            return {
                "success": True,
                "empty_dataset": True,
                "total_portfolio_value_eur": 0.0,
                "total_portfolio_value_formatted": "€0.00",
                "cash_balance_eur": cash_balance_eur,
                "cash_balance_formatted": f"€{cash_balance_eur:,.2f}",
                "asset_classes_eur": {},
                "holdings_by_nature_eur": {},
                "positions": [],
                "active_allocation_profile": active_profile,
                "allocation_targets": targets_list,
                "allocation_drift": [],
                "rebalance_needed": False,
                "risk_profile": risk_prof,
                "guidance": guidance,
                "message": f"No investment holdings found. {guidance}",
            }

        drift_alerts = [d for d in drift_data if d.get("alert")]
        rebalance_needed = len(drift_alerts) > 0
        total_positions_count = len(positions)
        positions_sorted = sorted(positions, key=lambda p: float(p.get("value_eur", 0.0)), reverse=True)
        top_positions = positions_sorted[:15]

        msg_parts = [
            f"Total investment portfolio value is €{total_portfolio_value_eur:,.2f} across {total_positions_count} total positions.",
            f"Asset nature breakdown: {json.dumps(holdings_by_nature)}.",
        ]
        if active_profile:
            if rebalance_needed:
                buckets = ", ".join(str(d.get("bucket")) for d in drift_alerts)
                msg_parts.append(
                    f"Active profile '{active_profile['name']}' indicates {len(drift_alerts)} allocation bucket(s) need rebalancing: {buckets}."
                )
            else:
                msg_parts.append(f"Active profile '{active_profile['name']}' is on target.")
        if cash_balance_eur > 0:
            msg_parts.append(f"Liquid cash balance is €{cash_balance_eur:,.2f}.")

        return {
            "success": True,
            "empty_dataset": False,
            "total_portfolio_value_eur": total_portfolio_value_eur,
            "total_portfolio_value_formatted": f"€{total_portfolio_value_eur:,.2f}",
            "cash_balance_eur": cash_balance_eur,
            "cash_balance_formatted": f"€{cash_balance_eur:,.2f}",
            "total_positions_count": total_positions_count,
            "asset_classes_eur": asset_classes,
            "holdings_by_nature_eur": holdings_by_nature,
            "positions": top_positions,
            "active_allocation_profile": active_profile,
            "allocation_targets": targets_list,
            "allocation_drift": drift_data,
            "rebalance_needed": rebalance_needed,
            "risk_profile": risk_prof,
            "message": " ".join(msg_parts),
        }
    finally:
        conn.close()


tool_get_portfolio_and_risk_summary = tool_analyze_investments


def tool_get_allocation_profiles() -> dict[str, Any]:
    """List every saved investment allocation profile with its target buckets."""
    conn = database.connect_readonly(DB_PATH)
    try:
        return {"success": True, "profiles": list_allocation_profiles(conn)}
    finally:
        conn.close()


def tool_create_allocation_profile(
    name: str,
    dimension: str,
    targets: dict[str, float],
    drift_band_pct: float = 5.0,
    include_cash: bool = False,
) -> dict[str, Any]:
    """Create a validated allocation profile (unique name, valid buckets, targets summing to 100)."""
    conn = database.connect(DB_PATH)
    try:
        return create_allocation_profile(
            conn,
            name=name,
            dimension=dimension,
            targets=targets,
            drift_band_pct=drift_band_pct,
            include_cash=include_cash,
        )
    finally:
        conn.close()


def tool_delete_allocation_profile(name: str, confirm_token: str = "") -> dict[str, Any]:
    """Delete an allocation profile; the first call returns a one time confirmation token to echo back."""
    conn = database.connect(DB_PATH)
    try:
        return delete_allocation_profile(conn, name=name, confirm_token=confirm_token)
    finally:
        conn.close()

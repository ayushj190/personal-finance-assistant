from datetime import date, datetime, timedelta
import statistics
from typing import Any

import pandas as pd
import streamlit as st

@st.cache_data(ttl=300)
def calculate_current_net_worth(_conn) -> dict[str, Any]:
    """Calculates live net worth: liquid cash, invested holdings, and home equity."""
    accounts = [dict(r) for r in _conn.execute("SELECT * FROM accounts WHERE is_active = 1").fetchall()]
    
    acc_balances: dict[int, float] = {}
    today = date.today()

    for acc in accounts:
        row = _conn.execute(
            "SELECT balance_minor, balance_eur_minor, snapshot_date FROM account_snapshots WHERE account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
            (acc["id"],),
        ).fetchone()
        if row:
            base_bal_eur = row["balance_eur_minor"] / 100.0
            apy = acc.get("apy")
            if apy and apy > 0:
                snap_date_str = str(row["snapshot_date"])[:10]
                try:
                    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
                    days = (today - snap_date).days
                    if days > 0:
                        daily_rate = (apy / 100.0) / 365.0
                        base_bal_eur += base_bal_eur * (daily_rate * days)
                except Exception:
                    pass
            acc_balances[acc["id"]] = base_bal_eur
        else:
            tx_sum = _conn.execute(
                "SELECT SUM(amount_eur_minor) AS total FROM transactions WHERE account_id = ?",
                (acc["id"],),
            ).fetchone()
            acc_balances[acc["id"]] = (tx_sum["total"] or 0) / 100.0

    # Liability balance & Property Asset
    lib_row = _conn.execute(
        "SELECT original_principal_minor, home_value_minor, balance_override_minor, balance_override_date FROM liabilities LIMIT 1"
    ).fetchone()
    home_value = 0.0
    mortgage_balance = 0.0
    if lib_row:
        orig_p = (lib_row["original_principal_minor"] / 100.0) if lib_row["original_principal_minor"] else 0.0
        home_value = (lib_row["home_value_minor"] / 100.0) if lib_row["home_value_minor"] is not None else orig_p
        if lib_row["balance_override_minor"]:
            mortgage_balance = lib_row["balance_override_minor"] / 100.0
        else:
            today_str = date.today().isoformat()
            mortgage_bal_row = _conn.execute(
                "SELECT balance_minor FROM liability_schedule WHERE due_date <= ? ORDER BY due_date DESC LIMIT 1",
                (today_str,),
            ).fetchone()
            if not mortgage_bal_row:
                mortgage_bal_row = _conn.execute("SELECT balance_minor FROM liability_schedule ORDER BY due_date ASC LIMIT 1").fetchone()
            mortgage_balance = (mortgage_bal_row["balance_minor"] / 100.0) if mortgage_bal_row else 0.0
    home_equity = home_value - mortgage_balance

    # Total cash & invested
    liquid_cash = sum(bal for acc in accounts if acc.get("asset_class") == "cash" and (bal := acc_balances.get(acc["id"], 0.0)))
    
    holdings_acc_rows = _conn.execute("SELECT DISTINCT account_id FROM holdings").fetchall()
    holdings_acc_ids = {r["account_id"] for r in holdings_acc_rows}
    invested_row = _conn.execute("SELECT SUM(CASE WHEN value_eur > 0 THEN value_eur ELSE cost_basis END) as total FROM v_holdings").fetchone()
    invested_holdings = float(invested_row["total"] or 0.0) if invested_row else 0.0
    invested_other = sum(
        bal for acc in accounts
        if acc.get("asset_class") == "investment" and acc["id"] not in holdings_acc_ids and (bal := acc_balances.get(acc["id"], 0.0))
    )
    invested = invested_holdings + invested_other
    net_worth = liquid_cash + invested + home_equity

    return {
        "liquid_cash": liquid_cash,
        "invested": invested,
        "home_equity": home_equity,
        "net_worth": net_worth,
        "acc_balances": acc_balances
    }

def calculate_savings_rate(income: float, expenses: float) -> float:
    if income <= 0:
        return 0.0
    return ((income - expenses) / income) * 100.0


@st.cache_data(ttl=300)
def calculate_burn_and_runway(
    monthly_expenses: list[float],
    liquid_cash: float,
) -> tuple[float, float, float]:
    """Returns (burn_rate, runway_months, runway_days).

    Burn rate is calculated from trailing 3 complete months (or available).
    """
    if not monthly_expenses:
        return 0.0, 0.0, 0.0

    recent_3 = monthly_expenses[-3:] if len(
        monthly_expenses) >= 3 else monthly_expenses
    burn_rate = sum(recent_3) / len(recent_3)

    if burn_rate <= 0:
        return 0.0, 999.0, 999.0 * 30.44

    runway_months = liquid_cash / burn_rate
    runway_days = runway_months * 30.44
    return burn_rate, runway_months, runway_days


def detect_recurring_charges(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detects recurring subscriptions / bills from transaction history.

    Filters: >=3 charges, amount within +-10% of median, cadence near 7, 30, or 365 days.
    """
    if not transactions:
        return []

    # Group by merchant
    by_merchant: dict[str, list[dict[str, Any]]] = {}
    for tx in transactions:
        if tx.get("is_internal_transfer"):
            continue
        # Subscriptions and recurring bills are outflows (negative in v_transactions)
        if tx.get("amount_eur", 0.0) >= 0 or tx.get("category_kind") == "income":
            continue
        amt = abs(tx.get("amount_eur", 0.0))
        if amt < 0.5:  # ignore micro test charges
            continue
        merchant = tx.get("merchant") or tx.get("merchant_normalized") or ""
        merchant = merchant.strip()
        if not merchant:
            continue
        by_merchant.setdefault(merchant, []).append(tx)

    recurring: list[dict[str, Any]] = []

    for merchant, txs in by_merchant.items():
        if len(txs) < 3:
            continue

        # Sort by date
        sorted_txs = sorted(
            txs,
            key=lambda x: (
                datetime.strptime(x["booking_date"][:10], "%Y-%m-%d").date()
                if isinstance(x["booking_date"], str)
                else x["booking_date"]
            ),
        )

        amounts = [abs(t.get("amount_eur", 0.0)) for t in sorted_txs]
        med_amt = statistics.median(amounts)
        if med_amt <= 0:
            continue

        # Check amount stability (+-10%)
        if not all(0.85 * med_amt <= a <= 1.15 * med_amt for a in amounts):
            continue

        dates = [
            datetime.strptime(t["booking_date"][:10], "%Y-%m-%d").date()
            if isinstance(t["booking_date"], str)
            else t["booking_date"]
            for t in sorted_txs
        ]

        intervals = [
            (dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        med_interval = statistics.median(intervals)

        cadence = None
        annual_mult = 0.0
        if 25 <= med_interval <= 35:
            cadence = "Monthly"
            annual_mult = 12.0
            next_date = dates[-1] + timedelta(days=30)
        elif 6 <= med_interval <= 8:
            cadence = "Weekly"
            annual_mult = 52.0
            next_date = dates[-1] + timedelta(days=7)
        elif 350 <= med_interval <= 380:
            cadence = "Yearly"
            annual_mult = 1.0
            next_date = dates[-1] + timedelta(days=365)

        if cadence:
            recurring.append(
                {
                    "merchant": merchant,
                    "cadence": cadence,
                    "amount_eur": round(med_amt, 2),
                    "annual_cost_eur": round(med_amt * annual_mult, 2),
                    "last_date": dates[-1].isoformat(),
                    "next_expected_date": next_date.isoformat(),
                    "occurrences": len(sorted_txs),
                }
            )

    return sorted(recurring, key=lambda x: x["annual_cost_eur"], reverse=True)


# Country names for the IBAN country code (first two letters), used to resolve a
# merchant's location. Only IBAN participating countries can resolve; there is no
# currency fallback, so merchants without an IBAN location stay blank.
IBAN_COUNTRY_NAMES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AL": "Albania", "AT": "Austria",
    "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BE": "Belgium",
    "BG": "Bulgaria", "BH": "Bahrain", "BR": "Brazil", "BY": "Belarus",
    "CH": "Switzerland", "CR": "Costa Rica", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "DO": "Dominican Republic", "EE": "Estonia",
    "EG": "Egypt", "ES": "Spain", "FI": "Finland", "FO": "Faroe Islands",
    "FR": "France", "GB": "United Kingdom", "GE": "Georgia", "GI": "Gibraltar",
    "GL": "Greenland", "GR": "Greece", "GT": "Guatemala", "HR": "Croatia",
    "HU": "Hungary", "IE": "Ireland", "IL": "Israel", "IQ": "Iraq", "IS": "Iceland",
    "IT": "Italy", "JO": "Jordan", "KW": "Kuwait", "KZ": "Kazakhstan", "LB": "Lebanon",
    "LC": "Saint Lucia", "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro",
    "MK": "North Macedonia", "MR": "Mauritania", "MT": "Malta", "MU": "Mauritius",
    "NL": "Netherlands", "NO": "Norway", "PK": "Pakistan", "PL": "Poland",
    "PS": "Palestine", "PT": "Portugal", "QA": "Qatar", "RO": "Romania",
    "RS": "Serbia", "SA": "Saudi Arabia", "SC": "Seychelles", "SE": "Sweden",
    "SI": "Slovenia", "SK": "Slovakia", "SM": "San Marino", "ST": "Sao Tome and Principe",
    "SV": "El Salvador", "TL": "Timor-Leste", "TN": "Tunisia", "TR": "Türkiye",
    "UA": "Ukraine", "VA": "Vatican City", "VG": "Virgin Islands", "XK": "Kosovo",
}


def resolve_iban_country(iban: str | None) -> str | None:
    """Return the country name for an IBAN's leading country code, else None."""
    if not iban:
        return None
    code = str(iban).strip().upper()[:2]
    if len(code) == 2 and code.isalpha():
        return IBAN_COUNTRY_NAMES.get(code)
    return None


def _dominant_merchant_category(group: pd.DataFrame) -> tuple[str, str | None]:
    """Most frequent category for a merchant, ties alphabetical, 'Mixed' when none exceeds half."""
    cats = group["category"].fillna("Uncategorized")
    counts = cats.value_counts()
    total = len(group)
    if total == 0 or counts.empty:
        return ("Uncategorized", None)
    top_count = int(counts.iloc[0])
    if top_count * 2 <= total:
        return ("Mixed", None)
    top_cat = sorted(c for c, n in counts.items() if n == top_count)[0]
    parents = group.loc[cats == top_cat, "parent_category"].dropna()
    parents = parents[parents.astype(str).str.strip() != ""]
    if parents.empty:
        return (str(top_cat), None)
    mode = parents.mode()
    return (str(top_cat), str(mode.iloc[0]) if not mode.empty else None)


def get_merchant_context(
    conn: Any,
    merchants: list[str],
    where_sql: str = "",
    params: list[Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve each merchant's IBAN location and used accounts with a dedicated query."""
    result: dict[str, dict[str, Any]] = {
        m: {"location": None, "accounts": []} for m in merchants if m
    }
    if not result:
        return result

    names = list(result.keys())
    placeholders = ",".join("?" for _ in names)
    clauses = [f"t.merchant_normalized IN ({placeholders})"]
    qparams: list[Any] = list(names)
    if where_sql:
        clauses.append(where_sql.replace("WHERE ", "", 1))
        qparams.extend(params or [])
    if start_date:
        clauses.append("t.booking_date >= ?")
        qparams.append(start_date)
    if end_date:
        clauses.append("t.booking_date <= ?")
        qparams.append(end_date)

    sql = f"""
        SELECT t.merchant_normalized AS merchant,
               t.counterparty_iban AS iban,
               a.name AS account
        FROM transactions t
        LEFT JOIN accounts a ON a.id = t.account_id
        WHERE {" AND ".join(clauses)}
    """
    rows = conn.execute(sql, qparams).fetchall()
    for r in rows:
        key = r["merchant"]
        entry = result.get(key)
        if entry is None:
            continue
        if entry["location"] is None:
            country = resolve_iban_country(r["iban"])
            if country:
                entry["location"] = country
        account = r["account"]
        if account and account not in entry["accounts"]:
            entry["accounts"].append(account)
    return result


def aggregate_top_merchants(
    display_df: pd.DataFrame,
    context: dict[str, dict[str, Any]] | None,
    scope_total_eur: float,
    month_divisor: int = 1,
    limit: int = 10,
) -> dict[str, Any]:
    """Aggregate the scope frame into Top Merchant rows plus the IBAN country totals."""
    empty = {"rows": [], "location_totals": [], "has_location": False}
    if display_df is None or display_df.empty:
        return empty

    df = display_df.copy()
    if "category" not in df.columns:
        df["category"] = "Uncategorized"
    if "parent_category" not in df.columns:
        df["parent_category"] = "Uncategorized"
    df["category"] = df["category"].fillna("Uncategorized")
    df["parent_category"] = df["parent_category"].fillna("Uncategorized")
    df["amount_eur_minor"] = pd.to_numeric(
        df.get("amount_eur_minor", 0), errors="coerce"
    ).fillna(0)
    df["booking_date"] = df["booking_date"].astype(str)

    divisor = month_divisor if month_divisor and month_divisor > 0 else 1
    context = context or {}

    all_rows: list[dict[str, Any]] = []
    for merchant, group in df.groupby("merchant"):
        if merchant is None or str(merchant).strip() == "":
            continue
        count = len(group)
        total_eur = -int(group["amount_eur_minor"].sum()) / 100.0 / divisor
        category, parent = _dominant_merchant_category(group)
        ctx = context.get(merchant, {})
        all_rows.append(
            {
                "merchant": str(merchant),
                "location": ctx.get("location"),
                "category": category,
                "parent": parent,
                "transactions": count,
                "avg_eur": (total_eur / count) if count else 0.0,
                "total_eur": total_eur,
                "share_pct": (total_eur / scope_total_eur * 100.0)
                if scope_total_eur and scope_total_eur > 0
                else 0.0,
                "last_date": str(group["booking_date"].max())[:10],
                "accounts": ", ".join(ctx.get("accounts", [])),
            }
        )

    all_rows.sort(key=lambda r: r["total_eur"], reverse=True)

    location_totals: dict[str, float] = {}
    for r in all_rows:
        if r["location"]:
            location_totals[r["location"]] = location_totals.get(r["location"], 0.0) + r["total_eur"]

    return {
        "rows": all_rows[:limit],
        "location_totals": sorted(
            ({"location": k, "total_eur": v} for k, v in location_totals.items()),
            key=lambda x: x["total_eur"],
            reverse=True,
        ),
        "has_location": bool(location_totals),
    }

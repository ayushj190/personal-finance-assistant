import json
from pathlib import Path
import sqlite3
from typing import Any
import pandas as pd

from core.config import DATA_DIR
from connectors.market_data_service import classify_asset, enrich_ticker_metadata
from db.repositories import HoldingRepository


def calculate_drift(
    current_values: dict[str, float],
    targets: dict[str, float],
    drift_band_pct: float = 5.0,
) -> list[dict[str, Any]]:
    total_val = sum(current_values.values())
    results: list[dict[str, Any]] = []

    # All buckets present in targets or current_values
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))

    for bucket in all_buckets:
        val = current_values.get(bucket, 0.0)
        actual_pct = (val / total_val * 100.0) if total_val > 0 else 0.0
        target_pct = targets.get(bucket, 0.0)
        diff_pp = actual_pct - target_pct

        # 5/25 rule: absolute drift > band OR relative drift > 25% of target
        is_abs_drift = abs(diff_pp) > drift_band_pct
        is_rel_drift = (abs(diff_pp) / target_pct >
                        0.25) if target_pct > 0 else (actual_pct > 0)
        alert = is_abs_drift or is_rel_drift

        results.append(
            {
                "bucket": bucket,
                "value_eur": val,
                "actual_pct": actual_pct,
                "target_pct": target_pct,
                "drift_pp": diff_pp,
                "alert": alert,
            }
        )
    return results


def rebalance_without_selling(
    current_values: dict[str, float],
    targets: dict[str, float],
) -> tuple[float, dict[str, float]]:
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    # Filter targets > 0
    valid_targets = {b: targets.get(b, 0.0)
                     for b in all_buckets if targets.get(b, 0.0) > 0}
    if not valid_targets:
        return 0.0, {}

    # Ratio of current value to target fraction
    total_needed = max(current_values.get(b, 0.0) /
                       (valid_targets[b] / 100.0) for b in valid_targets)
    buys: dict[str, float] = {}
    for b in valid_targets:
        target_val = (valid_targets[b] / 100.0) * total_needed
        buys[b] = max(0.0, target_val - current_values.get(b, 0.0))

    total_new_cash = sum(buys.values())
    return total_new_cash, buys


def allocate_contribution(
    current_values: dict[str, float],
    targets: dict[str, float],
    contribution: float,
) -> dict[str, float]:
    if contribution <= 0:
        return {b: 0.0 for b in targets}

    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    valid_targets = {b: targets.get(b, 0.0)
                     for b in all_buckets if targets.get(b, 0.0) > 0}
    if not valid_targets:
        return {}

    # Water-filling allocation iteratively
    vals = {b: float(current_values.get(b, 0.0)) for b in valid_targets}
    allocations = {b: 0.0 for b in valid_targets}
    remaining = float(contribution)
    step = min(1.0, remaining / 100.0) if remaining > 10 else 0.1

    while remaining > 1e-4:
        total = sum(vals.values())
        # Find bucket with lowest ratio of actual to target
        ratios = {b: (vals[b] / total) / (valid_targets[b] / 100.0)
                  if total > 0 else 0.0 for b in valid_targets}
        min_bucket = min(ratios, key=ratios.get)  # type: ignore

        cur_step = min(step, remaining)
        vals[min_bucket] += cur_step
        allocations[min_bucket] += cur_step
        remaining -= cur_step

    return allocations


def full_rebalance(
    current_values: dict[str, float],
    targets: dict[str, float],
) -> dict[str, float]:
    total_val = sum(current_values.values())
    all_buckets = sorted(set(current_values.keys()) | set(targets.keys()))
    deltas: dict[str, float] = {}

    for b in all_buckets:
        target_pct = targets.get(b, 0.0)
        target_val = (target_pct / 100.0) * total_val
        cur_val = current_values.get(b, 0.0)
        deltas[b] = target_val - cur_val

    return deltas


def classify_asset_nature(ticker: str, name: str, asset_type: str, sector: str) -> str:
    """Classify asset into major investment natures including commodities and real assets."""
    sec_lower = str(sector).lower()
    t_upper = str(ticker).upper()
    n_lower = str(name).lower()
    if (
        any(k in sec_lower for k in ["gold", "metal", "commodity", "materials", "energy", "uranium"])
        or any(t in t_upper for t in ["GLD", "URA", "SLV", "USO", "GSG", "PPFB", "RHM"])
        or any(k in n_lower for k in ["gold", "uranium", "silver", "commodity"])
    ):
        return "Commodities & Real Assets"
    if asset_type == "crypto" or "crypto" in sec_lower:
        return "Digital Assets (Crypto)"
    if asset_type in ("stock", "etf"):
        return "Equities"
    if asset_type in ("bond", "fixed_income") or "bond" in sec_lower:
        return "Fixed Income"
    return "Other / Multi-Asset"


def get_consolidated_holdings_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Build consolidated portfolio holdings DataFrame, resolving direct assets and mirror copy trades."""
    try:
        holdings_df = HoldingRepository.get_v_holdings_df(conn)
    except Exception:
        return pd.DataFrame()

    if holdings_df.empty:
        return pd.DataFrame()

    fx_close = HoldingRepository.get_latest_fx_quote(conn, "EURUSD=X")
    usd_to_eur = (1.0 / fx_close) if fx_close else 0.892

    cache_path = DATA_DIR / "etoro_mirrors_cache.json"
    meta_path = DATA_DIR / "ticker_metadata.json"

    mirrors_data = []
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                mirrors_data = json.load(f)
        except Exception:
            mirrors_data = []

    mirrors_map = {m["ticker"]: m for m in mirrors_data if isinstance(m, dict) and "ticker" in m}

    meta_map = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_map = json.load(f)
        except Exception:
            meta_map = {}

    consolidated_items = []
    for _, row in holdings_df.iterrows():
        t = row["ticker"]
        if str(t).startswith("COPY:"):
            m = mirrors_map.get(t, {})
            positions = m.get("positions", [])
            copy_user = m.get("username") or str(t).replace("COPY:", "")
            source_name = f"Copy: {copy_user}"
            for p in positions:
                inst_id = p.get("instrument_id")
                sym = p.get("symbol") or f"ID_{inst_id}"
                p_name = p.get("name") or sym
                m_info = meta_map.get(sym, {})
                a_type, sec = classify_asset(sym, p_name, m_info)
                nature = classify_asset_nature(sym, p_name, a_type, sec)
                reg = m_info.get("country") or "Unknown"
                cur = m_info.get("currency") or "USD"
                exc = m_info.get("exchange") or "Unknown"

                val_usd = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
                val_eur = val_usd * usd_to_eur
                consolidated_items.append({
                    "ticker": sym,
                    "name": p_name,
                    "value_eur": val_eur,
                    "asset_class": "investment",
                    "asset_type": a_type,
                    "asset_type_display": a_type.upper(),
                    "nature": nature,
                    "region": reg,
                    "sector": sec,
                    "currency": cur,
                    "exchange": exc,
                    "source": source_name,
                    "display_label": p_name if p_name and not p_name.startswith("ID_") else sym,
                    "is_copy": True,
                })
        else:
            m_info = meta_map.get(t, {})
            d_name = row.get("name") or t
            a_type, sec = classify_asset(t, d_name, m_info)
            nature = classify_asset_nature(t, d_name, a_type, sec)
            reg = m_info.get("country") or row.get("region") or "Unknown"
            cur = m_info.get("currency") or row.get("currency") or "EUR"
            exc = m_info.get("exchange") or "Unknown"
            consolidated_items.append({
                "ticker": t,
                "name": d_name,
                "value_eur": row.get("value_eur", 0.0),
                "asset_class": row.get("asset_class") or "investment",
                "asset_type": a_type,
                "asset_type_display": a_type.upper(),
                "nature": nature,
                "region": reg,
                "sector": sec,
                "currency": cur,
                "exchange": exc,
                "source": "Direct Holdings",
                "display_label": d_name if d_name else t,
                "is_copy": False,
            })

    all_syms = [
        item["ticker"]
        for item in consolidated_items
        if not item["ticker"].startswith("ID_")
    ]
    names_map = {item["ticker"]: item["name"] for item in consolidated_items}
    if all_syms:
        enrich_ticker_metadata(list(set(all_syms)), names_map=names_map)

    return pd.DataFrame(consolidated_items)


def aggregate_distinct_holdings(holdings_df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Collapse the per lot v_holdings frame into one row per distinct ticker.

    Quantity, cost basis, value, and unrealized profit are summed across lots.
    Copied trader rows keep their own ``COPY:`` key so they stay attributable.
    The average open price is the summed native cost over quantity when a group
    holds one currency and carries native cost; otherwise it falls back to the
    EUR cost column and the returned label is marked ``(EUR)``.
    """
    columns = [
        "ticker", "name", "asset_type", "quantity", "cost_basis", "cost_basis_native",
        "value_eur", "unrealized_pnl_eur", "latest_close", "currency", "avg_open_price",
    ]
    if holdings_df is None or holdings_df.empty:
        return pd.DataFrame(columns=columns), "Avg Open"

    rows: list[dict[str, Any]] = []
    eur_fallback = False
    for ticker, group in holdings_df.groupby("ticker", sort=False):
        quantity = float(group["quantity"].sum())
        cost_eur = float(group["cost_basis"].sum())
        native = float(group["cost_basis_native"].sum()) if "cost_basis_native" in group else 0.0
        currencies = [str(c) for c in group["currency"].dropna().unique()] if "currency" in group else []
        single_currency = len(currencies) == 1
        currency = currencies[0] if single_currency else "MIXED"
        use_native = single_currency and native > 0 and quantity != 0
        if not use_native:
            eur_fallback = True
        avg_open = (native / quantity) if use_native else (cost_eur / quantity if quantity else 0.0)
        latest_close = float(group["latest_close"].max() or 0.0) if "latest_close" in group else 0.0
        rows.append(
            {
                "ticker": ticker,
                "name": group["name"].iloc[0] if "name" in group else ticker,
                "asset_type": group["asset_type"].iloc[0] if "asset_type" in group else "",
                "quantity": quantity,
                "cost_basis": cost_eur,
                "cost_basis_native": native,
                "value_eur": float(group["value_eur"].sum()),
                "unrealized_pnl_eur": float(group["unrealized_pnl_eur"].sum()),
                "latest_close": latest_close,
                "currency": currency,
                "avg_open_price": avg_open,
            }
        )
    return pd.DataFrame(rows, columns=columns), ("Avg Open (EUR)" if eur_fallback else "Avg Open")


def exposure_dimension_column(dimension: str) -> str | None:
    """Map a dimension label (Sector, Region, Currency, Nature, Asset Class) to its DataFrame column."""
    dim_key = str(dimension).lower().strip().replace(" ", "_").replace("-", "_")
    if dim_key in ("asset_class", "asset_type", "asset_type_display", "assetclass"):
        return "asset_type_display"
    if dim_key in ("sector", "sectors", "theme", "themes"):
        return "sector"
    if dim_key in ("region", "regions", "country", "geography"):
        return "region"
    if dim_key in ("currency", "currencies"):
        return "currency"
    if dim_key in ("nature", "asset_nature", "commodity", "commodities"):
        return "nature"
    return None


def get_dimension_exposure_df(consolidated_df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """
    Aggregate portfolio exposure across a given dimension (Sector, Region, Currency, Asset Class, Nature/Commodity).
    Returns DataFrame with columns ['bucket', 'value_eur', 'weight_pct'].
    Falls back to 'Other' for missing or unknown values.
    """
    if consolidated_df.empty or "value_eur" not in consolidated_df.columns:
        return pd.DataFrame(columns=["bucket", "value_eur", "weight_pct"])

    # Map dimension name to DataFrame column
    col = exposure_dimension_column(dimension)
    if col == "asset_type_display" and "asset_type_display" not in consolidated_df.columns:
        col = "asset_type"
    if col is None or col not in consolidated_df.columns:
        col = dimension if dimension in consolidated_df.columns else "sector"

    df = consolidated_df.copy()
    if col not in df.columns:
        df[col] = "Other"
    else:
        df[col] = df[col].fillna("Other").replace({"": "Other", "Unknown": "Other"})

    grouped = df.groupby(col, as_index=False)["value_eur"].sum()
    grouped.rename(columns={col: "bucket"}, inplace=True)

    total_val = float(grouped["value_eur"].sum())
    grouped["weight_pct"] = (
        (grouped["value_eur"] / total_val * 100.0) if total_val > 0 else 0.0
    )
    grouped = grouped.sort_values(by="value_eur", ascending=False).reset_index(drop=True)
    return grouped[["bucket", "value_eur", "weight_pct"]]


def get_smart_allocation_profiles(conn: sqlite3.Connection, consolidated_df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    """Return smart, risk-tolerance-tailored allocation profiles across Sector, Region, Currency, and Multi-Asset dimensions."""
    from db import database
    risk_prof = database.get_latest_risk_profile(conn)
    tolerance = (risk_prof.get("risk_tolerance") or "Growth").capitalize() if risk_prof else "Growth"

    # Base profile targets adjusted for risk profile
    if tolerance in ("Aggressive", "Growth"):
        sector_targets = {
            "Technology": 30.0,
            "Industrials & Materials": 20.0,
            "Healthcare": 15.0,
            "Consumer & Entertainment": 15.0,
            "Energy": 10.0,
            "Cryptocurrency": 5.0,
            "Other": 5.0,
        }
        nature_targets = {
            "Equities": 75.0,
            "Commodities & Real Assets": 15.0,
            "Digital Assets (Crypto)": 5.0,
            "Fixed Income": 5.0,
        }
    else:
        sector_targets = {
            "Technology": 20.0,
            "Healthcare": 20.0,
            "Consumer & Entertainment": 20.0,
            "Industrials & Materials": 15.0,
            "Energy": 15.0,
            "Other": 10.0,
        }
        nature_targets = {
            "Equities": 60.0,
            "Commodities & Real Assets": 10.0,
            "Fixed Income": 25.0,
            "Digital Assets (Crypto)": 5.0,
        }

    region_targets = {
        "North America": 55.0,
        "Europe": 30.0,
        "Asia": 15.0,
    }

    currency_targets = {
        "EUR": 50.0,
        "USD": 45.0,
        "Other": 5.0,
    }

    profiles = [
        {
            "id": "smart_sector",
            "name": f"Smart Sector & Themes ({tolerance})",
            "dimension": "sector",
            "drift_band_pct": 5.0,
            "include_cash": 0,
            "description": f"Sector diversification tailored for {tolerance} risk profile and 10+ yr horizon",
            "targets": sector_targets,
            "is_smart": True,
        },
        {
            "id": "smart_nature",
            "name": f"Multi-Asset & Commodities ({tolerance})",
            "dimension": "nature",
            "drift_band_pct": 5.0,
            "include_cash": 0,
            "description": "Equities, real asset commodities, digital assets, and fixed income",
            "targets": nature_targets,
            "is_smart": True,
        },
        {
            "id": "smart_region",
            "name": f"Global Geographic Reach ({tolerance})",
            "dimension": "region",
            "drift_band_pct": 5.0,
            "include_cash": 0,
            "description": "Regional allocation across North America, Europe, and Asia",
            "targets": region_targets,
            "is_smart": True,
        },
        {
            "id": "smart_currency",
            "name": "Currency Neutrality (EUR / USD)",
            "dimension": "currency",
            "drift_band_pct": 5.0,
            "include_cash": 0,
            "description": "Currency exposure balance between EUR base and USD growth assets",
            "targets": currency_targets,
            "is_smart": True,
        },
    ]

    # Append saved database profiles (user-defined strategies)
    try:
        db_profiles = HoldingRepository.get_allocation_profiles(conn)
        for p in db_profiles:
            db_targets = HoldingRepository.get_allocation_targets(conn, p["id"])
            profiles.append({
                "id": p["id"],
                "name": p["name"],
                "dimension": p["dimension"],
                "drift_band_pct": float(p.get("drift_band_pct", 5.0)),
                "include_cash": bool(p.get("include_cash", 0)),
                "description": f"Saved profile ({p['dimension']})",
                "targets": db_targets,
                "is_smart": False,
            })
    except Exception:
        pass

    return profiles


def record_daily_portfolio_snapshot(
    conn: sqlite3.Connection,
    today_iso: str | None = None,
) -> bool:
    """Record one daily portfolio snapshot row into portfolio_snapshots from stored closes.

    Calculates market value, cost basis, and day P&L in euro minor units (cents).
    The upsert on snapshot_date is the once-per-day guard.
    Returns True if a snapshot was recorded, False if no holdings exist.
    """
    from datetime import date
    snapshot_date = str(today_iso or date.today().isoformat())
    holdings_df = HoldingRepository.get_v_holdings_df(conn)
    if holdings_df.empty:
        return False

    total_val = float(holdings_df["value_eur"].sum() or 0.0)
    total_cost = float(holdings_df["cost_basis"].sum() or 0.0)

    fx_close = HoldingRepository.get_latest_fx_quote(conn, "EURUSD=X")
    usd_to_eur = (1.0 / fx_close) if fx_close else 0.892

    total_day_pnl = 0.0
    has_day_pnl = False

    for _, row in holdings_df.iterrows():
        ticker = str(row.get("ticker") or "")
        if ticker.startswith("COPY:") or ticker.startswith("ID_"):
            continue
        qty = float(row.get("quantity") or 0.0)
        close = float(row.get("latest_close") or 0.0)
        prev_close = float(row.get("prev_close") or close)
        curr = str(row.get("currency") or "EUR")
        rate = usd_to_eur if curr == "USD" else 1.0

        if close > 0 and prev_close > 0 and qty > 0:
            diff = (close - prev_close) * qty * rate
            total_day_pnl += diff
            has_day_pnl = True

    val_minor = int(round(total_val * 100))
    cost_minor = int(round(total_cost * 100))
    pnl_minor = int(round(total_day_pnl * 100)) if has_day_pnl else None

    HoldingRepository.upsert_portfolio_snapshot(
        conn,
        snapshot_date=snapshot_date,
        market_value_eur_minor=val_minor,
        cost_basis_eur_minor=cost_minor,
        day_pnl_eur_minor=pnl_minor,
    )
    return True


def build_live_rows(
    consolidated_df: pd.DataFrame,
    aggregated_holdings_df: pd.DataFrame,
    mirror_cache: list[dict[str, Any]] | None = None,
    quote_cache: dict[str, Any] | None = None,
    fx_rate: float = 0.892,
    close_series: dict[str, list[float]] | None = None,
) -> pd.DataFrame:
    """Build one live row per distinct instrument symbol joining direct and mirror positions.

    Satisfies AC-1, AC-3, AC-5:
    - Distinct symbol rows merging direct and copied portions.
    - Day change percent and day P&L in EUR against previous close.
    - Preserves numeric types for sortability.
    """
    columns = [
        "symbol", "ticker", "name", "name_with_ticker", "quantity", "avg_open_price",
        "price", "day_change_pct", "day_pnl_eur", "cost_basis", "value_eur",
        "unrealized_pnl_eur", "total_pnl_pct", "weight_pct", "sparkline",
        "is_copy", "is_priced", "is_mirror_valued", "quote_age_str",
        "sector", "nature", "region", "currency",
    ]
    if consolidated_df.empty or "ticker" not in consolidated_df.columns:
        return pd.DataFrame(columns=columns)

    # Pre-index aggregated direct holdings
    direct_map: dict[str, dict[str, Any]] = {}
    if not aggregated_holdings_df.empty and "ticker" in aggregated_holdings_df.columns:
        for _, r in aggregated_holdings_df.iterrows():
            direct_map[str(r["ticker"])] = r.to_dict()

    # Pre-index copy mirrors by symbol and key
    copy_map: dict[str, list[dict[str, Any]]] = {}
    mirrors_by_key: dict[str, dict[str, Any]] = {}
    if mirror_cache:
        for m in mirror_cache:
            t_k = m.get("ticker")
            if t_k:
                mirrors_by_key[t_k] = m
            u_k = m.get("username") or m.get("name") or m.get("trader_name")
            if u_k:
                mirrors_by_key[f"COPY:{u_k}"] = m
                mirrors_by_key[u_k] = m
            for p in m.get("positions", []):
                sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
                copy_map.setdefault(sym, []).append(p)

    quotes = (quote_cache or {}).get("quotes", {})
    series_map = close_series or {}

    rows: list[dict[str, Any]] = []
    # Distinct tickers from consolidated_df / holdings_df
    for ticker, group in consolidated_df.groupby("ticker", sort=False):
        ticker_str = str(ticker).strip()
        first = group.iloc[0]
        raw_name = str(first.get("name") or first.get("display_label") or ticker_str)
        name_with_ticker = f"{raw_name} ({ticker_str})" if raw_name != ticker_str else ticker_str

        is_copy_pos = bool(group["is_copy"].any()) if "is_copy" in group.columns else False
        sector = str(first.get("sector") or "Other")
        nature = str(first.get("nature") or "Other")
        region = str(first.get("region") or "Unknown")
        currency = str(first.get("currency") or "EUR")

        if ticker_str.startswith("COPY:"):
            m_info = mirrors_by_key.get(ticker_str, {})
            u_name = ticker_str.split(":", 1)[1]
            raw_name = str(first.get("name") or f"Copy: {u_name}")
            name_with_ticker = f"{raw_name} ({ticker_str})"

            c_cost = float(m_info.get("invested_usd", 0.0)) * fx_rate if (m_info and m_info.get("invested_usd")) else float(first.get("cost_basis") or 0.0)
            c_val = float(m_info.get("value_usd", 0.0)) * fx_rate if (m_info and m_info.get("value_usd")) else float(first.get("value_eur") or c_cost)

            total_qty = float(first.get("quantity") or 1.0)
            total_cost = c_cost
            avg_open = total_cost / total_qty if total_qty > 0 else total_cost
            price = c_val / total_qty if total_qty > 0 else c_val
            prev_close = price
            day_change_pct = 0.0
            day_pnl_eur = 0.0
            market_val = c_val
            unrealized_pnl_eur = market_val - total_cost
            total_pnl_pct = (unrealized_pnl_eur / total_cost * 100.0) if total_cost > 0 else 0.0
            is_copy_pos = True
            is_priced = True
            is_mirror_val = True
            quote_age_str = "Mirror NAV"
            sector = "Copy Portfolio"
            nature = "Other / Multi-Asset"
            region = "Global"
            currency = "USD"
        else:
            # 1. Quantity & Cost basis across direct and copy legs
            direct_info = direct_map.get(ticker_str, {})
            d_qty = float(direct_info.get("quantity") if direct_info else (first.get("quantity") or 0.0))
            d_cost = float(direct_info.get("cost_basis") if direct_info else (first.get("cost_basis") or 0.0))

            c_positions = copy_map.get(ticker_str, [])
            c_qty = sum(
                float(p.get("units") or (float(p.get("amount_usd") or 0.0) / float(p.get("open_rate") or 1.0) if p.get("open_rate") else 0.0))
                for p in c_positions
            )
            c_cost = sum(float(p.get("amount_usd") or 0.0) * fx_rate for p in c_positions)
            c_val = sum((float(p.get("amount_usd") or 0.0) + float(p.get("pnl_usd") or 0.0)) * fx_rate for p in c_positions)

            total_qty = d_qty + c_qty
            total_cost = d_cost + c_cost
            avg_open = (total_cost / total_qty) if total_qty > 0 else 0.0

            # 2. Quotes & Price determination
            is_mirror_val = ticker_str.startswith("ID_")
            q_info = quotes.get(ticker_str)

            is_priced = False
            quote_age_str = "Delayed"
            price = 0.0
            prev_close = 0.0

            if is_mirror_val:
                is_mirror_val = True
                is_priced = True  # Valued from mirror NAV, not waiting on poll (AC-5)
                # Use consolidated value_eur for mirror items
                group_val = float(group["value_eur"].sum() or 0.0)
                price = (group_val / total_qty) if total_qty > 0 else 0.0
                prev_close = price
                quote_age_str = "Mirror NAV"
            elif q_info and float(q_info.get("price") or 0.0) > 0:
                price = float(q_info["price"])
                prev_close = float(q_info.get("prev_close") or price)
                is_priced = True
                source = q_info.get("source", "")
                fetched_at = q_info.get("fetched_at", "")
                if source == "yfinance_1m":
                    quote_age_str = "Live"
                elif fetched_at:
                    quote_age_str = str(fetched_at)[:10]
                else:
                    quote_age_str = "Stored close"
            else:
                # Fallback to consolidated group value if available
                group_val = float(group["value_eur"].sum() or 0.0) if "value_eur" in group.columns else 0.0
                if total_qty > 0 and group_val > 0:
                    price = group_val / total_qty
                    prev_close = price
                    quote_age_str = "Stored close"
                else:
                    is_priced = False
                    quote_age_str = "Unpriced"

            # 3. Currency conversion for price & P&L
            quote_curr = ((q_info.get("currency") if q_info else None) or currency).upper()
            if (quote_curr in ("GBP", "GBX") or ticker_str.endswith(".L")) and price > 50:
                price /= 100.0
                prev_close /= 100.0
                quote_curr = "GBP"

            if quote_curr == "USD":
                curr_mult = fx_rate
            elif quote_curr in ("GBP", "GBX"):
                curr_mult = 1.16
            else:
                curr_mult = 1.0

            # 4. Day change & Day P&L
            if is_priced and prev_close > 0 and not is_mirror_val:
                day_change_pct = ((price - prev_close) / prev_close) * 100.0
                day_pnl_eur = (price - prev_close) * total_qty * curr_mult
            else:
                day_change_pct = 0.0
                day_pnl_eur = 0.0

            # 5. Market value & Total P&L
            if is_priced and price > 0 and not is_mirror_val:
                direct_part = d_qty * price * curr_mult
                copy_part = (c_qty * price * curr_mult) if c_qty > 0 else c_val
                market_val = (direct_part + copy_part) if (direct_part > 0 or copy_part > 0) else (price * total_qty * curr_mult)
            else:
                market_val = float(group["value_eur"].sum() or 0.0) if "value_eur" in group.columns else (price * total_qty * curr_mult if price > 0 else total_cost)

            unrealized_pnl_eur = market_val - total_cost
            total_pnl_pct = (unrealized_pnl_eur / total_cost * 100.0) if total_cost > 0 else 0.0

        sparkline_pts = series_map.get(ticker_str, [])

        rows.append({
            "symbol": ticker_str,
            "ticker": ticker_str,
            "name": raw_name,
            "name_with_ticker": name_with_ticker,
            "quantity": total_qty,
            "avg_open_price": avg_open,
            "price": price,
            "day_change_pct": day_change_pct,
            "day_pnl_eur": day_pnl_eur,
            "cost_basis": total_cost,
            "value_eur": market_val,
            "unrealized_pnl_eur": unrealized_pnl_eur,
            "total_pnl_pct": total_pnl_pct,
            "weight_pct": 0.0,  # filled below
            "sparkline": sparkline_pts,
            "is_copy": is_copy_pos,
            "is_priced": is_priced,
            "is_mirror_valued": is_mirror_val,
            "quote_age_str": quote_age_str,
            "sector": sector,
            "nature": nature,
            "region": region,
            "currency": currency,
        })

    total_portfolio_val = sum(r["value_eur"] for r in rows)
    for r in rows:
        r["weight_pct"] = (
            (r["value_eur"] / total_portfolio_val * 100.0) if total_portfolio_val > 0 else 0.0
        )

    res_df = pd.DataFrame(rows, columns=columns)
    return res_df


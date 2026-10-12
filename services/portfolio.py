import json
from pathlib import Path
import sqlite3
from typing import Any
import pandas as pd

from config import DATA_DIR
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
                    "region": reg,
                    "sector": sec,
                    "currency": cur,
                    "exchange": exc,
                    "source": source_name,
                    "display_label": p_name if p_name and not p_name.startswith("ID_") else sym,
                })
        else:
            m_info = meta_map.get(t, {})
            d_name = row.get("name") or t
            a_type, sec = classify_asset(t, d_name, m_info)
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
                "region": reg,
                "sector": sec,
                "currency": cur,
                "exchange": exc,
                "source": "Direct Holdings",
                "display_label": d_name if d_name else t,
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


def get_dimension_exposure_df(consolidated_df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """
    Aggregate portfolio exposure across a given dimension (Sector, Region, Currency, Asset Class).
    Returns DataFrame with columns ['bucket', 'value_eur', 'weight_pct'].
    Falls back to 'Other' for missing or unknown values.
    """
    if consolidated_df.empty or "value_eur" not in consolidated_df.columns:
        return pd.DataFrame(columns=["bucket", "value_eur", "weight_pct"])

    dim_key = str(dimension).lower().strip().replace(" ", "_").replace("-", "_")

    # Map dimension name to DataFrame column
    if dim_key in ("asset_class", "asset_type", "asset_type_display", "assetclass"):
        col = "asset_type_display" if "asset_type_display" in consolidated_df.columns else "asset_type"
    elif dim_key in ("sector", "sectors"):
        col = "sector"
    elif dim_key in ("region", "regions", "country"):
        col = "region"
    elif dim_key in ("currency", "currencies"):
        col = "currency"
    else:
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

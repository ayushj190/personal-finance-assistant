"""Allocation strategy management: validated create, delete, and list.

This is the single write path for investment allocation strategies. The Copilot
tools and both UI surfaces call these functions so validation, the bucket
vocabulary, and the delete confirmation token live in one place (AC-12, AC-13).
"""

import hashlib
import sqlite3
from typing import Any

from db.repositories import HoldingRepository

ALLOWED_DIMENSIONS = ("asset_class", "asset_type", "region", "sector", "currency", "ticker")

# Fixed bucket vocabulary for the dimensions that are not derived from holdings.
BASE_BUCKETS: dict[str, list[str]] = {
    "asset_class": ["cash", "investment"],
    "asset_type": ["stock", "etf", "crypto", "commodity", "bond", "other"],
}

# Dimensions whose vocabulary is read from the values present in the holdings.
DYNAMIC_DIMENSIONS = ("region", "sector", "currency", "ticker")


def get_valid_buckets(conn: sqlite3.Connection, dimension: str) -> list[str]:
    """Return the documented bucket vocabulary for a dimension, plus an explicit cash bucket."""
    dim = str(dimension or "").strip().lower()
    if dim in BASE_BUCKETS:
        buckets = list(BASE_BUCKETS[dim])
    elif dim in DYNAMIC_DIMENSIONS:
        buckets = []
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {dim} FROM v_holdings WHERE {dim} IS NOT NULL AND {dim} != ''"
            ).fetchall()
        except sqlite3.Error:
            rows = []
        for r in rows:
            val = str(r[0]).strip()
            if val and val.lower() not in ("unknown", "none", "nan") and val not in buckets:
                buckets.append(val)
        buckets.sort()
    else:
        buckets = []
    if "cash" not in buckets:
        buckets.append("cash")
    return buckets


def list_allocation_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return every saved allocation profile with its targets attached."""
    profiles = HoldingRepository.get_allocation_profiles(conn)
    out: list[dict[str, Any]] = []
    for p in profiles:
        out.append(
            {
                "id": p["id"],
                "name": p["name"],
                "dimension": p["dimension"],
                "drift_band_pct": float(p.get("drift_band_pct", 5.0)),
                "include_cash": bool(p.get("include_cash", 0)),
                "is_active": bool(p.get("is_active", 0)),
                "targets": HoldingRepository.get_allocation_targets(conn, p["id"]),
            }
        )
    return out


def _confirm_token(profile_id: int, name: str) -> str:
    """One time delete token derived from the profile id and a hash of its name."""
    digest = hashlib.sha256(str(name).strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"{profile_id}-{digest}"


def create_allocation_profile(
    conn: sqlite3.Connection,
    name: str,
    dimension: str,
    targets: dict[str, float],
    drift_band_pct: float = 5.0,
    include_cash: bool = False,
) -> dict[str, Any]:
    """Validate and insert a new allocation profile. Writes nothing on any validation failure."""
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"success": False, "message": "A profile name is required."}

    dim = str(dimension or "").strip().lower()
    if dim not in ALLOWED_DIMENSIONS:
        return {
            "success": False,
            "message": f"Unknown dimension '{dimension}'. Allowed dimensions: {', '.join(ALLOWED_DIMENSIONS)}.",
        }

    if not isinstance(targets, dict) or not targets:
        return {"success": False, "message": "targets must be a non-empty map of bucket to percent."}

    try:
        band = float(drift_band_pct)
    except (TypeError, ValueError):
        return {"success": False, "message": f"Drift band '{drift_band_pct}' is not a number."}
    if not (0 <= band <= 100):
        return {"success": False, "message": f"Drift band must be between 0 and 100, got {band}."}

    existing = conn.execute(
        "SELECT id FROM allocation_profiles WHERE LOWER(name) = LOWER(?)", (clean_name,)
    ).fetchone()
    if existing:
        return {"success": False, "message": f"An allocation profile named '{clean_name}' already exists."}

    valid = get_valid_buckets(conn, dim)
    rounded: dict[str, float] = {}
    for bucket, pct in targets.items():
        bkey = str(bucket).strip()
        if bkey not in valid:
            return {
                "success": False,
                "message": f"Bucket '{bkey}' is not valid for dimension '{dim}'. Valid buckets: {', '.join(valid)}.",
            }
        try:
            pval = round(float(pct), 1)
        except (TypeError, ValueError):
            return {"success": False, "message": f"Target for '{bkey}' ({pct}) is not a number."}
        if not (0 <= pval <= 100):
            return {"success": False, "message": f"Target for '{bkey}' must be between 0 and 100."}
        rounded[bkey] = pval

    total = round(sum(rounded.values()), 1)
    if abs(total - 100.0) > 0.1:
        return {
            "success": False,
            "message": f"Targets must sum to 100 (±0.1). They sum to {total}.",
        }

    with conn:
        cur = conn.execute(
            "INSERT INTO allocation_profiles (name, dimension, include_cash, drift_band_pct, is_active) "
            "VALUES (?, ?, ?, ?, 0)",
            (clean_name, dim, 1 if include_cash else 0, band),
        )
        profile_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO allocation_targets (profile_id, bucket, target_pct) VALUES (?, ?, ?)",
            [(profile_id, b, p) for b, p in rounded.items()],
        )

    return {
        "success": True,
        "message": f"Created allocation profile '{clean_name}' ({dim}) with {len(rounded)} buckets.",
        "profile": {
            "id": profile_id,
            "name": clean_name,
            "dimension": dim,
            "drift_band_pct": band,
            "include_cash": bool(include_cash),
            "is_active": False,
            "targets": rounded,
        },
    }


def delete_allocation_profile(
    conn: sqlite3.Connection,
    name: str,
    confirm_token: str = "",
) -> dict[str, Any]:
    """Delete a profile once the confirmation token issued on the first call echoes back."""
    clean_name = str(name or "").strip()
    profiles = HoldingRepository.get_allocation_profiles(conn)
    available = [p["name"] for p in profiles]
    if not profiles:
        return {"success": False, "message": "No allocation profiles exist to delete."}

    match = next(
        (p for p in profiles if str(p["name"]).strip().lower() == clean_name.lower()), None
    )
    if match is None:
        return {
            "success": False,
            "message": f"Profile '{clean_name}' not found. Available profiles: {', '.join(available)}.",
        }

    if match.get("is_active"):
        return {
            "success": False,
            "message": (
                f"Cannot delete '{match['name']}' because it is the active profile. "
                f"Activate another profile first. Available profiles: {', '.join(available)}."
            ),
        }

    if len(profiles) == 1:
        return {
            "success": False,
            "message": (
                f"Cannot delete '{match['name']}' because it is the last remaining profile. "
                f"Available profiles: {', '.join(available)}."
            ),
        }

    token = _confirm_token(match["id"], match["name"])
    if str(confirm_token) != token:
        return {
            "success": False,
            "requires_confirmation": True,
            "confirm_token": token,
            "message": (
                f"Deleting '{match['name']}' needs confirmation. Re-run the delete with "
                f"confirm_token='{token}' to proceed."
            ),
            "summary": f"Delete allocation profile '{match['name']}' (dimension: {match['dimension']}).",
        }

    with conn:
        conn.execute("DELETE FROM allocation_profiles WHERE id = ?", (match["id"],))

    return {"success": True, "message": f"Deleted allocation profile '{match['name']}'."}

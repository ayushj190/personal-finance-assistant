import csv
from pathlib import Path
import sqlite3
from typing import Any

from db import database
from services.llm_client import classify_merchants

MCC_MAP_PATH = Path(__file__).resolve().parent.parent / "db" / "mcc_map.csv"
_MCC_CACHE: dict[str, str] | None = None


def load_mcc_map() -> dict[str, str]:
    global _MCC_CACHE
    if _MCC_CACHE is not None:
        return _MCC_CACHE

    mcc_dict: dict[str, str] = {}
    if MCC_MAP_PATH.exists():
        with open(MCC_MAP_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("mcc", "").strip()
                cat = row.get("category_name", "").strip()
                if code and cat:
                    mcc_dict[code] = cat
    _MCC_CACHE = mcc_dict
    return _MCC_CACHE


def categorize_transactions(
    conn: sqlite3.Connection,
    txs: list[dict[str, Any]],
    enable_llm: bool = False,
) -> list[dict[str, Any]]:
    rules_cache = database.get_rules_cache(conn)
    cat_map = database.get_category_map(conn)
    mcc_map = load_mcc_map()
    internal_transfer_cat_id = cat_map.get("Internal Transfer")

    unknown_merchants: dict[str, list[dict[str, Any]]] = {}

    for tx in txs:
        # Check internal transfer
        if tx.get("is_internal_transfer"):
            tx["category_id"] = internal_transfer_cat_id
            tx["category_source"] = "rule"
            continue

        merchant = tx.get("merchant_normalized", "").strip()

        # Check rules cache (user / llm overrides)
        if merchant and merchant in rules_cache:
            tx["category_id"] = rules_cache[merchant]
            tx["category_source"] = "rule"
            continue

        # Check MCC map
        mcc = tx.get("mcc")
        if mcc and mcc in mcc_map and mcc_map[mcc] in cat_map:
            tx["category_id"] = cat_map[mcc_map[mcc]]
            tx["category_source"] = "mcc"
            continue

        # Needs classification
        if merchant:
            unknown_merchants.setdefault(merchant, []).append(tx)

    # Optional LLM classification batch
    if enable_llm and unknown_merchants:
        cat_names = [name for name in cat_map.keys() if name != "Income" and name != "Transfers"]
        merchants_list = list(unknown_merchants.keys())
        # Chunk in batches of 30
        for i in range(0, len(merchants_list), 30):
            batch = merchants_list[i : i + 30]
            classifications = classify_merchants(batch, cat_names)
            for merchant, cat_name, conf in classifications:
                if cat_name in cat_map and conf >= 0.6:
                    cat_id = cat_map[cat_name]
                    database.upsert_category_rule(conn, merchant, cat_id, source="llm", confidence=conf)
                    rules_cache[merchant] = cat_id
                    for tx in unknown_merchants.get(merchant, []):
                        tx["category_id"] = cat_id
                        tx["category_source"] = "llm"

    return txs

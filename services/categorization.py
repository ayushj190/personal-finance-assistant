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


def match_heuristic_category(description: str, merchant: str, cat_map: dict[str, int]) -> int | None:
    text = f"{merchant} {description}".lower()

    # Interest
    if any(k in text for k in ("rente", "interest payment", "zinsen", "interest cash")):
        return cat_map.get("Interest")
    # Salary
    if any(k in text for k in ("salaris", "salary", "payroll", "loon")):
        return cat_map.get("Salary")
    # Supermarkets
    if any(k in text for k in ("albert heijn", "ah to go", "jumbo", "dekamarkt", "dirk", "lidl", "aldi", "spar", "coop", "ekoplaza", "vomar", "sahan")):
        return cat_map.get("Supermarket")
    # Food delivery
    if any(k in text for k in ("uber eats", "thuisbezorgd", "deliveroo", "yemeksepeti")):
        return cat_map.get("Food Delivery & Takeaway")
    # Cafes & Bakeries
    if any(k in text for k in ("starbucks", "bakkerij", "bagels & beans", "cafe ", "coffee")):
        return cat_map.get("Cafes & Bakeries")
    # Pharmacy & Drugstore
    if any(k in text for k in ("kruidvat", "etos", "apotheek", "drogist")):
        return cat_map.get("Pharmacy & Drugstore")
    # Home & Maintenance
    if any(k in text for k in ("action", "hema", "blokker", "ikea", "praxis", "gamma", "hornbach")):
        return cat_map.get("Home & Maintenance")
    # Restaurants
    if any(k in text for k in ("cirfood", "mcdonald", "burger king", "kfc", "restaurant")):
        return cat_map.get("Restaurants")
    # Public Transit & Rideshare
    if any(k in text for k in ("bit mobility", "ns groep", "gvb", "connexxion", "ov-chipkaart", "tier", "bolt", "uber ")):
        return cat_map.get("Public Transit")
    # Mortgage
    if any(k in text for k in ("hypotheek", "termijnbetaling hy", "mortgage")):
        return cat_map.get("Mortgage")
    # Insurance
    if any(k in text for k in ("zilveren kruis", "vgz", "cz zorg", "menzis", "onvz", "dsw zorg")):
        return cat_map.get("Health Insurance")
    if any(k in text for k in ("schadeverzekering", "schadev", "abn amro schade", "liability insurance")):
        return cat_map.get("Home & Liability Insurance")
    # Telecom & Utilities
    if any(k in text for k in ("kpn", "ziggo", "vodafone", "odido")):
        return cat_map.get("Internet & Telecom")
    if any(k in text for k in ("eneco", "vattenfall", "essent", "greenchoice", "budget energie")):
        return cat_map.get("Electricity & Gas")
    # Municipal taxes & Official
    if any(k in text for k in ("belastingdienst", "gemeente", "waterschap", "gblt", "bsgr", "duo inburgering", "duo ")):
        return cat_map.get("Municipal Taxes")
    # Subscriptions
    if any(k in text for k in ("netflix", "spotify", "apple.com/bill", "disney", "youtube", "amazon prime", "uber one")):
        return cat_map.get("Streaming & Media")
    # Travel & Flights
    if any(k in text for k in ("pegasus", "klm", "transavia", "ryanair", "easyjet", "airline")):
        return cat_map.get("Flights")
    # Shopping & Electronics
    if any(k in text for k in ("bol.com", "aliexpress", "amazon", "alipay", "media markt", "bsh household")):
        return cat_map.get("Shopping & Personal")
    # Personal Care
    if any(k in text for k in ("headlines", "kapper", "barber")):
        return cat_map.get("Personal Care")
    # Hobbies & Entertainment
    if any(k in text for k in ("squad (the)", "boulder", "cinema", "pathe")):
        return cat_map.get("Hobbies & Entertainment")
    # Supermarkets
    if any(k in text for k in ("albert heijn", "ah to go", "jumbo", "dekamarkt", "dirk", "lidl", "aldi", "spar", "coop", "ekoplaza", "vomar", "sahan", "koog supermarkten")):
        return cat_map.get("Supermarket")
    # Restaurants
    if any(k in text for k in ("cirfood", "mcdonald", "burger king", "kfc", "restaurant", "neni amsterdam", "tatsu", "madras diaries", "korean food", "osteria", "filippo manzini")):
        return cat_map.get("Restaurants")
    return None


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
        raw_desc = tx.get("description_raw", "")

        # Check rules cache (user / llm overrides)
        if merchant and merchant in rules_cache:
            tx["category_id"] = rules_cache[merchant]
            tx["category_source"] = "rule"
            continue

        # Check heuristics (interest, salary, supermarkets, health insurance)
        heur_cat_id = match_heuristic_category(raw_desc, merchant, cat_map)
        if heur_cat_id:
            tx["category_id"] = heur_cat_id
            tx["category_source"] = "rule"
            if merchant:
                database.upsert_category_rule(
                    conn, merchant, heur_cat_id, source="seed", confidence=0.95)
                rules_cache[merchant] = heur_cat_id
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
        cat_names = [name for name in cat_map.keys() if name !=
                     "Income" and name != "Transfers"]
        merchants_list = list(unknown_merchants.keys())
        # Chunk in batches of 30
        for i in range(0, len(merchants_list), 30):
            batch = merchants_list[i: i + 30]
            classifications = classify_merchants(batch, cat_names)
            for merchant, cat_name, conf in classifications:
                if cat_name in cat_map and conf >= 0.6:
                    cat_id = cat_map[cat_name]
                    database.upsert_category_rule(
                        conn, merchant, cat_id, source="llm", confidence=conf)
                    rules_cache[merchant] = cat_id
                    for tx in unknown_merchants.get(merchant, []):
                        tx["category_id"] = cat_id
                        tx["category_source"] = "llm"

    return txs

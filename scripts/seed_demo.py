#!/usr/bin/env python3
"""
Seed realistic demo data for the Amsterdam young professional profile.
Deterministic (seed 42, dates relative to today).
"""

import argparse
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import random
import sqlite3
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import DATA_DIR
from db import database
from db.migrations.runner import run_migrations
from services.budget_service import set_category_budget
from services.mortgage import calculate_mortgage_schedule
from services.normalization import dedup_hash


DEMO_DB_PATH = DATA_DIR / "demo.db"


def clean_demo_db() -> None:
    for ext in ["", "-wal", "-shm"]:
        p = Path(f"{DEMO_DB_PATH}{ext}")
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def seed_demo_data(reset: bool = False) -> None:
    if reset or not DEMO_DB_PATH.exists():
        clean_demo_db()

    conn = database.connect(DEMO_DB_PATH)
    try:
        run_migrations(conn)

        # If data already exists and not reset, skip
        acc_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        if acc_count > 0 and not reset:
            print(f"Demo database already seeded ({acc_count} accounts). Use --reset to rebuild.")
            return

        # Clear tables if reset
        with conn:
            conn.execute("DELETE FROM account_snapshots")
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM holdings")
            conn.execute("DELETE FROM market_quotes")
            conn.execute("DELETE FROM liability_schedule")
            conn.execute("DELETE FROM liability_rate_periods")
            conn.execute("DELETE FROM liability_extra_payments")
            conn.execute("DELETE FROM liabilities")
            conn.execute("DELETE FROM category_budgets")
            conn.execute("DELETE FROM accounts")

        random.seed(42)
        today = date.today()

        # ── 1. ACCOUNTS ──────────────────────────────────────────────
        accounts_data = [
            {
                "id": 1,
                "provider": "enable_banking",
                "institution": "ABN AMRO",
                "external_id": "abn-demo-01",
                "iban": "NL91ABNA0417164300",
                "name": "ABN AMRO Betaalrekening",
                "currency": "EUR",
                "asset_class": "cash",
                "apy": 0.0,
                "is_active": 1,
            },
            {
                "id": 2,
                "provider": "enable_banking",
                "institution": "Revolut",
                "external_id": "rev-demo-01",
                "iban": "NL12REVO7123984510",
                "name": "Revolut Daily & Travel",
                "currency": "EUR",
                "asset_class": "cash",
                "apy": 2.25,
                "is_active": 1,
            },
            {
                "id": 3,
                "provider": "etoro",
                "institution": "eToro",
                "external_id": "etoro-demo-01",
                "iban": None,
                "name": "eToro Investment Portfolio",
                "currency": "EUR",
                "asset_class": "investment",
                "apy": None,
                "is_active": 1,
            },
        ]

        with conn:
            for acc in accounts_data:
                conn.execute(
                    """
                    INSERT INTO accounts (id, provider, institution, external_id, iban, name, currency, asset_class, apy, is_active)
                    VALUES (:id, :provider, :institution, :external_id, :iban, :name, :currency, :asset_class, :apy, :is_active)
                    """,
                    acc,
                )

        # ── 2. MORTGAGE LIABILITY ─────────────────────────────────────
        mortgage_start = today - timedelta(days=548)  # 18 months ago
        with conn:
            conn.execute(
                """
                INSERT INTO liabilities (
                    id, name, lender, loan_type, original_principal_minor, home_value_minor,
                    start_date, term_months, payment_match_pattern
                ) VALUES (
                    1, 'ABN AMRO Woninghypotheek', 'ABN AMRO', 'annuity', 38500000, 48000000,
                    ?, 360, '(?i)hypotheek'
                )
                """,
                (mortgage_start.isoformat(),),
            )
            conn.execute(
                """
                INSERT INTO liability_rate_periods (liability_id, from_date, annual_rate, fixed_until)
                VALUES (1, ?, 0.0385, ?)
                """,
                (mortgage_start.isoformat(), (mortgage_start + timedelta(days=3650)).isoformat()),
            )

        # Materialize mortgage schedule
        schedule = calculate_mortgage_schedule(
            loan_type="annuity",
            principal_cents=38500000,
            start_date=mortgage_start,
            term_months=360,
            rate_periods=[{"from_date": mortgage_start, "annual_rate": 0.0385}],
            extra_payments=[],
        )
        with conn:
            for item in schedule:
                conn.execute(
                    """
                    INSERT INTO liability_schedule (
                        liability_id, month_idx, due_date, payment_minor, interest_minor, principal_minor, extra_minor, balance_minor
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["month_idx"],
                        item["due_date"].isoformat() if isinstance(item["due_date"], date) else str(item["due_date"]),
                        item["payment_minor"],
                        item["interest_minor"],
                        item["principal_minor"],
                        item["extra_minor"],
                        item["balance_minor"],
                    ),
                )

        # ── 3. ETORO HOLDINGS (12 ACTIVE + 3 CLOSED) ──────────────────
        holdings_data = [
            # Tickers: 12 Active
            {"ticker": "VWCE.DE", "isin": "IE00BK5BQT80", "name": "Vanguard FTSE All-World UCITS ETF", "asset_type": "etf", "region": "Global", "sector": "Diversified", "qty": 80.0, "cost": 920000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "VUAA.DE", "isin": "IE00BFMXXD54", "name": "Vanguard S&P 500 UCITS ETF", "asset_type": "etf", "region": "US", "sector": "Diversified", "qty": 45.0, "cost": 410000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "ASML.AS", "isin": "NL0010273215", "name": "ASML Holding N.V.", "asset_type": "stock", "region": "Europe", "sector": "Technology", "qty": 12.0, "cost": 860000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "AAPL", "isin": "US0378331005", "name": "Apple Inc.", "asset_type": "stock", "region": "US", "sector": "Technology", "qty": 25.0, "cost": 430000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "MSFT", "isin": "US5949181045", "name": "Microsoft Corporation", "asset_type": "stock", "region": "US", "sector": "Technology", "qty": 15.0, "cost": 490000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "GOOGL", "isin": "US02079K3059", "name": "Alphabet Inc.", "asset_type": "stock", "region": "US", "sector": "Technology", "qty": 30.0, "cost": 380000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "NVDA", "isin": "US67066G1040", "name": "NVIDIA Corporation", "asset_type": "stock", "region": "US", "sector": "Technology", "qty": 35.0, "cost": 360000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "SAP.DE", "isin": "DE0007164600", "name": "SAP SE", "asset_type": "stock", "region": "Europe", "sector": "Technology", "qty": 16.0, "cost": 260000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "NOVO-B.CO", "isin": "DK0062498333", "name": "Novo Nordisk A/S", "asset_type": "stock", "region": "Europe", "sector": "Healthcare", "qty": 32.0, "cost": 310000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "ADYEN.AS", "isin": "NL0012969182", "name": "Adyen N.V.", "asset_type": "stock", "region": "Europe", "sector": "Financial Services", "qty": 3.0, "cost": 410000, "curr": "EUR", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "BTC-USD", "isin": None, "name": "Bitcoin USD", "asset_type": "crypto", "region": "Global", "sector": "Crypto", "qty": 0.12, "cost": 540000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            {"ticker": "ETH-USD", "isin": None, "name": "Ethereum USD", "asset_type": "crypto", "region": "Global", "sector": "Crypto", "qty": 1.5, "cost": 350000, "curr": "USD", "status": "active", "pnl": 0, "proc": 0, "closed": None},
            # Closed positions (at least 3)
            {"ticker": "TSLA", "isin": "US88160R1014", "name": "Tesla Inc.", "asset_type": "stock", "region": "US", "sector": "Consumer Cyclical", "qty": 10.0, "cost": 210000, "curr": "USD", "status": "closed", "pnl": 45000, "proc": 255000, "closed": (today - timedelta(days=90)).isoformat()},
            {"ticker": "BABA", "isin": "US01609W1027", "name": "Alibaba Group Holding Ltd", "asset_type": "stock", "region": "EM", "sector": "Technology", "qty": 20.0, "cost": 190000, "curr": "USD", "status": "closed", "pnl": -30000, "proc": 160000, "closed": (today - timedelta(days=120)).isoformat()},
            {"ticker": "SOL-USD", "isin": None, "name": "Solana USD", "asset_type": "crypto", "region": "Global", "sector": "Crypto", "qty": 15.0, "cost": 110000, "curr": "USD", "status": "closed", "pnl": 75000, "proc": 185000, "closed": (today - timedelta(days=60)).isoformat()},
        ]

        with conn:
            for h in holdings_data:
                conn.execute(
                    """
                    INSERT INTO holdings (
                        account_id, ticker, isin, name, asset_type, region, sector, quantity,
                        cost_basis_minor, currency, status, closed_at, realized_pnl_minor,
                        realized_proceeds_minor, updated_at
                    ) VALUES (
                        3, :ticker, :isin, :name, :asset_type, :region, :sector, :qty,
                        :cost, :curr, :status, :closed, :pnl, :proc, :updated
                    )
                    """,
                    {
                        "ticker": h["ticker"],
                        "isin": h["isin"],
                        "name": h["name"],
                        "asset_type": h["asset_type"],
                        "region": h["region"],
                        "sector": h["sector"],
                        "qty": h["qty"],
                        "cost": h["cost"],
                        "curr": h["curr"],
                        "status": h["status"],
                        "closed": h["closed"],
                        "pnl": h["pnl"],
                        "proc": h["proc"],
                        "updated": today.isoformat(),
                    },
                )

        # ── 4. MARKET QUOTES ──────────────────────────────────────────
        quotes_data = [
            ("VWCE.DE", 128.50, 127.80, "EUR"),
            ("VUAA.DE", 106.20, 105.40, "EUR"),
            ("ASML.AS", 792.00, 785.00, "EUR"),
            ("AAPL", 228.00, 226.50, "USD"),
            ("MSFT", 418.00, 415.00, "USD"),
            ("GOOGL", 168.00, 166.50, "USD"),
            ("NVDA", 134.00, 131.50, "USD"),
            ("SAP.DE", 212.00, 210.00, "EUR"),
            ("NOVO-B.CO", 114.00, 112.50, "EUR"),
            ("ADYEN.AS", 1435.00, 1420.00, "EUR"),
            ("BTC-USD", 65200.00, 64100.00, "USD"),
            ("ETH-USD", 2680.00, 2620.00, "USD"),
            ("TSLA", 245.00, 240.00, "USD"),
            ("BABA", 85.00, 84.00, "USD"),
            ("SOL-USD", 152.00, 148.00, "USD"),
            ("EURUSD=X", 1.0850, 1.0825, "USD"),
        ]

        with conn:
            for ticker, close, prev_close, curr in quotes_data:
                conn.execute(
                    """
                    INSERT INTO market_quotes (ticker, quote_date, close, prev_close, currency, fetched_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (ticker, today.isoformat(), close, prev_close, curr),
                )

        # ── 5. BUDGETS ────────────────────────────────────────────────
        # Category IDs from seed.sql:
        # Supermarket: 41, Restaurants: 51, Gym: 33, Utility Bills: 103,
        # Electricity & Gas: 13, Insurances: 20, Subscriptions: 30, Public Transit: 71,
        # Shopping & Personal: 60
        budgets_data = {
            41: 450.0,   # Supermarket
            51: 250.0,   # Restaurants
            52: 60.0,    # Cafes & Bakeries
            54: 80.0,    # Food Delivery
            33: 50.0,    # Gym & Fitness
            13: 180.0,   # Electricity & Gas
            15: 55.0,    # Internet
            21: 150.0,   # Health Insurance
            30: 55.0,    # Subscriptions
            71: 100.0,   # Public Transit
            61: 120.0,   # Clothing & Shoes
        }
        for cat_id, limit_eur in budgets_data.items():
            set_category_budget(conn, cat_id, limit_eur)

        # ── 6. TRANSACTIONS (18 MONTHS) ──────────────────────────────
        # Generate transactions backwards from today across 18 months (~548 days)
        # Category IDs:
        # Salary: 2 (Income)
        # Mortgage: 11 (Fixed)
        # Health Insurance: 21 (Fixed)
        # Electricity & Gas: 13 (Fixed)
        # Internet & Telecom: 15 (Fixed)
        # Water: 14 (Fixed)
        # Subscriptions: 31 (Fixed)
        # Supermarket: 41 (Discretionary)
        # Pharmacy: 42 (Discretionary)
        # Restaurants: 51 (Discretionary)
        # Cafes: 52 (Discretionary)
        # Bars: 53 (Discretionary)
        # Food Delivery: 54 (Discretionary)
        # Gym: 33 (Discretionary)
        # Public Transit: 71 (Discretionary)
        # Clothing: 61 (Discretionary)
        # Electronics: 62 (Discretionary)
        # Flights: 81 (Discretionary)
        # Internal Transfer: 101 (Transfer)

        own_ibans = {"NL91ABNA0417164300", "NL12REVO7123984510"}
        all_txs = []

        # Current balances tracking for snapshots
        running_abn = 650000      # 6,500.00 EUR initial
        running_rev = 180000      # 1,800.00 EUR initial
        running_etoro = 4800000   # 48,000.00 EUR initial

        # Generate month-by-month
        for m_offset in range(18, -1, -1):
            m_date = today - timedelta(days=m_offset * 30)
            year, month = m_date.year, m_date.month

            # Fixed day transactions for each month
            def d_in_m(day_num: int) -> date:
                try:
                    return date(year, month, min(day_num, 28))
                except Exception:
                    return date(year, month, 28)

            # 1. Salary around 24th
            sal_date = d_in_m(24)
            if sal_date <= today:
                sal_amount = 475000  # €4,750.00
                running_abn += sal_amount
                all_txs.append({
                    "account_id": 1,
                    "date": sal_date.isoformat(),
                    "amount": sal_amount,
                    "curr": "EUR",
                    "desc": "SALARIS BOOKING.COM BV MAANDELIJKSE UITBETALING",
                    "cp_name": "Booking.com B.V.",
                    "cp_iban": "NL02INGB0001234567",
                    "merchant": "Booking.com",
                    "cat_id": 2,
                    "is_transfer": 0,
                })

            # 2. Mortgage payment around 28th
            mort_date = d_in_m(28)
            if mort_date <= today:
                mort_amount = -178520  # -€1,785.20
                running_abn += mort_amount
                all_txs.append({
                    "account_id": 1,
                    "date": mort_date.isoformat(),
                    "amount": mort_amount,
                    "curr": "EUR",
                    "desc": "ABN AMRO HYPOTHEKEN MAANDAFLOSSING EN RENTE",
                    "cp_name": "ABN AMRO Hypotheken",
                    "cp_iban": "NL91ABNA0999888777",
                    "merchant": "ABN AMRO Hypotheek",
                    "cat_id": 11,
                    "is_transfer": 0,
                })

            # 3. Health insurance around 1st
            ins_date = d_in_m(1)
            if ins_date <= today:
                ins_amt = -14850
                running_abn += ins_amt
                all_txs.append({
                    "account_id": 1,
                    "date": ins_date.isoformat(),
                    "amount": ins_amt,
                    "curr": "EUR",
                    "desc": "ZILVEREN KRUIS ACHMEA PREMIE BASISVERZEKERING",
                    "cp_name": "Zilveren Kruis",
                    "cp_iban": "NL44INGB0007654321",
                    "merchant": "Zilveren Kruis",
                    "cat_id": 21,
                    "is_transfer": 0,
                })

            # 4. Energy & Utilities around 5th
            util_date = d_in_m(5)
            if util_date <= today:
                util_amt = -17500
                running_abn += util_amt
                all_txs.append({
                    "account_id": 1,
                    "date": util_date.isoformat(),
                    "amount": util_amt,
                    "curr": "EUR",
                    "desc": "VATTENFALL MAANDELIJKSE ENERGIEVOORSCHOT",
                    "cp_name": "Vattenfall N.V.",
                    "cp_iban": "NL88ABNA0112233445",
                    "merchant": "Vattenfall",
                    "cat_id": 13,
                    "is_transfer": 0,
                })

            # 5. Internet around 15th
            net_date = d_in_m(15)
            if net_date <= today:
                net_amt = -5250
                running_abn += net_amt
                all_txs.append({
                    "account_id": 1,
                    "date": net_date.isoformat(),
                    "amount": net_amt,
                    "curr": "EUR",
                    "desc": "KPN GLASVEZEL INTERNET & TELEFONIE",
                    "cp_name": "KPN B.V.",
                    "cp_iban": "NL23INGB0678912345",
                    "merchant": "KPN",
                    "cat_id": 15,
                    "is_transfer": 0,
                })

            # 6. Gym around 1st
            gym_date = d_in_m(1)
            if gym_date <= today:
                gym_amt = -4999
                running_abn += gym_amt
                all_txs.append({
                    "account_id": 1,
                    "date": gym_date.isoformat(),
                    "amount": gym_amt,
                    "curr": "EUR",
                    "desc": "TRAINMORE AMSTERDAM OOST LIDMAATSCHAP",
                    "cp_name": "TrainMore",
                    "cp_iban": "NL99RABO0334455667",
                    "merchant": "TrainMore",
                    "cat_id": 33,
                    "is_transfer": 0,
                })

            # 7. Subscriptions on Revolut around 10th
            sub_date = d_in_m(10)
            if sub_date <= today:
                subs = [
                    ("NETFLIX.COM AMSTERDAM", "Netflix", -1799, 31),
                    ("SPOTIFY AB STOCKHOLM", "Spotify", -1099, 31),
                    ("APPLE.COM/BILL ICLOUD", "Apple", -999, 31),
                    ("OPENAI *CHATGPT SUBSCRIPTION", "OpenAI", -1850, 32),
                ]
                for s_desc, s_merch, s_amt, s_cat in subs:
                    running_rev += s_amt
                    all_txs.append({
                        "account_id": 2,
                        "date": sub_date.isoformat(),
                        "amount": s_amt,
                        "curr": "EUR",
                        "desc": s_desc,
                        "cp_name": s_merch,
                        "cp_iban": None,
                        "merchant": s_merch,
                        "cat_id": s_cat,
                        "is_transfer": 0,
                    })

            # 8. Monthly transfers: ABN -> Revolut (+€750), ABN -> eToro (+€600)
            tr_date = d_in_m(26)
            if tr_date <= today:
                # To Revolut
                running_abn -= 75000
                running_rev += 75000
                all_txs.append({
                    "account_id": 1,
                    "date": tr_date.isoformat(),
                    "amount": -75000,
                    "curr": "EUR",
                    "desc": "OVERBOEKING NAAR REVOLUT VAULT NL12REVO7123984510",
                    "cp_name": "Revolut Vault",
                    "cp_iban": "NL12REVO7123984510",
                    "merchant": "Revolut",
                    "cat_id": 101,
                    "is_transfer": 1,
                })
                all_txs.append({
                    "account_id": 2,
                    "date": tr_date.isoformat(),
                    "amount": 75000,
                    "curr": "EUR",
                    "desc": "TOP-UP FROM ABN AMRO BETAALREKENING NL91ABNA0417164300",
                    "cp_name": "ABN AMRO Betaalrekening",
                    "cp_iban": "NL91ABNA0417164300",
                    "merchant": "ABN AMRO",
                    "cat_id": 101,
                    "is_transfer": 1,
                })

                # To eToro
                running_abn -= 60000
                all_txs.append({
                    "account_id": 1,
                    "date": tr_date.isoformat(),
                    "amount": -60000,
                    "curr": "EUR",
                    "desc": "ETORO EUROPE INVESTMENTS DEPOSIT",
                    "cp_name": "eToro Europe",
                    "cp_iban": "NL01RABO0998877665",
                    "merchant": "eToro",
                    "cat_id": 91,
                    "is_transfer": 1,
                })

            # 9. Discretionary spending during the month (groceries, dining, transit)
            discretionary_items = [
                # ABN AMRO Groceries
                (1, 3, "ALBERT HEIJN 1421 AMSTERDAM", "Albert Heijn", 41, -4250, -8500),
                (1, 7, "JUMBO SUPERMARKTEN AMSTERDAM", "Jumbo", 41, -2200, -5600),
                (1, 12, "ALBERT HEIJN 1845 AMSTERDAM", "Albert Heijn", 41, -3400, -7800),
                (1, 18, "MARQT OOST AMSTERDAM", "Marqt", 41, -1950, -4200),
                (1, 23, "ALBERT HEIJN 1421 AMSTERDAM", "Albert Heijn", 41, -4500, -9200),
                (1, 27, "EKOPLAZA AMSTERDAM", "Ekoplaza", 41, -2100, -4800),
                (1, 14, "ETOS 3312 AMSTERDAM", "Etos", 42, -1250, -3200),
                # Revolut Cafes, Dining, Transit
                (2, 2, "BROUWERIJ T IJ AMSTERDAM", "Brouwerij 't IJ", 53, -2400, -4800),
                (2, 6, "CAFE DE KLOS AMSTERDAM", "Cafe de Klos", 51, -5500, -9800),
                (2, 9, "BAKKERIJ WOLF AMSTERDAM", "Bakkerij Wolf", 52, -1250, -2200),
                (2, 13, "UBER EATS AMSTERDAM", "Uber Eats", 54, -2650, -4200),
                (2, 17, "NS-REIZIGERS UTRECHT CS", "NS Trein", 71, -1860, -3200),
                (2, 21, "GVB AMSTERDAM CONTACTLESS", "GVB", 71, -850, -1850),
                (2, 22, "RESTAURANT BREDA AMSTERDAM", "Restaurant Breda", 51, -7800, -13500),
                (2, 25, "COOLBLUE AMSTERDAM", "Coolblue", 62, -4500, -12000),
                (2, 26, "UNIQLO KALVERSTRAAT", "Uniqlo", 61, -3990, -8990),
            ]

            for acc_id, day_val, desc, merch, cat_id, min_c, max_c in discretionary_items:
                tx_d = d_in_m(day_val)
                if tx_d <= today:
                    low = min(min_c, max_c)
                    high = max(min_c, max_c)
                    amt = random.randint(low, high)
                    if acc_id == 1:
                        running_abn += amt
                    else:
                        running_rev += amt
                    all_txs.append({
                        "account_id": acc_id,
                        "date": tx_d.isoformat(),
                        "amount": amt,
                        "curr": "EUR",
                        "desc": desc,
                        "cp_name": merch,
                        "cp_iban": None,
                        "merchant": merch,
                        "cat_id": cat_id,
                        "is_transfer": 0,
                    })

        # Insert transactions with deterministic dedup hash
        with conn:
            for idx, tx in enumerate(all_txs):
                h = dedup_hash(
                    booking_date=tx["date"],
                    amount_minor=tx["amount"],
                    currency=tx["curr"],
                    description=tx["desc"],
                    occurrence_idx=idx,
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        account_id, dedup_hash, booking_date, amount_minor, currency,
                        amount_eur_minor, description_raw, counterparty_name, counterparty_iban,
                        merchant_normalized, category_id, is_internal_transfer, source
                    ) VALUES (
                        :account_id, :hash, :date, :amount, :curr,
                        :amount, :desc, :cp_name, :cp_iban,
                        :merchant, :cat_id, :is_transfer, 'csv'
                    )
                    """,
                    {
                        "account_id": tx["account_id"],
                        "hash": h,
                        "date": tx["date"],
                        "amount": tx["amount"],
                        "curr": tx["curr"],
                        "desc": tx["desc"],
                        "cp_name": tx["cp_name"],
                        "cp_iban": tx["cp_iban"],
                        "merchant": tx["merchant"],
                        "cat_id": tx["cat_id"],
                        "is_transfer": tx["is_transfer"],
                    },
                )

        # ── 7. ACCOUNT SNAPSHOTS ──────────────────────────────────────
        # Generate daily snapshots for the past 60 days, and monthly for the 18 months prior
        with conn:
            # Monthly snapshots for past 18 months
            for mo in range(18, 2, -1):
                s_date = today - timedelta(days=mo * 30)
                factor = (18 - mo) / 18.0
                abn_bal = int(350000 + factor * 250000)
                rev_bal = int(120000 + factor * 80000)
                etoro_bal = int(3200000 + factor * 1400000)
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (1, ?, ?, ?)",
                    (s_date.isoformat(), abn_bal, abn_bal),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (2, ?, ?, ?)",
                    (s_date.isoformat(), rev_bal, rev_bal),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (3, ?, ?, ?)",
                    (s_date.isoformat(), etoro_bal, etoro_bal),
                )

            # Daily snapshots for the last 60 days
            for d in range(60, -1, -1):
                s_date = today - timedelta(days=d)
                # Modulate slightly for natural curves
                noise = int(random.uniform(-5000, 5000))
                abn_cur = max(100000, running_abn + noise)
                rev_cur = max(50000, running_rev + (noise // 2))
                etoro_cur = max(3000000, running_etoro + noise * 5)
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (1, ?, ?, ?)",
                    (s_date.isoformat(), abn_cur, abn_cur),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (2, ?, ?, ?)",
                    (s_date.isoformat(), rev_cur, rev_cur),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO account_snapshots VALUES (3, ?, ?, ?)",
                    (s_date.isoformat(), etoro_cur, etoro_cur),
                )

        # ── 8. REPORT SUMMARY & INVARIANTS ────────────────────────────
        n_accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        n_tx = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        n_holdings = conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
        n_closed = conn.execute("SELECT COUNT(*) FROM holdings WHERE status = 'closed'").fetchone()[0]
        n_quotes = conn.execute("SELECT COUNT(*) FROM market_quotes").fetchone()[0]
        n_liabilities = conn.execute("SELECT COUNT(*) FROM liabilities").fetchone()[0]

        print("=" * 60)
        print("DEMO DATABASE SEEDED SUCCESSFULLY")
        print(f"Database Path : {DEMO_DB_PATH}")
        print(f"Accounts      : {n_accounts} (ABN AMRO, Revolut, eToro)")
        print(f"Transactions  : {n_tx} (18 months categorized)")
        print(f"Holdings      : {n_holdings} ({n_closed} closed positions)")
        print(f"Market Quotes : {n_quotes}")
        print(f"Liabilities   : {n_liabilities} (Mortgage + 360-month schedule)")
        print("=" * 60)

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo database for Personal Finance Assistant.")
    parser.add_argument("--reset", action="store_true", help="Reset and rebuild data/demo.db from scratch.")
    args = parser.parse_args()

    seed_demo_data(reset=args.reset)


if __name__ == "__main__":
    main()

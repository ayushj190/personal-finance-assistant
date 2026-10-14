"""Copilot tool schemas definitions for LLM function calling."""
from typing import Any


def _date_scope_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Optional requested range. Use {\"preset\": one of Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time}, or {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"}.",
        "properties": {
            "preset": {"type": "string", "enum": ["Last 3 Months", "MTD", "Last Month", "YTD", "Last 12 Months", "All Time"]},
            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
        },
    }


COPILOT_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_net_worth",
            "description": "Calculate and return real-time net worth (cash, investments, home equity, total).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_by_category",
            "description": "Get total spending broken down by category for a specific month and year (e.g. year=2026, month=10), or overall. Prefer the date_scope argument for relative ranges like 'last month'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "4-digit year like 2026", "minimum": 1900, "maximum": 2100},
                    "month": {"type": "integer", "description": "Month number (1-12)", "minimum": 1, "maximum": 12},
                    "date_scope": {
                        "type": "object",
                        "description": "Optional requested range. Use {\"preset\": one of Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time}, or {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"}. Wins over year and month.",
                        "properties": {
                            "preset": {"type": "string", "enum": ["Last 3 Months", "MTD", "Last Month", "YTD", "Last 12 Months", "All Time"]},
                            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": "Retrieve recent transactions optionally filtered by category and by a requested date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of transactions to return (default 15, max 100)", "minimum": 1, "maximum": 100},
                    "category": {"type": "string", "description": "Category name filter (e.g. Groceries, Dining)"},
                    "date_scope": {
                        "type": "object",
                        "description": "Optional requested range. Use {\"preset\": one of Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time}, or {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"}.",
                        "properties": {
                            "preset": {"type": "string", "enum": ["Last 3 Months", "MTD", "Last Month", "YTD", "Last 12 Months", "All Time"]},
                            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_cashflow",
            "description": "Get monthly income, expenses, and savings summary. A requested date scope that is not aligned to whole months is snapped to whole months and noted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Filter by 4-digit year", "minimum": 1900, "maximum": 2100},
                    "date_scope": {
                        "type": "object",
                        "description": "Optional requested range. Use {\"preset\": one of Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time}, or {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"}.",
                        "properties": {
                            "preset": {"type": "string", "enum": ["Last 3 Months", "MTD", "Last Month", "YTD", "Last 12 Months", "All Time"]},
                            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_investments",
            "description": "Analyze investment portfolio asset classes, holdings by type, target drift, and risk profile alignment.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_tax_situation",
            "description": "Retrieve gross income and wealth balances for Dutch Box 1 and Box 3 calculations.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_mortgage",
            "description": "Analyze active mortgages, interest rate periods, and upcoming repayment schedules.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search web for news, company descriptions, or current market info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Web search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_market_data",
            "description": "Fetch live market price and fundamentals for a stock or ETF ticker (e.g. AAPL, VWCE.DE).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_privacy_mode",
            "description": "Toggle or set privacy mode to hide/show amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enable": {"type": "boolean", "description": "True to hide amounts, False to show"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_theme",
            "description": "Switch app theme between 'dark' and 'light'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "enum": ["dark", "light"]},
                },
                "required": ["theme"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_active_allocation_profile",
            "description": "Set the active investment asset allocation profile by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile_name": {"type": "string", "description": "Name of the allocation profile"},
                },
                "required": ["profile_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_allocation_profiles",
            "description": "List every saved investment allocation profile with its dimension, targets, drift band, and whether it is active.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_allocation_profile",
            "description": "Create a new investment allocation profile. Targets must sum to 100 percent within 0.1 and every bucket must be valid for the chosen dimension.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Unique profile name (matched case insensitively)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["sector", "region", "currency", "nature"],
                        "description": "Dimension the targets are grouped by. 'nature' is equities, bonds, commodities, and crypto.",
                    },
                    "targets": {
                        "type": "object",
                        "description": "Map of bucket name to target percent (0 to 100 at one decimal), e.g. {\"Equities\": 70.0, \"Fixed Income\": 30.0}",
                        "additionalProperties": {"type": "number"},
                    },
                    "drift_band_pct": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Absolute drift tolerance band in percentage points (default 5)",
                    },
                    "include_cash": {
                        "type": "boolean",
                        "description": "Treat liquid cash as an extra bucket (default false)",
                    },
                },
                "required": ["name", "dimension", "targets"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_allocation_profile",
            "description": "Delete an allocation profile. The first call returns a confirmation token; call again with the same name and that confirm_token to actually delete. Refuses the active or last remaining profile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the profile to delete (matched case insensitively)"},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_savings_rate",
            "description": "Update APY interest rate or balance for a savings/cash account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "institution_or_name": {"type": "string", "description": "Bank or account name"},
                    "apy_pct": {"type": "number", "description": "Annual interest percentage yield"},
                    "balance_eur": {"type": "number", "description": "Optional updated balance"},
                },
                "required": ["institution_or_name", "apy_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_mortgage_payment",
            "description": "Record extra principal repayment on a mortgage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_name": {"type": "string", "description": "Name or lender of the loan"},
                    "amount_eur": {"type": "number", "description": "Extra repayment amount in EUR"},
                    "paid_date": {"type": "string", "description": "YYYY-MM-DD date"},
                    "recalc": {"type": "string", "enum": ["lower_payment", "shorter_term"]},
                },
                "required": ["loan_name", "amount_eur"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_risk_profile",
            "description": "Retrieve user's investment risk profile.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "auto_categorize_uncategorized_transactions",
            "description": "Automatically categorize uncategorized transactions using AI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max transactions to categorize (default 50)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_profile_form",
            "description": "Request UI dialog form for 'tax_profile' or 'risk_profile'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_type": {"type": "string", "enum": ["tax_profile", "risk_profile", "mortgage_config"]},
                },
                "required": ["form_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_tax_optimization",
            "description": "Simulate 4-way capital trade-off (Mortgage Prepayment vs Pillar 3 Jaarruimte vs Groenfonds vs Taxable ETF) with interactive trajectory chart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "capital_eur": {"type": "number", "description": "Lump sum amount in EUR to allocate (e.g. 5000, 10000)", "minimum": 1},
                    "horizon_years": {"type": "integer", "description": "Investment horizon in years (default 10)", "minimum": 1, "maximum": 50},
                },
                "required": ["capital_eur"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_pension_room",
            "description": "Calculate official Dutch Pillar 3 pension gap (Jaarruimte), immediate Box 1 tax refund, and compound tax shield.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gross_income": {"type": "number", "description": "Optional gross annual income override", "minimum": 0},
                    "factor_a": {"type": "number", "description": "Optional Factor A (pensioenaangroei from UPO)", "minimum": 0},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_green_fund_strategy",
            "description": "Analyze Dutch Groenfondsen double tax benefit (Box 3 exemption up to €71k/€142k and 0.1% Box 1 credit) with certified fund list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_allocation": {"type": "number", "description": "Prospective amount in EUR to invest in green funds", "minimum": 0},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_tax_leaks",
            "description": "Proactively scan accounts, liabilities, and income for Dutch tax inefficiencies (cash drag, unused HRA/prepayments, top bracket deductions).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_financial_document",
            "description": "Index a custom financial text document (e.g. UPO pension statement, mortgage advice note) into local RAG knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_title": {"type": "string", "description": "Title of the document"},
                    "content": {"type": "string", "description": "Full text or summary of the document"},
                    "category": {"type": "string", "description": "Category (e.g. pension, mortgage, tax, custom)"},
                },
                "required": ["doc_title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_dutch_law_vault",
            "description": "Search the local Dutch Financial Law Vector Vault for verified statutory provisions, articles, and rulings across Box 1, Box 3 wealth tax, pensions (Wet toekomst pensioenen), mortgages (Wft/Nibud), gifting/inheritance (Successiewet 1956), and expat 30% facility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Legal or financial query (e.g. 'hypotheekrenteaftrek', 'werkelijk rendement box 3', 'jaarruimte 30%')"},
                    "category": {"type": "string", "enum": ["tax_box1", "tax_box3", "pension", "mortgage", "estate", "expat", "green_funds"], "description": "Optional category filter"},
                    "effective_year": {"type": "integer", "description": "Optional tax or regulatory year filter like 2026"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_tax_law_article",
            "description": "Look up an exact statutory tax article or legal reference (e.g. 'Art. 3.16', 'Art. 5.2', 'Art. 3.120', 'Hoge Raad') from the Dutch Financial Law Vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_ref": {"type": "string", "description": "Exact statutory article number, e.g. 'Art. 3.16', 'Art. 5.2', 'Art. 3.120'"},
                },
                "required": ["article_ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_view",
            "description": "Open the page that owns a topic for the user, optionally an Investments tab, a date scope, and validated view parameters that shape the page to the question. Call it whenever a question is about a topic with its own page (spending, investments, mortgage, tax, transactions, net worth), even if the user did not phrase it as navigation, alongside the data tool that answers. The result moves the app; the answer in chat should still quote the numbers the data tools returned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "string",
                        "enum": ["dashboard", "spending", "investments", "mortgage", "transactions", "tax", "settings"],
                        "description": "Destination page id: dashboard (net worth), spending, investments, mortgage, transactions, tax, settings",
                    },
                    "tab": {
                        "type": "string",
                        "enum": ["portfolio", "allocation", "income_tax", "goals"],
                        "description": "Optional Investments tab id; ignored with a note on a page with no tabs",
                    },
                    "date_scope": {
                        "type": "object",
                        "description": "Optional requested range. Use {\"preset\": one of Last 3 Months, MTD, Last Month, YTD, Last 12 Months, All Time}, or {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"}.",
                        "properties": {
                            "preset": {"type": "string", "enum": ["Last 3 Months", "MTD", "Last Month", "YTD", "Last 12 Months", "All Time"]},
                            "start": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end": {"type": "string", "description": "End date YYYY-MM-DD"},
                        },
                    },
                    "view": {
                        "type": "object",
                        "description": "Optional view parameters that shape the page to the question. spending: {category}. transactions: {category, search}. investments: {sort: value_eur|day_change_pct|day_pnl_eur|unrealized_pnl_eur|total_pnl_pct|quantity|price|cost_basis|name|ticker, movers: gainers|losers, search: ticker text, exposure_dimension: Sector|Region|Currency|Nature, focus: live bucket}. A key or value not allowed for the page is ignored with a note.",
                        "properties": {
                            "category": {"type": "string", "description": "Category name filter (Spending or Transactions)"},
                            "search": {"type": "string", "description": "Search text filter (Transactions merchant or Investments ticker/name)"},
                            "sort": {"type": "string", "enum": ["value_eur", "day_change_pct", "day_pnl_eur", "unrealized_pnl_eur", "total_pnl_pct", "quantity", "price", "cost_basis", "name", "ticker"], "description": "Investments live table sort column"},
                            "movers": {"type": "string", "enum": ["gainers", "losers"], "description": "Investments live table movers filter"},
                            "exposure_dimension": {"type": "string", "enum": ["Sector", "Region", "Currency", "Nature"], "description": "Investments exposure dimension"},
                            "focus": {"type": "string", "description": "A live bucket of the exposure dimension to focus the market carpet and dimension charts, e.g. Technology"},
                        },
                    },
                },
                "required": ["page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Compare spending and cashflow totals across two date ranges, with the difference (range B minus range A).",
            "parameters": {
                "type": "object",
                "properties": {
                    "range_a": _date_scope_schema(),
                    "range_b": _date_scope_schema(),
                },
                "required": ["range_a", "range_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": "Per category monthly budget status: budget, spent, remaining, and whether it is over budget.",
            "parameters": {
                "type": "object",
                "properties": {"date_scope": _date_scope_schema()},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balances",
            "description": "List every account with its latest balance and asset class.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_forecast",
            "description": "The average burn rate per month and the projected month end spend, for the requested date_scope (or the trailing three months when none is given).",
            "parameters": {
                "type": "object",
                "properties": {"date_scope": _date_scope_schema()},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_income_summary",
            "description": "Income by category over a period, plus projected holding dividends.",
            "parameters": {
                "type": "object",
                "properties": {"date_scope": _date_scope_schema()},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_bills",
            "description": "Recurring charges detected in the ledger and their next due date.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_net_worth_history",
            "description": "An approximate monthly net worth series (ledger running cash balance plus the current invested value held flat).",
            "parameters": {
                "type": "object",
                "properties": {"date_scope": _date_scope_schema()},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "categorize_transactions",
            "description": "Categorize transactions. The first call returns a confirmation token and changes nothing; call again with the same arguments plus that confirm_token to actually write.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Target category name"},
                    "transaction_ids": {"type": "array", "items": {"type": "integer"}, "description": "Explicit transaction ids to categorize"},
                    "tx_filter": {"type": "object", "description": "Instead of ids: {uncategorized: true}, {merchant: text}, or {category: name}", "properties": {"uncategorized": {"type": "boolean"}, "merchant": {"type": "string"}, "category": {"type": "string"}}},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_as_transfer",
            "description": "Mark transactions as internal transfers. The first call returns a confirmation token and changes nothing; call again with that confirm_token to write.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_ids": {"type": "array", "items": {"type": "integer"}, "description": "Transaction ids to mark as transfers"},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["transaction_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_transaction",
            "description": "Edit one transaction's category or description. The first call returns a confirmation token and changes nothing; call again with that confirm_token to write.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "integer", "description": "Transaction id to edit"},
                    "category": {"type": "string", "description": "New category name"},
                    "description": {"type": "string", "description": "New description text"},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "Delete one transaction. The first call returns a confirmation token and changes nothing; call again with that confirm_token to write.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "integer", "description": "Transaction id to delete"},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_budget_cap",
            "description": "Set a category monthly budget cap. The first call returns a confirmation token and changes nothing; call again with that confirm_token to write.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category name"},
                    "cap_eur": {"type": "number", "description": "Monthly budget cap in EUR"},
                    "confirm_token": {"type": "string", "description": "Token returned by the first call; empty on the first call"},
                },
                "required": ["category", "cap_eur"],
            },
        },
    },
]

"""Copilot tool schemas definitions for LLM function calling."""
from typing import Any

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
            "description": "Get total spending broken down by category for a specific month and year (e.g. year=2026, month=10), or overall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "4-digit year like 2026"},
                    "month": {"type": "integer", "description": "Month number (1-12)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_transactions",
            "description": "Retrieve recent transactions optionally filtered by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of transactions to return (default 15)"},
                    "category": {"type": "string", "description": "Category name filter (e.g. Groceries, Dining)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_cashflow",
            "description": "Get monthly income, expenses, and savings summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Filter by 4-digit year"},
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
            "name": "search_financial_knowledge_base",
            "description": "Search local unstructured knowledge base for Dutch tax laws, Box 1/3 rules, pension spaces (jaarruimte/lijfrente), or mortgage rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query about tax, mortgage, or financial concepts"},
                },
                "required": ["query"],
            },
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
                    "capital_eur": {"type": "number", "description": "Lump sum amount in EUR to allocate (e.g. 5000, 10000)"},
                    "horizon_years": {"type": "integer", "description": "Investment horizon in years (default 10)"},
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
                    "gross_income": {"type": "number", "description": "Optional gross annual income override"},
                    "factor_a": {"type": "number", "description": "Optional Factor A (pensioenaangroei from UPO)"},
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
                    "target_allocation": {"type": "number", "description": "Prospective amount in EUR to invest in green funds"},
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
]

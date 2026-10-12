"""Agent copilot tool package exposing registered tools and schemas."""

from agent.tool_schemas import COPILOT_TOOLS_SCHEMA
from agent.tools.net_worth import (
    tool_get_current_net_worth,
    tool_toggle_privacy_mode,
    tool_set_theme,
    tool_update_savings_rate,
)
from agent.tools.investments import (
    tool_set_active_allocation_profile,
    tool_get_allocation_profiles,
    tool_create_allocation_profile,
    tool_delete_allocation_profile,
    tool_save_risk_profile,
    tool_get_risk_profile,
    tool_analyze_investments,
    tool_get_portfolio_and_risk_summary,
)
from agent.tools.spending import (
    tool_auto_categorize_uncategorized_transactions,
    tool_get_spending_by_category,
    tool_get_recent_transactions,
    tool_get_monthly_cashflow,
)
from agent.tools.tax import (
    tool_save_tax_profile,
    tool_simulate_tax_optimization,
    tool_calculate_pension_room,
    tool_analyze_green_fund_strategy,
    tool_diagnose_tax_leaks,
    tool_analyze_tax_situation,
)
from agent.tools.legal import (
    tool_search_dutch_law_vault,
    tool_lookup_tax_law_article,
    tool_search_financial_knowledge_base,
    tool_ingest_financial_document,
)
from agent.tools.imports import (
    tool_parse_and_import_file,
)
from agent.tools.market import (
    tool_search_web,
    tool_analyze_market_data,
    tool_add_mortgage_payment,
    tool_analyze_mortgage,
    tool_request_profile_form,
)

# Re-exports for test compatibility and patch mocking
from db.repositories import AccountRepository, HoldingRepository
from services.portfolio import get_consolidated_holdings_df

__all__ = [
    "COPILOT_TOOLS_SCHEMA",
    "tool_get_current_net_worth",
    "tool_toggle_privacy_mode",
    "tool_set_theme",
    "tool_set_active_allocation_profile",
    "tool_get_allocation_profiles",
    "tool_create_allocation_profile",
    "tool_delete_allocation_profile",
    "tool_update_savings_rate",
    "tool_add_mortgage_payment",
    "tool_save_risk_profile",
    "tool_get_risk_profile",
    "tool_analyze_investments",
    "tool_get_portfolio_and_risk_summary",
    "tool_parse_and_import_file",
    "tool_auto_categorize_uncategorized_transactions",
    "tool_get_spending_by_category",
    "tool_get_recent_transactions",
    "tool_get_monthly_cashflow",
    "tool_search_dutch_law_vault",
    "tool_lookup_tax_law_article",
    "tool_search_financial_knowledge_base",
    "tool_search_web",
    "tool_analyze_market_data",
    "tool_save_tax_profile",
    "tool_simulate_tax_optimization",
    "tool_calculate_pension_room",
    "tool_analyze_green_fund_strategy",
    "tool_diagnose_tax_leaks",
    "tool_ingest_financial_document",
    "tool_analyze_tax_situation",
    "tool_analyze_mortgage",
    "tool_request_profile_form",
    "AccountRepository",
    "HoldingRepository",
    "get_consolidated_holdings_df",
]

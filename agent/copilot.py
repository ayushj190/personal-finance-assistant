from datetime import date
import json
from typing import Any, Iterator

from agent import tools
from agent.tools import COPILOT_TOOLS_SCHEMA
from services.llm_client import chat_with_tools, generate_stream

SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app.
You run locally and privately on the user's machine.
You have access to native deterministic tools for querying net worth, category spending, recent transactions, cashflows, portfolio investments, tax analysis, mortgage schedules, financial simulations, and a local Dutch Financial Law Vector Vault.

Always call the relevant tool when the user asks about their financial data, accounts, spending, mortgage options, or tax strategies:
- Use `search_dutch_law_vault` to search Dutch tax laws (Box 1 rates, Box 3 wealth tax & actual return rulings), mortgage deduction (HRA), Pillar 3 pension (Wet toekomst pensioenen / Jaarruimte), estate/gifting (Successiewet 1956), and expat 30% facility. Always cite the exact statutory articles returned.
- Use `lookup_tax_law_article` when the user asks for a specific statutory provision (e.g. 'Art. 3.16', 'Art. 5.2', 'Art. 3.120', 'Hoge Raad 2024').
- Use `search_financial_knowledge_base` as an alternative knowledge query tool.
- Use `simulate_tax_optimization` when the user asks how to allocate capital (e.g. bonus, savings) between mortgage prepayment, pension (Jaarruimte), green funds, or ETFs.
- Use `calculate_pension_room` for questions about Dutch pension gaps, Factor A, and tax rebates.
- Use `analyze_green_fund_strategy` for questions about Groenfondsen double tax benefits.
- Use `diagnose_tax_leaks` when the user asks for financial checkups or tax optimization tips.
- Use deterministic tool outputs rather than calculating compound growth or tax brackets in raw tokens.

Today's date is: {today}.
"""

TOOL_MAP = {
    "get_current_net_worth": tools.tool_get_current_net_worth,
    "get_spending_by_category": tools.tool_get_spending_by_category,
    "get_recent_transactions": tools.tool_get_recent_transactions,
    "get_monthly_cashflow": tools.tool_get_monthly_cashflow,
    "analyze_investments": tools.tool_analyze_investments,
    "analyze_tax_situation": tools.tool_analyze_tax_situation,
    "analyze_mortgage": tools.tool_analyze_mortgage,
    "search_financial_knowledge_base": tools.tool_search_financial_knowledge_base,
    "search_dutch_law_vault": tools.tool_search_dutch_law_vault,
    "lookup_tax_law_article": tools.tool_lookup_tax_law_article,
    "search_web": tools.tool_search_web,
    "analyze_market_data": tools.tool_analyze_market_data,
    "toggle_privacy_mode": tools.tool_toggle_privacy_mode,
    "set_theme": tools.tool_set_theme,
    "set_active_allocation_profile": tools.tool_set_active_allocation_profile,
    "update_savings_rate": tools.tool_update_savings_rate,
    "add_mortgage_payment": tools.tool_add_mortgage_payment,
    "save_risk_profile": tools.tool_save_risk_profile,
    "get_risk_profile": tools.tool_get_risk_profile,
    "save_tax_profile": tools.tool_save_tax_profile,
    "auto_categorize_uncategorized_transactions": tools.tool_auto_categorize_uncategorized_transactions,
    "request_profile_form": tools.tool_request_profile_form,
    "simulate_tax_optimization": tools.tool_simulate_tax_optimization,
    "calculate_pension_room": tools.tool_calculate_pension_room,
    "analyze_green_fund_strategy": tools.tool_analyze_green_fund_strategy,
    "diagnose_tax_leaks": tools.tool_diagnose_tax_leaks,
    "ingest_financial_document": tools.tool_ingest_financial_document,
}


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_MAP.get(tool_name)
    if not fn:
        return {"success": False, "message": f"Unknown tool '{tool_name}'"}

    try:
        return fn(**arguments)
    except Exception as e:
        return {"success": False, "message": f"Tool execution error: {str(e)}"}


def run_copilot(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run Copilot turn with native tool calling and return a stream generator plus artifacts."""
    # 1. Handle statement uploads directly
    if uploaded_files:
        file_results = []
        for uf in uploaded_files:
            res = tools.tool_parse_and_import_file(
                file_name=uf["name"],
                file_bytes=uf["bytes"],
                confirm_balance=uf.get("confirm_balance"),
            )
            file_results.append(res.get("message", f"Processed {uf['name']}"))

        combined_msg = "### 📥 Statement Import Results:\n" + "\n".join(f"- {m}" for m in file_results)

        def _direct_stream(text: str) -> Iterator[str]:
            import re
            import time
            tokens = re.split(r'(\s+)', text)
            for tok in tokens:
                if tok:
                    yield tok
                    time.sleep(0.012)

        return {
            "role": "assistant",
            "stream": _direct_stream(combined_msg),
            "figure": None,
            "df": None,
            "form_request": None,
        }

    # 2. Build conversation history
    system_text = SYSTEM_PROMPT.replace("{today}", date.today().isoformat())
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_text}]

    if history:
        for h in history[-6:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                # Truncate any past massive dumps to maintain light context
                if role == "assistant" and len(content) > 1000:
                    content = content[:500] + "\n... [truncated] ..." + content[-200:]
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    # 3. Call Ollama with native tools array
    assistant_msg = chat_with_tools(messages, tools=COPILOT_TOOLS_SCHEMA)

    if not assistant_msg:
        def _err_stream() -> Iterator[str]:
            yield "⚠️ Could not connect to local Ollama. Please ensure Ollama is running (`ollama serve`)."

        return {
            "role": "assistant",
            "stream": _err_stream(),
            "figure": None,
            "df": None,
            "form_request": None,
        }

    tool_calls = assistant_msg.get("tool_calls") or []

    # 4. If no tools called, return the direct response stream
    if not tool_calls:
        direct_content = assistant_msg.get("content") or "How can I help you with your finances today?"

        def _direct_content_stream(text: str) -> Iterator[str]:
            import re
            import time
            tokens = re.split(r'(\s+)', text)
            for tok in tokens:
                if tok:
                    yield tok
                    time.sleep(0.012)

        return {
            "role": "assistant",
            "stream": _direct_content_stream(direct_content),
            "figure": None,
            "df": None,
            "form_request": None,
        }

    # 5. Execute tool calls deterministically
    captured_figure = None
    captured_df = None
    captured_form = None
    captured_citations = []

    for tc in tool_calls:
        fn_info = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", {})
        fn_name = fn_info.get("name") if isinstance(fn_info, dict) else getattr(fn_info, "name", "")
        fn_args = fn_info.get("arguments") if isinstance(fn_info, dict) else getattr(fn_info, "arguments", {})
        if isinstance(fn_args, str):
            try:
                fn_args = json.loads(fn_args)
            except Exception:
                fn_args = {}

        result = execute_tool(fn_name, fn_args)

        if result.get("figure") is not None:
            captured_figure = result["figure"]
        if result.get("df") is not None:
            captured_df = result["df"]
        if result.get("form_request"):
            captured_form = result["form_request"]
        if result.get("citations"):
            captured_citations.extend(result["citations"])
        elif result.get("article"):
            captured_citations.append(result["article"])

        # Append assistant tool call & tool result to message history for final summarization
        messages.append({
            "role": "assistant",
            "content": f"Calling tool `{fn_name}` with arguments: {json.dumps(fn_args)}",
        })
        clean_result = {k: v for k, v in result.items() if k not in ("figure", "df")}
        messages.append({
            "role": "user",
            "content": f"Tool `{fn_name}` result:\n{json.dumps(clean_result, default=str)}\nPlease summarize these findings concisely for me.",
        })

    # 6. Stream final summarization from LLM
    stream_gen = generate_stream(messages)

    return {
        "role": "assistant",
        "stream": stream_gen,
        "figure": captured_figure,
        "df": captured_df,
        "form_request": captured_form,
        "citations": captured_citations,
    }

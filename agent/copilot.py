from datetime import date
import inspect
import json
from typing import Any, Iterator

from agent import tools
from agent.tools import COPILOT_TOOLS_SCHEMA
from services.llm_client import chat_with_tools, generate_stream
from services.navigation import match_fast_path

SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app, running locally and privately on the user's machine.

CRITICAL ACCURACY RULES:
- Never confuse debt liabilities (mortgage, loans) with investment portfolio capital.
- Always quote the exact numbers the tools return; never estimate or invent amounts.
- For investments rely on `total_portfolio_value_eur`, `total_portfolio_value_formatted`, and `holdings_by_asset_type_eur` from `analyze_investments`.
- Never present a minor unit (cents) figure; use the euro formatted fields the tools provide.

Call the relevant tool whenever the user asks about their financial data:
- analyze_investments: portfolio value, allocation, drift, and risk.
- get_allocation_profiles, create_allocation_profile, delete_allocation_profile: manage target allocation strategies. A create needs targets that sum to 100 percent; a delete needs the confirmation token returned by the first call.
- get_current_net_worth: overall balance sheet.
- get_spending_by_category, get_recent_transactions, get_monthly_cashflow: spending and cashflow. Pass the requested range as the date_scope argument (a preset name or a start and end date) so the answer and the page agree.
- open_view: actually open a page for the user, optionally an Investments tab and a date scope. Call it whenever the user asks to see, open, or go to a screen, even while you also call a data tool to answer.
- analyze_mortgage: mortgage schedules and rates.
- analyze_tax_situation, simulate_tax_optimization, calculate_pension_room, analyze_green_fund_strategy, diagnose_tax_leaks: Dutch tax questions.
- search_dutch_law_vault and lookup_tax_law_article: cite exact Dutch statutory articles.

NAVIGATION RULES:
- When the user asks to see, open, go to, or show a screen, call open_view with the matching page and tab. Never claim you opened a page unless you called open_view.
- If the destination screen is ambiguous, ask one short question naming the candidate screens and do not call open_view until the user answers.
- If the request names a page that has no date filter but asks for a period, still open the page and say plainly that the page has no date scope.
- Pass the requested period to the data tools as date_scope so the answer and the page agree.

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
    "get_allocation_profiles": tools.tool_get_allocation_profiles,
    "create_allocation_profile": tools.tool_create_allocation_profile,
    "delete_allocation_profile": tools.tool_delete_allocation_profile,
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
    "open_view": tools.tool_open_view,
}


import traceback


def _format_friendly_error(tool_name: str, exc: Exception) -> tuple[str, str]:
    """Return friendly message and remedy for tool errors."""
    err_str = str(exc)
    if "not authorized" in err_str.lower() or "authorization" in err_str.lower():
        return (
            f"The '{tool_name}' query was blocked by the read only database authorizer to keep your financial ledger secure.",
            "Copilot query tools cannot alter, insert, or delete ledger records.",
        )
    if "locked" in err_str.lower() or "busy" in err_str.lower():
        return (
            f"The database was temporarily busy while running '{tool_name}'.",
            "Please try running your question again in a few moments.",
        )
    if isinstance(exc, (ValueError, TypeError)):
        return (
            f"Invalid parameters were provided for tool '{tool_name}'.",
            "Check that dates, limits, and numeric values are formatted correctly.",
        )
    if isinstance(exc, FileNotFoundError):
        return (
            f"A required local database or file for '{tool_name}' could not be found.",
            "Verify that your local database exists and migrations have run.",
        )
    return (
        f"An error occurred while executing '{tool_name}': {err_str}",
        "Check technical diagnostics below or retry your request.",
    )


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_MAP.get(tool_name)
    if not fn:
        return {
            "success": False,
            "message": f"Unknown tool '{tool_name}'.",
            "error": f"Tool '{tool_name}' is not registered in TOOL_MAP.",
            "diagnostics": {
                "tool": tool_name,
                "arguments": arguments,
                "error_type": "UnknownToolError",
                "error_details": f"Tool '{tool_name}' is not recognized.",
            },
        }

    arguments = arguments or {}

    # Guided error for an argument a tool does not declare, instead of an internal TypeError (AC-16).
    try:
        signature = inspect.signature(fn)
        accepts_kwargs = any(
            p.kind == p.VAR_KEYWORD for p in signature.parameters.values()
        )
        if not accepts_kwargs:
            allowed = {
                name
                for name, p in signature.parameters.items()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            }
            unknown = [k for k in arguments if k not in allowed]
            if unknown:
                accepts = ", ".join(sorted(allowed)) if allowed else "no arguments"
                return {
                    "success": False,
                    "message": (
                        f"Tool '{tool_name}' does not accept the argument(s): "
                        f"{', '.join(unknown)}. It accepts: {accepts}."
                    ),
                    "diagnostics": {
                        "tool": tool_name,
                        "arguments": arguments,
                        "error_type": "UnknownArgumentError",
                        "error_details": f"Unexpected argument(s): {', '.join(unknown)}.",
                    },
                }
    except (TypeError, ValueError):
        pass

    try:
        res = fn(**arguments)
        if isinstance(res, dict) and not res.get("success", True):
            if "diagnostics" not in res:
                res["diagnostics"] = {
                    "tool": tool_name,
                    "arguments": arguments,
                    "error_type": "ToolReturnedFailure",
                    "error_details": res.get("message", "Tool returned failure status"),
                }
        return res
    except Exception as e:
        friendly_msg, remedy = _format_friendly_error(tool_name, e)
        return {
            "success": False,
            "message": f"{friendly_msg} {remedy}",
            "error": str(e),
            "diagnostics": {
                "tool": tool_name,
                "arguments": arguments,
                "error_type": type(e).__name__,
                "error_details": str(e),
                "traceback": traceback.format_exc(),
            },
        }


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
            "ui_intent": None,
        }

    # 1.5 Deterministic fast path for explicit navigation phrasing (AC-21). No model call.
    fast_intent = match_fast_path(user_message)
    if fast_intent:
        label = (fast_intent.get("tab") or fast_intent.get("page") or "").replace("_", " ").title()
        confirmation = f"Opening {label}."

        def _fast_stream(text: str) -> Iterator[str]:
            import re as _re
            import time as _time
            for tok in _re.split(r'(\s+)', text):
                if tok:
                    yield tok
                    _time.sleep(0.012)

        return {
            "role": "assistant",
            "stream": _fast_stream(confirmation),
            "figure": None,
            "df": None,
            "form_request": None,
            "ui_intent": fast_intent,
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
            "ui_intent": None,
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
            "ui_intent": None,
        }

    # 5. Execute tool calls deterministically
    captured_figure = None
    captured_df = None
    captured_form = None
    captured_citations = []
    captured_diagnostics = []
    captured_intent = None
    had_failure = False
    turn_scope = None
    scoped_tools = {
        "get_spending_by_category",
        "get_recent_transactions",
        "get_monthly_cashflow",
    }

    for tc in tool_calls:
        fn_info = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", {})
        fn_name = fn_info.get("name") if isinstance(fn_info, dict) else getattr(fn_info, "name", "")
        fn_args = fn_info.get("arguments") if isinstance(fn_info, dict) else getattr(fn_info, "arguments", {})
        if isinstance(fn_args, str):
            try:
                fn_args = json.loads(fn_args)
            except Exception:
                fn_args = {}
        fn_args = fn_args or {}

        # A scope resolved earlier in this turn is inherited by later data calls (AC-3).
        if turn_scope and fn_name in scoped_tools and "date_scope" not in fn_args:
            fn_args = {**fn_args, "date_scope": turn_scope}

        result = execute_tool(fn_name, fn_args)

        if result.get("success") is False:
            had_failure = True

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
        if result.get("diagnostics"):
            captured_diagnostics.append(result["diagnostics"])
        if result.get("ui_intent"):
            captured_intent = result["ui_intent"]
            ds = captured_intent.get("date_scope") or {}
            if ds.get("preset"):
                turn_scope = {"preset": ds["preset"]}
            elif ds.get("start_iso"):
                turn_scope = {"start": ds["start_iso"], "end": ds["end_iso"]}

        # Append assistant tool call & tool result to message history for final summarization
        messages.append({
            "role": "assistant",
            "content": f"Calling tool `{fn_name}` with arguments: {json.dumps(fn_args)}",
        })
        clean_result = {k: v for k, v in result.items() if k not in ("figure", "df", "ui_intent")}
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
        "diagnostics": captured_diagnostics,
        "ui_intent": captured_intent if not had_failure else None,
    }

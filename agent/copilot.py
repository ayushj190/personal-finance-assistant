from datetime import date
import inspect
import json
import re
import time
from typing import Any, Iterator

from agent import tools
from agent.tools import COPILOT_TOOLS_SCHEMA
from services.llm_client import chat_with_tools, generate_stream
from services.navigation import match_fast_path, topic_map_intent

SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app, running locally and privately on the user's machine.

CRITICAL ACCURACY RULES:
- Never confuse debt liabilities (mortgage, loans) with investment portfolio capital.
- Always quote the exact numbers the tools return; never estimate or invent amounts.
- Never state a money amount or a percentage unless a tool returned it in this turn.
- For investments rely on `total_portfolio_value_eur`, `total_portfolio_value_formatted`, and `holdings_by_nature_eur` from `analyze_investments`.
- Never present a minor unit (cents) figure; use the euro formatted fields the tools provide.

Call the relevant tool whenever the user asks about their financial data:
- analyze_investments: portfolio value, allocation, drift, and risk.
- get_allocation_profiles, create_allocation_profile, delete_allocation_profile: manage target allocation strategies. A create needs targets that sum to 100 percent; a delete needs the confirmation token returned by the first call.
- get_current_net_worth: overall balance sheet.
- get_spending_by_category, get_recent_transactions, get_monthly_cashflow: spending and cashflow.
- open_view: open the page that owns the topic of the question, optionally an Investments tab, a date scope, and validated view parameters. Call it whenever a question is about a topic with its own page (spending, investments, mortgage, tax, transactions, net worth), even when the user does not phrase it as navigation, alongside the data tool that answers. Use view to shape the page: Spending {category}, Transactions {category, search}, Investments {sort, movers, search, exposure_dimension, focus} (e.g. movers "gainers" or sort "day_pnl" for a movers question, search "AAPL" for a specific ticker, or exposure_dimension "Sector" and focus "Technology" for a technology holdings question).
- analyze_mortgage: mortgage schedules and rates.
- analyze_tax_situation, simulate_tax_optimization, calculate_pension_room, analyze_green_fund_strategy, diagnose_tax_leaks: Dutch tax questions.
- search_dutch_law_vault and lookup_tax_law_article: cite exact Dutch statutory articles.
- compare_periods: compare two periods. get_budget_status: category budget status. get_account_balances: every account balance. get_spending_forecast: burn rate and projected month end for the requested date_scope (or the last three months when none is given). get_income_summary: income and dividends. get_upcoming_bills: recurring bills. get_net_worth_history: net worth trend (approximate: the ledger cash balance plus the current invested value, excluding home equity and opening balances; use get_current_net_worth for the true current figure).

NAVIGATION RULES:
- When a question is about a topic with its own page, call open_view for that page and shape it with the view parameters that match the question. Never claim you opened a page unless you called open_view.
- If the destination screen is ambiguous (two pages fit equally), ask one short question naming the candidate screens and do not call open_view until the user answers. If the topic is weak or absent, answer in chat only and do not call open_view.
- If the request names a page that has no date filter but asks for a period, still open the page and say plainly that the page has no date scope.

DATE SCOPE RULES:
- Only these tools accept a period as the date_scope argument: get_spending_by_category, get_recent_transactions, get_monthly_cashflow, get_budget_status, get_income_summary, get_net_worth_history, get_spending_forecast, and open_view. Pass the requested range to them as date_scope so the answer and the page agree.
- Never pass a period, or a date_scope argument, to a tool that does not list it above. A tool with no date_scope argument must be called with no period at all.

WRITE RULES (the ledger changing tools):
- categorize_transactions, mark_as_transfer, edit_transaction, delete_transaction, and set_budget_cap change your data. Their first call changes nothing and returns a confirmation token.
- Tell me exactly what will change and wait for me to say yes. Only then call the same tool again with that confirm_token to perform the write. Never claim a change is done until the second call returns success.

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
    "compare_periods": tools.tool_compare_periods,
    "get_budget_status": tools.tool_get_budget_status,
    "get_account_balances": tools.tool_get_account_balances,
    "get_spending_forecast": tools.tool_get_spending_forecast,
    "get_income_summary": tools.tool_get_income_summary,
    "get_upcoming_bills": tools.tool_get_upcoming_bills,
    "get_net_worth_history": tools.tool_get_net_worth_history,
    "categorize_transactions": tools.tool_categorize_transactions,
    "mark_as_transfer": tools.tool_mark_as_transfer,
    "edit_transaction": tools.tool_edit_transaction,
    "delete_transaction": tools.tool_delete_transaction,
    "set_budget_cap": tools.tool_set_budget_cap,
}

# Navigation and pure app action tools: their success never grounds a numeric
# answer, so a turn that only ran these can never license a quoted figure (AC-5).
_NON_GROUNDING_TOOLS = frozenset({
    "open_view",
    "toggle_privacy_mode",
    "set_theme",
    "request_profile_form",
})

# A money amount or a percentage stated in a drafted answer (AC-5).
_FIGURE_RE = re.compile(
    r"[€$£]\s?[0-9][0-9,]*(\.[0-9]+)?"
    r"|\b[0-9][0-9,]*(\.[0-9]+)?\s?%"
    r"|\b[0-9][0-9,]*(\.[0-9]+)?\s?(?:percent|per cent)\b"
    r"|\b[0-9][0-9,]*(\.[0-9]+)?\s?(?:EUR|USD|GBP)\b",
    re.IGNORECASE,
)


def _mentions_figure(text: str) -> bool:
    """True when a drafted answer states a money amount or a percentage (AC-5)."""
    return bool(_FIGURE_RE.search(text or ""))


def _stream_text(text: str) -> Iterator[str]:
    """Yield a fixed string in token chunks, matching the streamed answer shape."""
    for tok in re.split(r"(\s+)", text):
        if tok:
            yield tok
            time.sleep(0.012)


def _final_stream(
    messages: list[dict[str, Any]],
    grounded: bool,
    failed_messages: list[str],
) -> Iterator[str]:
    """The turn's answer stream, gated so no invented figure reaches the user (AC-5).

    A grounded turn streams straight through. An ungrounded turn is drafted in
    full first: when it states a figure, it is replaced by a deterministic message.
    """
    if grounded:
        return generate_stream(messages)

    drafted = "".join(generate_stream(messages))
    if not _mentions_figure(drafted):
        return _stream_text(drafted)

    if failed_messages:
        fallback = (
            "I could not retrieve the numbers for that request, so I will not quote a "
            "figure. " + " ".join(dict.fromkeys(failed_messages))
        )
    else:
        fallback = (
            "I could not retrieve the numbers for that request, so I will not quote a "
            "figure. Please try again, or open the page and read the figures there."
        )
    return _stream_text(fallback)


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
    original_arguments = dict(arguments)
    dropped_date_scope = False

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
            # A period hint the model over generalizes onto a tool that does not
            # declare it is dropped, not fatal; every other undeclared argument
            # still returns the guided error (AC-3, AC-16).
            if "date_scope" in unknown:
                arguments = {k: v for k, v in arguments.items() if k != "date_scope"}
                dropped_date_scope = True
                unknown = [k for k in unknown if k != "date_scope"]
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
                        "arguments": original_arguments,
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
                    "arguments": original_arguments,
                    "error_type": "ToolReturnedFailure",
                    "error_details": res.get("message", "Tool returned failure status"),
                }
        if dropped_date_scope and isinstance(res, dict) and "diagnostics" not in res:
            res["diagnostics"] = {
                "tool": tool_name,
                "arguments": original_arguments,
                "error_type": "DroppedArgument",
                "error_details": "Ignored a date_scope argument this tool does not accept.",
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
                "arguments": original_arguments,
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
    captured_headline = None
    captured_df = None
    captured_form = None
    captured_citations = []
    captured_diagnostics = []
    captured_intent = None
    had_failure = False
    data_tool_succeeded = False
    failed_messages: list[str] = []
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
            failed_messages.append(
                str(result.get("guidance") or result.get("message") or f"Tool {fn_name} failed.")
            )
        elif fn_name not in _NON_GROUNDING_TOOLS:
            data_tool_succeeded = True

        if result.get("figure") is not None:
            captured_figure = result["figure"]
        if result.get("headline"):
            captured_headline = result["headline"]
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

    # 5.5 Deterministic topic map fallback (AC-6): runs whenever the model ran but
    # did not navigate, even when a data tool failed (AC-4). Routes a clear content
    # question to the one matching page and carries the turn's resolved scope so the
    # page agrees with the answer.
    if captured_intent is None:
        captured_intent = topic_map_intent(user_message, turn_scope)

    # 6. Stream the final summarization, gated so no invented figure reaches the user (AC-5).
    stream_gen = _final_stream(messages, data_tool_succeeded, failed_messages)

    return {
        "role": "assistant",
        "stream": stream_gen,
        "figure": captured_figure,
        "headline": captured_headline,
        "df": captured_df,
        "form_request": captured_form,
        "citations": captured_citations,
        "diagnostics": captured_diagnostics,
        "ui_intent": captured_intent,
    }

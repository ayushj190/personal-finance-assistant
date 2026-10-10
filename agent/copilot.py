from datetime import date
import json
from typing import Any
import pandas as pd

from agent import tools
from services.llm_client import generate_json, generate_stream

ROUTER_SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app.
You run locally and privately on the user's machine.

Your job is to route the user's request to the appropriate tool, or answer directly if no tool is needed.

Available Tools:
- toggle_privacy_mode(enable: bool | null)
- set_theme(theme: "dark" | "light")
- set_active_allocation_profile(profile_name: string)
- update_savings_rate(institution_or_name: string, apy_pct: number, balance_eur: number | null)
- add_mortgage_payment(loan_name: string, amount_eur: number, paid_date: string | null, recalc: "lower_payment" | "shorter_term")
- save_risk_profile(risk_score: number, risk_tolerance: string, notes: string, answers: object, investment_horizon_years: number | null, liquidity_needs: string | null, investment_experience: string | null)
- get_risk_profile()
- save_tax_profile(gross_annual_income: number, has_fiscal_partner: boolean, has_30_percent_ruling: boolean, is_entrepreneur: boolean, owns_home: boolean, birth_year: number | null, has_13th_month: boolean, expected_bonus_eur: number, pension_contribution_pct: number, employer_pension_match_pct: number)
- analyze_investments()
- get_current_net_worth()
- auto_categorize_uncategorized_transactions(limit: number)
- analyze_tax_situation()
- analyze_mortgage()
- query_financial_data(question: string)
- search_web(query: string)
- analyze_market_data(ticker: string)
- execute_python(code: string)
- request_profile_form(form_type: string)

CRITICAL RULE: If the user is asking for their CURRENT net worth, you MUST call `get_current_net_worth`. For questions about their specific data, spending behavior, category spending, transactions, or requesting a chart, YOU MUST call `query_financial_data` and pass their original question in the `question` argument. Use `analyze_tax_situation` for questions about taxes, Box 1/3, or optimizing gross income. Use `analyze_mortgage` for mortgage and liability questions. For general financial knowledge, hypothetical questions, or generic advice, answer directly and do not call `query_financial_data`.

CRITICAL RULE: If evaluating the user's tax or risk profile and any key details (like 30% ruling, investment horizon, age/birth_year, home ownership, 13th month, bonus, pension contribution %, or employer match %) are blank or missing, do NOT call `save_tax_profile` or `save_risk_profile`. Instead, call `request_profile_form` with `form_type` set to either `"tax_profile"` or `"risk_profile"`. This will prompt the user with a UI widget to fill out the remaining details. Note that 8% holiday allowance is automatically added to the base gross calculation.

CRITICAL: You MUST output valid JSON only, using this exact schema:
{
  "tool_call": {
    "name": "<tool_name_or_null>",
    "arguments": {
      "<arg_name>": "<arg_value>"
    }
  },
  "message": "<Brief message to the user, or your direct answer if no tool is needed>"
}
If no tool is needed, set "tool_call" to null.

Today's date is: {today}.
"""

SQL_GENERATOR_PROMPT = """You are a financial data analyst AI.
Your task is to write a SQLite query to answer the user's question, and optionally specify a Plotly chart.

Database Schema for Views:
- v_net_worth_daily (date, asset_class, value_eur)
- v_transactions (id, booking_date, institution, account, amount_eur, currency, merchant, category, parent_category, category_kind, is_internal_transfer, liability_id, liability_name)
- v_holdings (id, institution, account, ticker, isin, name, asset_type, region, sector, quantity, cost_basis, cost_basis_native, currency, latest_close, prev_close, value_eur, unrealized_pnl_eur)
- v_monthly_cashflow (month, income_eur, fixed_eur, discretionary_eur, savings_eur)
- v_mortgage_payments (loan_name, lender, month_idx, due_date, payment_eur, interest_eur, principal_eur, extra_eur, balance_eur)

For spending queries on v_transactions, always filter `WHERE is_internal_transfer = 0` and use `-amount_eur` so expenses appear positive.

CRITICAL: You MUST output valid JSON only, using this schema for the tool_call:
{
  "tool_call": {
    "name": "query_financial_data",
    "arguments": {
      "sql": "<your sqlite query>",
      "chart_spec": {"type": "bar|line|pie", "x": "col1", "y": "col2", "title": "Chart Title"} // or null
    }
  },
  "message": "<Brief message>"
}
"""

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool_map = {
        "toggle_privacy_mode": tools.tool_toggle_privacy_mode,
        "set_theme": tools.tool_set_theme,
        "set_active_allocation_profile": tools.tool_set_active_allocation_profile,
        "update_savings_rate": tools.tool_update_savings_rate,
        "add_mortgage_payment": tools.tool_add_mortgage_payment,
        "save_risk_profile": tools.tool_save_risk_profile,
        "get_risk_profile": tools.tool_get_risk_profile,
        "save_tax_profile": tools.tool_save_tax_profile,
        "analyze_investments": tools.tool_analyze_investments,
        "get_current_net_worth": tools.tool_get_current_net_worth,
        "auto_categorize_uncategorized_transactions": tools.tool_auto_categorize_uncategorized_transactions,
        "analyze_tax_situation": tools.tool_analyze_tax_situation,
        "analyze_mortgage": tools.tool_analyze_mortgage,
        "query_financial_data": tools.tool_query_financial_data,
        "search_web": tools.tool_search_web,
        "analyze_market_data": tools.tool_analyze_market_data,
        "execute_python": tools.tool_execute_python,
        "request_profile_form": tools.tool_request_profile_form,
    }

    fn = tool_map.get(tool_name)
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
    """Run full Copilot conversational loop with tool calling and file handling."""
    router_prompt = ROUTER_SYSTEM_PROMPT.replace("{today}", date.today().isoformat())

    # Check if files were uploaded directly
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
        return {
            "role": "assistant",
            "stream": [combined_msg],
            "figure": None,
            "df": None,
            "sql": None,
        }

    # Build prompt messages for Tier 1 Router
    messages = [{"role": "system", "content": router_prompt}]
    
    # Smart Context Management: keep text, truncate large data from previous turns
    if history:
        for h in history[-8:]:
            r = h.get("role", "user")
            c = h.get("content", "")
            
            # If the previous assistant message contained a huge data dump, truncate it.
            if r == "assistant" and len(c) > 1000:
                c = c[:500] + "\n... [Data truncated for context. Use execute_python to analyze further if needed] ..." + c[-200:]
                
            if r in ("user", "assistant") and c:
                messages.append({"role": r, "content": c})

    messages.append({"role": "user", "content": user_message})

    # Tier 1: Fast Intent Routing (Synchronous, fast JSON)
    # Using format="json" natively via generate_json without strict schema parameter
    resp_json = generate_json(messages)

    if not resp_json:
        return {
            "role": "assistant",
            "stream": ["⚠️ Could not connect to local Ollama. Please ensure Ollama is running (`ollama serve`)."],
            "figure": None, "df": None, "sql": None,
        }

    tool_call = resp_json.get("tool_call")
    if not tool_call or not isinstance(tool_call, dict) or not tool_call.get("name"):
        # No tool needed! We can stream the response directly for instant feedback.
        # Replace the router prompt with a regular chat prompt so it doesn't output JSON.
        chat_prompt = "You are the personal AI Copilot for this Personal Finance Assistant app. You run locally and privately on the user's machine. Help the user."
        messages[0] = {"role": "system", "content": chat_prompt}
        return {
            "role": "assistant",
            "stream": generate_stream(messages),
            "figure": None, "df": None, "sql": None,
        }

    t_name = tool_call.get("name")
    t_args = tool_call.get("arguments", {})

    # Tier 2: Specialized Data Query Routing
    if t_name == "query_financial_data":
        question = t_args.get("question", user_message)
        sql_prompt = SQL_GENERATOR_PROMPT
        sql_messages = [
            {"role": "system", "content": sql_prompt},
            {"role": "user", "content": f"Write a query for: {question}"}
        ]
        
        sql_resp = generate_json(sql_messages)
        if not sql_resp or not sql_resp.get("tool_call"):
            return {
                "role": "assistant",
                "stream": ["❌ Failed to generate a valid data query."],
                "figure": None, "df": None, "sql": None,
            }
        
        t_args = sql_resp["tool_call"].get("arguments", {})

    # Execute tool call synchronously
    tool_result = execute_tool(t_name, t_args)

    figure = tool_result.get("figure")
    df = tool_result.get("df")
    sql = tool_result.get("sql")

    # If it's a data query, we have the results. We should summarize them by streaming!
    if t_name == "query_financial_data":
        if "answer" in tool_result:
            return {
                "role": "assistant",
                "stream": [tool_result["answer"]],
                "figure": figure, "df": df, "sql": sql,
            }
        
        messages.append({"role": "assistant", "content": f"Tool `query_financial_data` executed. Result:\n{str(df.head(10) if df is not None else 'No data')}..."})
        messages.append({"role": "user", "content": "Briefly summarize these results for me."})
        chat_prompt = "You are the personal AI Copilot for this Personal Finance Assistant app. You run locally and privately on the user's machine. Help the user."
        messages[0] = {"role": "system", "content": chat_prompt}
        return {
            "role": "assistant",
            "stream": generate_stream(messages),
            "figure": figure, "df": df, "sql": sql,
        }

    # For action tools (e.g. toggle theme, etc)
    status_msg = tool_result.get("message", "")
    lead_msg = resp_json.get("message", "")
    
    if t_name == "analyze_investments":
        summary_prompt = (
            f"The user asked: {user_message}\n"
            f"Here is the portfolio and risk summary data:\n{json.dumps(tool_result, default=str)}\n"
            "Deeply evaluate the portfolio based on risk and asset allocation. Summarize current drift and how it aligns with their risk tolerance."
        )
        messages.append({"role": "assistant", "content": resp_json.get("message", "Getting portfolio summary...")})
        messages.append({"role": "user", "content": summary_prompt})
        chat_prompt = "You are the personal AI Copilot for this Personal Finance Assistant app. You run locally and privately on the user's machine. Help the user."
        messages[0] = {"role": "system", "content": chat_prompt}
        return {
            "role": "assistant",
            "stream": generate_stream(messages),
            "figure": figure, "df": df, "sql": sql,
        }
        
    if t_name == "analyze_tax_situation":
        summary_prompt = (
            f"The user asked: {user_message}\n"
            f"Here is the tax situation data:\n{json.dumps(tool_result, default=str)}\n"
            "Provide strategic financial advice regarding Dutch tax laws based on this data. Suggest green fund investments (groenfondsen), extra pension contributions (lijfrente), and home buyer advantages if applicable to their situation."
        )
        messages.append({"role": "assistant", "content": resp_json.get("message", "Analyzing tax situation...")})
        messages.append({"role": "user", "content": summary_prompt})
        chat_prompt = "You are the personal AI Copilot for this Personal Finance Assistant app. You run locally and privately on the user's machine. Help the user."
        messages[0] = {"role": "system", "content": chat_prompt}
        return {
            "role": "assistant",
            "stream": generate_stream(messages),
            "figure": figure, "df": df, "sql": sql,
        }
        
    if t_name == "analyze_mortgage":
        summary_prompt = (
            f"The user asked: {user_message}\n"
            f"Here is the mortgage data:\n{json.dumps(tool_result, default=str)}\n"
            "Explain the user's mortgage components clearly and suggest optimizations (like extra repayments or refinancing) based on their schedule and rates."
        )
        messages.append({"role": "assistant", "content": resp_json.get("message", "Analyzing mortgage...")})
        messages.append({"role": "user", "content": summary_prompt})
        chat_prompt = "You are the personal AI Copilot for this Personal Finance Assistant app. You run locally and privately on the user's machine. Help the user."
        messages[0] = {"role": "system", "content": chat_prompt}
        return {
            "role": "assistant",
            "stream": generate_stream(messages),
            "figure": figure, "df": df, "sql": sql,
        }

    # Default static string for simple tools wrapped in list
    full_content = f"{lead_msg}\n\n✅ {status_msg}".strip() if lead_msg else f"✅ {status_msg}"
    response_dict = {
        "role": "assistant",
        "stream": [full_content],
        "figure": figure,
        "df": df,
        "sql": sql,
    }
    
    if "form_request" in tool_result:
        response_dict["form_request"] = tool_result["form_request"]
        
    return response_dict

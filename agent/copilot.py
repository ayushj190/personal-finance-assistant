from datetime import date
import json
from typing import Any
import pandas as pd

from agent import tools
from services.llm_client import generate_json

ROUTER_SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app.
You run locally and privately on the user's machine.

Your job is to route the user's request to the appropriate tool, or answer directly if no tool is needed.

Available Tools:
- toggle_privacy_mode(enable: bool | null)
- set_theme(theme: "dark" | "light")
- set_active_allocation_profile(profile_name: string)
- update_savings_rate(institution_or_name: string, apy_pct: number, balance_eur: number | null)
- add_mortgage_payment(loan_name: string, amount_eur: number, paid_date: string | null, recalc: "lower_payment" | "shorter_term")
- save_risk_profile(risk_score: number, risk_tolerance: string, notes: string, answers: object)
- get_risk_profile()
- get_portfolio_and_risk_summary()
- categorize_expenses(limit: number)
- query_financial_data(question: string)
- search_web(query: string)
- analyze_market_data(ticker: string)
- execute_python(code: string)

CRITICAL RULE: If the user is asking ANY question about their data, spending, net worth, transactions, or requesting a chart, YOU MUST call `query_financial_data` and pass their original question in the `question` argument.

CRITICAL: You MUST output valid JSON only.

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

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool_call": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": "string"},
                "arguments": {"type": "object"}
            }
        },
        "message": {"type": "string"}
    },
    "required": ["message"]
}

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool_map = {
        "toggle_privacy_mode": tools.tool_toggle_privacy_mode,
        "set_theme": tools.tool_set_theme,
        "set_active_allocation_profile": tools.tool_set_active_allocation_profile,
        "update_savings_rate": tools.tool_update_savings_rate,
        "add_mortgage_payment": tools.tool_add_mortgage_payment,
        "save_risk_profile": tools.tool_save_risk_profile,
        "get_risk_profile": tools.tool_get_risk_profile,
        "get_portfolio_and_risk_summary": tools.tool_get_portfolio_and_risk_summary,
        "categorize_expenses": tools.tool_categorize_expenses,
        "query_financial_data": tools.tool_query_financial_data,
        "search_web": tools.tool_search_web,
        "analyze_market_data": tools.tool_analyze_market_data,
        "execute_python": tools.tool_execute_python,
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
            "content": combined_msg,
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

    # Tier 1: Fast Intent Routing
    resp_json = generate_json(messages, schema=RESPONSE_SCHEMA)

    if not resp_json:
        # Fallback if Ollama fails
        return {
            "role": "assistant",
            "content": "⚠️ Could not connect to local Ollama. Please ensure Ollama is running (`ollama serve`).",
            "figure": None, "df": None, "sql": None,
        }

    tool_call = resp_json.get("tool_call")
    if not tool_call or not isinstance(tool_call, dict) or not tool_call.get("name"):
        return {
            "role": "assistant",
            "content": resp_json.get("message", "Done."),
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
        
        # Explicit schema for SQL generator
        sql_schema = {
            "type": "object",
            "properties": {
                "tool_call": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {
                            "type": "object",
                            "properties": {
                                "sql": {"type": "string"},
                                "chart_spec": {"type": ["object", "null"]},
                                "summary_template": {"type": "string"}
                            },
                            "required": ["sql"]
                        }
                    },
                    "required": ["name", "arguments"]
                },
                "message": {"type": "string"}
            },
            "required": ["tool_call", "message"]
        }
        
        sql_resp = generate_json(sql_messages, schema=sql_schema)
        if not sql_resp or not sql_resp.get("tool_call"):
            return {
                "role": "assistant",
                "content": "❌ Failed to generate a valid data query.",
                "figure": None, "df": None, "sql": None,
            }
        
        t_args = sql_resp["tool_call"].get("arguments", {})

    # Execute tool call
    tool_result = execute_tool(t_name, t_args)

    figure = tool_result.get("figure")
    df = tool_result.get("df")
    sql = tool_result.get("sql")

    # Format response
    if t_name == "query_financial_data":
        # In Tier 2, we might not have a message from resp_json.
        ans = tool_result.get("answer", sql_resp.get("message", "Query executed successfully."))
        return {
            "role": "assistant",
            "content": ans,
            "figure": figure,
            "df": df,
            "sql": sql,
        }

    # For action tools
    status_msg = tool_result.get("message", "")
    lead_msg = resp_json.get("message", "")
    full_content = f"{lead_msg}\n\n✅ {status_msg}".strip() if lead_msg else f"✅ {status_msg}"

    if t_name == "get_portfolio_and_risk_summary":
        summary_prompt = (
            f"The user asked: {user_message}\n"
            f"Here is the portfolio and risk summary data:\n{json.dumps(tool_result, default=str)}\n"
            "Summarize the user's asset allocation, current drift, and how it aligns with their risk tolerance."
        )
        messages.append({"role": "assistant", "content": json.dumps(resp_json)})
        messages.append({"role": "user", "content": summary_prompt})
        second_resp = generate_json(messages, schema=RESPONSE_SCHEMA)
        if second_resp and second_resp.get("message"):
            full_content = second_resp["message"]

    return {
        "role": "assistant",
        "content": full_content,
        "figure": figure,
        "df": df,
        "sql": sql,
    }

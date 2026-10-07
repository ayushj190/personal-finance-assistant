from datetime import date
import json
import re
from typing import Any
import httpx
import pandas as pd

from agent import tools
from services.llm_client import get_llm_config

COPILOT_SYSTEM_PROMPT = """You are the personal AI Copilot for this Personal Finance Assistant app (like Copilot 365).
You run locally and privately on the user's machine.

Your capabilities:
1. APP GUIDE & ONBOARDING:
   - Instruct the user how to use all features: Dashboard, Spending, Investments, Mortgage, Transactions, Import, Settings.
   - Explain Open Banking (Enable Banking free PSD2 setup), eToro, Trade Republic, CSV/PDF imports.

2. SETTINGS & FINANCIAL UPDATES (via tool calls):
   - Toggle Privacy Mode (hiding/showing financial values).
   - Toggle theme ('dark' or 'light').
   - Switch active target allocation profile.
   - Update savings account APY interest rates and balances.
   - Record extra mortgage payments and recalculate amortization schedules.

3. INVESTMENT RISK TOLERANCE & PORTFOLIO BALANCE:
   - Guide the user through a risk assessment questionnaire (asking questions one or two at a time about: investment time horizon, reaction to a 20% market drop, cash emergency cushion, return objectives).
   - Compute a risk score (1-10) and category (Conservative [1-3], Moderate [4-6], Growth [7-8], Aggressive [9-10]).
   - Save the completed profile using the `save_risk_profile` tool.
   - Review current portfolio holdings and compare against risk tolerance and target allocations.
   - CRITICAL COMPLIANCE RULE: NEVER give direct financial advice or recommend specific stocks/ETFs to buy or sell. Instead, remind the user of their risk tolerance and help maintain their target portfolio balance.

4. EXPENSE CATEGORIZATION:
   - Use `categorize_expenses` to trigger AI categorization of uncategorized transactions.

5. FINANCIAL ANALYSIS & VISUALIZATION:
   - Generate safe SQLite queries on views (`v_transactions`, `v_net_worth_daily`, `v_holdings`, `v_monthly_cashflow`, `v_mortgage_payments`) and interactive Plotly charts.
   - For spending queries, always filter `WHERE is_internal_transfer = 0` and use `-amount_eur` so expenses appear positive.

OUTPUT FORMAT:
You MUST respond with a JSON object.
There are two response modes:
Mode A: Tool Call (When an action, query, or data lookup is needed)
{
  "tool_call": {
    "name": "<tool_name>",
    "arguments": { ... }
  },
  "message": "<Brief message explaining the action taken or context>"
}

Mode B: Direct Message (For answering questions, discussing risk tolerance, guiding how to use the app, or acknowledging tool results)
{
  "tool_call": null,
  "message": "<Your helpful Markdown-formatted response>"
}

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
- query_financial_data(sql: string, chart_spec: object | null, summary_template: string)

Example chart_spec:
{"type": "bar" | "line" | "area" | "pie", "x": "col1", "y": "col2", "title": "Chart Title"}

Today's date is: {today}.
"""


def _clean_json_response(content: str) -> dict[str, Any] | None:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except Exception:
        # Fallback: find first { and last }
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


def _call_ollama(messages: list[dict[str, str]]) -> dict[str, Any] | None:
    endpoint, model = get_llm_config()
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            return _clean_json_response(raw_content)
    except Exception:
        return None


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
    system_prompt = COPILOT_SYSTEM_PROMPT.replace("{today}", date.today().isoformat())

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

    # Build prompt messages
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-8:]:  # Keep recent context
            r = h.get("role", "user")
            c = h.get("content", "")
            if r in ("user", "assistant") and c:
                messages.append({"role": r, "content": c})

    messages.append({"role": "user", "content": user_message})

    resp_json = _call_ollama(messages)

    if not resp_json:
        # Heuristic fallback for common direct actions if Ollama is offline/starting
        msg_l = user_message.lower()
        if "privacy" in msg_l:
            res = tools.tool_toggle_privacy_mode()
            return {"role": "assistant", "content": f"✅ {res['message']} *(Executed via local fallback)*", "figure": None, "df": None, "sql": None}
        if "light" in msg_l and ("mode" in msg_l or "theme" in msg_l):
            res = tools.tool_set_theme("light")
            return {"role": "assistant", "content": f"✅ {res['message']} *(Executed via local fallback)*", "figure": None, "df": None, "sql": None}
        if "dark" in msg_l and ("mode" in msg_l or "theme" in msg_l):
            res = tools.tool_set_theme("dark")
            return {"role": "assistant", "content": f"✅ {res['message']} *(Executed via local fallback)*", "figure": None, "df": None, "sql": None}
        if "categoriz" in msg_l:
            res = tools.tool_categorize_expenses()
            return {"role": "assistant", "content": f"🏷️ {res['message']} *(Executed via local fallback)*", "figure": None, "df": None, "sql": None}
        if "drift" in msg_l or ("portfolio" in msg_l and "target" in msg_l):
            res = tools.tool_get_portfolio_and_risk_summary()
            classes = res.get("asset_classes_eur", {})
            profile = res.get("active_allocation_profile") or {}
            prof_name = profile.get("name", "None")
            lines = [f"**Portfolio & Drift Overview:**", f"- Active Allocation Profile: `{prof_name}`"]
            for ac, val in classes.items():
                lines.append(f"- **{ac.capitalize()}**: €{val:,.2f}")
            lines.append("\n*Tip: Start Ollama (`ollama serve`) for full interactive reasoning and automated rebalancing recommendations.*")
            return {"role": "assistant", "content": "\n".join(lines), "figure": None, "df": None, "sql": None}
        if "risk" in msg_l:
            rp = tools.tool_get_risk_profile()
            if rp.get("success") and rp.get("profile"):
                p = rp["profile"]
                return {
                    "role": "assistant",
                    "content": f"### 🎯 Current Risk Profile:\n- **Tolerance Tier:** `{p['risk_tolerance']}`\n- **Score:** `{p['risk_score']}/10`\n- **Assessed Date:** {p.get('assessed_date', '')[:10]}\n\nTo update your profile, start Ollama (`ollama serve`) or provide your investment horizon and drawdown preference here.",
                    "figure": None,
                    "df": None,
                    "sql": None,
                }
            return {
                "role": "assistant",
                "content": "### 🎯 Investment Risk Questionnaire:\n1. **Investment Horizon**: How long do you plan to keep your money invested before withdrawing? (e.g. <3 years, 3-7 years, 10+ years)\n2. **Drawdown Comfort**: If your portfolio drops 20% during a market correction, would you sell to prevent further loss, hold steady, or invest more?\n3. **Financial Cushion**: Do you have at least 3-6 months of emergency living expenses stored in safe cash?\n\nAnswer these questions to calibrate your risk profile.",
                "figure": None,
                "df": None,
                "sql": None,
            }

        return {
            "role": "assistant",
            "content": "⚠️ Could not connect to local Ollama. Please ensure Ollama is running (`ollama serve`) and the configured model is installed.\n\nYou can still use direct quick actions: upload files, toggle privacy/theme, or review risk profiles.",
            "figure": None,
            "df": None,
            "sql": None,
        }


    tool_call = resp_json.get("tool_call")
    if not tool_call or not isinstance(tool_call, dict) or not tool_call.get("name"):
        # Pure conversation response
        return {
            "role": "assistant",
            "content": resp_json.get("message", "Done."),
            "figure": None,
            "df": None,
            "sql": None,
        }

    # Execute tool call
    t_name = tool_call.get("name")
    t_args = tool_call.get("arguments", {})
    tool_result = execute_tool(t_name, t_args)

    figure = tool_result.get("figure")
    df = tool_result.get("df")
    sql = tool_result.get("sql")

    # If it was a query or data tool, format response nicely
    if t_name == "query_financial_data":
        ans = tool_result.get("answer", resp_json.get("message", "Query executed successfully."))
        return {
            "role": "assistant",
            "content": ans,
            "figure": figure,
            "df": df,
            "sql": sql,
        }

    # For action tools (settings, mortgage, savings, risk profile)
    status_msg = tool_result.get("message", "")
    lead_msg = resp_json.get("message", "")
    full_content = f"{lead_msg}\n\n✅ {status_msg}".strip() if lead_msg else f"✅ {status_msg}"

    if t_name == "get_portfolio_and_risk_summary":
        # Second call to LLM to summarize portfolio balance vs risk profile
        summary_prompt = (
            f"The user asked: {user_message}\n"
            f"Here is the portfolio and risk summary data:\n{json.dumps(tool_result, default=str)}\n"
            "Summarize the user's asset allocation, current drift, and how it aligns with their risk tolerance. "
            "Remind them of their risk tolerance and portfolio targets. Do NOT give financial advice or suggest specific assets."
        )
        messages.append({"role": "assistant", "content": json.dumps(resp_json)})
        messages.append({"role": "user", "content": summary_prompt})
        second_resp = _call_ollama(messages)
        if second_resp and second_resp.get("message"):
            full_content = second_resp["message"]

    return {
        "role": "assistant",
        "content": full_content,
        "figure": figure,
        "df": df,
        "sql": sql,
    }

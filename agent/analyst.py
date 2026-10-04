import json
from typing import Any
import httpx
import pandas as pd

from agent.chart_renderer import render_chart
from agent.prompt import ANALYST_SYSTEM_PROMPT, build_analyst_prompt
from agent.sql_sandbox import execute_safe_query
from services.llm_client import get_llm_config


def _call_llm_json(prompt: str, system: str = ANALYST_SYSTEM_PROMPT) -> dict[str, Any] | None:
    endpoint, model = get_llm_config()
    url = f"{endpoint}/v1/chat/completions"

    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        return None


def query_analyst(question: str) -> dict[str, Any]:
    prompt = build_analyst_prompt(question)
    response_json = _call_llm_json(prompt)

    if not response_json or "sql" not in response_json:
        return {
            "success": False,
            "answer": "Unable to generate an analysis query. Please ensure local Ollama / LLM is running.",
            "sql": None,
            "df": pd.DataFrame(),
            "figure": None,
        }

    sql = response_json.get("sql", "").strip()
    chart_spec = response_json.get("chart")
    summary = response_json.get("summary_template", "")

    # Attempt query execution
    df = pd.DataFrame()
    try:
        df = execute_safe_query(sql)
    except Exception as e:
        # Error repair retry
        repair_prompt = (
            f"The following SQL query failed with error: {str(e)}\n"
            f"Failed query: {sql}\n"
            "Please fix the SQL query and return strict JSON with 'sql', 'chart', 'summary_template'."
        )
        retry_json = _call_llm_json(repair_prompt)
        if retry_json and "sql" in retry_json:
            sql = retry_json["sql"].strip()
            chart_spec = retry_json.get("chart", chart_spec)
            summary = retry_json.get("summary_template", summary)
            try:
                df = execute_safe_query(sql)
            except Exception as e2:
                return {
                    "success": False,
                    "answer": f"Query execution failed: {str(e2)}",
                    "sql": sql,
                    "df": pd.DataFrame(),
                    "figure": None,
                }
        else:
            return {
                "success": False,
                "answer": f"Query execution failed: {str(e)}",
                "sql": sql,
                "df": pd.DataFrame(),
                "figure": None,
            }

    figure = render_chart(df, chart_spec)

    # Format summary template
    if summary and not df.empty:
        try:
            first_row = df.iloc[0].to_dict()
            first_val = list(first_row.values())[0] if first_row else ""
            summary = summary.replace("{total}", str(round(first_val, 2)) if isinstance(first_val, (int, float)) else str(first_val))
            summary = summary.replace("{count}", str(len(df)))
        except Exception:
            pass
    elif not summary:
        summary = f"Found {len(df)} matching records."

    return {
        "success": True,
        "answer": summary,
        "sql": sql,
        "df": df,
        "figure": figure,
    }

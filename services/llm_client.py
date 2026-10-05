import json
from typing import Any
import httpx

from config import DEFAULT_MODEL, DEFAULT_OLLAMA_URL
from services import secrets_vault


def get_llm_config() -> tuple[str, str]:
    endpoint = secrets_vault.get("ollama_endpoint") or DEFAULT_OLLAMA_URL
    model = secrets_vault.get("ollama_model") or DEFAULT_MODEL
    return endpoint.rstrip("/"), model


def search_brave(query: str) -> str:
    """Perform a web search query via Brave Search API if configured."""
    api_key = secrets_vault.get("brave_api_key")
    if not api_key:
        return ""
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                params={"q": f"{query} company business", "count": 2},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                snippets = [r.get("description") or r.get("title", "") for r in results if r.get("description") or r.get("title")]
                return " ".join(snippets[:2])
    except Exception:
        pass
    return ""


def classify_merchants(
    merchants: list[str],
    categories: list[str],
    endpoint: str | None = None,
    model: str | None = None,
    use_web_search: bool = True,
) -> list[tuple[str, str, float]]:
    if not merchants or not categories:
        return []

    ep, mdl = get_llm_config()
    endpoint = endpoint or ep
    model = model or mdl

    # If Brave API key is available and web search is enabled, fetch context for unknown merchants
    brave_ctx_lines = []
    if use_web_search and secrets_vault.get("brave_api_key"):
        for m in merchants:
            snip = search_brave(m)
            if snip:
                brave_ctx_lines.append(f"- {m}: {snip[:200]}")

    web_ctx_str = ""
    if brave_ctx_lines:
        web_ctx_str = "\nWeb Search Context for merchants:\n" + "\n".join(brave_ctx_lines) + "\n"

    prompt = (
        "Classify the following merchant/transaction names into one of the allowed categories.\n"
        f"Allowed categories: {json.dumps(categories)}\n"
        f"{web_ctx_str}"
        f"Merchants: {json.dumps(merchants)}\n"
        "Return a JSON object with a list of classifications containing: merchant, category, confidence (0.0 to 1.0)."
    )

    schema = {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "merchant": {"type": "string"},
                        "category": {"type": "string", "enum": categories},
                        "confidence": {"type": "number"},
                    },
                    "required": ["merchant", "category", "confidence"],
                },
            }
        },
        "required": ["classifications"],
    }

    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": "You are a financial classification system. Output strict JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "merchant_classification", "schema": schema, "strict": True},
        },
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                return []
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            results = []
            for item in parsed.get("classifications", []):
                results.append((item["merchant"], item["category"], float(item.get("confidence", 0.8))))
            return results
    except Exception:
        return []

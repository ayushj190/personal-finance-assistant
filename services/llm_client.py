import json
from typing import Any
import httpx
from ollama import Client

from config import DEFAULT_MODEL, DEFAULT_OLLAMA_URL
from services import secrets_vault


def get_ollama_client() -> tuple[Client, str]:
    endpoint = secrets_vault.get("ollama_endpoint") or DEFAULT_OLLAMA_URL
    model = secrets_vault.get("ollama_model") or DEFAULT_MODEL
    return Client(host=endpoint), model


def generate_json(messages: list[dict[str, str]], schema: dict[str, Any] | None = None) -> dict[str, Any] | None:
    client, model = get_ollama_client()
    try:
        response = client.chat(
            model=model,
            messages=messages,
            format=schema if schema else 'json',
            options={"temperature": 0.0}
        )
        content = response['message']['content']
        return json.loads(content)
    except Exception as e:
        print(f"Ollama generation error: {e}")
        return None

def generate_stream(messages: list[dict[str, str]]) -> Any:
    """Yields string chunks from the LLM response."""
    client, model = get_ollama_client()
    try:
        response = client.chat(
            model=model,
            messages=messages,
            stream=True
        )
        for chunk in response:
            if 'message' in chunk and 'content' in chunk['message']:
                yield chunk['message']['content']
    except Exception as e:
        yield f"\n⚠️ Error connecting to local Ollama model: {e}"


def search_brave(query: str) -> str:
    """Perform a web search query via Brave Search API if configured."""
    api_key = secrets_vault.get("brave_api_key")
    if not api_key:
        return ""
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json",
                         "X-Subscription-Token": api_key},
                params={"q": f"{query} company business", "count": 2},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                snippets = [r.get("description") or r.get("title", "")
                            for r in results if r.get("description") or r.get("title")]
                return " ".join(snippets[:2])
    except Exception:
        pass
    return ""


def classify_merchants(
    merchants: list[str],
    categories: list[str],
    use_web_search: bool = True,
) -> list[tuple[str, str, float]]:
    if not merchants or not categories:
        return []

    brave_ctx_lines = []
    if use_web_search and secrets_vault.get("brave_api_key"):
        for m in merchants:
            snip = search_brave(m)
            if snip:
                brave_ctx_lines.append(f"- {m}: {snip[:200]}")

    web_ctx_str = ""
    if brave_ctx_lines:
        web_ctx_str = "\nWeb Search Context for merchants:\n" + \
            "\n".join(brave_ctx_lines) + "\n"

    prompt = (
        "Classify the following merchant/transaction names into one of the allowed categories.\n"
        f"Allowed categories: {json.dumps(categories)}\n"
        f"{web_ctx_str}"
        f"Merchants: {json.dumps(merchants)}\n"
        "Return a JSON object with a list of classifications."
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

    messages = [
        {"role": "system", "content": "You are a financial classification system. Output strict JSON only."},
        {"role": "user", "content": prompt},
    ]

    parsed = generate_json(messages, schema=schema)
    if not parsed:
        return []

    results = []
    for item in parsed.get("classifications", []):
        results.append((item["merchant"], item["category"],
                       float(item.get("confidence", 0.8))))
    return results

from typing import Any

from config import DB_PATH
from db import database
from services.legal_vault_service import search_legal_vault, lookup_article
from services.rag_service import search_knowledge_base, ingest_user_document


def tool_search_dutch_law_vault(
    query: str,
    category: str | None = None,
    effective_year: int | None = None,
) -> dict[str, Any]:
    """Search the Dutch Financial Law Vector Vault using hybrid FTS5 and sqlite-vec RRF search."""
    if not query or not str(query).strip():
        return {
            "success": False,
            "message": "Search query cannot be empty. Please specify a financial, tax, or legal question.",
        }
    clean_query = str(query).strip()

    clean_year = None
    if effective_year is not None:
        try:
            clean_year = int(effective_year)
            if not (1900 <= clean_year <= 2100):
                return {
                    "success": False,
                    "message": f"Invalid effective year '{effective_year}'. Must be between 1900 and 2100.",
                }
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": f"Invalid effective year '{effective_year}'. Must be a 4-digit numeric year.",
            }

    results = search_legal_vault(clean_query, category=category, top_k=4, effective_year=clean_year)
    if not results:
        legacy_res = search_knowledge_base(clean_query, top_k=3, category=category)
        if legacy_res:
            citations = [
                {
                    "article_ref": r.get("id", "Guidance"),
                    "statute_title": r.get("title", "Dutch Tax & Mortgage Guidance"),
                    "summary": r.get("content", "")[:220],
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.75),
                    "effective_year": 2026,
                }
                for r in legacy_res
            ]
            return {
                "success": True,
                "results": legacy_res,
                "citations": citations,
                "message": f"Retrieved {len(legacy_res)} articles from knowledge base.",
            }
        return {
            "success": False,
            "results": [],
            "citations": [],
            "message": f"No statutory articles found for query '{clean_query}'.",
        }

    citations = [
        {
            "chunk_id": r.chunk_id,
            "article_ref": r.article_ref,
            "chunk_title": r.chunk_title,
            "statute_title": r.doc_title,
            "category": r.category,
            "effective_year": r.effective_year,
            "summary": r.summary,
            "content": r.content,
            "juriconnect_ref": r.juriconnect_ref,
            "source_url": r.source_url,
            "score": r.score,
        }
        for r in results
    ]

    return {
        "success": True,
        "results": [
            {
                "id": f"{r.doc_id}_{r.chunk_id}",
                "title": f"{r.article_ref} ({r.doc_title})",
                "category": r.category,
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ],
        "citations": citations,
        "message": f"Retrieved {len(results)} statutory citations from Dutch Financial Law Vault.",
    }


def tool_lookup_tax_law_article(article_ref: str) -> dict[str, Any]:
    """Look up an exact Dutch statutory tax code or legal article reference (e.g. 'Art. 3.16', 'Art. 5.2', 'Art. 3.120')."""
    if not article_ref or not str(article_ref).strip():
        return {
            "success": False,
            "message": "Article reference cannot be empty. Please specify an article reference such as 'Art. 3.16' or 'Art. 5.2'.",
        }
    clean_ref = str(article_ref).strip()
    res = lookup_article(clean_ref)
    if not res:
        return {
            "success": False,
            "message": f"Article reference '{clean_ref}' not found in the Dutch Financial Law Vault.",
        }

    citation = {
        "chunk_id": res.chunk_id,
        "article_ref": res.article_ref,
        "chunk_title": res.chunk_title,
        "statute_title": res.doc_title,
        "category": res.category,
        "effective_year": res.effective_year,
        "summary": res.summary,
        "content": res.content,
        "juriconnect_ref": res.juriconnect_ref,
        "source_url": res.source_url,
        "score": res.score,
    }

    return {
        "success": True,
        "article": citation,
        "citations": [citation],
        "message": f"Found statutory article {res.article_ref} from {res.doc_title}.",
    }


def tool_search_financial_knowledge_base(query: str, category: str | None = None) -> dict[str, Any]:
    """Search the local knowledge base for Dutch tax laws, Box 1/3 rules, pension spaces, or mortgages."""
    return tool_search_dutch_law_vault(query, category=category)


def tool_ingest_financial_document(doc_title: str, content: str, category: str = "custom") -> dict[str, Any]:
    """Index a custom text/markdown document (e.g. UPO pension statement, mortgage advice deed) into local RAG."""
    conn = database.connect(DB_PATH)
    try:
        res = ingest_user_document(title=doc_title, content=content, category=category, conn=conn)
        return res
    finally:
        conn.close()

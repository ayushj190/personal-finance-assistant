import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from config import DB_PATH
from db import database
from services.llm_client import get_ollama_client

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"

DEFAULT_KNOWLEDGE_DOCS = [
    {
        "id": "tax_box_1",
        "title": "Dutch Income Tax: Box 1 (Work and Home)",
        "category": "tax",
        "content": (
            "Box 1 taxes taxable income from employment and home ownership. "
            "For 2024/2026, the basic tax bracket is ~36.97% up to €75,518 gross income, "
            "and 49.50% above that threshold. Key deductions include mortgage interest deduction "
            "(hypotheekrenteaftrek) for primary residence (eigen woning) and deductible annuity premiums (lijfrente). "
            "The 30% ruling reduces taxable gross income for eligible international skilled workers."
        ),
    },
    {
        "id": "tax_box_3",
        "title": "Dutch Wealth Tax: Box 3 (Savings and Investments)",
        "category": "tax",
        "content": (
            "Box 3 taxes savings, investments, and other assets based on deemed return (fictief rendement). "
            "There is a tax-free wealth allowance (heffingvrij vermogen) of €57,000 per person (€114,000 for fiscal partners). "
            "Bank balances and cash have a low deemed yield (~1.03%), whereas investments and stocks have a higher deemed yield (~6.04%). "
            "Tax rate on the deemed yield is 36%. Investments in certified green funds (Groenfondsen) qualify for exemption up to €71,251."
        ),
    },
    {
        "id": "pension_lijfrente",
        "title": "Dutch Pension Space (Jaarruimte & Lijfrente)",
        "category": "pension",
        "content": (
            "Jaarruimte is the tax-deductible contribution space available for private pension accumulation (Pillar 3). "
            "Contributions into an approved blocked pension account (lijfrenterekening) or pension annuity reduce Box 1 taxable income, "
            "yielding immediate tax savings up to 49.5%. The funds grow exempt from Box 3 wealth tax until retirement, "
            "when distributions are taxed at standard Box 1 rates."
        ),
    },
    {
        "id": "mortgage_repayment",
        "title": "Dutch Mortgage Repayment and Deductions",
        "category": "mortgage",
        "content": (
            "Most Dutch residential mortgages are annuity (annuïteitenhypotheek) or linear (lineaire hypotheek). "
            "Mortgage interest deduction (hypotheekrenteaftrek) is only available for mortgages that repay principal over max 30 years. "
            "Lenders typically permit 10% to 20% penalty-free extra principal repayments per calendar year. "
            "Extra repayments directly lower future interest burden and can either lower monthly payment or shorten loan term."
        ),
    },
    {
        "id": "green_funds_groenfondsen",
        "title": "Certified Green Funds (Groenfondsen & Regeling Groenprojecten)",
        "category": "green_funds",
        "content": (
            "Under the Dutch Regeling groenprojecten, certified green funds (e.g., ASN Groenprojectenfonds NL0000440447, "
            "Triodos Groenfonds NL0000286147) offer a double tax benefit: 1) Box 3 wealth tax exemption up to €71,251 "
            "(€142,502 for fiscal partners), completely removing the ~2.17% deemed yield tax drag. 2) An additional 0.1% "
            "Box 1 income tax credit. Total guaranteed risk-free tax alpha is ~2.27% per year."
        ),
    },
    {
        "id": "emergency_fund_buffer",
        "title": "Emergency Fund Buffer Guidelines (Nibud)",
        "category": "savings",
        "content": (
            "The Dutch National Institute for Family Finance Information (Nibud) recommends maintaining 3 to 6 months "
            "of essential living expenses in accessible liquid cash (high-yield savings account). "
            "EU banks covered by the Deposit Guarantee Scheme (Depositogarantiestelsel / DGS) protect deposits up to €100,000 per account holder per banking license."
        ),
    },
]


def _tokenize(text: str) -> list[str]:
    """Extract normalized alphanumeric words >= 3 characters."""
    return [w.lower() for w in re.findall(r"\b\w{3,}\b", text)]


def _cosine_sim(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def _text_to_pseudo_vec(text: str, vocab: list[str]) -> list[float]:
    """Deterministic hash/vocab bag-of-words vector fallback for offline execution."""
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * len(vocab)
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    vec = [float(tf.get(v, 0)) for v in vocab]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _infer_category(filename: str, title: str) -> str:
    name_lower = (filename + " " + title).lower()
    if "box1" in name_lower or "box 1" in name_lower or "income" in name_lower:
        return "tax_box1"
    if "box3" in name_lower or "box 3" in name_lower or "wealth" in name_lower:
        return "tax_box3"
    if "green" in name_lower or "groen" in name_lower:
        return "green_funds"
    if "pension" in name_lower or "jaarruimte" in name_lower or "lijfrente" in name_lower:
        return "pension"
    if "mortgage" in name_lower or "hypotheek" in name_lower:
        return "mortgage"
    if "loss" in name_lower or "deduction" in name_lower:
        return "tax_strategy"
    return "general"


def load_raw_documents() -> list[dict[str, Any]]:
    """Load markdown documents from disk, or fallback to default in-memory documents."""
    docs: list[dict[str, Any]] = []
    if KNOWLEDGE_DIR.exists() and KNOWLEDGE_DIR.is_dir():
        for file in sorted(KNOWLEDGE_DIR.glob("*.md")):
            try:
                content = file.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                first_line = content.splitlines()[0].strip()
                title = first_line.lstrip("#").strip() if first_line.startswith("#") else file.stem.replace("_", " ").title()
                cat = _infer_category(file.stem, title)
                docs.append({
                    "id": file.stem,
                    "filename": file.name,
                    "title": title,
                    "category": cat,
                    "content": content,
                })
            except Exception:
                pass

    if not docs:
        docs = [dict(d) for d in DEFAULT_KNOWLEDGE_DOCS]
    return docs


def split_document_into_chunks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a markdown document into logical topic chunks based on headings."""
    content = doc.get("content", "")
    sections = re.split(r"\n(?=##\s+)", content)
    chunks: list[dict[str, Any]] = []

    doc_id = doc.get("id", "doc")
    doc_title = doc.get("title", "Financial Guidance")
    category = doc.get("category", "general")

    for idx, sec in enumerate(sections):
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.splitlines()
        first = lines[0].strip()
        chunk_title = first.lstrip("#").strip() if first.startswith("#") else f"{doc_title} (Part {idx + 1})"
        chunk_id = f"{doc_id}_{idx}"
        
        chunks.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "doc_title": doc_title,
            "chunk_title": chunk_title,
            "category": category,
            "content": sec,
        })

    if not chunks:
        chunks.append({
            "chunk_id": f"{doc_id}_0",
            "doc_id": doc_id,
            "doc_title": doc_title,
            "chunk_title": doc_title,
            "category": category,
            "content": content,
        })
    return chunks


def sync_knowledge_base_embeddings(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Ensure all chunks are persisted and vector-indexed in SQLite WAL."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
              id              INTEGER PRIMARY KEY,
              chunk_id        TEXT UNIQUE NOT NULL,
              doc_title       TEXT NOT NULL,
              category        TEXT NOT NULL,
              content         TEXT NOT NULL,
              embedding_json  TEXT,
              updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        raw_docs = load_raw_documents()
        all_chunks: list[dict[str, Any]] = []
        for d in raw_docs:
            all_chunks.extend(split_document_into_chunks(d))

        # Check existing cached chunks in database
        existing_rows = conn.execute("SELECT chunk_id, embedding_json FROM knowledge_embeddings").fetchall()
        existing_map = {r["chunk_id"]: r["embedding_json"] for r in existing_rows}

        # Build vocabulary across all chunks for pseudo-embedding fallback
        all_tokens = set()
        for ch in all_chunks:
            all_tokens.update(_tokenize(f"{ch['chunk_title']} {ch['content']}"))
        vocab = sorted(list(all_tokens))[:128]

        # Try to batch embed using Ollama if available
        ollama_embeddings: list[list[float]] = []
        try:
            client, model = get_ollama_client()
            texts_to_embed = [f"{c['chunk_title']}: {c['content'][:500]}" for c in all_chunks]
            resp = client.embed(model=model, input=texts_to_embed)
            embs = resp.get("embeddings", [])
            if len(embs) == len(all_chunks):
                ollama_embeddings = embs
        except Exception:
            ollama_embeddings = []

        with conn:
            for idx, ch in enumerate(all_chunks):
                cid = ch["chunk_id"]
                vec = None
                if ollama_embeddings:
                    vec = ollama_embeddings[idx]
                elif cid in existing_map and existing_map[cid]:
                    try:
                        vec = json.loads(existing_map[cid])
                    except Exception:
                        vec = None
                
                if not vec:
                    vec = _text_to_pseudo_vec(f"{ch['chunk_title']} {ch['content']}", vocab)

                emb_json = json.dumps(vec)
                conn.execute(
                    """
                    INSERT INTO knowledge_embeddings (chunk_id, doc_title, category, content, embedding_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(chunk_id) DO UPDATE SET
                      doc_title=excluded.doc_title,
                      category=excluded.category,
                      content=excluded.content,
                      embedding_json=excluded.embedding_json,
                      updated_at=datetime('now')
                    """,
                    (cid, ch["chunk_title"], ch["category"], ch["content"], emb_json),
                )
                ch["embedding"] = vec

        return all_chunks
    finally:
        if close_conn:
            conn.close()


def search_knowledge_base(
    query: str,
    top_k: int = 3,
    category: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Hybrid semantic vector + BM25 search across local Dutch tax & mortgage articles."""
    if not query.strip():
        return []

    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        try:
            rows = conn.execute("SELECT chunk_id, doc_title, category, content, embedding_json FROM knowledge_embeddings").fetchall()
        except sqlite3.OperationalError:
            sync_knowledge_base_embeddings(conn)
            rows = conn.execute("SELECT chunk_id, doc_title, category, content, embedding_json FROM knowledge_embeddings").fetchall()

        if not rows:
            sync_knowledge_base_embeddings(conn)
            rows = conn.execute("SELECT chunk_id, doc_title, category, content, embedding_json FROM knowledge_embeddings").fetchall()

        if not rows:
            # Fallback if DB is empty: use default docs
            raw = [dict(d) for d in DEFAULT_KNOWLEDGE_DOCS]
            return raw[:top_k]

        q_tokens = set(_tokenize(query))

        # Try to obtain query embedding
        q_vec = None
        try:
            client, model = get_ollama_client()
            resp = client.embed(model=model, input=query)
            embs = resp.get("embeddings", [])
            if embs:
                q_vec = embs[0]
        except Exception:
            q_vec = None

        scored_candidates: list[tuple[float, dict[str, Any]]] = []

        for r in rows:
            if category and r["category"] != category:
                continue

            doc_text = f"{r['doc_title']} {r['content']}"
            doc_tokens = _tokenize(doc_text)

            # 1. Lexical BM25 / token-overlap score
            lexical_score = 0.0
            if q_tokens and doc_tokens:
                overlap = sum(1 for t in q_tokens if t in doc_tokens)
                lexical_score = overlap / (math.sqrt(len(q_tokens) * len(doc_tokens)) + 1e-5)

            # 2. Vector cosine similarity
            vec_score = 0.0
            if q_vec and r["embedding_json"]:
                try:
                    c_vec = json.loads(r["embedding_json"])
                    if len(c_vec) == len(q_vec):
                        vec_score = max(0.0, _cosine_sim(q_vec, c_vec))
                except Exception:
                    pass

            # Combine scores: weighted blend if vector available, else lexical
            if q_vec and vec_score > 0:
                combined_score = 0.65 * vec_score + 0.35 * min(1.0, lexical_score)
            else:
                combined_score = lexical_score

            if combined_score > 0.02 or (not q_tokens):
                scored_candidates.append((
                    combined_score,
                    {
                        "id": r["chunk_id"],
                        "title": r["doc_title"],
                        "category": r["category"],
                        "content": r["content"],
                        "score": round(combined_score, 4),
                    }
                ))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored_candidates[:top_k]]
    finally:
        if close_conn:
            conn.close()


def ingest_user_document(
    title: str,
    content: str,
    category: str = "custom",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Ingest a custom user document (e.g. UPO pension statement, mortgage advice note) into RAG."""
    if not title.strip() or not content.strip():
        return {"success": False, "message": "Document title and content cannot be empty."}

    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", title.lower().strip())
    filename = f"user_{slug}.md"
    file_path = KNOWLEDGE_DIR / filename
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    file_path.write_text(f"# {title}\n\n{content}", encoding="utf-8")

    # Re-sync embeddings
    sync_knowledge_base_embeddings(conn)

    return {
        "success": True,
        "filename": filename,
        "title": title,
        "category": category,
        "message": f"Successfully ingested and indexed '{title}' into the knowledge base.",
    }


def get_all_knowledge_documents() -> list[dict[str, Any]]:
    """Return all available documents with summary metadata for UI presentation."""
    raw_docs = load_raw_documents()
    summaries = []
    for d in raw_docs:
        content = d.get("content", "")
        preview = content[:220].replace("\n", " ").strip() + "..."
        word_count = len(content.split())
        summaries.append({
            "id": d.get("id"),
            "title": d.get("title"),
            "category": d.get("category"),
            "word_count": word_count,
            "preview": preview,
            "content": content,
        })
    return summaries

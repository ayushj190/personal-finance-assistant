import math
import os
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import struct
from typing import Any

from config import DB_PATH
from db import database
from services.llm_client import get_ollama_client

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"
FASTEMBED_CACHE_DIR = os.environ.get("FASTEMBED_CACHE_DIR", str(Path(__file__).resolve().parent.parent / ".cache" / "fastembed"))
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "all-minilm")

_fastembed_model_instance = None
_ollama_embed_checked = False
_ollama_embed_available = False


def _is_ollama_available() -> bool:
    """Probe Ollama once for 384-dim embed model availability."""
    global _ollama_embed_checked, _ollama_embed_available
    if not _ollama_embed_checked:
        _ollama_embed_checked = True
        try:
            client, _ = get_ollama_client()
            resp = client.embed(model=OLLAMA_EMBED_MODEL, input="test")
            embs = resp.get("embeddings", [])
            if embs and len(embs[0]) == 384:
                _ollama_embed_available = True
            else:
                _ollama_embed_available = False
        except Exception:
            _ollama_embed_available = False
    return _ollama_embed_available


@dataclass
class LegalSearchResult:
    chunk_id: int
    doc_id: str
    article_ref: str
    chunk_title: str
    category: str
    effective_year: int
    summary: str
    content: str
    word_count: int
    juriconnect_ref: str | None
    source_url: str | None
    doc_title: str
    score: float
    fts_rank: int | None = None
    vec_rank: int | None = None


def load_sqlite_vec_extension(conn: sqlite3.Connection) -> bool:
    """Safely load sqlite-vec C extension into connection."""
    try:
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        return True
    except Exception:
        return False


def init_legal_vault_schema(conn: sqlite3.Connection) -> None:
    """Initialize legal vault relational, fallback, and vec0 virtual tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_documents (
            id              TEXT PRIMARY KEY,
            bwb_id          TEXT,
            title           TEXT NOT NULL,
            short_title     TEXT NOT NULL,
            category        TEXT NOT NULL,
            jurisdiction    TEXT NOT NULL DEFAULT 'NL',
            effective_year  INTEGER NOT NULL DEFAULT 2026,
            source_url      TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id          TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
            article_ref     TEXT NOT NULL,
            chunk_title     TEXT NOT NULL,
            category        TEXT NOT NULL,
            effective_year  INTEGER NOT NULL DEFAULT 2026,
            juriconnect_ref TEXT,
            summary         TEXT NOT NULL,
            content         TEXT NOT NULL,
            word_count      INTEGER NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_vec_fallback (
            chunk_id        INTEGER PRIMARY KEY REFERENCES legal_chunks(id) ON DELETE CASCADE,
            embedding_blob  BLOB NOT NULL
        );
    """)

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS legal_fts USING fts5(
            article_ref,
            chunk_title,
            content,
            category UNINDEXED,
            content='legal_chunks',
            content_rowid='id'
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS legal_query_audit (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text      TEXT NOT NULL,
            category_filter TEXT,
            retrieved_count INTEGER NOT NULL,
            top_score       REAL NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_chunks_category ON legal_chunks(category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_chunks_article ON legal_chunks(article_ref);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_legal_chunks_year ON legal_chunks(effective_year);")

    # Try creating sqlite-vec virtual table if extension is loaded
    if load_sqlite_vec_extension(conn):
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS legal_vec USING vec0(
                    chunk_id        INTEGER PRIMARY KEY,
                    embedding       float[384] distance_metric=cosine
                );
            """)
        except Exception:
            pass


def _get_fastembed_model():
    """Lazily initialize FastEmbed model singleton (384 dimensions)."""
    global _fastembed_model_instance
    if _fastembed_model_instance is None:
        from fastembed import TextEmbedding
        Path(FASTEMBED_CACHE_DIR).mkdir(parents=True, exist_ok=True)
        _fastembed_model_instance = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=FASTEMBED_CACHE_DIR,
        )
    return _fastembed_model_instance


def get_embedding(text: str) -> list[float]:
    """Obtain 384-dimensional embedding using Ollama with FastEmbed CPU fallback."""
    clean_text = text.strip()
    if not clean_text:
        return [0.0] * 384

    # 1. Try Ollama local model if probe succeeded
    if _is_ollama_available():
        try:
            client, _ = get_ollama_client()
            resp = client.embed(model=OLLAMA_EMBED_MODEL, input=clean_text)
            embs = resp.get("embeddings", [])
            if embs and len(embs[0]) == 384:
                return embs[0]
        except Exception:
            pass

    # 2. FastEmbed ONNX CPU fallback (always 384 dims)
    try:
        model = _get_fastembed_model()
        emb_gen = model.embed([clean_text])
        for vec in emb_gen:
            return [float(x) for x in vec]
    except Exception:
        pass

    # 3. Deterministic zero vector if both unavailable
    return [0.0] * 384


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple strings using Ollama with FastEmbed fallback."""
    if not texts:
        return []

    # 1. Try Ollama batch if probe succeeded
    if _is_ollama_available():
        try:
            client, _ = get_ollama_client()
            resp = client.embed(model=OLLAMA_EMBED_MODEL, input=texts)
            embs = resp.get("embeddings", [])
            if embs and len(embs) == len(texts) and len(embs[0]) == 384:
                return [[float(x) for x in e] for e in embs]
        except Exception:
            pass

    # 2. FastEmbed batch fallback
    try:
        model = _get_fastembed_model()
        embs = []
        for vec in model.embed(texts):
            embs.append([float(x) for x in vec])
        if len(embs) == len(texts):
            return embs
    except Exception:
        pass

    return [get_embedding(t) for t in texts]


def serialize_float32(vector: list[float]) -> bytes:
    """Serialize float vector to binary format for sqlite-vec and fallback blob."""
    import sqlite_vec
    try:
        return sqlite_vec.serialize_float32(vector)
    except Exception:
        return struct.pack(f"{len(vector)}f", *vector)


def deserialize_float32(blob: bytes) -> list[float]:
    """Deserialize binary blob back to float list."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def parse_knowledge_file(file_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse a markdown knowledge document into document metadata and individual statutory chunks."""
    text = file_path.read_text(encoding="utf-8").strip()
    
    # 1. Parse frontmatter if present
    frontmatter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()

    stem = file_path.stem
    doc_id = frontmatter.get("id", stem)
    bwb_id = frontmatter.get("bwb_id")
    category = frontmatter.get("category", _infer_doc_category(stem))
    effective_year = int(frontmatter.get("effective_year", 2026))
    source_url = frontmatter.get("source_url")
    title = frontmatter.get("title")
    short_title = frontmatter.get("short_title")

    # If title not in frontmatter, extract from first H1
    if not title:
        first_line = body.splitlines()[0] if body else stem
        title = first_line.lstrip("#").strip() if first_line.startswith("#") else stem.replace("_", " ").title()
    if not short_title:
        short_title = title.split("-")[0].strip() if "-" in title else title[:30]

    doc_meta = {
        "id": doc_id,
        "bwb_id": bwb_id,
        "title": title,
        "short_title": short_title,
        "category": category,
        "jurisdiction": frontmatter.get("jurisdiction", "NL"),
        "effective_year": effective_year,
        "source_url": source_url,
    }

    # 2. Split body into article sections based on '## '
    sections = re.split(r"\n(?=##\s+)", body)
    chunks: list[dict[str, Any]] = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if "## " in body and not sec.startswith("## "):
            continue
        lines = sec.splitlines()
        header_line = lines[0].lstrip("#").strip()
        
        # Check if header represents an article, e.g. "Art. 3.16 - Aftrekbeperking gemengde kosten"
        art_match = re.search(r"(Art(?:ikel)?\.?\s*[\w\.:]+|[A-Z][\w\s]+(?:Arrest|Norm|Regeling)[\w\s\d]*)", header_line, re.IGNORECASE)
        article_ref = art_match.group(1).strip() if art_match else header_line.split("-")[0].strip()
        
        chunk_title = header_line
        juriconnect_ref = None
        summary = ""
        content_lines = []

        for l in lines[1:]:
            l_str = l.strip()
            if l_str.lower().startswith("juriconnect:"):
                juriconnect_ref = l_str.split(":", 1)[1].strip()
            elif l_str.lower().startswith("summary:"):
                summary = l_str.split(":", 1)[1].strip()
            elif l_str.lower().startswith("content:"):
                pass
            else:
                content_lines.append(l)

        raw_content = "\n".join(content_lines).strip()
        if not raw_content:
            raw_content = sec

        if not summary:
            # Generate summary from first 1-2 sentences of content
            sentences = re.split(r"(?<=[.!?])\s+", raw_content)
            summary = " ".join(sentences[:2]).strip()[:240]

        words = len(raw_content.split())
        chunks.append({
            "doc_id": doc_id,
            "article_ref": article_ref,
            "chunk_title": chunk_title,
            "category": category,
            "effective_year": effective_year,
            "juriconnect_ref": juriconnect_ref,
            "summary": summary,
            "content": raw_content,
            "word_count": words,
        })

    return doc_meta, chunks


def _infer_doc_category(name: str) -> str:
    n = name.lower()
    if "box1" in n or "box 1" in n or "income" in n:
        return "tax_box1"
    if "box3" in n or "box 3" in n or "wealth" in n:
        return "tax_box3"
    if "pension" in n or "jaarruimte" in n:
        return "pension"
    if "mortgage" in n or "hypotheek" in n:
        return "mortgage"
    if "green" in n or "groen" in n:
        return "green_funds"
    if "estate" in n or "successie" in n or "gift" in n or "erf" in n:
        return "estate"
    if "expat" in n or "30" in n:
        return "expat"
    return "general"


def ingest_legal_corpus(force_reindex: bool = False, conn: sqlite3.Connection | None = None) -> dict[str, int]:
    """Ingest, parse, and index all legal documents from data/knowledge/ into SQLite."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        init_legal_vault_schema(conn)
        vec_available = load_sqlite_vec_extension(conn)

        doc_count = 0
        chunk_count = 0

        files = sorted(list(KNOWLEDGE_DIR.glob("*.md")))
        for f in files:
            doc_meta, chunks = parse_knowledge_file(f)
            if not chunks:
                continue

            with conn:
                # Upsert document
                conn.execute(
                    """
                    INSERT INTO legal_documents (id, bwb_id, title, short_title, category, jurisdiction, effective_year, source_url, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        bwb_id=excluded.bwb_id,
                        title=excluded.title,
                        short_title=excluded.short_title,
                        category=excluded.category,
                        effective_year=excluded.effective_year,
                        source_url=excluded.source_url,
                        updated_at=datetime('now');
                    """,
                    (
                        doc_meta["id"],
                        doc_meta["bwb_id"],
                        doc_meta["title"],
                        doc_meta["short_title"],
                        doc_meta["category"],
                        doc_meta["jurisdiction"],
                        doc_meta["effective_year"],
                        doc_meta["source_url"],
                    ),
                )
                doc_count += 1

                # Check existing chunks for this doc
                existing_rows = conn.execute("SELECT id, article_ref FROM legal_chunks WHERE doc_id = ?", (doc_meta["id"],)).fetchall()
                existing_map = {r["article_ref"]: r["id"] for r in existing_rows}

                pending_embeds = []
                for ch in chunks:
                    art_ref = ch["article_ref"]
                    chunk_id = existing_map.get(art_ref)

                    if chunk_id is not None and not force_reindex:
                        # Chunk exists and not forced reindex, continue
                        chunk_count += 1
                        continue

                    if chunk_id is None:
                        # Insert chunk
                        cur = conn.execute(
                            """
                            INSERT INTO legal_chunks (doc_id, article_ref, chunk_title, category, effective_year, juriconnect_ref, summary, content, word_count)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                ch["doc_id"],
                                ch["article_ref"],
                                ch["chunk_title"],
                                ch["category"],
                                ch["effective_year"],
                                ch["juriconnect_ref"],
                                ch["summary"],
                                ch["content"],
                                ch["word_count"],
                            ),
                        )
                        chunk_id = cur.lastrowid
                    else:
                        # Update chunk
                        conn.execute(
                            """
                            UPDATE legal_chunks SET
                                chunk_title = ?,
                                category = ?,
                                effective_year = ?,
                                juriconnect_ref = ?,
                                summary = ?,
                                content = ?,
                                word_count = ?
                            WHERE id = ?;
                            """,
                            (
                                ch["chunk_title"],
                                ch["category"],
                                ch["effective_year"],
                                ch["juriconnect_ref"],
                                ch["summary"],
                                ch["content"],
                                ch["word_count"],
                                chunk_id,
                            ),
                        )

                    embed_text = f"{ch['article_ref']} {ch['chunk_title']}: {ch['summary']} {ch['content'][:600]}"
                    pending_embeds.append((chunk_id, embed_text))
                    chunk_count += 1

                if pending_embeds:
                    batch_texts = [p[1] for p in pending_embeds]
                    batch_embs = get_embeddings_batch(batch_texts)
                    for (cid, _), emb in zip(pending_embeds, batch_embs):
                        blob = serialize_float32(emb)
                        conn.execute(
                            """
                            INSERT INTO legal_vec_fallback (chunk_id, embedding_blob)
                            VALUES (?, ?)
                            ON CONFLICT(chunk_id) DO UPDATE SET embedding_blob = excluded.embedding_blob;
                            """,
                            (cid, blob),
                        )
                        if vec_available:
                            try:
                                conn.execute(
                                    """
                                    INSERT INTO legal_vec (chunk_id, embedding)
                                    VALUES (?, ?)
                                    ON CONFLICT(chunk_id) DO UPDATE SET embedding = excluded.embedding;
                                    """,
                                    (cid, blob),
                                )
                            except Exception:
                                pass

        return {"documents_indexed": doc_count, "chunks_indexed": chunk_count}
    finally:
        if close_conn:
            conn.close()


def sanitize_fts_query(query: str) -> str:
    """Sanitize user query for safe FTS5 MATCH execution."""
    cleaned = re.sub(r"[^\w\s\.:\-]", " ", query).strip()
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    # Format each token as a prefix search or exact token
    safe_terms = []
    for tok in tokens:
        # If token has punctuation like 3.16 or 4:34, wrap in quotes
        if "." in tok or ":" in tok or "-" in tok:
            safe_terms.append(f'"{tok}"')
        else:
            safe_terms.append(f'{tok}*')
    return " OR ".join(safe_terms)


def search_legal_vault(
    query: str,
    category: str | None = None,
    top_k: int = 4,
    effective_year: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[LegalSearchResult]:
    """Hybrid search combining SQLite FTS5 BM25 and sqlite-vec cosine distance with Reciprocal Rank Fusion (k=60)."""
    if not query.strip():
        return []

    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        init_legal_vault_schema(conn)
        vec_available = load_sqlite_vec_extension(conn)

        # Ensure seed data exists
        row_count = conn.execute("SELECT COUNT(*) FROM legal_chunks").fetchone()[0]
        if row_count == 0:
            ingest_legal_corpus(force_reindex=False, conn=conn)

        # 1. Full text search (FTS5 BM25)
        fts_query = sanitize_fts_query(query)
        fts_ranked_ids: list[int] = []

        if fts_query:
            sql_fts = """
                SELECT c.id
                FROM legal_fts f
                JOIN legal_chunks c ON c.id = f.rowid
                WHERE legal_fts MATCH ?
            """
            params_fts: list[Any] = [fts_query]
            if category:
                sql_fts += " AND c.category = ?"
                params_fts.append(category)
            if effective_year:
                sql_fts += " AND c.effective_year = ?"
                params_fts.append(effective_year)
            
            clean_query = query.strip()
            sql_fts += " ORDER BY (CASE WHEN LOWER(c.article_ref) = LOWER(?) OR LOWER(c.article_ref) LIKE LOWER(?) THEN 0 ELSE 1 END), rank LIMIT 40"
            params_fts.extend([clean_query, f"%{clean_query}%"])

            try:
                rows = conn.execute(sql_fts, params_fts).fetchall()
                fts_ranked_ids = [r["id"] for r in rows]
            except Exception:
                fts_ranked_ids = []

        # 2. Vector search (sqlite-vec or fallback python cosine)
        q_emb = get_embedding(query)
        vec_ranked_ids: list[int] = []

        if vec_available:
            try:
                blob = serialize_float32(q_emb)
                sql_vec = """
                    SELECT v.chunk_id, v.distance
                    FROM legal_vec v
                    JOIN legal_chunks c ON c.id = v.chunk_id
                    WHERE v.embedding MATCH ? AND k = 40
                """
                params_vec: list[Any] = [blob]
                if category:
                    sql_vec += " AND c.category = ?"
                    params_vec.append(category)
                if effective_year:
                    sql_vec += " AND c.effective_year = ?"
                    params_vec.append(effective_year)

                rows = conn.execute(sql_vec, params_vec).fetchall()
                vec_ranked_ids = [r["chunk_id"] for r in rows]
            except Exception:
                vec_available = False

        if not vec_available or not vec_ranked_ids:
            # Fallback to Python cosine similarity against legal_vec_fallback
            sql_fb = """
                SELECT f.chunk_id, f.embedding_blob
                FROM legal_vec_fallback f
                JOIN legal_chunks c ON c.id = f.chunk_id
            """
            params_fb: list[Any] = []
            if category:
                sql_fb += " WHERE c.category = ?"
                params_fb.append(category)
                if effective_year:
                    sql_fb += " AND c.effective_year = ?"
                    params_fb.append(effective_year)
            elif effective_year:
                sql_fb += " WHERE c.effective_year = ?"
                params_fb.append(effective_year)

            fb_rows = conn.execute(sql_fb, params_fb).fetchall()
            scored_fb = []
            for r in fb_rows:
                emb = deserialize_float32(r["embedding_blob"])
                sim = cosine_similarity(q_emb, emb)
                scored_fb.append((r["chunk_id"], sim))
            scored_fb.sort(key=lambda x: x[1], reverse=True)
            vec_ranked_ids = [cid for cid, _ in scored_fb[:40]]

        # 3. Reciprocal Rank Fusion (RRF, k=60)
        # RRF formula: RRF = (0.5 / (60 + fts_rank)) + (0.5 / (60 + vec_rank))
        k = 60.0
        all_candidate_ids = set(fts_ranked_ids) | set(vec_ranked_ids)
        if not all_candidate_ids:
            return []

        fts_rank_map = {cid: idx + 1 for idx, cid in enumerate(fts_ranked_ids)}
        vec_rank_map = {cid: idx + 1 for idx, cid in enumerate(vec_ranked_ids)}

        # Fetch full chunk and document details for candidates
        candidate_ids_list = list(all_candidate_ids)
        placeholders = ",".join("?" for _ in candidate_ids_list)
        sql_fetch = f"""
            SELECT c.id, c.doc_id, c.article_ref, c.chunk_title, c.category,
                   c.effective_year, c.juriconnect_ref, c.summary, c.content,
                   c.word_count, d.title as doc_title, d.source_url
            FROM legal_chunks c
            JOIN legal_documents d ON d.id = c.doc_id
            WHERE c.id IN ({placeholders})
        """
        detail_rows = {r["id"]: r for r in conn.execute(sql_fetch, candidate_ids_list).fetchall()}

        # Check for statutory code intent in query (e.g. "Art. 3.16" or "3.16" or "5.2")
        q_clean = query.strip().lower()
        art_match = re.search(r"(?:art(?:ikel)?\.?\s*)?(\d+[\.\:\w]*)", q_clean)
        target_art = art_match.group(1).lower() if art_match else ""

        scored_candidates: list[tuple[int, float, int | None, int | None]] = []
        for cid in all_candidate_ids:
            f_rank = fts_rank_map.get(cid)
            v_rank = vec_rank_map.get(cid)

            f_score = 0.5 / (k + f_rank) if f_rank is not None else 0.0
            v_score = 0.5 / (k + v_rank) if v_rank is not None else 0.0
            rrf_score = f_score + v_score

            # Normalize to 0.0 - 1.0 (max theoretical score is 1.0 / (k + 1))
            normalized_score = min(1.0, rrf_score * (k + 1.0))

            # Exact statutory reference boost
            if cid in detail_rows and target_art and len(target_art) >= 2:
                art_ref_low = detail_rows[cid]["article_ref"].lower()
                if f"art. {target_art}" in art_ref_low or art_ref_low == target_art or art_ref_low.endswith(target_art):
                    normalized_score = min(1.0, normalized_score + 0.25)

            scored_candidates.append((cid, round(normalized_score, 4), f_rank, v_rank))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = scored_candidates[:top_k]

        results: list[LegalSearchResult] = []
        for cid, score, f_rank, v_rank in top_candidates:
            if cid in detail_rows:
                r = detail_rows[cid]
                results.append(
                    LegalSearchResult(
                        chunk_id=r["id"],
                        doc_id=r["doc_id"],
                        article_ref=r["article_ref"],
                        chunk_title=r["chunk_title"],
                        category=r["category"],
                        effective_year=r["effective_year"],
                        summary=r["summary"],
                        content=r["content"],
                        word_count=r["word_count"],
                        juriconnect_ref=r["juriconnect_ref"],
                        source_url=r["source_url"],
                        doc_title=r["doc_title"],
                        score=score,
                        fts_rank=f_rank,
                        vec_rank=v_rank,
                    )
                )

        # 5. Audit query
        try:
            top_score = results[0].score if results else 0.0
            with conn:
                conn.execute(
                    """
                    INSERT INTO legal_query_audit (query_text, category_filter, retrieved_count, top_score)
                    VALUES (?, ?, ?, ?);
                    """,
                    (query, category, len(results), top_score),
                )
        except Exception:
            pass

        return results
    finally:
        if close_conn:
            conn.close()


def lookup_article(article_ref: str, conn: sqlite3.Connection | None = None) -> LegalSearchResult | None:
    """Exact statutory code lookup (e.g. 'Art. 3.16' or '5.2' or '3.120')."""
    if not article_ref.strip():
        return None

    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        init_legal_vault_schema(conn)
        clean_ref = article_ref.strip()
        sql = """
            SELECT c.id, c.doc_id, c.article_ref, c.chunk_title, c.category,
                   c.effective_year, c.juriconnect_ref, c.summary, c.content,
                   c.word_count, d.title as doc_title, d.source_url
            FROM legal_chunks c
            JOIN legal_documents d ON d.id = c.doc_id
            WHERE LOWER(c.article_ref) = LOWER(?) OR LOWER(c.article_ref) LIKE LOWER(?)
            LIMIT 1
        """
        row = conn.execute(sql, (clean_ref, f"%{clean_ref}%")).fetchone()
        if not row:
            return None

        return LegalSearchResult(
            chunk_id=row["id"],
            doc_id=row["doc_id"],
            article_ref=row["article_ref"],
            chunk_title=row["chunk_title"],
            category=row["category"],
            effective_year=row["effective_year"],
            summary=row["summary"],
            content=row["content"],
            word_count=row["word_count"],
            juriconnect_ref=row["juriconnect_ref"],
            source_url=row["source_url"],
            doc_title=row["doc_title"],
            score=1.0,
            fts_rank=1,
            vec_rank=1,
        )
    finally:
        if close_conn:
            conn.close()


def get_all_legal_documents(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return all parent legal statutes with chunk counts for UI explorer."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        init_legal_vault_schema(conn)
        # First load race: the corpus is ingested on first search, so a fresh vault
        # would otherwise list 0 statutes here. Self heal the same way (AC-10).
        row_count = conn.execute("SELECT COUNT(*) FROM legal_documents").fetchone()[0]
        if row_count == 0:
            ingest_legal_corpus(force_reindex=False, conn=conn)

        sql = """
            SELECT d.id, d.bwb_id, d.title, d.short_title, d.category,
                   d.effective_year, d.source_url, COUNT(c.id) as chunk_count
            FROM legal_documents d
            LEFT JOIN legal_chunks c ON c.doc_id = d.id
            GROUP BY d.id
            ORDER BY d.effective_year DESC, d.title ASC
        """
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_conn:
            conn.close()


def get_all_chunks_for_document(doc_id: str, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return all statutory articles and chunks for a given document."""
    close_conn = False
    if conn is None:
        conn = database.connect(DB_PATH)
        close_conn = True

    try:
        sql = """
            SELECT id, doc_id, article_ref, chunk_title, category,
                   effective_year, juriconnect_ref, summary, content, word_count
            FROM legal_chunks
            WHERE doc_id = ?
            ORDER BY id ASC
        """
        rows = conn.execute(sql, (doc_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_conn:
            conn.close()

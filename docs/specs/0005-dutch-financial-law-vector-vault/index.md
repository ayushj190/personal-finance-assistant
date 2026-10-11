# 0005. Dutch Financial Law Vector Vault and Copilot Knowledge Engine

**Date**: 2026-10-11
**Status**: Accepted

## Summary

This specification upgrades the Dutch financial law knowledge vault into a true local vector database with hybrid search and curated legal taxonomy. It replaces the previous six document in memory loop with the fast sqlite-vec extension and SQLite full text search running directly in our local database files. Text embeddings run through local Ollama models with an in process FastEmbed CPU fallback matching the exact same 384 dimensions so search works reliably without cloud services or external servers. The copilot gains accurate retrieval across Dutch tax codes, pension reform rules, mortgage norms, and recent court decisions, providing actionable personal finance advice backed by verifiable article citations.

## Context

Reasoning, options considered, and legal source references: see [rationale.md](rationale.md).

## Requirements

**User stories**:
- As a personal finance user, I want the copilot to analyze my actual account balances, investments, and mortgage against official Dutch tax laws and pension regulations, so that I receive concrete optimization recommendations with exact legal citations.
- As a wealth owner navigating Box 3 changes, I want the system to reference current legislative rules and recent court decisions on actual return versus deemed return, so that I can evaluate whether submitting an actual return statement is advantageous.
- As an individual evaluating pension room (jaarruimte) or extra mortgage repayments, I want the assistant to calculate my tax deductions according to the latest pension reform (Wet toekomst pensioenen) and mortgage standards without sending any financial data to cloud servers.

**Acceptance criteria**:
- **AC-1**: The legal vault persists structured statutory articles and regulatory guidance across six core personal finance domains (Box 1 income and deductions, Box 3 wealth and actual return rulings, pensions and Wet toekomst pensioenen jaarruimte, mortgage and property rules under financial supervision laws and Nibud standards, gifting and inheritance under Successiewet 1956, and expat thirty percent facility) in local SQLite tables populated from bundled seed files in `data/knowledge/`.
- **AC-2**: Vector indexing operates locally using the sqlite-vec extension with 384 dimensional vector embeddings stored in a virtual table, loaded reliably via `sqlite_vec.load(conn)`, executing vector similarity queries in single digit milliseconds without external vector server processes.
- **AC-3**: Embedding generation standardizes on 384 dimensional embeddings across both providers: local Ollama models (such as `all-minilm` or 384 dimensional multilingual models) with automatic in process FastEmbed ONNX CPU fallback (`sentence-transformers/all-MiniLM-L6-v2` or `paraphrase-multilingual-MiniLM-L12-v2`), ensuring identical vector representations regardless of which engine generated them.
- **AC-4**: Hybrid search combines SQLite FTS5 full text BM25 keyword matching with sqlite-vec cosine similarity using Reciprocal Rank Fusion (standard ranking constant k=60), returning relevant legal articles for natural language queries as well as exact statutory codes (such as article 3.16 or 10a.1).
- **AC-5**: Copilot search tool `tool_search_dutch_law_vault` in the agent tool registry accepts natural language search queries, category filters, and legal validity year filters, returning structured citations with statute titles, article numbers, validity years, and verbatim source passages.
- **AC-6**: Copilot chat responses display expandable citation cards indicating exact legal article numbers, legal validity year, and relevance scores, with direct quotes from statutory texts supporting the advice.
- **AC-7**: Failure resilience ensures that if the sqlite-vec C extension fails to load on a specific operating system, retrieval degrades gracefully to FTS5 full text search and Python cosine similarity on vector blobs without throwing unhandled exceptions.

## Decision

**Chosen option**: Option 1: SQLite Vector Extension (sqlite-vec) with FTS5 Hybrid Search and Local Dual Embedding Engine.

We adopt sqlite-vec as our native vector storage engine embedded directly in our SQLite database, paired with SQLite FTS5 full text search for hybrid retrieval. Embeddings are aligned to 384 dimensions locally via Ollama with FastEmbed CPU fallback. The legal knowledge base is populated with structured statutory articles, official ministerial circulars, and Supreme Court rulings covering all core personal finance domains.

## Feature design

**Data model sketch**:

```sql
-- Parent legal statutes and regulatory acts
CREATE TABLE IF NOT EXISTS legal_documents (
    id              TEXT PRIMARY KEY,          -- Slug identifier, e.g. 'wib_2001'
    bwb_id          TEXT,                      -- Official Basis Wetten Bestand ID, e.g. 'BWBR0011353'
    title           TEXT NOT NULL,             -- Full official name, e.g. 'Wet inkomstenbelasting 2001'
    short_title     TEXT NOT NULL,             -- Friendly name, e.g. 'Wet IB 2001'
    category        TEXT NOT NULL,             -- tax_box1, tax_box3, pension, mortgage, estate, expat
    jurisdiction    TEXT NOT NULL DEFAULT 'NL',
    effective_year  INTEGER NOT NULL DEFAULT 2026,
    source_url      TEXT,                      -- Official portal link at wetten.overheid.nl
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Granular statutory articles and sections
CREATE TABLE IF NOT EXISTS legal_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
    article_ref     TEXT NOT NULL,             -- Exact legal identifier, e.g. 'Art. 3.16' or 'Art. 5.2'
    chunk_title     TEXT NOT NULL,             -- Descriptive topic, e.g. 'Aftrekbare kosten eigen woning'
    category        TEXT NOT NULL,             -- Canonical category matching document
    effective_year  INTEGER NOT NULL DEFAULT 2026,
    juriconnect_ref TEXT,                      -- Standard Juriconnect deep link reference
    summary         TEXT NOT NULL,             -- Concise plain language digest
    content         TEXT NOT NULL,             -- Full official statutory text or regulatory guideline
    word_count      INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- sqlite-vec virtual table for SIMD cosine vector search (standardized 384 dimensions)
CREATE VIRTUAL TABLE IF NOT EXISTS legal_vec USING vec0(
    chunk_id        INTEGER PRIMARY KEY,
    embedding       float[384] distance_metric=cosine
);

-- SQLite FTS5 virtual table for BM25 keyword search
CREATE VIRTUAL TABLE IF NOT EXISTS legal_fts USING fts5(
    article_ref,
    chunk_title,
    content,
    category UNINDEXED,
    content='legal_chunks',
    content_rowid='id'
);

-- Audit log for copilot retrieval performance and citations
CREATE TABLE IF NOT EXISTS legal_query_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text      TEXT NOT NULL,
    category_filter TEXT,
    retrieved_count INTEGER NOT NULL,
    top_score       REAL NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_category ON legal_chunks(category);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_article ON legal_chunks(article_ref);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_year ON legal_chunks(effective_year);
```

**State transitions**:

Knowledge article lifecycle:
1. `raw_source`: Structured Markdown or XML files stored in `data/knowledge/` with YAML metadata.
2. `parsed`: Extracted into typed legal document and chunk dataclasses.
3. `persisted`: Written into `legal_documents` and `legal_chunks` relational tables.
4. `vector_indexed`: Text converted to 384 dimensional float vectors and inserted into `legal_vec`.
5. `text_indexed`: Tokenized and indexed in `legal_fts` for BM25 keyword matching.
6. `active`: Queryable by copilot tools and UI explorer.

**API surface**:

| Function or Tool | Location | Inputs | Outputs | Auth or Security | Key Errors |
|---|---|---|---|---|---|
| `search_legal_vault` | `services/legal_vault_service.py` | `query: str`, `category: str \| None`, `top_k: int`, `effective_year: int \| None` | `list[LegalSearchResult]` with text, citations, scores | Internal service call, read only connection | Database locked, extension missing |
| `ingest_legal_corpus` | `services/legal_vault_service.py` | `force_reindex: bool` | `dict[str, int]` count of documents and chunks indexed | Administrative service call | Corrupt source file, embedding model timeout |
| `tool_search_dutch_law_vault` | `agent/tools.py` | `query: str`, `category: str \| None`, `effective_year: int \| None` | `dict[str, Any]` with success flag, citations, passages | Copilot tool call, read only authorizer | Query empty, no matching articles |
| `tool_lookup_tax_law_article` | `agent/tools.py` | `article_ref: str` | `dict[str, Any]` with full article text and explanation | Copilot tool call, read only authorizer | Article reference not found |

**Value sourcing**:

| Action | Value produced or displayed | Source |
|---|---|---|
| Search legal vault | Relevance score (0.0 to 1.0) | Derived via Reciprocal Rank Fusion: RRF = (0.5 / (60 + fts_rank)) + (0.5 / (60 + vec_rank)) |
| Search legal vault | Article reference (e.g. 'Art. 5.2 WIB 2001') | Stored in `legal_chunks.article_ref` column |
| Search legal vault | Legal validity year | Stored in `legal_chunks.effective_year` column |
| Search legal vault | Official portal link | Derived from `legal_documents.source_url` combined with `legal_chunks.juriconnect_ref` |
| Copilot tax explanation | Estimated tax bracket rate | Computed using ledger income against `legal_chunks` content for Box 1 thresholds |
| Copilot Box 3 assessment | Actual return comparison | Computed by comparing investment ledger performance against Box 3 deemed rates from legal vault |
| Copilot pension advice | Available jaarruimte deduction ceiling | Computed using user gross salary against 30 percent premium space rules in Wet toekomst pensioenen chunks |

**Key invariants**:
- Complete local execution: No user transaction, account balance, or law query text is ever transmitted outside the local machine.
- Read only copilot access: The copilot agent interacts with legal data strictly through read only SQLite connections and deterministic tools.
- Strict citation traceability: Every factual claim about tax rates, deduction rules, or legal deadlines generated by the copilot tool must include an associated chunk identifier and statutory article reference.
- Synchronization consistency: Reindexing is atomic within a single SQLite transaction, ensuring readers never observe partially populated vector tables.

**Security model**:
- Local privacy compliance: All financial ledgers and legal embeddings reside within `data/finance.db` in SQLite WAL mode.
- SQLite authorizer enforcement: Database connections used by the copilot block all `INSERT`, `UPDATE`, `DELETE`, and `DROP` commands, preventing accidental or adversarial modifications.
- Local model isolation: Ollama and FastEmbed run on localhost, requiring zero external API keys or cloud subscriptions.

**Configuration required**:
- `OLLAMA_EMBED_MODEL`: Preferred Ollama embedding model name (defaults to `all-minilm` for 384 dimensional vector alignment).
- `FASTEMBED_CACHE_DIR`: Cache directory for local FastEmbed ONNX weights (defaults to `.cache/fastembed` inside project tree).

**Critical test scenarios**:
- Happy path vector and keyword retrieval: Query for "hypotheekrenteaftrek eigen woning" returns article 3.120 and 3.120a WIB 2001 with high confidence, verifying **AC-1**, **AC-2**, and **AC-4**.
- Exact statutory code lookup: Direct query for "Art. 5.2" or "3.16" immediately returns the exact statutory chunk via FTS5 keyword matching even if vector distance is moderate, verifying **AC-4** and **AC-5**.
- Offline embedding resilience: When Ollama daemon is stopped or unreachable, the vault automatically initializes FastEmbed ONNX CPU embeddings and answers queries without error, verifying **AC-3** and **AC-7**.
- Copilot tool response format: `tool_search_dutch_law_vault` produces structured markdown with expandable citation details and statutory reference tags, verifying **AC-5** and **AC-6**.
- Extension load failure fallback: When the sqlite-vec native binary is intentionally disabled or unavailable, search falls back cleanly to FTS5 BM25 search without throwing exceptions, verifying **AC-7**.

## Migration plan

**Strategy**: Strangler pattern.

**Phases**:
1. Phase 1 (Coexistence): Create `services/legal_vault_service.py` alongside the existing `services/rag_service.py`. Implement database tables, sqlite-vec virtual table initialization, and document parsing for the curated legal corpus.
2. Phase 2 (Validation): Run automated test suites comparing retrieval quality between legacy in memory search and the new hybrid vector vault. Verify all acceptance criteria pass.
3. Phase 3 (Cutover): Update `agent/tools.py` and `ui/pages/tax.py` to route all queries through `services/legal_vault_service.py`. Deprecate legacy functions in `services/rag_service.py`.
4. Phase 4 (Cleanup): Remove legacy fallback tables and pseudo vector logic once verification succeeds.

**Rollback**:
If sqlite-vec encounters unforeseen platform incompatibilities on a target machine, a configuration toggle instantly reverts tool dispatch in `agent/tools.py` to `services/rag_service.py` without requiring database schema reverts.

**Risks**:
- SQLite binary compatibility on Windows: Mitigated by using the precompiled `sqlite-vec` wheel distribution from PyPI via `sqlite_vec.load(conn)` and providing a transparent pure Python fallback for vector distance.
- Initial embedding generation time: Parsing and embedding several hundred statutory articles may take fifteen to thirty seconds on CPU during initial setup; mitigated by persisting embeddings permanently in SQLite WAL and executing ingestion in background or during setup.

## Build plan
- [x] 1. Add `sqlite-vec` and `fastembed` dependencies to `requirements.txt` and project environment, satisfies **AC-2**, **AC-3**.
- [x] 2. Create `services/legal_vault_service.py` with SQLite schema migration for `legal_documents`, `legal_chunks`, `legal_vec`, and `legal_fts`, loaded via `sqlite_vec.load(conn)`, satisfies **AC-1**, **AC-2**, **AC-4**.
- [x] 3. Implement dual embedding provider supporting 384 dimensional embeddings from local Ollama (`all-minilm`) with automatic FastEmbed ONNX CPU fallback (`sentence-transformers/all-MiniLM-L6-v2`), satisfies **AC-3**, **AC-7**.
- [x] 4. Ingest and curate the Dutch financial legal knowledge corpus across the six core life domains with verified metadata and statutory articles in `data/knowledge/`, satisfies **AC-1**.
- [x] 5. Implement hybrid search algorithm with Reciprocal Rank Fusion (k=60) combining FTS5 BM25 and sqlite-vec cosine distance, satisfies **AC-4**, **AC-7**.
- [x] 6. Implement `tool_search_dutch_law_vault` and `tool_lookup_tax_law_article` in `agent/tools.py`, satisfies **AC-5**.
- [x] 7. Update copilot prompt in `agent/copilot.py` and chat response renderer in `ui/copilot_sidebar.py` to format legal citations into expandable cards with statutory references, satisfies **AC-6**.
- [x] 8. Update `ui/pages/tax.py` with an interactive Dutch Financial Law Vault tab featuring live category filtering, statutory search, and article inspection, satisfies **AC-1**, **AC-6**.
- [x] 9. Write unit and integration test suite in `tests/test_legal_vault_service.py` validating retrieval precision, offline resilience, and citation formatting, satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**, **AC-5**, **AC-7**.

## Consequences

**Positive**:
- Vastly superior copilot intelligence: The assistant can ground tax planning, mortgage decisions, and pension optimizations in actual Dutch legislation rather than generic guesses.
- Sub millisecond local search: Moving vector similarity search inside SQLite via sqlite-vec eliminates Python loop overhead and scales effortlessly to thousands of statutory articles.
- High reliability: FastEmbed fallback ensures vector search works out of the box even before a user configures or launches Ollama.
- Strong privacy: 100 percent local execution preserves user financial secrecy.

**Negative**:
- Adds `sqlite-vec` binary dependency and ONNX runtime library to the project environment.
- Increased database size: Embedding tables add approximately two to four megabytes of persistent vector storage in `data/finance.db`.

**Neutral**:
- Legal knowledge requires annual updates as Dutch tax brackets, pension caps, and mortgage rules evolve with each calendar year Belastingplan.

## Follow-up

- [ ] Automated annual statutory sync: Implement an optional script to fetch updated statutory texts from the KOOP Basis Wetten Bestand SRU service at the start of each tax year.
- [ ] Tax return form guidance: Ingest Belastingdienst annual income tax return explanatory booklets (Handboek Loonheffingen / Aangifte Inkomstenbelasting) to help users fill specific tax return fields.

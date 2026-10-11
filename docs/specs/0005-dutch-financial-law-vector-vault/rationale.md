# Rationale: Dutch Financial Law Vector Vault and Copilot Knowledge Engine

This document records the decision context, options evaluated, architectural rationale, and verified reference citations for the Dutch Financial Law Vector Vault.

## Context

The personal finance assistant includes an AI copilot whose goal is providing sound analysis and guidance across personal finance decisions. In the Netherlands, personal finance is tightly bound to statutory codes:
1. Income taxation (Box 1 of the Wet inkomstenbelasting 2001) with mortgage interest deductions (hypotheekrenteaftrek), eigenwoningforfait, and thirty percent ruling rules.
2. Wealth taxation (Box 3) which has undergone unprecedented legal upheaval following Supreme Court (Hoge Raad) rulings requiring taxation of actual investment yields rather than fictitious deemed rates when actual yield is lower.
3. Pension accumulation following the historic pension reform (Wet toekomst pensioenen) which increased annual tax deductible annuity room (jaarruimte) to thirty percent of the contribution base.
4. Mortgage lending norms and energy efficiency borrowing buffers regulated under the Wet op het financieel toezicht (Wft) and annual Nibud standards.
5. Wealth transfer and gift exemptions under the Successiewet 1956, including the abolition of the home purchase gift exemption (jubelton).

The current implementation in the repository consists of six small hand written markdown files totaling fewer than fifty lines, indexed via a naive in memory cosine distance loop over a 128 token bag of words fallback or an unindexed JSON text column in SQLite. This setup fails in multiple ways:
- The knowledge coverage is far too shallow to answer real user questions about tax deduction eligibility, exact limits, carry forward rules, or Box 3 actual return calculations.
- Retrieval lacks exact statutory keyword precision, failing to locate specific articles when users or copilot ask for article numbers like 3.16 or 5.2.
- Vector search performs full table scans in Python, which does not scale beyond a few dozen paragraphs.
- If Ollama is offline or embedding models are not pulled, retrieval collapses to a toy bag of words heuristic.

To achieve our overarching goal of an AI copilot that delivers excellent, legally sound financial intelligence while preserving strict local privacy, we require a true vector database, a comprehensive statutory taxonomy, and robust hybrid search.

## Options considered

### Option 1: SQLite Vector Extension (sqlite-vec) with FTS5 Hybrid Retrieval (Chosen)

Embed vector indexing directly into our primary SQLite database using `sqlite-vec`, an official native SQLite extension written in C. It adds vector virtual tables (`vec0`) supporting SIMD accelerated KNN vector search. We pair it with SQLite FTS5 for full text BM25 keyword matching and use Reciprocal Rank Fusion to blend lexical and semantic scores. Text embeddings are generated locally via Ollama with an automatic in process FastEmbed ONNX CPU fallback.

**Pros**:
- Zero additional servers or background daemons needed; runs directly inside `data/finance.db` in SQLite WAL mode.
- Enables true relational joins between user financial records and statutory knowledge chunks in a single SQL query.
- High performance SIMD vector indexing executing in sub millisecond time.
- Preserves the project rule that all financial and operational data lives in local SQLite files.
- Dual embedding pipeline guarantees functionality even when Ollama is unavailable.

**Cons**:
- Requires loading a compiled C extension (`sqlite-vec`), which requires careful testing across Windows runtime environments.

### Option 2: Dedicated Local ChromaDB or Qdrant Embedded Directory

Deploy a standalone embedded vector database such as ChromaDB or Qdrant Client running in local disk mode, persisting vectors to a dedicated `data/vector_store/` folder.

**Pros**:
- High level Python API with built in collection management, metadata filtering, and chunking utilities.
- Popular in the open source AI ecosystem with broad tutorial support.

**Cons**:
- Introduces another database engine alongside SQLite, creating data synchronization overhead.
- Cannot perform native SQL joins between user transaction tables and vector search results.
- ChromaDB and Qdrant bring substantial dependency trees and occasional file lock contention on Windows systems.
- Violates the simplicity principle of keeping application state unified in SQLite.

### Option 3: Incremental Enhancement of Existing In Memory Cosine Loop

Retain the existing architecture in `services/rag_service.py`, expanding the number of markdown files in `data/knowledge/` while keeping vectors stored as JSON text arrays in a standard SQLite table and computing cosine distance in Python.

**Pros**:
- Requires no new binary dependencies or native extensions.
- Minimal code changes to existing services.

**Cons**:
- Poor retrieval performance: scanning hundreds or thousands of legal chunks requires loading and parsing large JSON strings in Python on every query.
- Lacks proper vector indexing (no HNSW or IVFFlat index structures).
- Does not solve the lack of keyword indexing for exact legal article references.
- Leaves the legal vault feeling brittle and amateurish.

## Rationale

We selected Option 1 because it delivers true vector database performance while respecting the existing architectural principles of the personal finance assistant.

The personal finance assistant is explicitly designed around local first privacy with SQLite WAL as its single source of truth. Adding ChromaDB or Qdrant would split application persistence into two separate storage systems, complicating backups, migrations, and transactional consistency.

By adopting `sqlite-vec`, vector indexes live directly inside our SQLite database as virtual tables. Queries can filter chunks by legal category, effective year, and statutory article using standard SQL where clauses, then rank results by cosine distance in a single compiled C call. Pairing `sqlite-vec` with SQLite FTS5 gives us hybrid search: FTS5 handles exact legal terms and article numbers with BM25 precision, while `sqlite-vec` captures high level semantic meaning.

Furthermore, implementing a dual embedding engine (Ollama with FastEmbed ONNX fallback) resolves the reliability weakness of the previous implementation. If the user does not have Ollama running, the copilot continues functioning seamlessly using lightweight local CPU embeddings.

## References

### Project Sources and Conventions
- Repository architecture rule: Local first privacy, storage in `data/finance.db`, connection handling via `db.database.connect()` in SQLite WAL mode.
- Existing RAG service: [services/rag_service.py](file:///c:/Users/ayush/Documents/Repos/personal-finance-assistant/services/rag_service.py).
- Copilot tool registry: [agent/tools.py](file:///c:/Users/ayush/Documents/Repos/personal-finance-assistant/agent/tools.py).
- Copilot system prompt: [agent/copilot.py](file:///c:/Users/ayush/Documents/Repos/personal-finance-assistant/agent/copilot.py).

### Official Dutch Legal Sources and Verified Portals
- KOOP Basis Wetten Bestand (BWB): National consolidated legislation repository managed by Kennis en Exploitatiecentrum voor Officiële Overheidspublicaties: [https://data.overheid.nl/dataset/basis-wetten-bestand](https://data.overheid.nl/dataset/basis-wetten-bestand)
- Wet inkomstenbelasting 2001 (WIB 2001): Primary Dutch personal income, home ownership, and wealth tax statute: [https://wetten.overheid.nl/BWBR0011353](https://wetten.overheid.nl/BWBR0011353)
- Wet toekomst pensioenen (Wtp) and Pensioenwet: Legal framework governing personal pension contributions and annual deduction space (jaarruimte): [https://wetten.overheid.nl/BWBR0020809](https://wetten.overheid.nl/BWBR0020809)
- Successiewet 1956: Statutory rules for gift tax exemptions and inheritance tax brackets: [https://wetten.overheid.nl/BWBR0002226](https://wetten.overheid.nl/BWBR0002226)
- Wet op het financieel toezicht (Wft) and Tijdelijke regeling hypothecair krediet: Legal limits on mortgage borrowing, loan to value ratios, and Nibud financing standards: [https://wetten.overheid.nl/BWBR0020368](https://wetten.overheid.nl/BWBR0020368)
- Hoge Raad der Nederlanden Box 3 Judgments (June 2024 and Kerstarrest): Court jurisprudence mandating taxation on actual yields (werkelijk rendement) over deemed returns: [https://www.rechtspraak.nl](https://www.rechtspraak.nl)
- Belastingdienst Official Guidance: Circulars and forms for actual return declarations (Opgaaf werkelijk rendement) and annual tax tables: [https://www.belastingdienst.nl](https://www.belastingdienst.nl)

### Technical Libraries
- `sqlite-vec`: Native vector search extension for SQLite: [https://github.com/asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- `fastembed`: Fast, lightweight CPU based text embedding generation via ONNX runtime: [https://github.com/qdrant/fastembed](https://github.com/qdrant/fastembed)

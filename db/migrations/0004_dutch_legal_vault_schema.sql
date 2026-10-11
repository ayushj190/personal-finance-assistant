-- 0004_dutch_legal_vault_schema.sql
-- Dutch Financial Law Vector Vault tables, FTS5 index, and sync triggers

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

CREATE TABLE IF NOT EXISTS legal_vec_fallback (
    chunk_id        INTEGER PRIMARY KEY REFERENCES legal_chunks(id) ON DELETE CASCADE,
    embedding_blob  BLOB NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS legal_fts USING fts5(
    article_ref,
    chunk_title,
    content,
    category UNINDEXED,
    content='legal_chunks',
    content_rowid='id'
);

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

CREATE TRIGGER IF NOT EXISTS trg_legal_chunks_ai AFTER INSERT ON legal_chunks BEGIN
    INSERT INTO legal_fts(rowid, article_ref, chunk_title, content, category)
    VALUES (new.id, new.article_ref, new.chunk_title, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS trg_legal_chunks_ad AFTER DELETE ON legal_chunks BEGIN
    INSERT INTO legal_fts(legal_fts, rowid, article_ref, chunk_title, content, category)
    VALUES('delete', old.id, old.article_ref, old.chunk_title, old.content, old.category);
END;

CREATE TRIGGER IF NOT EXISTS trg_legal_chunks_au AFTER UPDATE ON legal_chunks BEGIN
    INSERT INTO legal_fts(legal_fts, rowid, article_ref, chunk_title, content, category)
    VALUES('delete', old.id, old.article_ref, old.chunk_title, old.content, old.category);
    INSERT INTO legal_fts(rowid, article_ref, chunk_title, content, category)
    VALUES (new.id, new.article_ref, new.chunk_title, new.content, new.category);
END;

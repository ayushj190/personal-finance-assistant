# 0013. Rationale: Multi Bank Manual Accounts and Hybrid Statement Ingestion

## Context

Many users hold bank accounts across various countries (including Türkiye İş Bankası) that do not support European open banking APIs or standard European CAMT.053 XML exports. Previously, the system assumed hardcoded mappings for a few European banks (such as ABN AMRO and Revolut) and lacked a clean interface for users to manually register accounts or track balances.

Furthermore, bank export statements from international institutions often come as PDF documents formatted with tables in different languages (such as Turkish or English). Ingesting these files required Either hardcoded parsers or manual transcription.

Users need a reliable, privacy respecting workflow to register custom accounts and ingest statement files smoothly.

## Options considered

### Option 1: Reusable account dialog, deterministic pypdf parser with local Ollama fallback, and interactive target confirmation (Chosen)

We add a reusable modal dialog to create or edit manual bank accounts with customized institutions, currencies, and starting balances. The statement ingestion pipeline uses `pypdf` to extract text and tables deterministically for known institutions like Türkiye İş Bankası (handling both Turkish and English column headers). If the format is unknown or unconventional, the pipeline falls back to local Ollama via `generate_json`. Users confirm or pick the target account and ending balance before saving.

**Pros**:
- Instant and accurate parsing for known PDF bank statement layouts.
- Graceful local recovery via Ollama when statement layouts differ, keeping all data private.
- Clear user control over which account receives imported transactions.
- Zero forced currency distortion: native currency amounts remain untouched.

**Cons**:
- Local LLM fallback adds a few seconds of processing time if a statement layout is completely unrecognized.

### Option 2: Pure LLM parsing for all PDF statements without deterministic rules

Send all uploaded PDF text directly to local Ollama for JSON extraction without building regex or table based parsers.

**Pros**:
- Single code path for all file formats.

**Cons**:
- Slower import times for standard bank statements that could be parsed instantly.
- Potential LLM hallucinations on large multi page statements or complex transaction descriptions.
- Higher GPU or CPU load on the user machine during imports.

## Rationale

Option 1 provides the speed, accuracy, and reliability of deterministic parsing while keeping the flexible intelligence of local LLMs as a fallback safety net. Türkiye İş Bankası PDF statements follow structured tabular layouts that pypdf can extract in milliseconds. Having explicit format detection ensures that known statements parse with 100% precision and zero token overhead.

Allowing the user to select or confirm the target account before importing prevents data pollution and duplicate account creation.

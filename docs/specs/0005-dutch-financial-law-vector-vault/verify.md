# Verify: Dutch Financial Law Vector Vault · spec 0005 · updated 2026-10-11
_Steps derived from spec 0005 acceptance criteria and value sourcing. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual
- [ ] Open Tax Analysis page (`/tax`) → scroll to "Dutch Financial Law Vector Vault" → expect category dropdown with 6 domains and search bar → AC-1, AC-6
- [ ] In Tax page search input, enter "werkelijk rendement Hoge Raad" → expect ECLI:NL:HR:2024:704 ruling card with score badge and expandable statutory text → AC-4, AC-6
- [ ] In Tax page search input, enter exact article code "Art. 3.16" → expect Art. 3.16 WIB 2001 (Aftrekbeperking gemengde kosten) ranked first → AC-4, AC-6
- [ ] In Tax page, select domain filter "Pensions & Jaarruimte" with empty query → expect Wet toekomst pensioenen statutes and articles listed with digests → AC-1, AC-6
- [ ] Open Copilot sidebar → send prompt "Wat zijn de regels voor hypotheekrenteaftrek en eigenwoningforfait?" → expect assistant response with expandable citation card citing Art. 3.112 and Art. 3.120 → AC-5, AC-6
- [ ] Open Copilot sidebar → send prompt "Kan ik belasting besparen via werkelijk rendement in box 3?" → expect citation of Supreme Court 6 June 2024 ruling → AC-5, AC-6

## Commands
- [ ] `.\.venv\Scripts\python -m unittest tests/test_legal_vault_service.py` → all 8 unit tests pass in single-digit seconds → AC-1, AC-2, AC-3, AC-4, AC-5, AC-7
- [ ] `.\.venv\Scripts\python -c "from services.legal_vault_service import search_legal_vault; res = search_legal_vault('hypotheekrenteaftrek'); assert len(res) > 0"` → returns non-empty structured citations → AC-2, AC-4
- [ ] `.\.venv\Scripts\python -c "from services.legal_vault_service import lookup_article; res = lookup_article('Art. 5.2'); assert res.category == 'tax_box3'"` → exact article lookup resolves in <10ms → AC-4, AC-5
- [ ] `.\.venv\Scripts\pytest -q tests/test_legal_vault_service.py tests/test_copilot_tools.py tests/test_copilot_sidebar.py` → all tests pass → AC-5, AC-6

## Value sourcing verification
- [ ] Search legal vault → calculate RRF score `(0.5 / (60 + fts_rank)) + (0.5 / (60 + vec_rank))` normalized to [0.0, 1.0] → Value Sourcing Row 1
- [ ] Search legal vault → inspect `article_ref` column in `legal_chunks` table for WIB 2001, Wft, Successiewet → Value Sourcing Row 2
- [ ] Search legal vault → inspect `effective_year` column (2026) → Value Sourcing Row 3
- [ ] Search legal vault → inspect source URL derived from `legal_documents.source_url` and `juriconnect_ref` → Value Sourcing Row 4
- [ ] Copilot Box 1 threshold check → verify bracket rates (36.97% / 49.50%) against `legal_chunks.content` → Value Sourcing Row 5
- [ ] Copilot Box 3 deemed rates → verify 1.03% bank savings and 6.04% other investments against Art. 5.2 → Value Sourcing Row 6
- [ ] Copilot Jaarruimte ceiling → verify 30% premium space under Wtp reform against Art. 3.127 → Value Sourcing Row 7

## Acceptance-criteria coverage
- AC-1: Curated Dutch financial legal corpus across six life domains covered by UI manual steps 1, 4, command step 1, value sourcing steps 2, 5, 6, 7.
- AC-2: Vector indexing with sqlite-vec extension and 384 dimensions covered by command steps 1, 2.
- AC-3: Dual embedding provider with FastEmbed ONNX CPU fallback covered by command step 1.
- AC-4: Hybrid search with Reciprocal Rank Fusion covered by UI manual steps 2, 3, command steps 2, 3, value sourcing step 1.
- AC-5: Copilot tools `tool_search_dutch_law_vault` and `tool_lookup_tax_law_article` covered by UI manual steps 5, 6, command steps 3, 4.
- AC-6: Expandable citation cards in Copilot chat and Tax UI covered by UI manual steps 1, 2, 5, 6.
- AC-7: Resilience fallback when sqlite-vec is absent covered by command step 1 (`test_ac7_graceful_fallback_when_sqlite_vec_disabled`).

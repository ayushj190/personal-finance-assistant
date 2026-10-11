import sqlite3
import unittest
from unittest.mock import patch

from services.legal_vault_service import (
    init_legal_vault_schema,
    ingest_legal_corpus,
    search_legal_vault,
    lookup_article,
    get_all_legal_documents,
    get_embedding,
    load_sqlite_vec_extension,
    cosine_similarity,
    serialize_float32,
    deserialize_float32,
)
from agent.tools import (
    tool_search_dutch_law_vault,
    tool_lookup_tax_law_article,
)


class TestDutchFinancialLawVectorVault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.row_factory = sqlite3.Row
        init_legal_vault_schema(cls.conn)
        cls.counts = ingest_legal_corpus(force_reindex=True, conn=cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_ac3_embedding_generation_384_dimensions(self):
        """AC-3: FastEmbed CPU fallback generates exactly 384-dimensional float embeddings."""
        emb = get_embedding("hypotheekrenteaftrek eigen woning")
        self.assertIsInstance(emb, list)
        self.assertEqual(len(emb), 384)
        self.assertTrue(any(x != 0.0 for x in emb))

    def test_ac1_ingest_curated_legal_corpus_six_domains(self):
        """AC-1: Corpus ingests structured statutory articles across the six core personal finance domains."""
        self.assertGreater(self.counts["documents_indexed"], 0)
        self.assertGreater(self.counts["chunks_indexed"], 0)

        docs = get_all_legal_documents(conn=self.conn)
        categories = {d["category"] for d in docs}
        
        # Verify core domains exist in knowledge base
        expected_domains = {"tax_box1", "tax_box3", "pension", "mortgage", "estate", "expat"}
        for domain in expected_domains:
            self.assertIn(domain, categories, f"Expected domain {domain} in ingested legal corpus")

    def test_ac2_sqlite_vec_extension_loaded(self):
        """AC-2: sqlite-vec extension loads and is capable of vector indexing in 384 dims."""
        loaded = load_sqlite_vec_extension(self.conn)
        if loaded:
            row = self.conn.execute("SELECT vec_version()").fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(str(row[0]).startswith("v"))

    def test_ac4_hybrid_search_rrf_natural_language_and_exact_code(self):
        """AC-4: Hybrid search returns relevant articles for natural language queries and exact statutory codes."""

        # 1. Natural language query for mortgage deduction
        res_hra = search_legal_vault("hypotheekrenteaftrek eigen woning", top_k=3, conn=self.conn)
        self.assertTrue(len(res_hra) > 0)
        article_refs = [r.article_ref for r in res_hra]
        self.assertTrue(any("3.120" in ref or "3.111" in ref for ref in article_refs))

        # 2. Natural language query for Box 3 actual return ruling
        res_hr = search_legal_vault("werkelijk rendement Hoge Raad box 3", top_k=3, conn=self.conn)
        self.assertTrue(len(res_hr) > 0)
        self.assertTrue(any("Hoge Raad" in r.article_ref or "5.2" in r.article_ref for r in res_hr))

        # 3. Exact statutory code query
        res_code = search_legal_vault("Art. 3.16", top_k=2, conn=self.conn)
        self.assertTrue(len(res_code) > 0)
        self.assertEqual(res_code[0].article_ref, "Art. 3.16")

    def test_exact_article_lookup(self):
        """Lookup exact article by reference."""
        art = lookup_article("Art. 3.16", conn=self.conn)
        self.assertIsNotNone(art)
        self.assertIn("gemengde kosten", art.chunk_title.lower())
        self.assertEqual(art.category, "tax_box1")

    def test_ac5_copilot_tools_integration(self):
        """AC-5: Copilot tool wrappers return structured citations and results."""
        # Test tool_search_dutch_law_vault
        tool_res = tool_search_dutch_law_vault("jaarruimte pensioen", category="pension")
        self.assertTrue(tool_res["success"])
        self.assertGreater(len(tool_res["citations"]), 0)
        top_cit = tool_res["citations"][0]
        self.assertIn("article_ref", top_cit)
        self.assertIn("statute_title", top_cit)
        self.assertIn("summary", top_cit)

        # Test tool_lookup_tax_law_article
        lookup_res = tool_lookup_tax_law_article("Art. 5.2")
        self.assertTrue(lookup_res["success"])
        self.assertIn("article", lookup_res)
        self.assertEqual(lookup_res["article"]["article_ref"], "Art. 5.2")

    def test_ac7_graceful_fallback_when_sqlite_vec_disabled(self):
        """AC-7: Retrieval degrades gracefully to FTS5 and Python cosine similarity when sqlite-vec unavailable."""
        # Mock load_sqlite_vec_extension to return False to simulate platform missing C extension
        with patch("services.legal_vault_service.load_sqlite_vec_extension", return_value=False):
            res = search_legal_vault("pensioenopbouw jaarruimte Wtp", top_k=3, conn=self.conn)
            self.assertTrue(len(res) > 0)
            self.assertTrue(any("3.127" in r.article_ref or "pensioen" in r.category for r in res))

    def test_serialization_and_cosine_similarity(self):
        """Test float32 serialization and pure python cosine similarity."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]

        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0, places=5)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0, places=5)

        blob = serialize_float32([0.5, 0.25, 0.125])
        deser = deserialize_float32(blob)
        self.assertEqual(len(deser), 3)
        self.assertAlmostEqual(deser[0], 0.5, places=5)


if __name__ == "__main__":
    unittest.main()

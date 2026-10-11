import unittest
from services.rag_service import (
    load_raw_documents,
    split_document_into_chunks,
    search_knowledge_base,
    get_all_knowledge_documents,
    ingest_user_document,
)


class TestRagService(unittest.TestCase):
    def test_load_and_chunk_documents(self):
        docs = load_raw_documents()
        self.assertGreaterEqual(len(docs), 5)
        titles = [d["title"].lower() for d in docs]
        self.assertTrue(any("box 1" in t or "box1" in t for t in titles))
        self.assertTrue(any("box 3" in t or "box3" in t for t in titles))
        self.assertTrue(any("green" in t or "groen" in t for t in titles))
        self.assertTrue(any("pension" in t or "jaarruimte" in t for t in titles))

        # Check chunking
        chunks = split_document_into_chunks(docs[0])
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("content", chunks[0])

    def test_search_knowledge_base(self):
        # Search Box 3 rules
        res_box3 = search_knowledge_base("fictief rendement Box 3 savings investments", top_k=3)
        self.assertGreaterEqual(len(res_box3), 1)
        self.assertTrue(any("box" in r["title"].lower() or "box" in r["content"].lower() for r in res_box3))

        # Search Groenfondsen green funds
        res_green = search_knowledge_base("Groenfondsen certified green investments exemption", top_k=3)
        self.assertGreaterEqual(len(res_green), 1)
        self.assertTrue(any("groen" in r["content"].lower() or "green" in r["content"].lower() for r in res_green))

        # Search Pension Jaarruimte
        res_pension = search_knowledge_base("Jaarruimte Pillar 3 Lijfrente Factor A", top_k=3)
        self.assertGreaterEqual(len(res_pension), 1)
        self.assertTrue(any("jaarruimte" in r["content"].lower() or "pension" in r["content"].lower() for r in res_pension))

    def test_get_all_knowledge_documents(self):
        all_docs = get_all_knowledge_documents()
        self.assertGreaterEqual(len(all_docs), 5)
        for doc in all_docs:
            self.assertIn("title", doc)
            self.assertIn("category", doc)
            self.assertGreater(doc["word_count"], 5)

    def test_custom_document_ingestion(self):
        test_title = "Test UPO Pension Advice 2026"
        test_content = "This is a custom test uniform pensioenoverzicht noting Factor A of 1200 euros."
        ingest_res = ingest_user_document(test_title, test_content, category="pension")
        self.assertTrue(ingest_res["success"])

        # Search for custom ingested document
        found = search_knowledge_base("Test UPO Pension Advice 2026", top_k=2)
        self.assertGreaterEqual(len(found), 1)

        # Cleanup test file
        from services.rag_service import KNOWLEDGE_DIR
        test_file = KNOWLEDGE_DIR / "user_test_upo_pension_advice_2026.md"
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    unittest.main()

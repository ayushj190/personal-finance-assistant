from datetime import date
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from connectors.base import RawTransaction
from connectors.file_import.detect import (
    FileFormat,
    detect_statement_account_hint,
    parse_statement,
    parse_statement_balance,
)
from connectors.file_import.isbank_pdf import parse_isbank_pdf
from db.database import create_manual_account, upsert_account
from db.migrations.runner import run_migrations
from services.sync_service import process_and_save_transactions


class TestManualAccountsHybridImport(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_create_manual_account_with_initial_balance(self):
        """AC-1, AC-2: Creates manual account and writes initial balance snapshot in minor units."""
        acc_dict = {
            "name": "İşbank Vadesiz TRY",
            "institution": "Türkiye İş Bankası",
            "currency": "TRY",
            "asset_class": "cash",
            "apy": 0.0,
            "iban": "TR120006400000112345678901",
        }
        initial_balance_minor = 125050  # 1,250.50 TRY

        acc_id = create_manual_account(self.conn, acc_dict, initial_balance_minor=initial_balance_minor)
        self.assertGreater(acc_id, 0)

        # Verify account record
        row = self.conn.execute("SELECT * FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "İşbank Vadesiz TRY")
        self.assertEqual(row["institution"], "Türkiye İş Bankası")
        self.assertEqual(row["currency"], "TRY")

        # Verify initial snapshot
        snap = self.conn.execute("SELECT * FROM account_snapshots WHERE account_id = ?", (acc_id,)).fetchone()
        self.assertIsNotNone(snap)
        self.assertEqual(snap["balance_minor"], 125050)
        self.assertEqual(snap["balance_eur_minor"], 125050)

    @patch("connectors.file_import.isbank_pdf.pypdf.PdfReader")
    def test_parse_isbank_pdf_turkish_headers(self, mock_reader_cls):
        """AC-3, AC-7: Deterministically extracts Turkish İş Bankası transactions, ending balance, and IBAN."""
        sample_turkish_text = """
        TÜRKİYE İŞ BANKASI A.Ş.
        HESAP ÖZETİ
        Müşteri Adı: AHMET YILMAZ
        IBAN: TR33 0006 4000 0011 2345 6789 01
        Para Birimi: TL
        Dönem: 01/03/2026 - 31/03/2026
        Kapanış Bakiyesi: 24.750,50 TL

        Tarih Açıklama Tutar Bakiye
        05.03.2026 MAAS YATIRILDI 45.000,00 45.000,00
        12.03.2026 FAST EFT - KIRALIK EV -15.000,00 30.000,00
        18.03.2026 MARKET HARCAMASI (B) 5.249,50 24.750,50
        """
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_turkish_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        fake_pdf = b"%PDF-1.4 fake pdf content"
        txs, ending_bal, iban = parse_isbank_pdf(fake_pdf)

        self.assertEqual(iban, "TR330006400000112345678901")
        self.assertEqual(ending_bal, 2475050)  # 24,750.50 -> 2475050 minor
        self.assertEqual(len(txs), 3)

        # Check transactions
        t1, t2, t3 = txs
        self.assertEqual(t1.booking_date, date(2026, 3, 5))
        self.assertEqual(t1.amount_minor, 4500000)
        self.assertEqual(t1.currency, "TRY")

        self.assertEqual(t2.booking_date, date(2026, 3, 12))
        self.assertEqual(t2.amount_minor, -1500000)

        self.assertEqual(t3.booking_date, date(2026, 3, 18))
        self.assertEqual(t3.amount_minor, -524950)

    @patch("connectors.file_import.isbank_pdf.pypdf.PdfReader")
    def test_parse_isbank_pdf_english_headers(self, mock_reader_cls):
        """AC-3: Deterministically extracts English İşbank statements."""
        sample_english_text = """
        TURKIYE IS BANKASI
        ACCOUNT STATEMENT
        Account No: 1234-567890
        Currency: TRY
        Closing Balance: 12,300.00

        Date Description Amount Balance
        10/04/2026 RESTAURANT EXPENSE -250.00 12,300.00
        02/04/2026 SALARY TRANSFER 12,550.00 12,550.00
        """
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_english_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        fake_pdf = b"%PDF-1.4 fake pdf content"
        txs, ending_bal, iban = parse_isbank_pdf(fake_pdf)

        self.assertEqual(iban, "1234-567890")
        self.assertEqual(ending_bal, 1230000)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount_minor, -25000)
        self.assertEqual(txs[1].amount_minor, 1255000)

    @patch("connectors.file_import.detect.parse_isbank_pdf")
    @patch("connectors.file_import.detect.parse_statement_with_llm")
    @patch("connectors.file_import.detect.pypdf.PdfReader")
    def test_pdf_llm_fallback_when_unrecognized(self, mock_pdf_reader, mock_llm_parse, mock_isbank):
        """AC-4: Falls back to local Ollama LLM extraction when PDF format is unknown."""
        mock_isbank.return_value = ([], None, None)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Random unfamiliar bank statement text"
        mock_pdf_reader.return_value.pages = [mock_page]

        expected_tx = RawTransaction(
            account_external_id="imported_acc",
            booking_date=date(2026, 7, 1),
            amount_minor=-5000,
            currency="EUR",
            description="Coffee Shop",
        )
        mock_llm_parse.return_value = [expected_tx]

        fake_pdf = b"%PDF-1.4 unrecognized"
        fmt, txs = parse_statement(fake_pdf, default_account_id="imported_acc")

        self.assertEqual(fmt, FileFormat.UNKNOWN)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].description, "Coffee Shop")
        mock_llm_parse.assert_called_once()

    def test_non_eur_native_currency_preservation(self):
        """AC-6: Preserves native minor units without forced FX conversion for non-EUR accounts."""
        acc_id = create_manual_account(
            self.conn,
            {"name": "İşbank TRY", "institution": "İşbank", "currency": "TRY", "asset_class": "cash"},
        )
        raw_txs = [
            RawTransaction(
                account_external_id="manual_acc",
                booking_date=date(2026, 8, 1),
                amount_minor=-150000,  # -1,500.00 TRY
                currency="TRY",
                description="Kira",
            )
        ]

        inserted, skipped = process_and_save_transactions(self.conn, acc_id, raw_txs)
        self.assertEqual(inserted, 1)

        row = self.conn.execute("SELECT * FROM transactions WHERE account_id = ?", (acc_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["currency"], "TRY")
        self.assertEqual(row["amount_minor"], -150000)
        self.assertEqual(row["amount_eur_minor"], -150000)  # Preserved 1:1 without FX conversion


if __name__ == "__main__":
    unittest.main()

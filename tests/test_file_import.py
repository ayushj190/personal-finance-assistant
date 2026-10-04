from datetime import date
from pathlib import Path
import unittest

from connectors.file_import.detect import FileFormat, detect_format, parse_statement


class TestFileImport(unittest.TestCase):
    def test_etoro_money_tsv_fixture(self):
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "etoro_money_sample.tsv"
        content = fixture_path.read_text(encoding="utf-8")

        fmt, txs = parse_statement(content)
        self.assertEqual(fmt, FileFormat.ETORO_MONEY_TSV)
        self.assertEqual(len(txs), 4)

        # First row: Dekamarkt € -7.49
        self.assertEqual(txs[0].amount_minor, -749)
        self.assertEqual(txs[0].currency, "EUR")
        self.assertEqual(txs[0].booking_date, date(2026, 10, 3))

        # Foreign spend: Coffee Shop with exchange rate and local amount
        self.assertEqual(txs[3].amount_minor, -350)
        self.assertIn("GBP", txs[3].description)

    def test_revolut_csv_format(self):
        csv_sample = """Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance
CARD_PAYMENT,Current,2026-03-01 12:00:00,2026-03-01 12:05:00,Albert Heijn,-24.50,0.00,EUR,COMPLETED,100.00
TOPUP,Current,2026-03-02 09:00:00,2026-03-02 09:00:00,Top-Up from ABN,500.00,0.00,EUR,COMPLETED,600.00
"""
        fmt, txs = parse_statement(csv_sample)
        self.assertEqual(fmt, FileFormat.REVOLUT_CSV)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount_minor, -2450)
        self.assertEqual(txs[1].amount_minor, 50000)

    def test_abn_amro_tab_format(self):
        tab_sample = "NL91ABNA0417164300\tEUR\t20260301\t1000.00\t975.50\t20260301\t-24.50\tAlbert Heijn Amsterdam\n"
        fmt, txs = parse_statement(tab_sample)
        self.assertEqual(fmt, FileFormat.ABN_AMRO_TAB)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].amount_minor, -2450)
        self.assertEqual(txs[0].booking_date, date(2026, 3, 1))

    def test_mt940_format(self):
        mt940_sample = """:20:START
:25:NL91ABNA0417164300
:28C:1
:60F:C260301EUR1000,00
:61:2603010301D50,00NTRFNONREF//12345
:86:Bakkerij De Boer
:62F:C260301EUR950,00
-"""
        fmt = detect_format(mt940_sample)
        self.assertEqual(fmt, FileFormat.MT940)


if __name__ == "__main__":
    unittest.main()

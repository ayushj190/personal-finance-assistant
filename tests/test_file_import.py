from datetime import date
from pathlib import Path
import unittest

from connectors.file_import.detect import FileFormat, detect_format, parse_statement


class TestFileImport(unittest.TestCase):
    def test_etoro_money_tsv_fixture(self):
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "etoro_money_sample.tsv"
        content = fixture_path.read_text(encoding="utf-8")

        fmt, txs = parse_statement(content, default_account_id="etoro_cash_eur")
        self.assertEqual(fmt, FileFormat.ETORO_MONEY_TSV)
        self.assertEqual(len(txs), 4)

        # First row: Dekamarkt € -7.49
        self.assertEqual(txs[0].amount_minor, -749)
        self.assertEqual(txs[0].currency, "EUR")
        self.assertEqual(txs[0].booking_date, date(2026, 10, 3))
        self.assertEqual(txs[0].account_external_id, "etoro_cash_eur")

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

    def test_etoro_statement_format(self):
        sample = """Account Activity
Date,Type,Details,Amount,Realized Equity Change,Realized Equity,Balance
01/10/2026 10:00:00,Deposit,Deposit via iDEAL,500.00,0.00,500.00,500.00

Open Positions
Position ID,Action,Amount,Units,Open Rate,Current Rate,Spread,Profit(USD),Open Date,Take Profit Rate,Stop Loss Rate,Rollover Fees and Dividends,Copied From,Type,ISIN,Notes
1234567,Buy Apple Inc.,150.00,1.0,150.00,175.00,0.0,25.00,01/09/2026 12:00:00,0.0,0.0,0.0,-,Stocks,US0378331005,-
"""
        from connectors.file_import.detect import parse_statement_holdings
        fmt, txs = parse_statement(sample)
        self.assertEqual(fmt, FileFormat.ETORO_STATEMENT_CSV)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].amount_minor, 50000)

        holdings = parse_statement_holdings(sample)
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].ticker, "Apple Inc.")
        self.assertEqual(holdings[0].quantity, 1.0)
        self.assertEqual(holdings[0].cost_basis_minor, 15000)

    def test_trade_republic_csv_format(self):
        sample = """Date;Type;Description;Amount
2026-03-01;Trade;Buy VWCE.DE;-500.00
2026-03-15;Interest;Monthly Interest;15.25
"""
        fmt, txs = parse_statement(sample)
        self.assertEqual(fmt, FileFormat.TRADE_REPUBLIC_CSV)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].amount_minor, -50000)
        self.assertEqual(txs[1].amount_minor, 1525)


    def test_trade_republic_pdf_parsing(self):
        from connectors.file_import.trade_republic_pdf import parse_trade_republic_pdf
        pdf_text = """TRADE REPUBLIC BANK GMBH
KONTOAUSZUG
01.03.2026 Kartenzahlung Supermarkt -24,50 EUR
15.03.2026 Zinsen 12,30 EUR
20.03.2026 Gutschrift Überweisung 1.000,00 EUR
"""
        txs, holdings, _ = parse_trade_republic_pdf(pdf_text)
        self.assertEqual(len(txs), 3)
        self.assertEqual(txs[0].amount_minor, -2450)
        self.assertEqual(txs[1].amount_minor, 1230)
        self.assertEqual(txs[2].amount_minor, 100000)

    def test_trade_republic_eindsaldo_balance(self):
        from connectors.file_import.trade_republic_pdf import parse_trade_republic_pdf
        pdf_text = """TRADE REPUBLIC BANK GMBH
REKENINGAFSCHRIFT
BEGINSALDO
€ 1.000,00
01.03.2026 Zinsen 52,33 EUR
EINDSALDO
€ 18.052,33
"""
        txs, holdings, balance = parse_trade_republic_pdf(pdf_text)
        self.assertEqual(balance, 1805233)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].amount_minor, 5233)


if __name__ == "__main__":
    unittest.main()

import unittest

from services.normalization import clean_merchant, detect_internal_transfer


class TestNormalization(unittest.TestCase):
    def test_clean_merchant_cases(self):
        cases = [
            ("SUMUP *KOFFIE AMSTERDAM NLD", "Koffie"),
            ("CCV*BAKKERIJ DE BOER", "Bakkerij De Boer"),
            ("DEKAMARKT LOC 691 ZAANDAM NL", "Dekamarkt"),
            ("aliexpress Luxembourg LU", "Aliexpress"),
            ("PAYPAL *NETFLIX 35314369001", "Netflix"),
            ("BEA, APPLE PAY ALBERT HEIJN 1234", "Albert Heijn"),
            ("BEA, GOOGLE PAY JUMBO SUPERMARKTEN", "Jumbo Supermarkten"),
            ("ZETTLE_*CAFE CENTRAL", "Cafe Central"),
            ("SQ *COFFEE ROASTERS LONDON GBR", "Coffee Roasters"),
            ("STRIPE *GITHUB INC SAN FRANCISCO USA", "Github Inc"),
            ("MOLLIE *BOL.COM BV UTRECHT NLD", "Bol.Com Bv"),
            ("STICHTING MOLLIE PAYMENTS COOLBLUE", "Coolblue"),
            ("ADYEN N.V. UBER TRIP AMSTERDAM", "Uber Trip"),
            ("BUCKAROO BASIC FIT HOOFDDORP NLD", "Basic Fit"),
            ("GEA, GELDMAAT AMSTERDAM", "Geldmaat"),
            ("ALBERT HEIJN 1421 AMSTERDAM NLD", "Albert Heijn"),
            ("DIRK VAN DEN BROEK 2026-03-01", "Dirk Van Den Broek"),
            ("SHELL STATION #4912 UTRECHT NL", "Shell Station"),
            ("BP EXPRESS 99182 PAS:192", "Bp Express"),
            ("TOTAL ENERGIES TERM:91823 NL", "Total Energies"),
            ("AMAZON EU SARL LUXEMBOURG LUX", "Amazon Eu Sarl"),
            ("SPOTIFY AB STOCKHOLM SWE", "Spotify Ab Stockholm Swe"),
            ("STEAM GAMES PURCHASE 991823", "Steam Games Purchase"),
            ("NS GROEP UTRECHT NLD", "Ns Groep"),
            ("TFL TRAVEL CH CHARGE LONDON GBR", "Tfl Travel Ch Charge"),
            ("HOTEL IBIS PARIS FRA", "Hotel Ibis"),
            ("ZALANDO PAYMENTS BERLIN DEU", "Zalando Payments"),
            ("IKEA NEDERLAND BV AMSTERDAM NL", "Ikea Nederland Bv"),
            ("RESTAURANT DE KAS AMSTERDAM", "Restaurant De Kas"),
            ("MEDIAMARKT 1029 ZAANDAM NL", "Mediamarkt"),
        ]

        for raw, expected in cases:
            cleaned = clean_merchant(raw)
            self.assertEqual(
                cleaned, expected, f"Failed for '{raw}': got '{cleaned}', expected '{expected}'")

    def test_detect_internal_transfer(self):
        own_ibans = {"NL91ABNA0417164300", "NL02REVO7291820000"}

        # Matched own IBAN
        self.assertTrue(detect_internal_transfer(
            "Overboeking", counterparty_iban="NL91ABNA0417164300", own_ibans=own_ibans))
        # Keyword matches
        self.assertTrue(detect_internal_transfer("eToro Trading Platform WDL"))
        self.assertTrue(detect_internal_transfer("Trade Republic Top-Up"))
        self.assertTrue(detect_internal_transfer("Top-Up Revolut"))
        self.assertTrue(detect_internal_transfer(
            "Overboeking naar spaarrekening"))

        # Ordinary merchant should NOT be transfer
        self.assertFalse(detect_internal_transfer("Albert Heijn Supermarket"))
        self.assertFalse(detect_internal_transfer("Shell Petrol Station"))


if __name__ == "__main__":
    unittest.main()

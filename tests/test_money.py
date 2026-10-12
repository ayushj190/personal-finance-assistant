from decimal import Decimal
import unittest
from unittest.mock import patch

from money import Money, sum_money
from ui.components import format_money


class TestMoney(unittest.TestCase):
    def setUp(self):
        from ui import state
        state.set(state.K.PRIVACY_HIDDEN, False)

    def test_from_cents(self):
        m = Money.from_cents(1234, "EUR")
        self.assertEqual(m.cents, 1234)
        self.assertEqual(m.currency, "EUR")
        self.assertEqual(m.to_major(), 12.34)

        # None cents defaults to 0
        m_none = Money.from_cents(None)
        self.assertEqual(m_none.cents, 0)
        self.assertEqual(m_none.currency, "EUR")

    def test_from_major(self):
        self.assertEqual(Money.from_major(12.34).cents, 1234)
        self.assertEqual(Money.from_major("12.34").cents, 1234)
        self.assertEqual(Money.from_major(Decimal("12.34")).cents, 1234)
        self.assertEqual(Money.from_major(12).cents, 1200)

        # Rounding HALF_UP
        self.assertEqual(Money.from_major(12.345).cents, 1235)
        self.assertEqual(Money.from_major(12.344).cents, 1234)
        self.assertEqual(Money.from_major(-12.345).cents, -1235)

    def test_arithmetic(self):
        m1 = Money(1000, "EUR")
        m2 = Money(500, "EUR")

        self.assertEqual((m1 + m2).cents, 1500)
        self.assertEqual((m1 - m2).cents, 500)
        self.assertEqual((-m1).cents, -1000)
        self.assertEqual(abs(Money(-1000, "EUR")).cents, 1000)

        # Currency mismatch in addition/subtraction
        m_usd = Money(500, "USD")
        with self.assertRaises(ValueError):
            _ = m1 + m_usd
        with self.assertRaises(ValueError):
            _ = m1 - m_usd

    def test_multiplication(self):
        m = Money(1000, "EUR")
        self.assertEqual((m * 2).cents, 2000)
        self.assertEqual((2 * m).cents, 2000)
        self.assertEqual((m * Decimal("1.5")).cents, 1500)
        self.assertEqual((m * 0.33333).cents, 333)

    def test_comparisons(self):
        m1 = Money(1000, "EUR")
        m2 = Money(2000, "EUR")
        m3 = Money(1000, "EUR")
        m_usd = Money(1000, "USD")

        self.assertTrue(m1 < m2)
        self.assertTrue(m1 <= m3)
        self.assertTrue(m2 > m1)
        self.assertTrue(m1 >= m3)
        self.assertEqual(m1, m3)
        self.assertNotEqual(m1, m_usd)

        with self.assertRaises(ValueError):
            _ = m1 < m_usd

    def test_sum_money(self):
        items = [Money(100, "EUR"), Money(250, "EUR"), Money(50, "EUR")]
        self.assertEqual(sum_money(items).cents, 400)
        self.assertEqual(sum_money([]).cents, 0)

        with self.assertRaises(ValueError):
            sum_money([Money(100, "EUR"), Money(100, "USD")])

    def test_format_money_with_money_object(self):
        m = Money(123456, "EUR")
        self.assertEqual(format_money(m), "€1,234.56")

        m_usd = Money(50000, "USD")
        self.assertEqual(format_money(m_usd), "$500.00")

        # Privacy hidden
        with patch("ui.components.is_hidden", return_value=True):
            self.assertEqual(format_money(m), "€****")
            self.assertEqual(format_money(m_usd), "$****")


if __name__ == "__main__":
    unittest.main()

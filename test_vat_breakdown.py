"""Tests for vat_breakdown().

    python3 -m unittest -v        # all tests in the directory
    python3 -m unittest test_vat_breakdown -v

Each test fails for exactly one reason, so the error message points at the cause:

    TestVatRateMath   pure math per VAT rate
    TestVatBreakdown  the whole result, following the example in the spec

All tests follow the function's own contract: prices are int/float and the rates
are 25, 12 and 6. No demands are made on other input types.
"""

import unittest
from decimal import Decimal

from kvitto import format_receipt, vat_breakdown

SPEC_ITEMS = [("Kaffe", 100, 25), ("Bröd", 50, 12), ("Bok", 200, 6)]


class TestVatRateMath(unittest.TestCase):
    """VAT for a single rate. Reads only that rate from the result, so a test
    does not depend on the other rates being right."""

    def vat_for(self, rate, price):
        result = vat_breakdown([("Start", 0, 25), ("Vara", price, rate)])
        self.assertIn(rate, result, f"ingen momsrad för {rate} %: fick {result}")
        return float(result[rate])

    def test_25_percent(self):
        """100 kr at 25 % VAT gives 25 kr."""
        self.assertAlmostEqual(self.vat_for(25, 100), 25.0, places=6)

    def test_12_percent(self):
        """50 kr at 12 % VAT gives 6 kr."""
        self.assertAlmostEqual(self.vat_for(12, 50), 6.0, places=6)

    def test_6_percent(self):
        """200 kr at 6 % VAT gives 12 kr."""
        self.assertAlmostEqual(self.vat_for(6, 200), 12.0, places=6)


class TestVatBreakdown(unittest.TestCase):
    """The whole result, compared with the example in the spec."""

    def assert_breakdown(self, actual, expected):
        self.assertEqual(
            sorted(actual),
            sorted(expected),
            f"fel momssatser: fick {sorted(actual)}, förväntade {sorted(expected)}",
        )
        for rate, amount in expected.items():
            self.assertAlmostEqual(
                float(actual[rate]), float(amount), places=6, msg=f"moms {rate} %"
            )

    def test_docstring_example(self):
        """The docstring says {25: 25.0, 12: 6.0} for Kaffe + Bröd."""
        self.assert_breakdown(
            vat_breakdown([("Kaffe", 100, 25), ("Bröd", 50, 12)]),
            {25: 25.0, 12: 6.0},
        )

    def test_all_three_vat_rates_from_the_spec(self):
        """All three rates must be present: 25, 12 and 6."""
        self.assert_breakdown(vat_breakdown(SPEC_ITEMS), {25: 25.0, 12: 6.0, 6: 12.0})

    def test_first_item_is_included(self):
        """The first item in the list must not be skipped."""
        self.assert_breakdown(vat_breakdown([("Kaffe", 100, 25)]), {25: 25.0})

    def test_items_with_the_same_rate_are_summed(self):
        """Two items at 25 % must give 50 kr VAT together."""
        result = vat_breakdown([("A", 100, 25), ("B", 100, 25)])
        self.assert_breakdown(result, {25: 50.0})

    def test_agrees_with_format_receipt(self):
        """The VAT rows in format_receipt() and vat_breakdown() must agree."""
        expected = {}
        for line in format_receipt(SPEC_ITEMS).split("\n"):
            if not line.startswith("Moms "):
                continue
            rate = int(line.split()[1])
            amount = Decimal(line.split()[-1].replace(".", "").replace(",", "."))
            expected[rate] = amount
        self.assert_breakdown(vat_breakdown(SPEC_ITEMS), expected)

    def test_empty_list_has_no_vat(self):
        self.assertEqual(vat_breakdown([]), {})


class TestVatBreakdownInput(unittest.TestCase):
    """The VAT table is the contract: anything outside it is an error."""

    def test_supported_rates_are_accepted(self):
        self.assertEqual(
            vat_breakdown([("A", 100, 25), ("B", 100, 12), ("C", 100, 6)]),
            {25: 25.0, 12: 12.0, 6: 6.0},
        )

    def test_unsupported_rates_are_rejected(self):
        for rate in (0, 3, 24, 7.5, 100):
            with self.assertRaises(ValueError) as ctx:
                vat_breakdown([("Skum sak", 500, rate)])
            self.assertIn("stöds inte", str(ctx.exception), rate)

    def test_error_names_the_item_and_the_supported_rates(self):
        with self.assertRaises(ValueError) as ctx:
            vat_breakdown([("Skum sak", 500, 3)])
        message = str(ctx.exception)
        self.assertIn("Skum sak", message)
        self.assertIn("25, 12, 6", message)


if __name__ == "__main__":
    unittest.main()

"""Tests for kvitto.py. Run: python3 -m unittest -v"""

import io
import re
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from kvitto import EMPTY_RECEIPT, FALLBACK_NAME, format_receipt, print_receipt

# Exact expected output according to the specification (31 characters wide).
EXAMPLE = "\n".join(
    [
        "KVITTO",
        "Kaffe                    100,00",
        "Bröd                      50,00",
        "Bok                      200,00",
        "-------------------------------",
        "Summa exkl. moms         350,00",
        "Moms 25 %                 25,00",
        "Moms 12 %                  6,00",
        "Moms 6 %                  12,00",
        "-------------------------------",
        "ATT BETALA               393,00",
    ]
)

EXAMPLE_ITEMS = [("Kaffe", 100, 25), ("Bröd", 50, 12), ("Bok", 200, 6)]

# Item row in print_receipt: "<name><padding><quantity> x <unit price>"
ITEM_ROW = re.compile(r"^(?P<label>.*?)\s+(?P<qty>\d+) x (?P<price>[\d ]*,\d\d)$")

# Basket and file for the golden test of print_receipt: every rate, a skipped
# blank-name item, thousands separator and a name that must be shortened.
GOLDEN_ITEMS = [
    ("Kaffe", 2, Decimal("39.90"), 25),
    ("Extra långt varunamn som inte får plats", 1, Decimal("1234.50"), 12),
    ("", 1, Decimal("0.00")),
    ("Bok", 1, Decimal("212.00"), 6),
]
GOLDEN_FILE = Path(__file__).with_name("golden_butikskvitto.txt")


class PrintReceiptHelpers:
    """Helpers for the print_receipt tests, which write to stdout.

    Mixed into the test classes so every test can read the receipt as text
    without repeating the redirect_stdout dance.
    """

    def print_to_text(self, items, **kwargs):
        """Runs print_receipt with a fixed timestamp and returns what it wrote."""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_receipt(items, timestamp=datetime(2026, 10, 23, 14, 32), **kwargs)
        return buffer.getvalue()

    def vat_lines(self, text):
        return [line for line in text.split("\n") if line.startswith("Moms ")]

    def vat_amount(self, text, percent):
        """The amount on the 'Moms <percent>%' row."""
        prefix = f"Moms {percent}%"
        line = next(ln for ln in self.vat_lines(text) if ln.startswith(prefix))
        return line.split()[-1]

    def item_rows(self, text):
        """Regex matches for the '<name> <qty> x <price>' rows."""
        matches = (ITEM_ROW.match(line) for line in text.split("\n"))
        return [match for match in matches if match]

    def labels(self, text):
        """Item names in the order they were printed."""
        return [match.group("label").strip() for match in self.item_rows(text)]

    def total_amount(self, text):
        """The amount on the ATT BETALA row."""
        line = next(ln for ln in text.split("\n") if ln.startswith("ATT BETALA"))
        return line.split()[-1]

class TestAmountFormatting(unittest.TestCase):
    def test_comma_and_two_decimals(self):
        self.assertIn("100,00", format_receipt([("X", 100, 25)]))
        self.assertIn("0,50", format_receipt([("X", "0.5", 25)]))
        self.assertIn("7,00", format_receipt([("X", 7, 25)]))

    def test_amounts_are_rounded_half_up(self):
        row = format_receipt([("X", "10.005", 25)]).split("\n")[1]
        self.assertTrue(row.endswith("10,01"), row)

    def test_vat_is_rounded_half_up(self):
        # 10,02 * 25 % = 2,505 -> 2,51
        lines = format_receipt([("X", "10.02", 25)]).split("\n")
        vat_line = next(ln for ln in lines if ln.startswith("Moms 25 %"))
        self.assertTrue(vat_line.endswith("2,51"), vat_line)

    def test_totals_add_up(self):
        result = format_receipt([("A", 100, 25), ("B", 50, 12), ("C", 200, 6)])
        lines = result.split("\n")
        excl = Decimal(lines[5].split()[-1].replace(".", "").replace(",", "."))
        vat = sum(
            Decimal(ln.split()[-1].replace(".", "").replace(",", "."))
            for ln in lines
            if ln.startswith("Moms ")
        )
        paid = Decimal(lines[-1].split()[-1].replace(".", "").replace(",", "."))
        self.assertEqual(excl + vat, paid)

    def test_negative_price_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("X", -1, 25)])

    def test_negative_vat_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("X", 10, -1)])

class TestFormatReceiptBlankNames(unittest.TestCase):
    """Blank item name: 0 kr is skipped, otherwise the item is called '(övrigt)'."""

    def test_blank_name_with_zero_price_is_skipped(self):
        result = format_receipt([("", 0, 25), ("Kaffe", 100, 25)])
        lines = result.split("\n")
        self.assertEqual(len(lines), 7)  # KVITTO, Kaffe, 2 rules, sum, VAT, total
        self.assertTrue(lines[1].startswith("Kaffe"), lines[1])
        self.assertNotIn(FALLBACK_NAME, result)

    def test_whitespace_only_name_with_zero_price_is_skipped(self):
        result = format_receipt([("   ", 0, 25), ("Kaffe", 100, 25)])
        self.assertNotIn(FALLBACK_NAME, result)
        self.assertEqual(len(result.split("\n")), 7)

    def test_blank_name_with_price_becomes_ovrigt(self):
        lines = format_receipt([("", 250, 25)]).split("\n")
        self.assertTrue(lines[1].startswith("(övrigt)"), lines[1])
        self.assertTrue(lines[1].endswith("250,00"), lines[1])
        self.assertEqual(len(lines[1]), 31)

    def test_whitespace_only_name_with_price_becomes_ovrigt(self):
        lines = format_receipt([("  \t ", 250, 25)]).split("\n")
        self.assertTrue(lines[1].startswith("(övrigt)"), lines[1])

    def test_ovrigt_still_gets_one_row_per_item(self):
        lines = format_receipt([("", 100, 25), ("", 50, 25)]).split("\n")
        self.assertEqual(sum(1 for ln in lines if ln.startswith("(övrigt)")), 2)

    def test_only_skipped_items_gives_inga_varor(self):
        self.assertEqual(format_receipt([("", 0, 25)]), "Inga varor")
        self.assertEqual(format_receipt([("", 0, 25), (" ", 0, 12)]), EMPTY_RECEIPT)

    def test_skipped_item_does_not_add_vat_line(self):
        # Only the 12 % item has a blank name and price 0 -> no "Moms 12 %" row
        result = format_receipt([("", 0, 12), ("Kaffe", 100, 25)])
        self.assertNotIn("Moms 12 %", result)
        self.assertIn("Moms 25 %", result)

    def test_skipped_item_does_not_affect_totals(self):
        lines = format_receipt([("", 0, 25), ("Kaffe", 100, 25)]).split("\n")
        sum_line = next(ln for ln in lines if ln.startswith("Summa"))
        self.assertTrue(sum_line.endswith("100,00"), sum_line)
        vat_line = next(ln for ln in lines if ln.startswith("Moms"))
        self.assertTrue(vat_line.endswith("25,00"), vat_line)
        self.assertTrue(lines[-1].endswith("125,00"))

    def test_zero_price_with_name_is_still_listed(self):
        lines = format_receipt([("Gratis", 0, 25)]).split("\n")
        self.assertTrue(lines[1].startswith("Gratis"), lines[1])
        self.assertNotIn(FALLBACK_NAME, "\n".join(lines))

    def test_price_rounding_to_zero_counts_as_free(self):
        # 0.001 kr rounds to 0.00 and is therefore skipped
        self.assertEqual(format_receipt([("", "0.001", 25)]), "Inga varor")

    def test_ovrigt_name_is_kept_within_20_chars(self):
        lines = format_receipt([("", 100, 25)]).split("\n")
        self.assertNotIn("...", lines[1])

class TestFormatReceiptEdgeCases(unittest.TestCase):
    def test_empty_list_returns_inga_varor(self):
        self.assertEqual(format_receipt([]), "Inga varor")

    def test_empty_tuple_returns_inga_varor(self):
        self.assertEqual(format_receipt(()), "Inga varor")

    def test_long_name_is_truncated_with_ellipsis(self):
        name = "Extra långt varunamn som inte får plats"
        result = format_receipt([(name, 100, 25)])
        row = result.split("\n")[1]
        self.assertTrue(row.startswith("Extra långt varun..."), row)
        label = row[: row.index("100,00")]
        self.assertEqual(label.rstrip(), "Extra långt varun...")
        self.assertEqual(len(label.rstrip()), 20)
        self.assertEqual(len(row), 31)

    def test_name_of_exactly_20_chars_is_untouched(self):
        name = "A" * 20
        row = format_receipt([(name, 100, 25)]).split("\n")[1]
        self.assertEqual(row, name + " " * 5 + "100,00")

    def test_name_of_21_chars_is_truncated(self):
        name = "A" * 21
        row = format_receipt([(name, 100, 25)]).split("\n")[1]
        self.assertTrue(row.startswith("A" * 17 + "..."), row)

    def test_only_present_vat_rates_are_shown(self):
        result = format_receipt([("Bok", 200, 6), ("Kaffe", 100, 25)])
        vat_lines = [ln for ln in result.split("\n") if ln.startswith("Moms ")]
        self.assertEqual(len(vat_lines), 2)
        self.assertNotIn("Moms 12 %", result)

    def test_vat_lines_are_sorted_descending(self):
        result = format_receipt([("Bok", 200, 6), ("Bröd", 50, 12), ("Kaffe", 100, 25)])
        vat_lines = [ln for ln in result.split("\n") if ln.startswith("Moms ")]
        labels = [ln.rstrip()[: ln.rstrip().index(" ", 5)].strip() for ln in vat_lines]
        self.assertEqual(labels, ["Moms 25", "Moms 12", "Moms 6"])

    def test_thousands_separator_keeps_rows_at_31_chars(self):
        row = format_receipt([("Dyr", 1234.5, 25)]).split("\n")[1]
        self.assertEqual(row, "Dyr" + " " * 20 + "1 234,50")
        self.assertEqual(len(row), 31)

class TestFormatReceiptExample(unittest.TestCase):
    def test_exact_output(self):
        self.assertEqual(format_receipt(EXAMPLE_ITEMS), EXAMPLE)

    def test_expected_block_is_31_chars_wide(self):
        for line in EXAMPLE.split("\n"):
            if line in ("KVITTO", "Inga varor"):
                continue
            self.assertEqual(len(line), 31, f"fel bredd: {line!r}")

    def test_accepts_decimals_and_strings_as_input(self):
        items = [
            ("Kaffe", Decimal("100.00"), Decimal("25")),
            ("Bröd", "50.00", "12"),
            ("Bok", 200, 6),
        ]
        self.assertEqual(format_receipt(items), EXAMPLE)

    def test_all_rows_are_full_width(self):
        for line in format_receipt(EXAMPLE_ITEMS).split("\n")[1:]:
            self.assertEqual(len(line), 31, f"fel bredd: {line!r}")

class TestFormatReceiptRobustness(unittest.TestCase):
    def test_text_price_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", "abc", 25)])
        self.assertIn("Ogiltigt värde för pris", str(ctx.exception))

    def test_none_price_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("A", None, 25)])

    def test_bool_price_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("A", True, 25)])

    def test_nan_price_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("A", Decimal("NaN"), 25)])

    def test_infinite_price_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([("A", Decimal("Infinity"), 25)])

    def test_text_vat_rate_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", 100, "hög")])
        self.assertIn("Ogiltigt värde för momssats", str(ctx.exception))

    def test_vat_rate_above_100_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", 100, 300)])
        self.assertIn("stöds inte", str(ctx.exception))

    def test_two_field_item_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", 100)])
        self.assertIn("(namn, pris, momssats)", str(ctx.exception))

    def test_non_iterable_item_is_rejected(self):
        with self.assertRaises(ValueError):
            format_receipt([100])

    def test_amount_too_wide_for_the_format_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", 10**24, 25)])
        self.assertIn("ryms inte", str(ctx.exception))

    def test_amount_beyond_decimal_precision_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("A", 10**30, 25)])
        self.assertIn("för stort", str(ctx.exception))

    def test_name_is_truncated_further_when_amount_is_wide(self):
        # "1 000 000,00" is 12 characters -> the left field becomes 19 characters
        row = format_receipt([("Ett mycket långt varunamn", 10**6, 25)]).split("\n")[1]
        self.assertEqual(len(row), 31)
        self.assertTrue(row.startswith("Ett mycket lång... "), row)
        self.assertTrue(row.endswith("1 000 000,00"), row)

class TestFormatReceiptStructure(unittest.TestCase):
    def test_single_item_receipt(self):
        lines = format_receipt([("Kaffe", 100, 25)]).split("\n")
        self.assertEqual(
            lines,
            [
                "KVITTO",
                "Kaffe                    100,00",
                "-------------------------------",
                "Summa exkl. moms         100,00",
                "Moms 25 %                 25,00",
                "-------------------------------",
                "ATT BETALA               125,00",
            ],
        )

    def test_items_keep_input_order(self):
        result = format_receipt([("Zebra", 1, 25), ("Alfa", 1, 25), ("Mitt", 1, 25)])
        names = [ln.split()[0] for ln in result.split("\n")[1:4]]
        self.assertEqual(names, ["Zebra", "Alfa", "Mitt"])

    def test_same_vat_rate_is_aggregated_into_one_line(self):
        # 100 + 50 = 150 excl. VAT, 25 % of 150 = 37.50
        result = format_receipt([("A", 100, 25), ("B", 50, 25)])
        vat_lines = [ln for ln in result.split("\n") if ln.startswith("Moms ")]
        self.assertEqual(len(vat_lines), 1)
        self.assertTrue(vat_lines[0].endswith("37,50"), vat_lines[0])

    def test_same_name_twice_is_listed_twice(self):
        lines = format_receipt([("Kaffe", 10, 25), ("Kaffe", 10, 25)]).split("\n")
        self.assertEqual(sum(1 for ln in lines if ln.startswith("Kaffe")), 2)

    def test_zero_price_item(self):
        lines = format_receipt([("Gratis", 0, 25)]).split("\n")
        self.assertTrue(lines[1].endswith("0,00"), lines[1])
        self.assertTrue(lines[-1].endswith("0,00"), lines[-1])

    def test_zero_vat_rate_is_rejected(self):
        """0 % is not in VAT_RATES, so it is an unsupported rate."""
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("Bok", 100, 0)])
        self.assertIn("stöds inte", str(ctx.exception))

    def test_hundred_percent_vat_rate_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("X", 100, 100)])
        self.assertIn("stöds inte", str(ctx.exception))

    def test_unsupported_rate_lists_the_supported_ones(self):
        with self.assertRaises(ValueError) as ctx:
            format_receipt([("X", 100, 24)])
        self.assertIn("25, 12, 6", str(ctx.exception))

    def test_all_supported_rates_are_accepted(self):
        for rate in (25, 12, 6):
            lines = format_receipt([(f"Vara {rate}", 100, rate)]).split("\n")
            self.assertTrue(any(ln.startswith(f"Moms {rate} %") for ln in lines), rate)

    def test_generator_input(self):
        items = ((name, 100, 25) for name in ("A", "B"))
        lines = format_receipt(items).split("\n")
        self.assertEqual(len(lines), 8)  # KVITTO, 2 items, 2 rules, sum, VAT, total

    def test_list_of_lists_input(self):
        as_list = format_receipt([["Kaffe", 100, 25]])
        as_tuple = format_receipt([("Kaffe", 100, 25)])
        self.assertEqual(as_list, as_tuple)

    def test_price_with_three_decimals_is_rounded(self):
        row = format_receipt([("A", "10.567", 25)]).split("\n")[1]
        self.assertTrue(row.endswith("10,57"), row)

    def test_float_input_does_not_leak_binary_noise(self):
        row = format_receipt([("A", 19.99, 25)]).split("\n")[1]
        self.assertTrue(row.endswith("19,99"), row)

    def test_swedish_characters_count_as_one(self):
        row = format_receipt([("Bröd", 50, 12)]).split("\n")[1]
        self.assertEqual(row, "Bröd" + " " * 22 + "50,00")
        self.assertEqual(len(row), 31)

    def test_empty_name_with_price_is_called_ovrigt(self):
        row = format_receipt([("", 100, 25)]).split("\n")[1]
        self.assertEqual(row, "(övrigt)" + " " * 17 + "100,00")
        self.assertEqual(len(row), 31)

    def test_no_trailing_whitespace_or_newline(self):
        result = format_receipt(EXAMPLE_ITEMS)
        self.assertEqual(result, result.rstrip())
        for line in result.split("\n"):
            self.assertEqual(line, line.rstrip(), f"skräp i slutet: {line!r}")

    def test_returns_str(self):
        self.assertIsInstance(format_receipt(EXAMPLE_ITEMS), str)
        self.assertIsInstance(format_receipt([]), str)

    def test_input_list_is_not_mutated(self):
        items = [["Kaffe", 100, 25]]
        format_receipt(items)
        self.assertEqual(items, [["Kaffe", 100, 25]])

class TestPrintReceiptBlankNames(PrintReceiptHelpers, unittest.TestCase):
    """Same blank-name rules as format_receipt: 0 kr is skipped, else '(övrigt)'."""

    def test_blank_name_with_zero_price_is_skipped(self):
        text = self.print_to_text(
            [
                ("Kaffe", 2, Decimal("39.90"), 25),
                ("", 2, Decimal("0.00")),
                ("Påse", 1, Decimal("7.00"), 25),
            ]
        )
        self.assertEqual(self.labels(text), ["Kaffe", "Påse"])
        self.assertEqual(len(self.item_rows(text)), 2)

    def test_whitespace_only_name_with_zero_price_is_skipped(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("10.00"), 25), ("   ", 1, Decimal("0.00"))]
        )
        self.assertEqual(self.labels(text), ["Kaffe"])

    def test_skipped_item_does_not_change_totals(self):
        text = self.print_to_text(
            [
                ("Kaffe", 2, Decimal("39.90"), 25),
                ("", 2, Decimal("0.00")),
                ("Påse", 1, Decimal("7.00"), 25),
            ]
        )
        self.assertEqual(self.total_amount(text), "86,80")   # 79,80 + 7,00

    def test_skipped_item_does_not_add_a_moms_line(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("125.00"), 25), ("", 1, Decimal("0.00"), 6)]
        )
        self.assertNotIn("Moms 6%", text)
        self.assertIn("Moms 25%", text)

    def test_blank_name_with_price_becomes_ovrigt(self):
        text = self.print_to_text([("", 1, Decimal("50.00"), 25)])
        self.assertEqual(self.labels(text), [FALLBACK_NAME])

    def test_named_zero_price_item_is_still_printed(self):
        text = self.print_to_text([("Gratis", 1, Decimal("0.00"), 25)])
        self.assertEqual(self.labels(text), ["Gratis"])

    def test_price_rounding_to_zero_counts_as_free(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("10.00"), 25), ("", 1, Decimal("0.001"), 25)]
        )
        self.assertEqual(self.labels(text), ["Kaffe"])

    def test_only_skipped_items_gives_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("", 1, Decimal("0.00"), 25)])
        self.assertIn("saknar varor", str(ctx.exception))

class TestPrintReceiptGolden(PrintReceiptHelpers, unittest.TestCase):
    """Locks the printed receipt byte for byte.

    The golden file is only regenerated when a layout change is intended:

        python3 -c "import test_kvitto as t; \\
            open('golden_butikskvitto.txt', 'w', encoding='utf-8').write( \\
                t.TestPrintReceiptGolden().print_to_text(t.GOLDEN_ITEMS))"
    """

    def test_same_input_gives_identical_bytes(self):
        first = self.print_to_text(GOLDEN_ITEMS).encode("utf-8")
        second = self.print_to_text(GOLDEN_ITEMS).encode("utf-8")
        self.assertEqual(first, second)

    def test_matches_the_golden_file_byte_for_byte(self):
        actual = self.print_to_text(GOLDEN_ITEMS).encode("utf-8")
        self.assertEqual(actual, GOLDEN_FILE.read_bytes())

    def test_golden_receipt_is_23_lines_of_40_chars(self):
        # 3 printed items (the blank 0 kr one is skipped) and one row per rate
        lines = self.print_to_text(GOLDEN_ITEMS).splitlines()
        self.assertEqual(len(lines), 23)
        self.assertTrue(all(len(line) == 40 for line in lines))

class TestPrintReceiptMixedVat(PrintReceiptHelpers, unittest.TestCase):
    """print_receipt with a different VAT rate per item."""

    def test_one_moms_line_per_rate(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("125.00"), 25), ("Bok", 1, Decimal("212.00"), 6)]
        )
        self.assertEqual(len(self.vat_lines(text)), 2)

    def test_rates_are_sorted_descending(self):
        text = self.print_to_text(
            [
                ("Bok", 1, Decimal("212.00"), 6),
                ("Bröd", 1, Decimal("18.00"), 12),
                ("Kaffe", 1, Decimal("125.00"), 25),
            ]
        )
        order = [ln.split()[1] for ln in self.vat_lines(text)]
        self.assertEqual(order, ["25%", "12%", "6%"])

    def test_vat_is_calculated_from_inclusive_price(self):
        text = self.print_to_text([("Bok", 1, Decimal("212.00"), 6)])
        self.assertEqual(self.vat_amount(text, 6), "12,00")

    def test_twenty_five_percent(self):
        text = self.print_to_text([("Kaffe", 1, Decimal("125.00"), 25)])
        self.assertEqual(self.vat_amount(text, 25), "25,00")

    def test_same_rate_is_aggregated(self):
        text = self.print_to_text(
            [("A", 1, Decimal("125.00"), 25), ("B", 1, Decimal("125.00"), 25)]
        )
        self.assertEqual(len(self.vat_lines(text)), 1)
        self.assertEqual(self.vat_amount(text, 25), "50,00")

    def test_three_tuple_items_use_the_default_rate(self):
        """Backwards compatible: (name, quantity, price) should still give 25 %."""
        text = self.print_to_text([("Kaffe", 1, Decimal("125.00"))])
        self.assertEqual(self.vat_amount(text, 25), "25,00")

    def test_global_vat_rate_applies_to_items_without_own_rate(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("125.00")), ("Bok", 1, Decimal("212.00"), 6)],
            vat_rate=Decimal("0.12"),
        )
        self.assertEqual(self.vat_amount(text, 12), "13,39")   # 125 - 125/1.12
        self.assertEqual(self.vat_amount(text, 6), "12,00")

    def test_zero_percent_is_rejected(self):
        """0 % is not in VAT_RATES, so it is an unsupported rate."""
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("Bok", 1, Decimal("100.00"), 0)])
        self.assertIn("stöds inte", str(ctx.exception))

    def test_total_is_the_sum_of_all_items(self):
        text = self.print_to_text(
            [("Kaffe", 2, Decimal("39.90"), 25), ("Bok", 1, Decimal("212.00"), 6)]
        )
        self.assertEqual(self.total_amount(text), "291,80")     # 79,80 + 212,00

    def test_all_lines_are_40_chars_with_mixed_rates(self):
        text = self.print_to_text(
            [
                ("Kaffe", 2, Decimal("39.90"), 25),
                ("Bröd", 1, Decimal("18.00"), 12),
                ("Bok", 1, Decimal("212.00"), 6),
            ]
        )
        for line in text.splitlines():
            self.assertEqual(len(line), 40, f"fel bredd: {line!r}")

    def test_rate_above_100_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("10.00"), 101)])
        self.assertIn("stöds inte", str(ctx.exception))

    def test_unsupported_rate_lists_the_supported_ones(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("10.00"), 24)])
        self.assertIn("25, 12, 6", str(ctx.exception))

    def test_all_supported_rates_are_accepted(self):
        expected = {25: "20,00", 12: "10,71", 6: "5,66"}   # 100 / (1 + rate)
        for rate, amount in expected.items():
            text = self.print_to_text([(f"Vara {rate}", 1, Decimal("100.00"), rate)])
            self.assertEqual(self.vat_amount(text, rate), amount, rate)

    def test_unsupported_default_vat_rate_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("100.00"))], vat_rate=Decimal("0.05"))
        self.assertIn("stöds inte", str(ctx.exception))

    def test_negative_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            self.print_to_text([("A", 1, Decimal("10.00"), -1)])

    def test_too_many_fields_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("10.00"), 25, "extra")])
        self.assertIn("(namn, antal, à-pris[, moms %])", str(ctx.exception))

    def test_too_few_fields_is_rejected(self):
        with self.assertRaises(ValueError):
            self.print_to_text([("A", 1)])

class TestPrintReceiptRegression(PrintReceiptHelpers, unittest.TestCase):
    def test_still_writes_40_char_receipt(self):
        text = self.print_to_text(
            [("Kaffe", 2, Decimal("39.90")), ("Påse", 1, Decimal("7.00"))]
        )
        lines = text.splitlines()
        self.assertEqual(len(lines), 19)
        self.assertTrue(all(len(line) == 40 for line in lines))


class TestPrintReceiptRobustness(PrintReceiptHelpers, unittest.TestCase):
    """Input and layout errors: nothing may reach the screen half-written."""

    def test_long_store_name_is_truncated_with_ellipsis(self):
        text = self.print_to_text(
            [("Kaffe", 1, Decimal("10.00"), 25)], store_name="A" * 50
        )
        header = text.split("\n")[1]
        self.assertTrue(header.endswith("…"), header)
        self.assertEqual(len(header), 40)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", -1, Decimal("10.00"), 25)])
        self.assertIn("Antal måste vara positivt", str(ctx.exception))

    def test_negative_unit_price_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("-10.00"), 25)])
        self.assertIn("À-pris får inte vara negativt", str(ctx.exception))

    def test_too_wide_right_column_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self.print_to_text([("A", 1, Decimal("10.00"), 25)], cashier="1" * 40)
        self.assertIn("Högerkolumnen ryms inte", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

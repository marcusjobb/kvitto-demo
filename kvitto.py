"""Receipts in the terminal. No external dependencies.

Three functions:
    print_receipt()   prints a 40 character wide shop receipt to stdout
                      (prices incl. VAT).
    format_receipt()  returns a 31 character wide summary receipt as a string
                      (prices excl. VAT, one VAT row per rate).
    vat_breakdown()   returns the VAT amount per rate as a dict.

Run:  python3 kvitto.py
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable, Sequence

# Layout
RECEIPT_WIDTH = 40          # width of print_receipt
SUMMARY_WIDTH = 31          # width of format_receipt
NAME_LIMIT = 20             # longest item name in format_receipt
ELLIPSIS = "..."            # required by the format_receipt spec
TIGHT_ELLIPSIS = "…"        # used where a spec does not pin the layout

# Texts printed on the receipt (output stays Swedish)
FALLBACK_NAME = "(övrigt)"
EMPTY_RECEIPT = "Inga varor"

# Money
CENT = Decimal("0.01")

# VAT rates in percent mapped to their fraction of the price. A rate that is
# not listed here is rejected: this table is the contract.
DEFAULT_VAT_RATE = Decimal("0.25")
VAT_RATES = {
    25: 0.25,
    12: 0.12,
    6: 0.06,
}


def format_receipt(items: Iterable[Sequence]) -> str:
    """Returns a receipt as a string, 31 characters wide.

    items: iterable of (name, price_excl_vat, vat_percent), e.g. ("Kaffe", 100, 25).
    Prices exclude VAT and the rate is given in percent, one of the VAT_RATES.
    One VAT row is written per rate present, highest rate first.

    Items without a name: an item costing 0 kr is skipped entirely, otherwise it is
    called "(övrigt)". An empty list, or a list where everything is skipped, gives
    "Inga varor".
    """
    items = list(items)
    if not items:
        return EMPTY_RECEIPT

    lines = ["KVITTO"]
    total_excl = Decimal("0.00")
    base_by_rate: dict[Decimal, Decimal] = {}

    for item in items:
        try:
            name, price, vat_percent = item
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Varje vara måste vara (namn, pris, momssats), fick: {item!r}"
            ) from error

        name = str(name)
        blank_name = not name.strip()
        price = _to_decimal(price, "pris", name)
        vat_percent = _to_decimal(vat_percent, "momssats", name)
        if price < 0:
            raise ValueError(f"Pris får inte vara negativt för {name!r}: {price}")
        fraction = _vat_fraction(vat_percent, name)

        base = _round_to_cent(price)
        if blank_name and base == 0:
            continue
        if blank_name:
            name = FALLBACK_NAME

        total_excl += base
        base_by_rate[fraction] = base_by_rate.get(fraction, Decimal("0.00")) + base
        lines.append(_summary_row(_truncate_name(name), _format_sek(base)))

    if not base_by_rate:
        return EMPTY_RECEIPT

    lines.append("-" * SUMMARY_WIDTH)
    lines.append(_summary_row("Summa exkl. moms", _format_sek(total_excl)))

    total_vat = Decimal("0.00")
    for fraction in sorted(base_by_rate, reverse=True):
        vat = _round_to_cent(base_by_rate[fraction] * fraction)
        total_vat += vat
        lines.append(
            _summary_row(f"Moms {_format_percent(fraction)} %", _format_sek(vat))
        )

    lines.append("-" * SUMMARY_WIDTH)
    lines.append(_summary_row("ATT BETALA", _format_sek(total_excl + total_vat)))

    return "\n".join(lines)


def print_receipt(
    items: Iterable[Sequence],
    store_name: str = "MIN BUTIK AB",
    address: str = "Storgatan 1, 411 00 Göteborg",
    org_number: str = "556000-0000",
    cashier: str = "01",
    vat_rate: Decimal = DEFAULT_VAT_RATE,
    timestamp: datetime | None = None,
) -> None:
    """Prints a shop receipt to stdout.

    items: iterable of (name, quantity, unit_price) or
           (name, quantity, unit_price, vat_percent).
           Prices include VAT. vat_percent is given in percent, one of VAT_RATES.
           Items without their own rate use vat_rate, which is given as a
           fraction (Decimal("0.25") = 25 %).

    One VAT row is written per rate present, highest rate first.

    Items without a name are handled as in format_receipt: an item costing 0 kr
    is skipped entirely, otherwise it is called "(övrigt)".
    """
    timestamp = timestamp or datetime.now()
    default_rate = Decimal(vat_rate) * 100
    default_fraction = _vat_fraction(default_rate, "kvittots standardsats")

    item_rows: list[tuple[str, int, Decimal, Decimal]] = []
    total = Decimal("0.00")
    gross_by_rate: dict[Decimal, Decimal] = {}

    for item in items:
        try:
            name, quantity, unit_price, *extra = item
        except (TypeError, ValueError) as error:
            raise _item_shape_error(item) from error
        if len(extra) > 1:
            raise _item_shape_error(item)

        quantity = int(quantity)
        unit_price = Decimal(str(unit_price))
        name = str(name)
        blank_name = not name.strip()
        if extra:
            fraction = _vat_fraction(Decimal(str(extra[0])), name)
        else:
            fraction = default_fraction
        if quantity <= 0:
            raise ValueError(f"Antal måste vara positivt för {name!r}: {quantity}")
        if unit_price < 0:
            raise ValueError(
                f"À-pris får inte vara negativt för {name!r}: {unit_price}"
            )

        line_total = _round_to_cent(unit_price * quantity)
        if blank_name and line_total == 0:
            continue
        if blank_name:
            name = FALLBACK_NAME

        total += line_total
        gross = gross_by_rate.get(fraction, Decimal("0.00")) + line_total
        gross_by_rate[fraction] = gross
        item_rows.append((name, quantity, unit_price, line_total))

    if not item_rows:
        raise ValueError("Kvittot saknar varor.")

    lines = [
        "=" * RECEIPT_WIDTH,
        _left(store_name.center(RECEIPT_WIDTH).rstrip()),
        _left(address.center(RECEIPT_WIDTH).rstrip()),
        _left(f"Org.nr {org_number}".center(RECEIPT_WIDTH).rstrip()),
        "=" * RECEIPT_WIDTH,
        _receipt_row(f"{timestamp:%Y-%m-%d %H:%M}", f"Kassör: {cashier}"),
        "-" * RECEIPT_WIDTH,
    ]

    for name, quantity, unit_price, line_total in item_rows:
        lines.append(_receipt_row(name, f"{quantity} x {_format_sek(unit_price)}"))
        lines.append(_receipt_row("", _format_sek(line_total)))

    lines += ["-" * RECEIPT_WIDTH, _receipt_row("Summa", _format_sek(total))]

    for fraction in sorted(gross_by_rate, reverse=True):
        gross = gross_by_rate[fraction]
        vat = _round_to_cent(gross - gross / (1 + fraction))
        lines.append(
            _receipt_row(
                f"Moms {_format_percent(fraction)}% (ingår)", _format_sek(vat)
            )
        )

    lines += [
        "=" * RECEIPT_WIDTH,
        _receipt_row("ATT BETALA", _format_sek(total)),
        "=" * RECEIPT_WIDTH,
        _left("Tack för ditt besök!".center(RECEIPT_WIDTH).rstrip()),
        "=" * RECEIPT_WIDTH,
    ]

    print("\n".join(lines))


def vat_breakdown(items: Iterable[Sequence]) -> dict:
    """Returns the VAT amount per rate, e.g. {25: 25.0, 12: 6.0}.

    items: iterable of (name, price_excl_vat, vat_percent).
    Only the rates in VAT_RATES are supported; any other rate raises ValueError.
    """
    breakdown: dict = {}
    for name, price, rate in items:
        if rate not in VAT_RATES:
            raise _unsupported_vat_rate(rate, name)
        # The table decides which rates exist; the maths stays price * rate / 100
        # so the float result is bit-for-bit what the contract promises.
        breakdown[rate] = breakdown.get(rate, 0) + price * rate / 100
    return breakdown


# --------------------------------------------------------------------------
# Validation and conversion
# --------------------------------------------------------------------------


def _item_shape_error(item) -> ValueError:
    """Builds the error raised for an item that is not a valid item tuple."""
    return ValueError(
        f"Varje vara måste vara (namn, antal, à-pris[, moms %]), fick: {item!r}"
    )


def _to_decimal(value, field: str, name: str) -> Decimal:
    """Converts input to Decimal and raises a readable error for garbage input."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Ogiltigt värde för {field} i {name!r}: {value!r}") from error
    if not number.is_finite():
        raise ValueError(f"Ogiltigt värde för {field} i {name!r}: {value!r}")
    return number


def _unsupported_vat_rate(rate_percent, name: str) -> ValueError:
    """Builds the error raised for a VAT rate that is not in VAT_RATES."""
    supported = ", ".join(str(known) for known in sorted(VAT_RATES, reverse=True))
    return ValueError(
        f"Momssats {rate_percent} % stöds inte för {name!r}. "
        f"Stödda satser: {supported} %."
    )


def _vat_fraction(rate_percent, name: str) -> Decimal:
    """VAT fraction as Decimal for a supported rate, e.g. 25 -> Decimal('0.25')."""
    try:
        return Decimal(str(VAT_RATES[rate_percent]))
    except KeyError:
        raise _unsupported_vat_rate(rate_percent, name) from None


# --------------------------------------------------------------------------
# Layout and formatting
# --------------------------------------------------------------------------


def _format_percent(fraction: Decimal) -> str:
    """Decimal('0.25') -> '25'."""
    return f"{(fraction * 100).normalize():f}"


def _format_sek(amount: Decimal) -> str:
    """Formats an amount as '1 234,50' (comma, space as thousands separator)."""
    integer_part, _, decimals = f"{_round_to_cent(amount):.2f}".partition(".")
    grouped = f"{int(integer_part):,}".replace(",", " ")
    return f"{grouped},{decimals}"


def _left(text: str) -> str:
    """Left-aligned row, always exactly RECEIPT_WIDTH characters wide."""
    if len(text) > RECEIPT_WIDTH:
        text = text[: RECEIPT_WIDTH - 1] + TIGHT_ELLIPSIS
    return text.ljust(RECEIPT_WIDTH)


def _receipt_row(left: str, right: str) -> str:
    """Two columns in the 40 character receipt: name left, amount right."""
    space = RECEIPT_WIDTH - len(right) - 1
    if space < 0:
        raise ValueError(f"Högerkolumnen ryms inte: {right!r}")
    if len(left) > space:
        left = left[: space - 1] + TIGHT_ELLIPSIS if space > 0 else ""
    return left.ljust(space) + " " + right


def _round_to_cent(amount: Decimal) -> Decimal:
    """Rounds to two decimals, half up, with a readable error for absurd amounts."""
    try:
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise ValueError(
            f"Beloppet är för stort för att hanteras: {amount!r}"
        ) from error


def _summary_row(left: str, amount: str, width: int = SUMMARY_WIDTH) -> str:
    """Row with text on the left and the amount right-aligned, exactly width wide."""
    space = width - len(amount)
    if space <= len(ELLIPSIS):
        raise ValueError(f"Beloppet ryms inte i {width} tecken: {amount!r}")
    if len(left) > space:
        left = left[: space - len(ELLIPSIS) - 1] + ELLIPSIS
    return left.ljust(space) + amount


def _truncate_name(name: str, limit: int = NAME_LIMIT) -> str:
    """Shortens names longer than limit characters, ending with '...'."""
    if len(name) <= limit:
        return name
    return name[: limit - len(ELLIPSIS)] + ELLIPSIS


if __name__ == "__main__":
    print_receipt(
        items=[
            ("Kaffe", 2, Decimal("39.90"), 25),
            ("", 2, Decimal("0.00")),
            ("Ostfralla", 1, Decimal("18.00"), 12),
            ("Påse", 1, Decimal("7.00"), 25),
            ("Bok", 1, Decimal("212.00"), 6),
            ("Skum sak", 1, Decimal("500.00"), 12),
            ("Gratis gåva", 1, Decimal("0.00"), 12),
            ("", 1, Decimal("1.00"), 12),
        ],
        timestamp=datetime(2026, 10, 23, 14, 32),
    )
    print()

    print(
        format_receipt(
            [
                ("", 0, 25),
                ("Kaffe", 100, 25),
                ("Bröd", 50, 12),
                ("Bok", 200, 6),
            ]
        )
    )

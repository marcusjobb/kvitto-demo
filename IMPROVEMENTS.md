# Förbättringar av kvitto-demo

Samlat från två oberoende genomgångar (Claude och OpenCode) av `kvitto.py`, testerna och `agents.md`.
Alla 104 tester går igenom idag. Allt nedan följer `agents.md`: **testet först**, refaktorering ändrar inga tester.

## Att behålla som det är

- `Decimal` och `_round_to_cent` på ett enda ställe
- `VAT_RATES` som kontrakt
- Svenska felmeddelanden som namnger varan och de giltiga värdena
- Golden-testet och exakt-output-testet
- `format_receipt` returnerar, `print_receipt` skriver (men se steg 5)
- Endast stdlib

## Steg 1 — Buggar (beteendefel, inte smak)

Varje punkt börjar med ett fallerande test. Det ger en ändring av beteende, inte en refaktorering.

| # | Problem | Idag | Önskat |
|---|---------|------|--------|
| 1.1 | Antal `1.9` i `print_receipt` | `int()` trunkerar tyst till `1` | `ValueError` som namnger varan och värdet |
| 1.2 | Antal `True` i `print_receipt` | blir `1` | `ValueError` |
| 1.3 | Antal `"abc"` | engelsk `ValueError: invalid literal for int()` | svenskt meddelande (bryter regel 1) |
| 1.4 | Pris `"abc"`, `None`, `"NaN"` i `print_receipt` | rå `InvalidOperation` utan varunamn | samma svenska `ValueError` som `format_receipt` |
| 1.5 | Pris `Infinity` i `print_receipt` | "Beloppet är för stort" (sant men missvisande) | "Ogiltigt värde för pris" |
| 1.6 | `vat_breakdown` mot kvittot | `10,02 × 25 %` ger `2.505` mot kvittots `2,51`; `0.1 × 3` ger `0.07500000000000001` | avrundad till ören som kvittot, `Decimal` (beslut 1) |
| 1.7 | `print_receipt` anropar `datetime.now()` som default | samma indata ger olika utdata (regel 12) | `timestamp` blir obligatorisk (beslut 3) |
| 1.8 | Tom lista i `print_receipt` | undantag `"Kvittot saknar varor."` | `"Inga varor"` som i `format_receipt` (beslut 2) |
| 1.9 | 0 % moms | avvisas | giltig sats (beslut 4) |

Rotorsak till 1.1–1.5: `print_receipt` parsar och validerar själv i stället för att dela väg med `format_receipt`.

## Steg 2 — En normaliseringsväg (största kvarvarande DRY-bristen)

- Reglerna för tomt namn (`blank_name`, hoppa över vid 0 kr, `FALLBACK_NAME`) står i två kopior på ~12 rader.
- Inför `@dataclass(frozen=True, slots=True) class Item` med `name`, `quantity`, `unit_price`, `vat_percent`.
- Validering i `__post_init__`, och en `parse_item()` som båda funktionerna delar.
- Publika API:t tar fortfarande tupler; de blir tunna adaptrar in till `Item`.
- Samma regel för tom lista i båda funktionerna: `"Inga varor"` (beslut 2).
- Löser steg 1.3–1.5 av sig själv när 1.1–1.2 har fått sina tester.

## Steg 3 — En momsenhet och Decimal hela vägen

- Procent överallt. Idag är `vat_rate=Decimal("0.25")` (andel) per kvitto och `25` (procent) per vara, i samma signatur.
- `VAT_RATES` med `Decimal`-nycklar i stället för `int → float → Decimal(str(...))`.
- `vat_breakdown` returnerar `Decimal` och använder samma beräkning som `format_receipt`. Båda anropar en gemensam funktion så att de inte kan glida isär.
- Ändrar ett dokumenterat beteende (`{25: 25.0}`); beslutet är taget (beslut 1).
- `VAT_RATES` får även `0` (beslut 4).

## Steg 4 — Tester

- **Oberoende facit.** Handräknad moms per sats i testet, inte `format_receipt` jämförd med `vat_breakdown`. Dagens `test_agrees_with_format_receipt` jämför våra egna funktioner med varandra.
- **Invarianter över korgar.** Varje rad har rätt bredd, summan av varuraderna är lika med totalen, och momsraderna summerar till total minus exkl. Använd `random.Random(seed)` så att regel 12 gäller.
- **Samma gränsfallssvit för båda funktionerna.** Idag har bara `format_receipt` tester för `NaN`, `"abc"` och `None`.
- **En-orsak-regeln (regel 7).** Flera tester har fler asserts än en, t.ex. `test_comma_and_two_decimals` har tre. Dela dem.

## Steg 5 — Struktur (sist, och bara om det blir enklare)

- `print_receipt` blir en tunn wrapper kring `render_receipt(...) -> str`. Då försvinner `redirect_stdout` och mixin:en `PrintReceiptHelpers`, och golden-testet jämför strängar direkt.
- Butiksuppgifter (namn, adress, org.nr, kassör) som ett `Store`-objekt i stället för fem strängparametrar med defaults.
- Dela filen efter ansvar, inte efter "klasser": domän (`Item`, moms, avrundning) och layout (rader, bredder, avkortning). Troligen två moduler.
- Layout: en gemensam `row(left, right, width, ...)` i stället för `_left`, `_receipt_row`, `_summary_row`, `_truncate_name`. Gör det **bara** om det blir enklare än fyra små funktioner. `...` mot `…` och 31 mot 40 tecken kommer från specen och ska finnas kvar.

## Beslut (Marcus, 2026-10-23)

1. **`vat_breakdown` avrundar per sats till hela ören**, som kvittot, och returnerar `Decimal`. Båda delar en gemensam beräkning.
2. **Tom lista ger `"Inga varor"` i båda funktionerna.** `print_receipt` slutar kasta `"Kvittot saknar varor."`.
3. **`timestamp` är obligatorisk** i `print_receipt` (inget `datetime.now()` inuti). Tiden sätts av den som anropar, så den ändras inte om något dröjer.
4. **0 % moms är giltigt.** `0` läggs till i `VAT_RATES`.

Konsekvenser för testerna (ändras först, eftersom beteendet ändras):

- `test_unsupported_rates_are_rejected` har `0` i listan över avvisade satser. Ta bort `0` därifrån.
- Nytt test: 0 % ger en rad `Moms 0 %` med `0,00` på kvittot, och `{0: 0}` i `vat_breakdown`.
- `vat_breakdown`-testerna som jämför mot `float` (`{25: 25.0, ...}`) fungerar fortfarande, eftersom `Decimal("25.00") == 25.0`. Testen `assertAlmostEqual(float(...))` behöver ingen ändring.
- Nytt test: `10,02 × 25 %` ger `Decimal("2.51")` i både kvitto och `vat_breakdown`.
- Det gamla testet för `print_receipt` utan varor (undantag) ändras till `"Inga varor"`.
- Alla anrop till `print_receipt` utan `timestamp` måste få en. `__main__`-blocket har redan det.
- Rättning i steg 1.7: `timestamp` blir obligatorisk.

## Förslag till `agents.md`

- **Byt filnamn till `AGENTS.md`.** Linux är skiftlägeskänsligt och verktyg letar efter standardnamnet.
- Byt "Dela filen i klasser" till: *"En fil har ett ansvar. Växer den, dela efter ansvar — modul eller klass."*
- Lägg till: *"Pengar är alltid `Decimal` med `ROUND_HALF_UP`, aldrig `float`."* (Koden följer redan det, utom `vat_breakdown`, som rättas i steg 3.) *(OpenCode, utökad)*
- Lägg till: *"Jämför aldrig två av våra egna funktioner med varandra och kalla det verifiering. Testa mot ett handräknat facit."*
- Lägg till: *"Felmeddelanden är ett kontrakt. Antingen låser vi texten i testerna medvetet, eller testar vi typ och fält."*
- Lägg till hur man kör testerna: `uv run python -m unittest -v`. Hela sviten körs, aldrig en enskild fil som facit: `python3 test_kvitto.py` kör 92 tester och missar de 12 momstesterna i `test_vat_breakdown.py` (hela sviten är 104). *(OpenCode)*
- Affärsregler är tabeller, inte if-kedjor: en ny sats är en rad i `VAT_RATES`, och ett okänt värde är ett fel. *(OpenCode)*
- Skärp regel 8 (DRY) med: *"En regel ger samma svar från alla funktioner."* Samma ogiltiga indata ger samma undantagstyp och samma meddelande, oavsett vilken funktion som anropas. Idag bryts det av `print_receipt` (steg 1.3–1.5). *(OpenCode)*
- Bara kanten skriver: endast `print_receipt` anropar `print()`, allt annat returnerar. Gäller även efter steg 5, då `print_receipt` blir en tunn wrapper. *(OpenCode)*
- Specad utdata låses exakt: `EXAMPLE` och `golden_butikskvitto.txt` jämförs tecken för tecken. En layoutändring är ett medvetet beslut som ändrar facit, inte en bieffekt. *(OpenCode)*
- Lägg till domän och gränssnitt: de tre funktionernas ansvar, vad som är krav i specen (31 tecken, `...`, exkl. moms) och vad som är val.
- Bestäm språk för filnamn och testnamn, så att regel 3 är entydig.

## Föreslagen ordning

1. ~~Beslut 1–4~~ — klara
2. Steg 1: ett fallerande test i taget, sedan fixen
3. Steg 2 och 3: refaktorering med testerna som skyddsnät
4. Steg 4: nya tester, parallellt med steg 2–3
5. Steg 5 och `agents.md`: sist

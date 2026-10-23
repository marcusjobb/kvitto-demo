## Regler

- Kodens namn — variabler, metoder, klasser, kommentarer — är på engelska, allt som skrivs ut är på svenska
- Tester först: skriv testet som fallerar, sedan koden som får det att passera
- Alla ändringar börjar i testet, även när kod ska tas bort
- Refaktorering ändrar inget beteende och inga tester; ändras beteendet är det ingen refaktorering
- Ett test ska fallera av exakt en anledning, så felmeddelandet pekar på orsaken
- DRY: en regel finns på ett ställe — men bara om utbrytningen blir enklare än upprepningen
- Publika delar först, sedan metoderna grupperade per användningsområde och alfabetiskt inom gruppen
- Dela filen i klasser när den växer, innan den blir svår att överblicka
- Endast stdlib — ett nytt beroende ska motiveras, inte smygas in
- Skicka in det som varierar (tid, slump); samma indata ska ge samma byte ut
- Fel kastas med ett meddelande som namnger varan och de värden som gäller — inget tystas

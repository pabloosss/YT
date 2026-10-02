from agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    name = "Research"

    def run(self, *, topic: str) -> str:
        if self.ai.demo_mode:
            return f"""# Research: {topic}

## Cel
Przygotować materiał do filmu na temat: {topic}.

## Kierunek
1. Mocny fakt lub pytanie na otwarcie.
2. 3-5 najważniejszych informacji.
3. Chronologia lub logiczny ciąg przyczynowo-skutkowy.
4. Element zaskoczenia.
5. Konkretna puenta.

## Do weryfikacji
- daty
- liczby
- nazwy własne
- cytaty
- źródła materiałów wizualnych

To wynik DEMO. Po podaniu OPENAI_API_KEY agent przygotuje właściwy research.
"""

        return self.ai.ask(
            instructions=(
                "Jesteś research agentem studia YouTube. Przygotowuj rzetelny, konkretny "
                "research po polsku. Oddzielaj fakty od hipotez i zaznaczaj rzeczy wymagające "
                "weryfikacji. Nie wymyślaj źródeł."
            ),
            prompt=(
                f"Temat filmu: {topic}\n\n"
                "Przygotuj research: hook, najważniejsze fakty, chronologię jeśli potrzebna, "
                "ryzyka błędów i najlepszy kąt narracyjny."
            ),
        )

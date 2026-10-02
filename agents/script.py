from agents.base import BaseAgent


class ScriptAgent(BaseAgent):
    name = "Scenariusz"

    def run(self, *, topic: str, research: str) -> str:
        if self.ai.demo_mode:
            return f"""TYTUŁ ROBOCZY: {topic}

[HOOK]
A co, jeśli najciekawsza część tej historii jest zwykle pomijana?

[ROZWINIĘCIE]
To jest przykładowy scenariusz trybu DEMO.
Po podaniu klucza OpenAI agent zamieni research w gotowy tekst lektorski,
z krótkimi zdaniami i tempem dopasowanym do YouTube.

[FINAŁ]
I właśnie dlatego temat „{topic}” warto zobaczyć z innej strony.
"""

        return self.ai.ask(
            instructions=(
                "Jesteś scenarzystą YouTube. Pisz naturalnie po polsku, bez sztucznego tonu AI. "
                "Mocny hook, konkretne tempo, krótkie zdania. Nie wymyślaj faktów spoza researchu."
            ),
            prompt=(
                f"Temat: {topic}\n\nRESEARCH:\n{research}\n\n"
                "Napisz gotowy scenariusz lektorski: HOOK, rozwinięcie, finał. "
                "Bez komentarzy technicznych."
            ),
        )

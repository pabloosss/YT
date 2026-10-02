from agents.base import BaseAgent


class ScriptAgent(BaseAgent):
    name = "Scenariusz"

    def run(self, *, topic: str, research: str) -> str:
        if self.ai.demo_mode:
            return f"""[HOOK]
Czy wiesz, że najciekawsza część tej historii jest zwykle pomijana?

[ROZWINIĘCIE]
Oto najważniejszy fakt dotyczący tematu „{topic}”. Film rozwija go szybko, prostymi zdaniami i bez zbędnych dygresji. Każde zdanie prowadzi do kolejnego obrazu.

[FINAŁ]
I właśnie dlatego ta krótka historia wygląda zupełnie inaczej, niż mogło się wydawać.
"""

        return self.ai.ask(
            instructions=(
                "Jesteś scenarzystą pionowych filmów TikTok i YouTube Shorts. "
                "Pisz naturalnie po polsku, energicznie i bez sztucznego tonu AI. "
                "Film ma trwać około 30 sekund. Scenariusz ma mieć 55–65 słów, mocny hook w pierwszych "
                "dwóch sekundach, szybkie rozwinięcie i krótką puentę. Używaj krótkich zdań. "
                "Nie dodawaj powitania, próśb o subskrypcję ani komentarzy technicznych. "
                "Nie wymyślaj faktów spoza researchu."
            ),
            prompt=(
                f"Temat: {topic}\n\nRESEARCH:\n{research}\n\n"
                "Napisz wyłącznie gotowy tekst lektorski z sekcjami HOOK, ROZWINIĘCIE i FINAŁ. "
                "Łącznie 55–65 słów, tempo na około 30 sekund."
            ),
        )

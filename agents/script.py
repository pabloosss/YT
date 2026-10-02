from agents.base import BaseAgent
from core.subtitles import clean_narration


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
                "Dobierz długość historii od około 30 do maksymalnie 60 sekund. Scenariusz ma mieć 55–125 słów, "
                "mocny hook, logiczne rozwinięcie oraz pełne zakończenie. Nie urywaj myśli ani zdania. "
                "Używaj krótkich zdań i zapisuj liczby oraz skróty w formie łatwej do przeczytania przez lektora. "
                "Nie dodawaj powitania, próśb o subskrypcję ani komentarzy technicznych. "
                "Nie wymyślaj faktów spoza researchu."
            ),
            prompt=(
                f"Temat: {topic}\n\nRESEARCH:\n{research}\n\n"
                "Napisz wyłącznie gotowy tekst lektorski z sekcjami HOOK, ROZWINIĘCIE i FINAŁ. "
                "Użyj 55–125 słów. Wybierz długość potrzebną do opowiedzenia pełnej historii, bez lania wody."
            ),
        )

    def prepare_for_voice(self, *, topic: str, script: str) -> str:
        """Use the local model as an editor; never mechanically cut narration mid-story."""
        cleaned = clean_narration(script)
        if self.ai.demo_mode:
            return cleaned
        raw = self.ai.ask(
            instructions=(
                "Jesteś redaktorem końcowym lektora do YouTube Shorts. Popraw tekst tak, aby tworzył kompletną "
                "miniopowieść: hook, rozwinięcie i domknięty finał. Długość 55–125 słów, co odpowiada mniej więcej "
                "30–60 sekundom. Usuń powtórzenia i techniczne nagłówki. Nie urywaj zdań. Zapisuj liczby, daty i "
                "skróty w sposób naturalny do wymówienia po polsku. Nie dodawaj nowych faktów. Zwróć tylko tekst lektora."
            ),
            prompt=f"Temat: {topic}\n\nTEKST DO REDAKCJI:\n{cleaned}",
        )
        prepared = clean_narration(raw)
        words = prepared.split()
        if not 45 <= len(words) <= 135 or prepared[-1:] not in ".!?…":
            raise RuntimeError(
                f"Lokalny redaktor nie przygotował pełnego scenariusza 30–60 s ({len(words)} słów). Spróbuj wznowić projekt."
            )
        return prepared

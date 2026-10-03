"""Local, bounded production memory for the studio's AI agents."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile


BASE_STUDIO_INSTRUCTIONS = """
STAŁE ZASADY AI CONTENT STUDIO:
1. Najpierw ustal cel etapu i sprawdź dostępne dane, dopiero potem twórz wynik.
2. Fakty opieraj na przekazanym researchu. Nie wymyślaj źródeł, cytatów ani pewności.
3. Film ma być pełną miniopowieścią: mocny hook, logiczny rozwój i wyraźnie domknięty finał.
4. Każde ujęcie ma wnosić nową informację. Nie planuj zapętleń ani seryjnych powtórzeń obrazu.
5. Projektuj pionowo 9:16, z czytelnym centrum i spokojnym dolnym pasem pod małe napisy.
6. Tekst lektora ma brzmieć naturalnie po polsku; liczby, daty i skróty muszą być łatwe do wymówienia.
7. Przed płatną operacją popraw plan lokalnie i wykorzystuj prawidłowe wyniki zapisane wcześniej.
8. Krytykuj wcześniejszy wynik niezależnie. Jeśli jest słaby, popraw go zamiast go bronić.
9. Nie ujawniaj ukrytego toku rozumowania. Zwracaj wynik, krótkie uzasadnienie lub wymagany JSON.
10. Nie twierdź, że widziałeś lub usłyszałeś materiał, jeśli dostałeś tylko jego opis albo parametry.
""".strip()

ALLOWED_CATEGORIES = {"research", "narracja", "tempo", "obraz", "lektor", "metadata", "workflow"}
MAX_LESSONS = 20


class StudioMemory:
    """Stores reusable production lessons, never episode facts or hidden reasoning."""

    def __init__(self, root: Path):
        self.path = Path(root) / "studio_lessons.json"

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Nie można odczytać pamięci doświadczeń {self.path}: {exc}") from exc
        if not isinstance(value, list):
            raise RuntimeError(f"Pamięć doświadczeń {self.path} nie jest listą.")
        return [item for item in value if isinstance(item, dict)]

    def _write(self, lessons: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(lessons[-MAX_LESSONS:], stream, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _clean_lesson(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value)).strip(" -–—\t\n")
        if len(text) < 15 or len(text) > 280:
            return ""
        if re.search(
            r"https?://|\bsk_[A-Za-z0-9]+|api[_ -]?key|hasło|token|"
            r"ignoruj.{0,30}instrukc|system prompt|poleceni[ae] system",
            text,
            flags=re.I,
        ):
            return ""
        return text

    def add(self, candidates: list[dict], *, project: str) -> list[dict]:
        lessons = self.load()
        known = {re.sub(r"\W+", "", str(item.get("lesson", "")).lower()) for item in lessons}
        added: list[dict] = []
        for candidate in candidates[:5]:
            if not isinstance(candidate, dict):
                continue
            category = str(candidate.get("category") or "workflow").strip().lower()
            lesson = self._clean_lesson(candidate.get("lesson") or "")
            key = re.sub(r"\W+", "", lesson.lower())
            if category not in ALLOWED_CATEGORIES or not lesson or key in known:
                continue
            try:
                confidence = float(candidate.get("confidence", 0.7))
            except (TypeError, ValueError):
                confidence = 0.7
            if confidence < 0.6:
                continue
            record = {
                "category": category,
                "lesson": lesson,
                "confidence": round(min(confidence, 1.0), 2),
                "source_project": Path(project).name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            lessons.append(record)
            added.append(record)
            known.add(key)
        self._write(lessons)
        return added

    def context(self) -> str:
        lessons = self.load()
        if not lessons:
            return "Brak zapisanych doświadczeń z wcześniejszych zatwierdzonych filmów."
        lines = [
            f"- [{item.get('category', 'workflow')}] {item.get('lesson', '')}"
            for item in lessons[-MAX_LESSONS:]
            if item.get("lesson")
        ]
        return "SPRAWDZONE WNIOSKI PRODUKCYJNE Z POPRZEDNICH PROJEKTÓW:\n" + "\n".join(lines)

    def display(self) -> str:
        lessons = self.load()
        if not lessons:
            return "AI nie zapisało jeszcze żadnych wniosków. Pamięć powstaje dopiero po zatwierdzonym filmie."
        return "\n".join(
            f"{index}. [{item.get('category', 'workflow')}] {item.get('lesson', '')}"
            for index, item in enumerate(lessons, start=1)
        )

    def clear(self) -> None:
        self._write([])

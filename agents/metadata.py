from __future__ import annotations

import json

from agents.base import BaseAgent


class MetadataAgent(BaseAgent):
    name = "YouTube Meta"

    def run(self, *, topic: str, script: str) -> dict:
        if self.ai.demo_mode:
            return {
                "title": topic[:100],
                "description": (
                    f"Film o temacie: {topic}\n\n"
                    "Opis demonstracyjny wygenerowany przez AI Content Studio."
                ),
                "tags": ["youtube", "ai content studio"],
                "category_id": "22",
                "privacy_status": "private",
            }

        raw = self.ai.ask(
            instructions=(
                "Jesteś specjalistą od metadanych YouTube. Tworzysz konkretny tytuł, opis i tagi "
                "na podstawie scenariusza. Nie stosuj clickbaitu sprzecznego z treścią. "
                "Odpowiadaj WYŁĄCZNIE poprawnym JSON-em."
            ),
            prompt=(
                f"Temat: {topic}\n\nSCENARIUSZ:\n{script}\n\n"
                "Zwróć obiekt JSON z polami: title (max 100 znaków), description, tags (tablica), "
                "category_id (domyślnie 22), privacy_status ustawione zawsze na private."
            ),
        )

        data = json.loads(raw)
        title = str(data.get("title") or topic).strip()[:100]
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = []

        return {
            "title": title,
            "description": str(data.get("description") or "").strip(),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()][:25],
            "category_id": str(data.get("category_id") or "22"),
            "privacy_status": "private",
        }

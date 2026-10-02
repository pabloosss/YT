from __future__ import annotations

from agents.base import BaseAgent
from core.json_utils import loads_relaxed


class MetadataAgent(BaseAgent):
    name = "YouTube Meta"

    def run(self, *, topic: str, script: str) -> dict:
        if self.ai.demo_mode:
            return {
                "title": (topic[:91].rstrip() + " #Shorts")[:100],
                "description": f"Krótki film o temacie: {topic}\n\n#shorts #tiktok",
                "tags": ["shorts", "tiktok", "ciekawostki"],
                "category_id": "22",
                "privacy_status": "private",
            }

        raw = self.ai.ask(
            instructions=(
                "Jesteś specjalistą od metadanych YouTube Shorts i TikToka. Tworzysz krótki, konkretny "
                "tytuł, opis oraz tagi na podstawie scenariusza. Nie stosuj clickbaitu sprzecznego z treścią. "
                "Opis zakończ pasującymi hashtagami, w tym #shorts. Odpowiadaj WYŁĄCZNIE poprawnym JSON-em."
            ),
            prompt=(
                f"Temat: {topic}\n\nSCENARIUSZ:\n{script}\n\n"
                "Zwróć obiekt JSON z polami: title (najlepiej do 60 znaków, maks. 100), "
                "description (krótki opis i 3–5 hashtagów), tags (tablica), "
                "category_id (domyślnie 22), privacy_status zawsze private."
            ),
        )

        data = loads_relaxed(raw)
        title = str(data.get("title") or topic).strip()
        if "#shorts" not in title.lower():
            title = title[:91].rstrip() + " #Shorts"
        title = title[:100]
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        description = str(data.get("description") or "").strip()
        if "#shorts" not in description.lower():
            description = (description + "\n\n#shorts").strip()

        return {
            "title": title,
            "description": description,
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()][:25],
            "category_id": str(data.get("category_id") or "22"),
            "privacy_status": "private",
        }

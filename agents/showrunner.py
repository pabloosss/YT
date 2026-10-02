from __future__ import annotations

from agents.base import BaseAgent
from core.json_utils import loads_relaxed


SHORT_DURATIONS = (8, 8, 8, 6)


class ShowrunnerAgent(BaseAgent):
    name = "Showrunner"

    def run(self, *, topic: str, script: str) -> list[dict]:
        if self.ai.demo_mode:
            return [
                {"shot": 1, "duration_sec": 8, "visual": f"Mocne pionowe otwarcie: {topic}", "camera": "dynamic push-in", "lighting": "filmowe, kontrastowe", "purpose": "hook"},
                {"shot": 2, "duration_sec": 8, "visual": "Ujęcie ilustrujące pierwszy kluczowy fakt", "camera": "subtelny tracking", "lighting": "naturalne", "purpose": "wyjaśnienie"},
                {"shot": 3, "duration_sec": 8, "visual": "Najbardziej zaskakujący element historii", "camera": "dynamiczny detal", "lighting": "spójne i wyraziste", "purpose": "kulminacja"},
                {"shot": 4, "duration_sec": 6, "visual": "Mocne symboliczne zakończenie", "camera": "slow zoom out", "lighting": "wyraziste", "purpose": "finał"},
            ]

        raw = self.ai.ask(
            instructions=(
                "Jesteś showrunnerem pionowych filmów TikTok i YouTube Shorts. "
                "Rozbij scenariusz na dokładnie 4 dynamiczne ujęcia w kadrze 9:16. "
                "Łączny plan trwa 30 sekund: 8, 8, 8 i 6 sekund. "
                "Najważniejszy element trzymaj w bezpiecznym centrum kadru, aby dobrze wyglądał na telefonie. "
                "Pilnuj ciągłości wizualnej, światła, tempa i czytelności pod napisy w dolnej części. "
                "Odpowiadaj WYŁĄCZNIE poprawną tablicą JSON."
            ),
            prompt=(
                f"Temat: {topic}\n\nSCENARIUSZ:\n{script}\n\n"
                "Zwróć dokładnie 4 elementy. Każdy ma pola: shot, duration_sec, visual, camera, lighting, purpose. "
                "Czasy kolejno: 8, 8, 8, 6. Wszystkie kadry pionowe 9:16, bez tekstu i logo w obrazie."
            ),
        )
        try:
            data = loads_relaxed(raw)
        except ValueError:
            raw = self.ai.ask(
                instructions=(
                    "Napraw plan ujęć. Zwróć WYŁĄCZNIE poprawną tablicę JSON z dokładnie 4 elementami. "
                    "Nie używaj Markdownu ani obiektu {shots: ...}. Każdy element musi mieć pola: "
                    "shot, duration_sec, visual, camera, lighting, purpose."
                ),
                prompt=f"Temat: {topic}\n\nNIEPOPRAWNA ODPOWIEDŹ:\n{raw}",
            )
            data = loads_relaxed(raw)

        if isinstance(data, dict):
            data = data.get("shots")
        if not isinstance(data, list) or not data:
            raise ValueError("Showrunner nie zwrócił listy ujęć.")

        normalized = []
        for index, source in enumerate(data[:4], start=1):
            if not isinstance(source, dict):
                continue
            shot = dict(source)
            if "lighting" not in shot and "lightyng" in shot:
                shot["lighting"] = shot.pop("lightyng")
            shot["shot"] = index
            shot["duration_sec"] = SHORT_DURATIONS[index - 1]
            shot.setdefault("visual", "")
            shot.setdefault("camera", "")
            shot.setdefault("lighting", "")
            shot.setdefault("purpose", "")
            normalized.append(shot)

        if not normalized:
            raise ValueError("Showrunner nie zwrócił poprawnych ujęć.")
        while len(normalized) < 4:
            clone = dict(normalized[-1])
            clone["shot"] = len(normalized) + 1
            clone["duration_sec"] = SHORT_DURATIONS[len(normalized)]
            clone["purpose"] = "uzupełnienie pionowego filmu"
            normalized.append(clone)
        return normalized

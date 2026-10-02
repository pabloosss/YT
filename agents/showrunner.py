from __future__ import annotations

from agents.base import BaseAgent
from core.json_utils import loads_relaxed


class ShowrunnerAgent(BaseAgent):
    name = "Showrunner"

    def run(self, *, topic: str, script: str) -> list[dict]:
        if self.ai.demo_mode:
            return [
                {"shot": 1, "duration_sec": 3, "visual": f"Mocne otwarcie: {topic}", "camera": "slow push-in", "lighting": "filmowe, kontrastowe", "purpose": "hook"},
                {"shot": 2, "duration_sec": 5, "visual": "Ujęcie ilustrujące pierwszy kluczowy fakt", "camera": "subtelny ruch", "lighting": "naturalne", "purpose": "wyjaśnienie"},
                {"shot": 3, "duration_sec": 5, "visual": "Drugie ujęcie rozwijające historię", "camera": "powolny tracking", "lighting": "spójne", "purpose": "rozwinięcie"},
                {"shot": 4, "duration_sec": 4, "visual": "Mocne symboliczne zakończenie", "camera": "slow zoom out", "lighting": "wyraziste", "purpose": "finał"},
            ]

        raw = self.ai.ask(
            instructions=(
                "Jesteś showrunnerem i reżyserem filmów internetowych. Rozbij scenariusz na ujęcia. "
                "Pilnuj ciągłości wizualnej, kadru, światła i tempa. Odpowiadaj WYŁĄCZNIE poprawnym JSON-em."
            ),
            prompt=(
                f"Temat: {topic}\n\nSCENARIUSZ:\n{script}\n\n"
                "Zwróć tablicę JSON. Każdy element ma: shot, duration_sec, visual, camera, lighting, purpose."
            ),
        )
        try:
            data = loads_relaxed(raw)
        except ValueError:
            raw = self.ai.ask(
                instructions=(
                    "Napraw poniższy plan ujęć. Zwróć WYŁĄCZNIE poprawną tablicę JSON. "
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
        for index, shot in enumerate(data, start=1):
            if not isinstance(shot, dict):
                continue
            if "lighting" not in shot and "lightyng" in shot:
                shot["lighting"] = shot.pop("lightyng")
            shot.setdefault("shot", index)
            shot.setdefault("duration_sec", 4)
            shot.setdefault("visual", "")
            shot.setdefault("camera", "")
            shot.setdefault("lighting", "")
            shot.setdefault("purpose", "")
            normalized.append(shot)

        if not normalized:
            raise ValueError("Showrunner nie zwrócił poprawnych ujęć.")
        return normalized

from __future__ import annotations

from agents.base import BaseAgent
from core.json_utils import loads_relaxed


SHORT_DURATIONS = (4, 4, 4, 4, 4, 4, 3, 3)


def durations_for(target_duration: int) -> tuple[int, ...]:
    if target_duration >= 55:
        return (5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5)
    if target_duration >= 40:
        return (5, 5, 5, 5, 5, 4, 4, 4, 4, 4)
    return SHORT_DURATIONS


class ShowrunnerAgent(BaseAgent):
    name = "Showrunner"

    def run(self, *, topic: str, script: str, target_duration: int = 30) -> list[dict]:
        durations = durations_for(target_duration)
        if self.ai.demo_mode:
            purposes = [
                "hook", "kontekst", "pierwszy fakt", "wyjaśnienie", "rozwinięcie", "szczegół",
                "zwrot", "konsekwencje", "kulminacja", "znaczenie", "domknięcie", "finał",
            ]
            return [
                {"shot": index, "duration_sec": duration,
                 "visual": f"Pionowe ujęcie {index} ilustrujące historię: {topic}",
                 "camera": "subtelny ruch kamery", "lighting": "filmowe, spójne",
                 "purpose": purposes[index - 1]}
                for index, duration in enumerate(durations, start=1)
            ]

        raw = self.ai.ask(
            instructions=(
                "Jesteś showrunnerem pionowych filmów TikTok i YouTube Shorts. "
                f"Rozbij scenariusz na dokładnie {len(durations)} dynamicznych ujęć w kadrze 9:16. "
                f"Łączny plan trwa około {sum(durations)} sekund. Czasy ujęć: {list(durations)}. "
                "Najważniejszy element trzymaj w bezpiecznym centrum kadru, aby dobrze wyglądał na telefonie. "
                "Pilnuj ciągłości wizualnej, światła, tempa i czytelności pod napisy w dolnej części. "
                "Odpowiadaj WYŁĄCZNIE poprawną tablicą JSON."
            ),
            prompt=(
                f"Temat: {topic}\n\nSCENARIUSZ:\n{script}\n\n"
                f"Zwróć dokładnie {len(durations)} elementów. Każdy ma pola: shot, duration_sec, visual, camera, lighting, purpose. "
                f"Czasy kolejno: {list(durations)}. Wszystkie kadry pionowe 9:16, bez tekstu i logo w obrazie."
            ),
        )
        try:
            data = loads_relaxed(raw)
        except ValueError:
            raw = self.ai.ask(
                instructions=(
                    f"Napraw plan ujęć. Zwróć WYŁĄCZNIE poprawną tablicę JSON z dokładnie {len(durations)} elementami. "
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
        for index, source in enumerate(data[:len(durations)], start=1):
            if not isinstance(source, dict):
                continue
            shot = dict(source)
            if "lighting" not in shot and "lightyng" in shot:
                shot["lighting"] = shot.pop("lightyng")
            shot["shot"] = index
            shot["duration_sec"] = durations[index - 1]
            shot.setdefault("visual", "")
            shot.setdefault("camera", "")
            shot.setdefault("lighting", "")
            shot.setdefault("purpose", "")
            normalized.append(shot)

        if not normalized:
            raise ValueError("Showrunner nie zwrócił poprawnych ujęć.")
        while len(normalized) < len(durations):
            clone = dict(normalized[-1])
            clone["shot"] = len(normalized) + 1
            clone["duration_sec"] = durations[len(normalized)]
            clone["purpose"] = "uzupełnienie pionowego filmu"
            normalized.append(clone)
        return normalized

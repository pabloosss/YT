"""Bounded local planning; no tool execution or paid-service permissions."""
from agents.base import BaseAgent
from core.json_utils import loads_relaxed


class DirectorAgent(BaseAgent):
    name = "Dyrektor"

    def run(self, *, topic: str) -> dict:
        self.ai.set_active_agent(self.name)
        if self.ai.demo_mode:
            return {"goal": topic, "angle": "Jedna pełna historia.",
                    "research_questions": ["Które fakty mają źródła?"],
                    "acceptance_checks": ["Pełny finał", "Różne ujęcia"]}
        correction = ""
        for _ in range(2):
            raw = self.ai.ask(
                instructions=("Jesteś dyrektorem lokalnego studia. Zaplanuj kompletny Short 30–60 s, "
                              "nie pisz jeszcze scenariusza. Ustal jeden kąt narracji, pytania do researchu "
                              "i mierzalne kryteria odbioru. Nie zakładaj faktów przed researchem. "
                              "Nie zmieniaj budżetu, ustawień ani uprawnień. Zwróć tylko JSON."),
                prompt=(f"Temat: {topic}\nPola: goal i angle (krótkie teksty), research_questions "
                        "i acceptance_checks (po 2–4 krótkie teksty). Kryteria obejmują "
                        "źródła, pełne zakończenie, unikalne ujęcia i czytelne napisy. " + correction),
            )
            try:
                data = loads_relaxed(raw)
                if not isinstance(data, dict):
                    raise ValueError("Oczekiwano obiektu")
                result = {}
                for key in ("goal", "angle"):
                    if not isinstance(data.get(key), str) or not data[key].strip():
                        raise ValueError(key)
                    result[key] = data[key].strip()[:200]
                for key in ("research_questions", "acceptance_checks"):
                    values = data.get(key)
                    if not isinstance(values, list) or not values or not all(isinstance(v, str) and v.strip() for v in values):
                        raise ValueError(key)
                    result[key] = [v.strip()[:140] for v in values[:4]]
                return result
            except (ValueError, TypeError):
                correction = "Poprzednia odpowiedź miała zły format. Użyj dokładnie wymaganych pól i typów."
        raise RuntimeError("Dyrektor nie przygotował poprawnego planu po dwóch próbach. Nie uruchomiono płatnych generacji.")

from __future__ import annotations

from pathlib import Path


class QualityAgent:
    name = "Kontrola"

    def run(self, *, project_path: Path, shots: list[dict]) -> dict:
        issues: list[str] = []
        warnings: list[str] = []

        required = [
            "01_research.md",
            "02_script.txt",
            "03_shots.json",
            "04_image_prompts.json",
            "05_narration.txt",
        ]
        for filename in required:
            if not (project_path / filename).exists():
                issues.append(f"Brakuje pliku: {filename}")

        if not shots:
            issues.append("Showrunner nie wygenerował żadnych ujęć.")

        total_duration = 0
        for index, shot in enumerate(shots, start=1):
            duration = shot.get("duration_sec", 0)
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = 0

            if duration <= 0:
                issues.append(f"Ujęcie {index}: nieprawidłowy czas.")
            if duration > 15:
                warnings.append(f"Ujęcie {index}: długie ujęcie ({duration}s).")
            total_duration += max(duration, 0)

            if not str(shot.get("visual", "")).strip():
                issues.append(f"Ujęcie {index}: brak opisu wizualnego.")

        if total_duration < 10:
            warnings.append("Plan filmu ma mniej niż 10 sekund.")

        return {
            "approved": not issues,
            "issues": issues,
            "warnings": warnings,
            "planned_duration_sec": total_duration,
        }

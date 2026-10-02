from __future__ import annotations

from pathlib import Path


class VoiceAgent:
    name = "Lektor"

    def run(self, *, script: str, project_path: Path) -> Path:
        """v0.2: przygotowuje tekst do TTS. Provider audio będzie podpinany osobno."""
        target = project_path / "audio" / "narration.txt"
        target.write_text(script, encoding="utf-8")
        return target

from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent


class VoiceAgent(BaseAgent):
    name = "Lektor"

    def run(
        self,
        *,
        script: str,
        project_path: Path,
        generate_audio: bool,
        model: str,
        voice: str,
        instructions: str,
    ) -> Path | None:
        audio_dir = project_path / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "narration.txt").write_text(script, encoding="utf-8")

        if not generate_audio or self.ai.demo_mode:
            return None

        target = audio_dir / "narration.mp3"
        return self.ai.text_to_speech(
            text=script,
            output_path=target,
            model=model,
            voice=voice,
            instructions=instructions,
        )

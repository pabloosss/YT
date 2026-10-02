from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent
from core.elevenlabs_client import ElevenLabsClient
from core.subtitles import short_narration


class VoiceAgent(BaseAgent):
    name = "Lektor"

    def run(
        self,
        *,
        script: str,
        project_path: Path,
        generate_audio: bool,
        api_key: str = "",
        voice_id: str = "",
        model: str = "eleven_flash_v2_5",
        **_legacy,
    ) -> Path | None:
        audio_dir = project_path / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        clean = short_narration(script)
        (audio_dir / "narration.txt").write_text(clean, encoding="utf-8")

        if not generate_audio or self.ai.demo_mode:
            return None

        target = audio_dir / "narration.mp3"
        subtitles = project_path / "subtitles" / "narration.srt"
        ElevenLabsClient(api_key).synthesize(
            text=clean,
            output_audio=target,
            output_srt=subtitles,
            voice_id=voice_id,
            model_id=model,
        )
        return target

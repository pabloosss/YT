from __future__ import annotations

import json
from pathlib import Path

from agents.base import BaseAgent
from core.elevenlabs_client import ElevenLabsClient
from core.subtitles import clean_narration, normalize_polish_tts


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
        model: str = "eleven_turbo_v2_5",
        **_legacy,
    ) -> Path | None:
        audio_dir = project_path / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        source_narration = clean_narration(script)
        clean = normalize_polish_tts(source_narration)
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
        (audio_dir / "voice_settings.json").write_text(
            json.dumps(
                {"model": model, "source_narration": source_narration, "tts_text": clean},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

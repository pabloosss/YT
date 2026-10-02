from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.config import load_settings
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore

from core.elevenlabs_client import ElevenLabsClient
from core.subtitles import alignment_to_srt, clean_narration
from core.veo_client import VeoClient


class SubtitleTests(unittest.TestCase):
    def test_veo_reuses_existing_clip_without_api_call(self):
        with TemporaryDirectory() as temp:
            output_dir = Path(temp)
            existing = output_dir / "shot_001.mp4"
            existing.write_bytes(b"x" * 2048)
            client = VeoClient("dummy")
            with patch.object(client, "generate_clip", side_effect=AssertionError("Veo must not be called")):
                result = client.generate_all(
                    prompts=[{"shot": 1, "prompt": "first"}],
                    output_dir=output_dir,
                    max_clips=1,
                )
            self.assertEqual(result, [existing])

    def test_clean_narration_removes_markdown_and_sources(self):
        source = "**Hook:** Koty były święte. [1]\n\n**Finał:** To koniec.\n---\n*Uwagi do źródeł*"
        self.assertEqual(clean_narration(source), "Koty były święte. To koniec.")

    def test_alignment_creates_srt(self):
        text = "To jest test. Drugi napis."
        alignment = {
            "characters": list(text),
            "character_start_times_seconds": [index * 0.05 for index in range(len(text))],
            "character_end_times_seconds": [(index + 1) * 0.05 for index in range(len(text))],
        }
        with TemporaryDirectory() as temp:
            output = alignment_to_srt(alignment, Path(temp) / "narration.srt", words_per_caption=3)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("-->", rendered)
            self.assertIn("To jest test.", rendered)
            self.assertIn("Drugi napis.", rendered)

    def test_elevenlabs_requires_key_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "ELEVENLABS_API_KEY"):
            ElevenLabsClient("").voices()

    def test_recovery_reuses_clips_without_calling_veo(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "failed_project"
            (project / "video_clips").mkdir(parents=True)
            (project / "audio").mkdir()
            (project / "subtitles").mkdir()
            (project / "02_script.txt").write_text("Gotowy tekst.", encoding="utf-8")
            (project / "video_clips" / "shot_001.mp4").write_bytes(b"saved veo")
            (project / "audio" / "narration.mp3").write_bytes(b"saved voice")
            (project / "subtitles" / "narration.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n", encoding="utf-8")

            settings = load_settings()
            settings.projects_dir = root
            pipeline = ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)

            def render(**kwargs):
                output = kwargs["output"]
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"finished")
                return output

            pipeline.editor.available = lambda: True
            pipeline.editor.render_clips = render
            with patch("core.pipeline.VeoClient", side_effect=AssertionError("Veo must not be called")):
                output = pipeline.finish_existing(project)

            self.assertTrue(output.exists())
            recovery = (project / "recovery_result.json").read_text(encoding="utf-8")
            self.assertIn('"veo_called_again": false', recovery)


if __name__ == "__main__":
    unittest.main()

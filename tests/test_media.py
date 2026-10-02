from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from core.config import load_settings
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore

from core.elevenlabs_client import ElevenLabsClient
from core.editor import FFmpegEditor
from core.subtitles import alignment_to_srt, clean_narration, normalize_polish_tts, short_narration, text_to_srt
from core.veo_client import VeoClient


class SubtitleTests(unittest.TestCase):
    def test_existing_voice_is_reused_only_for_same_narration_and_model(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "voice_project"
            audio_dir = project / "audio"
            audio_dir.mkdir(parents=True)
            (audio_dir / "narration.mp3").write_bytes(b"a" * 2048)
            (audio_dir / "voice_settings.json").write_text(
                json.dumps({
                    "model": "eleven_turbo_v2_5",
                    "source_narration": "Ten sam tekst.",
                    "tts_text": "Ten sam tekst.",
                }),
                encoding="utf-8",
            )
            settings = load_settings()
            settings.projects_dir = root
            settings.elevenlabs_model = "eleven_turbo_v2_5"
            pipeline = ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)

            self.assertTrue(pipeline._audio_matches(project, "Ten sam tekst."))
            self.assertFalse(pipeline._audio_matches(project, "Zmieniony tekst."))

    def test_vertical_subtitles_are_small_and_bottom_aligned(self):
        profile = FFmpegEditor.subtitle_profile()
        self.assertLessEqual(profile["font_size"], 20)
        self.assertEqual(profile["alignment"], "bottom_center")
        rendered_filter = FFmpegEditor._subtitle_filter(Path("captions.srt"))
        self.assertIn("FontSize=20", rendered_filter)
        self.assertIn("Alignment=2", rendered_filter)
        self.assertIn("MarginV=45", rendered_filter)

    @staticmethod
    def _mock_finish_services(pipeline: ContentPipeline) -> None:
        pipeline.script_agent.prepare_for_voice = lambda **_kwargs: (
            "To jest kompletna opowieść przygotowana do testu. Ma wyraźny początek, rozwinięcie oraz spokojny finał."
        )
        pipeline._audio_matches = lambda *_args: True
        pipeline._supervise_narration = lambda **kwargs: (
            kwargs["narration"], {"approved": True, "cycles": 1, "issues": [], "summary": "OK"}
        )
        pipeline.editor.media_duration = lambda _path: 28.0
        pipeline.editor.inspect_short = lambda _path: {
            "width": 720,
            "height": 1280,
            "duration_seconds": 30.0,
            "vertical": True,
            "short_eligible": True,
        }

        def create_thumbnail(_video, output):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"t" * 2048)
            return output

        pipeline.editor.create_thumbnail = create_thumbnail
        pipeline._final_ai_review = lambda **_kwargs: {
            "approved": True,
            "summary": "Historia jest kompletna.",
            "strengths": ["Pełne zakończenie"],
            "risks": [],
            "video_info": {"short_eligible": True},
        }
        pipeline._review_visual_plan = lambda **kwargs: (
            kwargs["prompts"],
            {
                "approved": True,
                "summary": "Plan wizualny jest spójny.",
                "risks": [],
                "scope": "test",
            },
        )
        pipeline._prefetch_hybrid_images = lambda **_kwargs: {}
        pipeline._build_unique_shot_folder = lambda **kwargs: kwargs["video_clips"]

    def test_polish_tts_spells_dates_and_years(self):
        result = normalize_polish_tts("Film z 2.10.2026 opisuje odkrycie z 1799 roku.")
        self.assertIn("drugi października dwa tysiące dwadzieścia sześć", result)
        self.assertIn("tysiąc siedemset dziewięćdziesiąt dziewięć", result)
        self.assertNotIn("1799", result)

    def test_hybrid_builder_creates_readable_unique_shot_folder(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            video = project / "shot_001.mp4"
            image = project / "commons_002.jpg"
            video.write_bytes(b"v" * 2048)
            image.write_bytes(b"i" * 2048)
            settings = load_settings()
            settings.projects_dir = root
            pipeline = ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)

            def prepare_shot(*, output, **_kwargs):
                output.write_bytes(b"s" * 2048)
                return output

            pipeline.editor.prepare_shot = prepare_shot
            outputs = pipeline._build_unique_shot_folder(
                project_path=project,
                prompts=[
                    {"shot": 1, "prompt": "cat temple", "description_pl": "Kot w świątyni", "tags": ["kot"]},
                    {"shot": 2, "prompt": "Bastet statue", "description_pl": "Posąg bogini Bastet", "tags": ["Bastet"]},
                ],
                video_clips=[video],
                images={2: (image, {"author": "Autor", "license": "CC BY", "source_url": "https://example.org"})},
                duration_seconds=30,
            )

            self.assertEqual(len(outputs), 2)
            self.assertIn("kot_w_swiatyni", outputs[0].name)
            self.assertTrue((project / "shots" / "OPIS_UJEC.txt").exists())
            manifest = json.loads((project / "05_shot_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([item["source_type"] for item in manifest], ["veo", "wikimedia_commons"])
            self.assertTrue((root / "_media_library" / "manifest.json").exists())

    def test_short_narration_caps_paid_tts_input(self):
        source = " ".join(f"słowo{index}" for index in range(100))
        result = short_narration(source)
        self.assertLessEqual(len(result.split()), 60)
        self.assertLessEqual(len(result), 551)

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

    def test_veo_balanced_selection_keeps_hook_and_finale(self):
        with TemporaryDirectory() as temp:
            output_dir = Path(temp)
            client = VeoClient("dummy")
            generated_shots = []

            def generate(*, output, **_kwargs):
                generated_shots.append(output.stem)
                output.write_bytes(b"x" * 2048)
                return output

            prompts = [{"shot": index, "prompt": f"shot {index}"} for index in range(1, 7)]
            with patch.object(client, "generate_clip", side_effect=generate):
                client.generate_all(prompts=prompts, output_dir=output_dir, max_clips=3)

            self.assertEqual(generated_shots[0], "shot_001")
            self.assertEqual(generated_shots[-1], "shot_006")

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

    def test_local_subtitles_restore_interrupted_project(self):
        with TemporaryDirectory() as temp:
            output = text_to_srt("To jest lokalnie odtworzony napis do filmu.", Path(temp) / "narration.srt")
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 -->", rendered)
            self.assertIn("To jest lokalnie odtworzony", rendered)

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
            (project / "07_youtube.json").write_text('{"title":"Test"}', encoding="utf-8")
            (project / "03_shots.json").write_text('[{"shot":1,"visual":"Test"}]', encoding="utf-8")
            (project / "04_video_prompts.json").write_text('[{"shot":1,"prompt":"test"}]', encoding="utf-8")
            (project / "video_clips" / "shot_001.mp4").write_bytes(b"v" * 2048)
            (project / "audio" / "narration.mp3").write_bytes(b"a" * 2048)
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
            self._mock_finish_services(pipeline)
            with patch("core.pipeline.VeoClient", side_effect=AssertionError("Veo must not be called")):
                output = pipeline.finish_existing(project)

            self.assertTrue(output.exists())
            recovery = (project / "recovery_result.json").read_text(encoding="utf-8")
            self.assertIn('"veo_called_again": false', recovery)

    def test_recovery_ignores_broken_clip_and_restores_video(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "interrupted_project"
            (project / "video_clips").mkdir(parents=True)
            (project / "audio").mkdir()
            (project / "02_script.txt").write_text("Gotowy tekst.", encoding="utf-8")
            (project / "07_youtube.json").write_text('{"title":"Test"}', encoding="utf-8")
            (project / "04_video_prompts.json").write_text(
                '[{"shot": 1, "prompt": "test"}]', encoding="utf-8"
            )
            (project / "video_clips" / "shot_001.mp4").write_bytes(b"")
            (project / "audio" / "narration.mp3").write_bytes(b"a" * 2048)

            settings = load_settings()
            settings.projects_dir = root
            pipeline = ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)
            generated = project / "video_clips" / "shot_002.mp4"

            def generate_all(**_kwargs):
                generated.write_bytes(b"v" * 2048)
                return [generated]

            def render(**kwargs):
                self.assertEqual(kwargs["clips"], [generated])
                output = kwargs["output"]
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"finished")
                return output

            pipeline.editor.available = lambda: True
            pipeline.editor.render_clips = render
            self._mock_finish_services(pipeline)
            with patch.object(VeoClient, "healthcheck", return_value="ok"), \
                 patch.object(VeoClient, "generate_all", side_effect=generate_all):
                output = pipeline.finish_existing(project, allow_generate_veo=True)

            self.assertTrue(output.exists())
            self.assertTrue((project / "subtitles" / "narration.srt").exists())

    def test_recovery_resumes_before_missing_script_and_creates_metadata(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "old_project"
            (project / "video_clips").mkdir(parents=True)
            (project / "audio").mkdir()
            (project / "subtitles").mkdir()
            (project / "01_research.md").write_text("Sprawdzony research.", encoding="utf-8")
            (project / "03_shots.json").write_text('[{"shot":1,"visual":"Test"}]', encoding="utf-8")
            (project / "04_video_prompts.json").write_text('[{"shot":1,"prompt":"test"}]', encoding="utf-8")
            (project / "video_clips" / "shot_001.mp4").write_bytes(b"v" * 2048)
            (project / "audio" / "narration.mp3").write_bytes(b"a" * 2048)

            settings = load_settings()
            settings.projects_dir = root
            pipeline = ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)
            pipeline.editor.available = lambda: True
            pipeline.editor.render_clips = lambda **kwargs: kwargs["output"]

            def render(**kwargs):
                output = kwargs["output"]
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"finished")
                return output

            pipeline.editor.render_clips = render
            self._mock_finish_services(pipeline)
            with patch.object(pipeline.script_agent, "run", return_value="Odtworzony scenariusz."), \
                 patch.object(pipeline.metadata_agent, "run", return_value={"title": "Odtworzony", "description": "#shorts", "tags": []}):
                output = pipeline.finish_existing(project)

            self.assertTrue(output.exists())
            self.assertTrue((project / "02_script.txt").exists())
            self.assertTrue((project / "07_youtube.json").exists())
            self.assertIn('"recovered": true', (project / "state.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

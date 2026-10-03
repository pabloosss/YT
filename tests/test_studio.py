import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from agents.director import DirectorAgent
from core.config import load_settings
from core.editor import FFmpegEditor
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.studio_memory import StudioMemory
from core.test_clip import TestClipPipeline


class StudioTests(unittest.TestCase):
    def test_careful_mode_requires_two_reviews_even_when_first_approves(self):
        with TemporaryDirectory() as tmp:
            settings = load_settings()
            settings.projects_dir = Path(tmp)
            ai = OpenAIGateway(settings)
            pipeline = ContentPipeline(ProjectStore(Path(tmp)), ai, settings)
            narration = " ".join(["Słowo"] * 50) + "."
            reply = json.dumps({"approved": True, "revised_narration": narration, "issues": []})
            with patch.object(ai, "ask", return_value=reply) as ask:
                settings.quality_mode = "careful"
                _, review = pipeline._supervise_narration(topic="t", research="r", narration=narration)
                self.assertEqual(ask.call_count, 2)
                self.assertEqual(review["cycles"], 2)
            with patch.object(ai, "ask", return_value=reply) as ask:
                settings.quality_mode = "standard"
                pipeline._supervise_narration(topic="t", research="r", narration=narration)
                self.assertEqual(ask.call_count, 1)

    def test_director_has_bounded_repair_and_no_paid_calls(self):
        ai = MagicMock(demo_mode=False)
        plan = {"goal": "historia", "angle": "jeden fakt", "research_questions": ["źródła?"],
                "acceptance_checks": ["pełny finał"]}
        ai.ask.side_effect = ["invalid", json.dumps(plan)]
        self.assertEqual(DirectorAgent(ai).run(topic="temat"), plan)
        self.assertEqual(ai.ask.call_count, 2)
        ai.ask.side_effect = ["invalid", "invalid"]
        with self.assertRaises(RuntimeError):
            DirectorAgent(ai).run(topic="temat")

    def test_custom_model_survives_version_seven_configuration(self):
        with patch.dict(os.environ, {"AI_STUDIO_SETTINGS_VERSION": "7", "OLLAMA_MODEL": "local-text:12b"}):
            self.assertEqual(load_settings().ollama_model, "local-text:12b")

    def test_old_lessons_are_pending_until_human_approval(self):
        with TemporaryDirectory() as tmp:
            memory = StudioMemory(Path(tmp))
            memory.path.write_text(json.dumps([{"lesson": "Domykaj obietnicę z początku filmu.", "category": "narracja"}]))
            self.assertNotIn("Domykaj", memory.context())
            memory.decide(0, approve=True)
            self.assertIn("Domykaj", StudioMemory(Path(tmp)).context())
            memory.decide(0, approve=False)
            self.assertEqual(memory.load(), [])

    def test_pending_lessons_cannot_evict_approved_rules(self):
        with TemporaryDirectory() as tmp:
            memory = StudioMemory(Path(tmp))
            memory.add([{"lesson": "Domykaj obietnicę z początku filmu."}], project="a")
            memory.decide(0, approve=True)
            for i in range(30):
                memory.add([{"lesson": f"Przykładowa sugestia produkcyjna numer {i}."}], project="b")
            self.assertEqual(len(memory.load()), 21)
            self.assertIn("Domykaj", memory.context())

    def test_failed_learning_does_not_invalidate_completed_media(self):
        with TemporaryDirectory() as tmp:
            settings = load_settings()
            settings.projects_dir = Path(tmp)
            pipeline = ContentPipeline(ProjectStore(Path(tmp)), OpenAIGateway(settings), settings)
            with patch.object(pipeline, "_propose_lessons", side_effect=RuntimeError("offline")):
                result = pipeline._learn_from_project(project_path=Path(tmp), topic="t", script_review={}, visual_review={}, final_review={"approved": True})
            self.assertEqual(result, [])
            self.assertEqual(json.loads((Path(tmp) / "10_studio_learning.json").read_text())["status"], "failed")

    def run_sample(self, root, *, audio_seconds=2.0):
        settings = load_settings()
        settings.projects_dir = root
        ai = OpenAIGateway(settings)
        ai.project_context = "previous"
        pipeline = TestClipPipeline(ProjectStore(root), ai, settings)
        editor = MagicMock()
        editor.available.return_value = True
        editor.media_duration.return_value = audio_seconds
        editor.inspect_short.return_value = {"vertical": True, "duration_seconds": 4}
        pipeline.editor = editor
        def voice(**kwargs):
            path = kwargs["project_path"]
            (path / "subtitles").mkdir()
            (path / "subtitles" / "narration.srt").write_text("captions")
            target = path / "audio" / "narration.mp3"
            target.write_bytes(b"a" * 2048)
            return target
        with patch.object(ai, "ask", side_effect=["An atmospheric garden shot.", '{"approved":true,"prompt":"An atmospheric garden shot, vertical."}']), \
             patch("core.test_clip.VoiceAgent.run", side_effect=voice) as tts, \
             patch("core.test_clip.ElevenLabsClient"), patch("core.test_clip.VeoClient") as veo:
            veo.return_value.generate_all.return_value = [root / "clip.mp4"]
            if audio_seconds > 3.8:
                with self.assertRaisesRegex(RuntimeError, "nie mieści"):
                    pipeline.run("garden")
                veo.return_value.generate_all.assert_not_called()
            else:
                project = pipeline.run("garden")
                self.assertTrue((project.path / "test_mode.json").is_file())
                self.assertFalse((project.path / "07_youtube.json").exists())
                veo.return_value.generate_all.assert_called_once()
                self.assertEqual(veo.return_value.generate_all.call_args.kwargs["max_clips"], 1)
                self.assertTrue(editor.render_clips.call_args.kwargs["test_mode"])
                self.assertFalse((root / "_memory" / "studio_lessons.json").exists())
                with self.assertRaisesRegex(RuntimeError, "krótki test"):
                    ContentPipeline(pipeline.store, ai, settings).finish_existing(project.path)
            tts.assert_called_once()
            self.assertEqual(ai.project_context, "previous")

    def test_sample_limits_paid_calls_and_cannot_become_full_project(self):
        with TemporaryDirectory() as tmp:
            self.run_sample(Path(tmp))

    def test_long_test_voice_stops_before_veo_without_paid_retry(self):
        with TemporaryDirectory() as tmp:
            self.run_sample(Path(tmp), audio_seconds=5)

    def test_real_ffmpeg_four_second_output(self):
        editor = FFmpegEditor()
        executable = editor._executable()
        if not executable:
            self.skipTest("FFmpeg unavailable")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip, audio = root / "clip.mp4", root / "voice.wav"
            subprocess.run([executable, "-y", "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30",
                            "-t", "4", "-c:v", "libx264", str(clip)], check=True, capture_output=True)
            subprocess.run([executable, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            str(audio)], check=True, capture_output=True)
            output = editor.render_clips(clips=[clip], audio=audio, output=root / "test.mp4",
                                         aspect_ratio="9:16", duration_seconds=4, test_mode=True)
            info = editor.inspect_short(output)
            self.assertEqual((info["width"], info["height"]), (720, 1280))
            self.assertAlmostEqual(info["duration_seconds"], 4, delta=.1)

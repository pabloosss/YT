import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from core.channel_memory import ChannelMemory
from core.config import load_settings
from core.openai_gateway import OpenAIGateway
from core.json_utils import loads_relaxed
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.stream_filter import VisibleStream
from core.web_research import normalize_results, ResearchUnavailable
from agents.research import ResearchAgent


class ReliabilityTests(unittest.TestCase):
    def test_memory_survives_restart_and_validates_before_write(self):
        with TemporaryDirectory() as temp:
            memory = ChannelMemory(Path(temp))
            memory.save({"rules": "Bez clickbaitu", "knowledge": "Daty wymagają źródeł"})
            self.assertIn("Bez clickbaitu", ChannelMemory(Path(temp)).context())
            original = memory.path.read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                memory.save({"rules": "x" * 4001})
            self.assertEqual(original, memory.path.read_text(encoding="utf-8"))
            memory.path.write_text("broken", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                memory.load()
            self.assertEqual(memory.path.read_text(encoding="utf-8"), "broken")

    def test_source_validation_deduplication_and_empty_error(self):
        result = normalize_results("historia", [
            {"href": "javascript:alert(1)"},
            {"href": "https://example.org/a#b", "title": "Source", "body": "x" * 2000},
            {"href": "https://example.org/a#c"},
            {"href": "https://user:password@example.org"}])
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(len(result["sources"][0]["excerpt"]), 700)
        with self.assertRaises(ResearchUnavailable):
            normalize_results("historia", [])

    def test_repairs_missing_commas_in_showrunner_json(self):
        raw = """{
          "shots": [
            {
              "shot": "1",
              "duration_sec": 5,
              "visual": "Kot w cieniu"
              "camera": "Zbliżenie",
              "lightyng": "Ciemne",
              "purpose": "Hook"
            }
          ]
        }"""
        data = loads_relaxed(raw)
        self.assertEqual(data["shots"][0]["camera"], "Zbliżenie")

    def test_showrunner_accepts_wrapped_shots_and_lighting_typo(self):
        from agents.showrunner import ShowrunnerAgent
        from unittest.mock import MagicMock
        ai = MagicMock(demo_mode=False)
        ai.ask.return_value = '{"shots":[{"shot":1,"duration_sec":4,"visual":"Kot","camera":"Zoom","lightyng":"Ciemne","purpose":"Hook"}]}'
        shots = ShowrunnerAgent(ai).run(topic="koty", script="tekst")
        self.assertEqual(len(shots), 8)
        self.assertEqual(shots[0]["lighting"], "Ciemne")
        self.assertEqual([shot["duration_sec"] for shot in shots], [4, 4, 4, 4, 4, 4, 3, 3])
        self.assertEqual(sum(shot["duration_sec"] for shot in shots), 30)

    def test_think_tags_never_leak_with_any_chunk_boundary(self):
        original = "Wstęp<think>PRIVATE</think>Wynik<think>SECRET</think>Koniec"
        for size in range(1, len(original)):
            stream = VisibleStream()
            output = "".join(stream.feed(original[i:i+size]) for i in range(0, len(original), size)) + stream.finish()
            self.assertEqual(output, "WstępWynikKoniec")
        stream = VisibleStream()
        self.assertEqual(stream.feed("OK<think>private") + stream.finish(), "OK")

    def test_project_names_do_not_collide(self):
        with TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp))
            self.assertNotEqual(store.create("same").path, store.create("same").path)

    def pipeline(self, root):
        settings = load_settings()
        settings.demo_mode = True
        settings.ai_provider = "demo"
        settings.generate_media = False
        settings.projects_dir = root
        return ContentPipeline(ProjectStore(root), OpenAIGateway(settings), settings)

    def test_profile_snapshot_demo_offline_and_completion(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ChannelMemory(root / "_memory").save({"style": "krótkie zdania"})
            pipeline = self.pipeline(root)
            with patch("core.pipeline.search_web", side_effect=AssertionError("demo must be offline")):
                project = pipeline.run("Demo")
            self.assertIn("krótkie zdania", (project.path / "00_channel_profile.txt").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((project.path / "state.json").read_text(encoding="utf-8"))["status"], "completed")
            self.assertEqual(pipeline.ai.channel_context, "")

    def test_failed_research_preserves_project_and_does_not_make_script(self):
        with TemporaryDirectory() as temp:
            pipeline = self.pipeline(Path(temp))
            pipeline.settings.demo_mode = False
            with patch("core.pipeline.search_web", side_effect=ResearchUnavailable("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    pipeline.run("test")
            project = next(p for p in Path(temp).iterdir() if p.is_dir())
            self.assertEqual(json.loads((project / "state.json").read_text(encoding="utf-8"))["status"], "failed")
            self.assertFalse((project / "02_script.txt").exists())

    def test_stop_keeps_finished_stage_and_stops_next_agent(self):
        with TemporaryDirectory() as temp:
            pipeline = self.pipeline(Path(temp))
            cancel = threading.Event()
            def callback(agent, state):
                if agent == "Research" and state == "DONE":
                    cancel.set()
            with self.assertRaises(RuntimeError):
                pipeline.run("test", callback, cancel=cancel)
            project = next(p for p in Path(temp).iterdir() if p.is_dir())
            self.assertTrue((project / "01_research.md").exists())
            self.assertFalse((project / "02_script.txt").exists())
            self.assertEqual(json.loads((project / "state.json").read_text(encoding="utf-8"))["status"], "cancelled")

    def test_channel_context_is_in_actual_model_instructions(self):
        settings = load_settings()
        settings.ai_provider = "ollama"
        settings.demo_mode = False
        ai = OpenAIGateway(settings)
        ai.channel_context = "Unikaj clickbaitu"
        with patch.object(ai, "_ask_ollama", return_value="ok") as ask:
            ai.ask("Scenariusz", "film")
            self.assertIn("Unikaj clickbaitu", ask.call_args.kwargs["instructions"])

    def test_research_includes_real_source_and_labels_offline(self):
        settings = load_settings()
        settings.demo_mode = False
        ai = OpenAIGateway(settings)
        evidence = normalize_results("test", [{"href": "https://example.org", "title": "Title", "body": "Excerpt"}])
        with patch.object(ai, "ask", return_value="Research"):
            self.assertIn("https://example.org", ResearchAgent(ai).run(topic="test", evidence=evidence))
            self.assertIn("SZKIC OFFLINE", ResearchAgent(ai).run(topic="test"))

    def test_ram_defaults_and_clamping(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
            self.assertEqual(settings.ollama_ram_limit_percent, 50)
            self.assertEqual(settings.ollama_num_ctx, 4096)
            self.assertEqual(settings.veo_aspect_ratio, "9:16")
            self.assertEqual(settings.veo_max_clips, 3)
            self.assertEqual(settings.veo_duration_seconds, 4)
            self.assertEqual(settings.veo_model, "veo-3.1-lite-generate-preview")
            self.assertEqual(settings.elevenlabs_model, "eleven_turbo_v2_5")
            self.assertEqual(settings.ollama_model, "qwen3:14b")
        with patch.dict(os.environ, {"OLLAMA_RAM_LIMIT_PERCENT": "99"}):
            self.assertEqual(load_settings().ollama_ram_limit_percent, 90)


if __name__ == "__main__":
    unittest.main()


class ConnectionAndTopicsTests(unittest.TestCase):
    def test_project_allows_only_supported_qwen_modes(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "demo", "AI_STUDIO_DEMO": "true",
                                     "OLLAMA_MODEL": "qwen3:30b", "OLLAMA_RAM_LIMIT_PERCENT": "50",
                                     "OLLAMA_NUM_CTX": "8192"}, clear=True):
            settings = load_settings()
            self.assertEqual(settings.ai_provider, "ollama")
            self.assertFalse(settings.demo_mode)
            self.assertEqual(settings.ollama_model, "qwen3:14b")
            self.assertEqual(settings.ollama_ram_limit_percent, 50)
        with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen3:8b", "AI_STUDIO_SETTINGS_VERSION": "6"}, clear=True):
            self.assertEqual(load_settings().ollama_model, "qwen3:8b")

    def test_ai_plans_queries_then_uses_real_search_results(self):
        from agents.topics import TopicsAgent
        from unittest.mock import MagicMock
        ai = MagicMock(demo_mode=False)
        ai.ask.side_effect = ['["zamek historia", "zamek archeologia"]', "Temat: zamek [1]"]
        sources = normalize_results("query", [{"href": "https://example.org", "body": "Evidence"}])
        saved = {}
        with patch("agents.topics.search_web", return_value=sources) as search:
            output = TopicsAgent(ai).run(subject="historia", save=lambda name, data: saved.update({name: data}))
        self.assertEqual(search.call_count, 2)
        self.assertEqual(ai.ask.call_count, 2)
        self.assertIn("Evidence", ai.ask.call_args.kwargs["prompt"])
        self.assertIn("https://example.org", output)
        self.assertEqual(len(saved["00_sources.json"]["sources"]), 1)

    def test_ai_query_objects_are_accepted(self):
        from agents.topics import TopicsAgent
        from unittest.mock import MagicMock
        ai = MagicMock(demo_mode=False)
        ai.ask.side_effect = [
            '[{"query": "koty religia Egiptu"}, {"query": "koty archeologia Egiptu"}]',
            "Tematy [1]",
        ]
        sources = normalize_results("query", [{"href": "https://example.org", "body": "Evidence"}])
        with patch("agents.topics.search_web", return_value=sources) as search:
            output = TopicsAgent(ai).run(subject="koty w Egipcie")
        self.assertEqual(search.call_count, 2)
        self.assertIn("https://example.org", output)

    def test_search_error_is_not_replaced_by_invented_topics(self):
        from agents.topics import TopicsAgent
        from unittest.mock import MagicMock
        ai = MagicMock(demo_mode=False)
        ai.ask.return_value = '["query"]'
        with patch("agents.topics.search_web", side_effect=ResearchUnavailable("network")):
            with self.assertRaises(ResearchUnavailable):
                TopicsAgent(ai).run(subject="historia")
        self.assertEqual(ai.ask.call_count, 1)

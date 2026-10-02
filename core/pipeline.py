from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from agents.graphics import GraphicsAgent
from agents.metadata import MetadataAgent
from agents.quality import QualityAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.showrunner import ShowrunnerAgent
from agents.voice import VoiceAgent
from core.channel_memory import ChannelMemory
from core.config import Settings
from core.editor import FFmpegEditor
from core.openai_gateway import OpenAIGateway
from core.project_store import ProjectStore
from core.veo_client import VeoClient
from core.web_research import search_web


StatusCallback = Callable[[str, str], None]


class ContentPipeline:
    def __init__(self, store: ProjectStore, ai: OpenAIGateway, settings: Settings):
        self.store = store
        self.ai = ai
        self.settings = settings
        self.editor = FFmpegEditor(settings.ffmpeg_path)

        self.research_agent = ResearchAgent(ai)
        self.script_agent = ScriptAgent(ai)
        self.showrunner_agent = ShowrunnerAgent(ai)
        self.graphics_agent = GraphicsAgent(ai)
        self.voice_agent = VoiceAgent(ai)
        self.quality_agent = QualityAgent()
        self.metadata_agent = MetadataAgent(ai)

    def run(self, topic: str, status: StatusCallback | None = None, *, online: bool = True,
            cancel: threading.Event | None = None):
        callback = status or (lambda _agent, _state: None)
        cancel = cancel or threading.Event()
        project = self.store.create(topic)
        current = "Przygotowanie"

        def report(agent, state):
            nonlocal current
            if cancel.is_set():
                raise InterruptedError("Zatrzymano po bieżącym etapie. Wyniki zapisano.")
            current = agent
            project.write_json("state.json", {"status": "running", "agent": agent, "stage_status": state})
            callback(agent, state)

        try:
            profile = ChannelMemory(self.settings.projects_dir / "_memory").context()
            project.write_text("00_channel_profile.txt", profile)
            self.ai.channel_context = profile
            result = self._run_project(topic, project, report, online)
            project.write_json("state.json", {"status": "completed", "agent": current})
            return result
        except Exception as exc:
            state = "cancelled" if isinstance(exc, InterruptedError) else "failed"
            project.write_json("state.json", {"status": state, "agent": current, "error": str(exc)})
            callback(current, "STOP" if state == "cancelled" else "BŁĄD")
            raise RuntimeError(f"{exc}\nZapisane wyniki: {project.path}") from exc
        finally:
            self.ai.channel_context = ""

    def _run_project(self, topic, project, status, online):
        self.ai.set_active_agent("Research")
        status("Research", "RUNNING")
        evidence = search_web(topic) if online and not self.ai.demo_mode else None
        project.write_json("00_sources.json", evidence or {"sources": [], "mode": "demo" if self.ai.demo_mode else "offline"})
        research = self.research_agent.run(topic=topic, evidence=evidence)
        project.write_text("01_research.md", research)
        status("Research", "DONE")

        self.ai.set_active_agent("Scenariusz")
        status("Scenariusz", "RUNNING")
        script = self.script_agent.run(topic=topic, research=research)
        project.write_text("02_script.txt", script)
        status("Scenariusz", "DONE")

        self.ai.set_active_agent("Showrunner")
        status("Showrunner", "RUNNING")
        shots = self.showrunner_agent.run(topic=topic, script=script)
        project.write_json("03_shots.json", shots)
        status("Showrunner", "DONE")

        self.ai.set_active_agent("Grafika")
        status("Grafika", "PROMPTY")
        prompts = self.graphics_agent.run(
            topic=topic,
            shots=shots,
            aspect_ratio=self.settings.veo_aspect_ratio,
        )
        # Old filename stays for compatibility with projects and quality checks.
        project.write_json("04_image_prompts.json", prompts)
        project.write_json("04_video_prompts.json", prompts)

        video_clips: list[Path] = []
        if self.settings.generate_media:
            veo = VeoClient(
                self.settings.google_api_key,
                model=self.settings.veo_model,
                aspect_ratio=self.settings.veo_aspect_ratio,
                resolution=self.settings.veo_resolution,
            )
            video_clips = veo.generate_all(
                prompts=prompts,
                output_dir=project.path / "video_clips",
                max_clips=self.settings.veo_max_clips,
                progress=lambda index, total: status("Grafika", f"VEO {index}/{total}"),
            )
        status("Grafika", "DONE" if video_clips else "PROMPTS ONLY")

        status("Lektor", "RUNNING")
        project.write_text("05_narration.txt", script)
        audio_file = self.voice_agent.run(
            script=script,
            project_path=project.path,
            generate_audio=self.settings.generate_media,
            api_key=self.settings.elevenlabs_api_key,
            voice_id=self.settings.elevenlabs_voice_id,
            model=self.settings.elevenlabs_model,
        )
        subtitle_file = project.path / "subtitles" / "narration.srt"
        status("Lektor", "DONE" if audio_file else "TEXT ONLY")

        status("Montaż", "RUNNING")
        video_file = None
        if self.settings.generate_media and video_clips:
            music = Path(self.settings.music_path) if self.settings.music_path else None
            video_file = self.editor.render_clips(
                clips=video_clips,
                audio=audio_file,
                subtitles=subtitle_file if self.settings.burn_subtitles else None,
                music=music,
                aspect_ratio=self.settings.veo_aspect_ratio,
                output=project.path / "exports" / "final.mp4",
            )
            status("Montaż", "DONE")
        else:
            status("Montaż", "SKIPPED")

        status("Kontrola", "RUNNING")
        quality = self.quality_agent.run(project_path=project.path, shots=shots)
        quality["media_enabled"] = self.settings.generate_media
        quality["generated_images"] = 0
        quality["generated_clips"] = len(video_clips)
        quality["audio_generated"] = bool(audio_file)
        quality["subtitles_generated"] = subtitle_file.exists()
        quality["video_generated"] = bool(video_file)
        project.write_json("06_quality.json", quality)
        status("Kontrola", "DONE" if quality["approved"] else "ISSUES")

        self.ai.set_active_agent("YouTube Meta")
        status("YouTube Meta", "RUNNING")
        metadata = self.metadata_agent.run(topic=topic, script=script)
        project.write_json("07_youtube.json", metadata)
        status("YouTube Meta", "DONE")

        project.write_json(
            "pipeline_result.json",
            {
                "project": str(project.path),
                "images": [],
                "clips": [str(path) for path in video_clips],
                "audio": str(audio_file) if audio_file else None,
                "subtitles": str(subtitle_file) if subtitle_file.exists() else None,
                "video": str(video_file) if video_file else None,
                "quality_approved": bool(quality["approved"]),
            },
        )
        return project

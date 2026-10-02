from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import json
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
from core.elevenlabs_client import ElevenLabsClient
from core.openai_gateway import OpenAIGateway
from core.project_store import ProjectStore
from core.subtitles import text_to_srt
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

    def finish_existing(
        self,
        project_path: Path,
        status: StatusCallback | None = None,
        *,
        allow_generate_veo: bool = False,
        online: bool = True,
    ) -> Path:
        """Continue from the first missing stage. Existing paid media is always reused."""
        callback = status or (lambda _agent, _state: None)
        project_path = Path(project_path)
        topic = project_path.name
        metadata_path = project_path / "project.json"
        if metadata_path.exists():
            try:
                topic = str(json.loads(metadata_path.read_text(encoding="utf-8")).get("title") or topic)
            except (OSError, ValueError):
                pass

        script_path = project_path / "02_script.txt"
        clips = sorted(path for path in (project_path / "video_clips").glob("*.mp4")
                       if path.is_file() and path.stat().st_size >= 1024)
        if not clips:
            clips = sorted(path for path in (project_path / "video").glob("*.mp4")
                           if path.is_file() and path.stat().st_size >= 1024)
        if not clips and not allow_generate_veo:
            raise RuntimeError("Projekt nie ma klipów Veo. Wybierz płatne dokończenie ze starego scenariusza.")
        if not self.editor.available():
            raise RuntimeError("FFmpeg nie jest dostępny. Uruchom ponownie run_windows.bat.")

        if not script_path.exists() or not script_path.read_text(encoding="utf-8").strip():
            research_path = project_path / "01_research.md"
            if research_path.exists() and research_path.read_text(encoding="utf-8").strip():
                research = research_path.read_text(encoding="utf-8")
            else:
                callback("Research", "WZNAWIAM")
                evidence = search_web(topic) if online and not self.ai.demo_mode else None
                (project_path / "00_sources.json").write_text(
                    json.dumps(evidence or {"sources": [], "mode": "offline"}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                research = self.research_agent.run(topic=topic, evidence=evidence)
                research_path.write_text(research, encoding="utf-8")
                callback("Research", "DONE")
            callback("Scenariusz", "WZNAWIAM")
            script_path.write_text(self.script_agent.run(topic=topic, research=research), encoding="utf-8")
            callback("Scenariusz", "DONE")

        script = script_path.read_text(encoding="utf-8")
        audio = project_path / "audio" / "narration.mp3"
        subtitles = project_path / "subtitles" / "narration.srt"
        audio_ready = audio.exists() and audio.stat().st_size >= 1024
        if not audio_ready:
            callback("Lektor", "TEST API")
            ElevenLabsClient(self.settings.elevenlabs_api_key).healthcheck(
                self.settings.elevenlabs_voice_id
            )
            callback("Lektor", "GENERUJĘ")
            audio_file = self.voice_agent.run(
                script=script,
                project_path=project_path,
                generate_audio=True,
                api_key=self.settings.elevenlabs_api_key,
                voice_id=self.settings.elevenlabs_voice_id,
                model=self.settings.elevenlabs_model,
            )
            if audio_file is None:
                raise RuntimeError("Nie udało się wygenerować lektora.")
            audio = audio_file
        elif not subtitles.exists() or subtitles.stat().st_size == 0:
            callback("Lektor", "ODTWARZAM NAPISY LOKALNIE")
            text_to_srt(script, subtitles, duration_seconds=30)
        callback("Lektor", "DONE")

        generated_veo = False
        if not clips:
            prompt_path = project_path / "04_video_prompts.json"
            if not prompt_path.exists():
                prompt_path = project_path / "04_image_prompts.json"
            if prompt_path.exists():
                prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
            else:
                shots_path = project_path / "03_shots.json"
                if shots_path.exists():
                    shots = json.loads(shots_path.read_text(encoding="utf-8"))
                else:
                    callback("Showrunner", "ODTWARZAM")
                    shots = self.showrunner_agent.run(topic=topic, script=script)
                    shots_path.write_text(json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8")
                callback("Grafika", "ODTWARZAM PROMPTY")
                prompts = self.graphics_agent.run(topic=topic, shots=shots, aspect_ratio="9:16")
                prompt_path = project_path / "04_video_prompts.json"
                prompt_path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")

            if not isinstance(prompts, list) or not prompts:
                raise RuntimeError("Nie udało się odtworzyć promptów Veo ze starego projektu.")
            callback("Grafika", "TEST VEO")
            veo = VeoClient(
                self.settings.google_api_key,
                model=self.settings.veo_model,
                aspect_ratio="9:16",
                resolution=self.settings.veo_resolution,
            )
            veo.healthcheck()
            clips = veo.generate_all(
                prompts=prompts,
                output_dir=project_path / "video_clips",
                max_clips=self.settings.veo_max_clips,
                progress=lambda index, total: callback("Grafika", f"VEO {index}/{total}"),
            )
            generated_veo = True
            callback("Grafika", "DONE")

        callback("Montaż", "RUNNING")
        music = Path(self.settings.music_path) if self.settings.music_path else None
        output = self.editor.render_clips(
            clips=clips,
            audio=audio,
            subtitles=subtitles if self.settings.burn_subtitles else None,
            music=music,
            aspect_ratio="9:16",
            output=project_path / "exports" / "final.mp4",
        )
        callback("Montaż", "DONE")

        youtube_path = project_path / "07_youtube.json"
        if not youtube_path.exists():
            self.ai.set_active_agent("YouTube Meta")
            callback("YouTube Meta", "GENERUJĘ")
            youtube_path.write_text(
                json.dumps(self.metadata_agent.run(topic=topic, script=script), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            callback("YouTube Meta", "DONE")

        (project_path / "recovery_result.json").write_text(
            json.dumps(
                {
                    "reused_veo_clips": 0 if generated_veo else len(clips),
                    "generated_veo_clips": len(clips) if generated_veo else 0,
                    "veo_called_again": generated_veo,
                    "audio": str(audio),
                    "subtitles": str(subtitles) if subtitles.exists() else None,
                    "video": str(output),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (project_path / "state.json").write_text(
            json.dumps({"status": "completed", "agent": "YouTube Meta", "recovered": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

    def _media_preflight(self) -> None:
        if not self.settings.generate_media:
            return
        if not self.editor.available():
            raise RuntimeError("FFmpeg nie jest dostępny. Uruchom ponownie run_windows.bat.")
        # Check both paid services before generating any billable media.
        ElevenLabsClient(self.settings.elevenlabs_api_key).healthcheck(
            self.settings.elevenlabs_voice_id
        )
        VeoClient(
            self.settings.google_api_key,
            model=self.settings.veo_model,
            aspect_ratio=self.settings.veo_aspect_ratio,
            resolution=self.settings.veo_resolution,
        ).healthcheck()

    def _run_project(self, topic, project, status, online):
        status("Lektor", "TEST API")
        self._media_preflight()
        status("Lektor", "GOTOWY" if self.settings.generate_media else "TEXT ONLY")

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

        # Generate the inexpensive voice before billable video clips. A TTS error can no longer
        # waste completed Veo generations.
        status("Lektor", "GENERUJĘ")
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

        self.ai.set_active_agent("Grafika")
        status("Grafika", "PROMPTY")
        prompts = self.graphics_agent.run(
            topic=topic,
            shots=shots,
            aspect_ratio=self.settings.veo_aspect_ratio,
        )
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

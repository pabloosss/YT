from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import json
import math
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
from core.json_utils import loads_relaxed
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

    def _final_ai_review(self, *, project_path: Path, topic: str, narration: str,
                         metadata: dict, video_info: dict) -> dict:
        if self.ai.demo_mode:
            return {
                "approved": bool(video_info.get("short_eligible")),
                "summary": "Kompletna historia z pionowym filmem i metadanymi Shorts.",
                "strengths": ["Pełna narracja", "Pionowy format", "Długość Shorts"],
                "risks": [],
                "video_info": video_info,
            }
        research_path = project_path / "01_research.md"
        shots_path = project_path / "03_shots.json"
        research = research_path.read_text(encoding="utf-8")[:5000] if research_path.exists() else "brak"
        shots = shots_path.read_text(encoding="utf-8")[:5000] if shots_path.exists() else "brak"
        raw = self.ai.ask(
            instructions=(
                "Jesteś końcowym redaktorem i kontrolerem YouTube Shorts. Oceń, czy historia ma hook, logiczne "
                "rozwinięcie i pełne zakończenie, czy nie przeczy researchowi oraz czy metadata pasują do treści. "
                "Uwzględnij parametry techniczne filmu. Nie twierdź, że widziałeś jego klatki. Zablokuj publikację "
                "przy urwanej historii, poważnej sprzeczności, poziomym obrazie albo czasie ponad 3 minuty. "
                "Odpowiadaj wyłącznie poprawnym JSON-em."
            ),
            prompt=(
                f"TEMAT: {topic}\nRESEARCH:\n{research}\n\nLEKTOR:\n{narration}\n\nUJĘCIA:\n{shots}\n\n"
                f"METADATA:\n{json.dumps(metadata, ensure_ascii=False)}\n\n"
                f"PARAMETRY FILMU:\n{json.dumps(video_info, ensure_ascii=False)}\n\n"
                "Zwróć: approved (true/false), summary (2–4 zdania), strengths (lista), risks (lista)."
            ),
        )
        data = loads_relaxed(raw)
        return {
            "approved": data.get("approved") is True and bool(video_info.get("short_eligible")),
            "summary": str(data.get("summary") or "Brak podsumowania."),
            "strengths": [str(x) for x in data.get("strengths", [])] if isinstance(data.get("strengths"), list) else [],
            "risks": [str(x) for x in data.get("risks", [])] if isinstance(data.get("risks"), list) else [],
            "video_info": video_info,
        }

    def _audio_matches(self, project_path: Path, narration: str) -> bool:
        audio = project_path / "audio" / "narration.mp3"
        manifest = project_path / "audio" / "voice_settings.json"
        if not audio.exists() or audio.stat().st_size < 1024 or not manifest.exists():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return data.get("model") == self.settings.elevenlabs_model and data.get("narration") == narration
        except (OSError, ValueError):
            return False

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
        callback("Scenariusz", "REDAKCJA KOŃCOWA")
        narration = self.script_agent.prepare_for_voice(topic=topic, script=script)
        script_path.write_text(narration, encoding="utf-8")
        (project_path / "05_narration.txt").write_text(narration, encoding="utf-8")
        planned_duration = 30 if len(narration.split()) <= 70 else 45 if len(narration.split()) <= 100 else 60
        callback("Scenariusz", "DONE")
        audio = project_path / "audio" / "narration.mp3"
        subtitles = project_path / "subtitles" / "narration.srt"
        audio_ready = self._audio_matches(project_path, narration)
        if not audio_ready:
            callback("Lektor", "TEST API")
            ElevenLabsClient(self.settings.elevenlabs_api_key).healthcheck(
                self.settings.elevenlabs_voice_id
            )
            callback("Lektor", "GENERUJĘ")
            audio_file = self.voice_agent.run(
                script=narration,
                project_path=project_path,
                generate_audio=True,
                api_key=self.settings.elevenlabs_api_key,
                voice_id=self.settings.elevenlabs_voice_id,
                model=self.settings.elevenlabs_model,
            )
            if audio_file is None:
                raise RuntimeError("Nie udało się wygenerować lektora.")
            audio = audio_file
        callback("Lektor", "DONE")

        audio_seconds = self.editor.media_duration(audio)
        if audio_seconds > 58:
            raise RuntimeError(
                f"Lektor trwa {audio_seconds:.1f} s i nie zmieści się w limicie 60 s. "
                "Lokalny redaktor musi skrócić scenariusz; wznów projekt."
            )
        target_duration = max(30, min(60, math.ceil(audio_seconds + 2)))
        if not subtitles.exists() or subtitles.stat().st_size == 0:
            callback("Lektor", "ODTWARZAM NAPISY LOKALNIE")
            text_to_srt(narration, subtitles, duration_seconds=audio_seconds)
        desired_clips = 2 if target_duration <= 45 else 3

        generated_veo = False
        if len(clips) < desired_clips and allow_generate_veo:
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
                    shots = self.showrunner_agent.run(
                        topic=topic, script=narration, target_duration=planned_duration
                    )
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
                duration_seconds=self.settings.veo_duration_seconds,
            )
            veo.healthcheck()
            generated_clips = veo.generate_all(
                prompts=prompts,
                output_dir=project_path / "video_clips",
                max_clips=min(desired_clips, self.settings.veo_max_clips),
                progress=lambda index, total: callback("Grafika", f"VEO {index}/{total}"),
            )
            clips = sorted(set(clips + generated_clips))
            generated_veo = bool(generated_clips)
            callback("Grafika", "DONE")
        if not clips:
            raise RuntimeError("Projekt nie ma prawidłowych klipów Veo do montażu.")

        callback("Montaż", "RUNNING")
        music = Path(self.settings.music_path) if self.settings.music_path else None
        output = self.editor.render_clips(
            clips=clips,
            audio=audio,
            subtitles=subtitles if self.settings.burn_subtitles else None,
            music=music,
            aspect_ratio="9:16",
            duration_seconds=target_duration,
            output=project_path / "exports" / "final.mp4",
        )
        video_info = self.editor.inspect_short(output)
        if not video_info["short_eligible"]:
            raise RuntimeError(
                f"Plik nie spełnia wymagań Shorts: {video_info['width']}x{video_info['height']}, "
                f"{video_info['duration_seconds']} s."
            )
        thumbnail = self.editor.create_thumbnail(output, project_path / "thumbnail" / "thumbnail.jpg")
        callback("Montaż", "DONE")

        youtube_path = project_path / "07_youtube.json"
        if not youtube_path.exists():
            self.ai.set_active_agent("YouTube Meta")
            callback("YouTube Meta", "GENERUJĘ")
            youtube_path.write_text(
                json.dumps(self.metadata_agent.run(topic=topic, script=narration), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            callback("YouTube Meta", "DONE")

        metadata = json.loads(youtube_path.read_text(encoding="utf-8"))
        callback("Kontrola", "PODSUMOWANIE AI")
        review = self._final_ai_review(
            project_path=project_path,
            topic=topic,
            narration=narration,
            metadata=metadata,
            video_info=video_info,
        )
        (project_path / "08_ai_review.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        callback("Kontrola", "ZATWIERDZONE" if review["approved"] else "BLOKADA")

        (project_path / "recovery_result.json").write_text(
            json.dumps(
                {
                    "reused_veo_clips": 0 if generated_veo else len(clips),
                    "generated_veo_clips": len(clips) if generated_veo else 0,
                    "veo_called_again": generated_veo,
                    "audio": str(audio),
                    "subtitles": str(subtitles) if subtitles.exists() else None,
                    "video": str(output),
                    "duration_seconds": target_duration,
                    "thumbnail": str(thumbnail),
                    "ai_review_approved": review["approved"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (project_path / "state.json").write_text(
            json.dumps({"status": "completed", "agent": "Kontrola", "recovered": True}, ensure_ascii=False, indent=2),
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
            duration_seconds=self.settings.veo_duration_seconds,
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
        narration = self.script_agent.prepare_for_voice(topic=topic, script=script)
        project.write_text("02_script.txt", narration)
        project.write_text("05_narration.txt", narration)
        planned_duration = 30 if len(narration.split()) <= 70 else 45 if len(narration.split()) <= 100 else 60
        status("Scenariusz", "DONE")

        self.ai.set_active_agent("Showrunner")
        status("Showrunner", "RUNNING")
        shots = self.showrunner_agent.run(
            topic=topic, script=narration, target_duration=planned_duration
        )
        project.write_json("03_shots.json", shots)
        status("Showrunner", "DONE")

        # Generate the inexpensive voice before billable video clips. A TTS error can no longer
        # waste completed Veo generations.
        status("Lektor", "GENERUJĘ")
        audio_file = self.voice_agent.run(
            script=narration,
            project_path=project.path,
            generate_audio=self.settings.generate_media,
            api_key=self.settings.elevenlabs_api_key,
            voice_id=self.settings.elevenlabs_voice_id,
            model=self.settings.elevenlabs_model,
        )
        subtitle_file = project.path / "subtitles" / "narration.srt"
        status("Lektor", "DONE" if audio_file else "TEXT ONLY")
        if audio_file:
            audio_seconds = self.editor.media_duration(audio_file)
            if audio_seconds > 58:
                raise RuntimeError(
                    f"Lektor trwa {audio_seconds:.1f} s. Lokalny redaktor musi skrócić tekst poniżej 60 sekund."
                )
            target_duration = max(30, min(60, math.ceil(audio_seconds + 2)))
        else:
            target_duration = 30
        desired_clips = 2 if target_duration <= 45 else 3

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
                duration_seconds=self.settings.veo_duration_seconds,
            )
            video_clips = veo.generate_all(
                prompts=prompts,
                output_dir=project.path / "video_clips",
                max_clips=min(desired_clips, self.settings.veo_max_clips),
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
                duration_seconds=target_duration,
                output=project.path / "exports" / "final.mp4",
            )
            video_info = self.editor.inspect_short(video_file)
            if not video_info["short_eligible"]:
                raise RuntimeError(
                    f"Plik nie spełnia wymagań Shorts: {video_info['width']}x{video_info['height']}, "
                    f"{video_info['duration_seconds']} s."
                )
            thumbnail_file = self.editor.create_thumbnail(
                video_file, project.path / "thumbnail" / "thumbnail.jpg"
            )
            status("Montaż", "DONE")
        else:
            video_info = {}
            thumbnail_file = None
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
        metadata = self.metadata_agent.run(topic=topic, script=narration)
        project.write_json("07_youtube.json", metadata)
        status("YouTube Meta", "DONE")

        if video_file:
            self.ai.set_active_agent("Kontrola")
            status("Kontrola", "PODSUMOWANIE AI")
            review = self._final_ai_review(
                project_path=project.path,
                topic=topic,
                narration=narration,
                metadata=metadata,
                video_info=video_info,
            )
            project.write_json("08_ai_review.json", review)
            status("Kontrola", "ZATWIERDZONE" if review["approved"] else "BLOKADA")
        else:
            review = None

        project.write_json(
            "pipeline_result.json",
            {
                "project": str(project.path),
                "images": [],
                "clips": [str(path) for path in video_clips],
                "audio": str(audio_file) if audio_file else None,
                "subtitles": str(subtitle_file) if subtitle_file.exists() else None,
                "video": str(video_file) if video_file else None,
                "duration_seconds": target_duration,
                "thumbnail": str(thumbnail_file) if thumbnail_file else None,
                "ai_review_approved": bool(review and review["approved"]),
                "quality_approved": bool(quality["approved"]),
            },
        )
        return project

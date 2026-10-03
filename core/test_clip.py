"""Explicitly paid, bounded technical rehearsal. Never publishes or teaches memory."""
import json
import math
import threading
from pathlib import Path

from agents.voice import VoiceAgent
from core.channel_memory import ChannelMemory
from core.editor import FFmpegEditor
from core.elevenlabs_client import ElevenLabsClient
from core.json_utils import loads_relaxed
from core.studio_memory import StudioMemory
from core.veo_client import VeoClient


class TestClipPipeline:
    __test__ = False
    NARRATION = "To próba naszego studia."

    def __init__(self, store, ai, settings):
        self.store, self.ai, self.settings = store, ai, settings
        self.editor = FFmpegEditor(settings.ffmpeg_path)

    def run(self, topic: str, *, status=None, cancel=None):
        callback = status or (lambda *_: None)
        cancel = cancel or threading.Event()
        project = self.store.create("TEST 4 s: " + topic)
        project.write_json("test_mode.json", {
            "duration_seconds": 4, "max_veo_clips": 1, "max_tts_requests": 1,
            "publish_allowed": False, "learning_allowed": False,
            "purpose": "Test techniczny, nie gotowy odcinek ani test poprawności faktów.",
        })
        previous = (self.ai.channel_context, self.ai.studio_context, self.ai.project_context)

        def stage(agent, state):
            if cancel.is_set():
                raise InterruptedError("Test zatrzymany. Zachowano gotowe pliki; nie wykonuję kolejnych płatnych etapów.")
            self.ai.set_active_agent(agent)
            project.write_json("state.json", {"status": "running", "agent": agent, "stage_status": state})
            callback(agent, state)

        try:
            self.ai.channel_context = ChannelMemory(self.settings.projects_dir / "_memory").context()
            self.ai.studio_context = StudioMemory(self.settings.projects_dir / "_memory").context()
            self.ai.project_context = "TEST TECHNICZNY: 4 sekundy, jeden klip, bez publikacji i bez uczenia."
            stage("Dyrektor", "TEST POŁĄCZEŃ")
            if not self.editor.available():
                raise RuntimeError("Brak FFmpeg.")
            veo = VeoClient(self.settings.google_api_key, model=self.settings.veo_model,
                            aspect_ratio="9:16", resolution="720p", duration_seconds=4)
            veo.healthcheck()
            ElevenLabsClient(self.settings.elevenlabs_api_key).healthcheck(self.settings.elevenlabs_voice_id)
            stage("Grafika", "PLAN TESTOWEGO KADRU")
            prompt = self.ai.ask(
                instructions="Zwróć wyłącznie krótki angielski prompt jednego 4-sekundowego klipu 9:16. Bez tekstu, logo i dialogów. Spokojny dół kadru pod napisy.",
                prompt=f"Motyw wizualny: {topic[:300]}. To próbka techniczna, nie rekonstrukcja historyczna.",
            ).strip()
            stage("Kontrola", "SPRAWDZAM PROMPT")
            review = loads_relaxed(self.ai.ask(
                instructions="Sprawdź i popraw prompt jednej próbki Veo 4 s, 9:16. Bez napisów i dialogów. Zwróć JSON: approved (bool), prompt (poprawiony tekst). Nie twierdź, że widziałeś klip.",
                prompt=prompt[:1600],
            ))
            if not isinstance(review, dict) or review.get("approved") is not True:
                raise RuntimeError("Kontrola zablokowała plan testu. Nie naliczono generacji mediów.")
            prompt = review.get("prompt")
            if not isinstance(prompt, str) or not 20 <= len(prompt.strip()) <= 2000:
                raise RuntimeError("Niepoprawny prompt testowy. Nie naliczono generacji mediów.")
            project.write_json("04_video_prompts.json", [{"shot": 1, "prompt": prompt}])
            project.write_text("02_script.txt", self.NARRATION)
            stage("Lektor", "JEDNA KRÓTKA GENERACJA")
            audio = VoiceAgent(self.ai).run(
                script=self.NARRATION, project_path=project.path, generate_audio=True,
                api_key=self.settings.elevenlabs_api_key, voice_id=self.settings.elevenlabs_voice_id,
                model=self.settings.elevenlabs_model,
            )
            if audio is None:
                raise RuntimeError("Brak lektora do testu.")
            seconds = self.editor.media_duration(audio)
            if not math.isfinite(seconds) or not 0 < seconds <= 3.8:
                raise RuntimeError("Głos nie mieści się w próbce 4 s. Zachowano audio; nie zamawiam Veo ani kolejnego lektora.")
            captions = project.path / "subtitles" / "narration.srt"
            if not captions.is_file():
                raise RuntimeError("Brak napisów lektora; zatrzymano przed kosztem Veo.")
            stage("Grafika", "VEO 1/1 · 4 s")
            clips = veo.generate_all(prompts=[{"shot": 1, "prompt": prompt}],
                                     output_dir=project.path / "video_clips", max_clips=1)
            stage("Montaż", "MONTAŻ TESTU")
            output = self.editor.render_clips(
                clips=clips, output=project.path / "exports" / "test_4s.mp4", audio=audio,
                subtitles=captions, aspect_ratio="9:16", duration_seconds=4, test_mode=True,
            )
            stage("Kontrola", "SPRAWDZAM PARAMETRY")
            info = self.editor.inspect_short(output)
            if not info.get("vertical") or abs(float(info["duration_seconds"]) - 4) > 0.25:
                raise RuntimeError("Test nie spełnia wymagań: pionowy obraz i 4 sekundy.")
            project.write_json("test_result.json", {"video": str(output), "video_info": info,
                                                     "publish_allowed": False, "learning_allowed": False})
            project.write_json("state.json", {"status": "completed", "agent": "Kontrola"})
            callback("Kontrola", "TEST GOTOWY — OBEJRZYJ I ODSŁUCHAJ")
            return project
        except Exception as exc:
            project.write_json("state.json", {"status": "cancelled" if isinstance(exc, InterruptedError) else "failed",
                                              "error": str(exc)})
            raise RuntimeError(f"{exc}\nPliki testu: {project.path}") from exc
        finally:
            self.ai.channel_context, self.ai.studio_context, self.ai.project_context = previous

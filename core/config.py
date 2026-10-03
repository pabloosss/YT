from dataclasses import dataclass
from pathlib import Path
import os
import re

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs) -> None:
        return None

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    ai_provider: str
    openai_api_key: str
    openai_model: str

    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    ollama_keep_alive: str
    ollama_num_ctx: int
    ollama_num_predict: int
    ollama_num_thread: int
    ollama_think: bool
    ollama_unload_after_request: bool
    ollama_ram_limit_percent: int

    demo_mode: bool
    projects_dir: Path
    ffmpeg_path: str

    generate_media: bool
    image_model: str
    image_size: str
    image_quality: str
    tts_model: str
    tts_voice: str
    tts_instructions: str

    google_api_key: str = ""
    elevenlabs_api_key: str = ""
    veo_model: str = "veo-3.1-lite-generate-preview"
    veo_aspect_ratio: str = "9:16"
    veo_resolution: str = "720p"
    veo_max_clips: int = 3
    veo_duration_seconds: int = 4
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_turbo_v2_5"
    burn_subtitles: bool = True
    music_path: str = ""
    quality_mode: str = "careful"


def load_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    ram_percent = int(os.getenv("OLLAMA_RAM_LIMIT_PERCENT", "50"))
    context = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    # Aplikacja jest wyspecjalizowana w pionowych filmach TikTok/YouTube Shorts.
    aspect_ratio = "9:16"
    requested_model = os.getenv("OLLAMA_MODEL", "qwen3:14b").strip().lower()
    try:
        settings_version = int(os.getenv("AI_STUDIO_SETTINGS_VERSION", "0"))
    except ValueError:
        settings_version = 0
    # Version 7 preserves a model explicitly selected from the local Ollama inventory.
    supported = requested_model in {"qwen3:8b", "qwen3:14b"}
    valid_name = bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,159}", requested_model))
    ollama_model = requested_model if (settings_version >= 7 and valid_name or settings_version >= 6 and supported) else "qwen3:14b"

    return Settings(
        ai_provider="ollama",
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6").strip(),

        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=ollama_model,
        ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "900")),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "15m").strip() or "15m",
        ollama_num_ctx=max(2048, context),
        ollama_num_predict=max(128, int(os.getenv("OLLAMA_NUM_PREDICT", "2048"))),
        ollama_num_thread=max(0, int(os.getenv("OLLAMA_NUM_THREAD", "0"))),
        ollama_think=_as_bool(os.getenv("OLLAMA_THINK"), default=True),
        ollama_unload_after_request=_as_bool(os.getenv("OLLAMA_UNLOAD_AFTER_REQUEST"), default=False),
        ollama_ram_limit_percent=min(90, max(20, ram_percent)),

        demo_mode=False,
        projects_dir=Path(os.getenv("PROJECTS_DIR", "projects")),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg",

        generate_media=_as_bool(os.getenv("GENERATE_MEDIA"), default=False),
        image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip(),
        image_size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip(),
        image_quality=os.getenv("OPENAI_IMAGE_QUALITY", "low").strip(),
        tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip(),
        tts_voice=os.getenv("OPENAI_TTS_VOICE", "coral").strip(),
        tts_instructions=os.getenv(
            "OPENAI_TTS_INSTRUCTIONS",
            "Mów naturalnie po polsku, energicznie, ale bez przesadnej teatralności.",
        ).strip(),

        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
        veo_model="veo-3.1-lite-generate-preview",
        veo_aspect_ratio=aspect_ratio,
        veo_resolution=os.getenv("VEO_RESOLUTION", "720p").strip() or "720p",
        veo_max_clips=3,
        veo_duration_seconds=4,
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "").strip(),
        elevenlabs_model="eleven_turbo_v2_5",
        burn_subtitles=_as_bool(os.getenv("BURN_SUBTITLES"), default=True),
        music_path=os.getenv("MUSIC_PATH", "").strip(),
        quality_mode="standard" if os.getenv("STUDIO_QUALITY_MODE") == "standard" else "careful",
    )

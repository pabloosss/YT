from dataclasses import dataclass
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        return None

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    openai_api_key: str
    openai_model: str
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


def load_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return Settings(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6").strip(),
        demo_mode=_as_bool(os.getenv("AI_STUDIO_DEMO"), default=not bool(api_key)) or not bool(api_key),
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
    )

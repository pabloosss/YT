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
    ai_provider: str
    openai_api_key: str
    openai_model: str
    ollama_url: str
    ollama_model: str
    ollama_timeout: int
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
    provider = os.getenv(
        "AI_PROVIDER",
        "openai" if api_key else "demo",
    ).strip().lower()

    if provider not in {"demo", "openai", "ollama"}:
        provider = "demo"

    demo_mode = _as_bool(
        os.getenv("AI_STUDIO_DEMO"),
        default=(provider == "demo"),
    )

    if provider == "openai" and not api_key:
        demo_mode = True

    return Settings(
        ai_provider=provider,
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6").strip(),
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:30b").strip(),
        ollama_timeout=int(os.getenv("OLLAMA_TIMEOUT", "900")),
        demo_mode=demo_mode,
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

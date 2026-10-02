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


def load_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return Settings(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol").strip(),
        demo_mode=_as_bool(os.getenv("AI_STUDIO_DEMO"), default=not bool(api_key)) or not bool(api_key),
        projects_dir=Path(os.getenv("PROJECTS_DIR", "projects")),
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg",
    )

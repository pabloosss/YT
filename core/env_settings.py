from __future__ import annotations

from pathlib import Path

from core.config import Settings


def save_ai_settings(settings: Settings, env_path: Path = Path(".env")) -> None:
    try:
        from dotenv import set_key
    except ImportError as exc:
        raise RuntimeError(
            "Brakuje python-dotenv. Uruchom ponownie run_windows.bat."
        ) from exc

    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")

    values = {
        "AI_STUDIO_SETTINGS_VERSION": "4",
        "GENERATE_MEDIA": "true" if settings.generate_media else "false",
        "AI_PROVIDER": "ollama",
        "AI_STUDIO_DEMO": "false",
        "OLLAMA_URL": settings.ollama_url,
        "OLLAMA_MODEL": "qwen3:8b",
        "OLLAMA_TIMEOUT": str(settings.ollama_timeout),
        "OLLAMA_KEEP_ALIVE": settings.ollama_keep_alive,
        "OLLAMA_NUM_CTX": str(settings.ollama_num_ctx),
        "OLLAMA_NUM_PREDICT": str(settings.ollama_num_predict),
        "OLLAMA_NUM_THREAD": str(settings.ollama_num_thread),
        "OLLAMA_THINK": "true" if settings.ollama_think else "false",
        "OLLAMA_UNLOAD_AFTER_REQUEST": (
            "true" if settings.ollama_unload_after_request else "false"
        ),
        "OLLAMA_RAM_LIMIT_PERCENT": str(settings.ollama_ram_limit_percent),
    }

    for key, value in values.items():
        set_key(str(env_path), key, value, quote_mode="never")


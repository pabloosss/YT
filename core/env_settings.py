from __future__ import annotations

from pathlib import Path

from core.config import Settings


def save_ai_settings(settings: Settings, env_path: Path = Path(".env")) -> None:
    try:
        from dotenv import set_key
    except ImportError as exc:
        raise RuntimeError("Brakuje python-dotenv. Uruchom ponownie run_windows.bat.") from exc

    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")

    values = {
        "AI_STUDIO_SETTINGS_VERSION": "6",
        "GENERATE_MEDIA": "true" if settings.generate_media else "false",
        "AI_PROVIDER": "ollama",
        "AI_STUDIO_DEMO": "false",
        "OLLAMA_URL": settings.ollama_url,
        "OLLAMA_MODEL": settings.ollama_model,
        "OLLAMA_TIMEOUT": str(settings.ollama_timeout),
        "OLLAMA_KEEP_ALIVE": settings.ollama_keep_alive,
        "OLLAMA_NUM_CTX": str(settings.ollama_num_ctx),
        "OLLAMA_NUM_PREDICT": str(settings.ollama_num_predict),
        "OLLAMA_NUM_THREAD": str(settings.ollama_num_thread),
        "OLLAMA_THINK": "true" if settings.ollama_think else "false",
        "OLLAMA_UNLOAD_AFTER_REQUEST": "true" if settings.ollama_unload_after_request else "false",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_RAM_LIMIT_PERCENT": str(settings.ollama_ram_limit_percent),
        "GOOGLE_API_KEY": settings.google_api_key,
        "ELEVENLABS_API_KEY": settings.elevenlabs_api_key,
        "VEO_MODEL": settings.veo_model,
        "VEO_ASPECT_RATIO": settings.veo_aspect_ratio,
        "VEO_RESOLUTION": settings.veo_resolution,
        "VEO_MAX_CLIPS": str(settings.veo_max_clips),
        "VEO_DURATION_SECONDS": str(settings.veo_duration_seconds),
        "ELEVENLABS_VOICE_ID": settings.elevenlabs_voice_id,
        "ELEVENLABS_MODEL": settings.elevenlabs_model,
        "BURN_SUBTITLES": "true" if settings.burn_subtitles else "false",
        "MUSIC_PATH": settings.music_path,
    }

    for key, value in values.items():
        set_key(str(env_path), key, value, quote_mode="auto")

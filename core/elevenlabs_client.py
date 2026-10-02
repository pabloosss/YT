from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from core.subtitles import alignment_to_srt, clean_narration


class ElevenLabsClient:
    api_url = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str, *, timeout: int = 180):
        self.api_key = api_key.strip()
        self.timeout = timeout

    def _request(self, path: str, *, data: dict | None = None) -> dict:
        if not self.api_key:
            raise RuntimeError("Brak ELEVENLABS_API_KEY. Wpisz klucz w Ustawieniach.")
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = Request(
            self.api_url + path,
            data=body,
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:700]
            if "quota_exceeded" in detail or "credits remaining" in detail:
                message = "Limit kredytów klucza ElevenLabs jest za niski dla tego lektora. Zwiększ limit klucza lub saldo konta."
            elif exc.code == 401:
                message = "ElevenLabs odrzucił klucz. Utwórz nowy klucz i nie używaj klucza ujawnionego w rozmowie."
            elif exc.code == 403:
                message = "Klucz ElevenLabs nie ma wymaganych uprawnień. Włącz Text to Speech oraz odczyt Voices."
            elif exc.code == 429:
                message = "ElevenLabs odrzucił żądanie z powodu limitu lub braku kredytów."
            else:
                message = f"ElevenLabs HTTP {exc.code}"
            raise RuntimeError(f"{message} Szczegóły: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Nie można połączyć z ElevenLabs: {exc}") from exc

    def voices(self) -> list[dict]:
        payload = self._request("/voices")
        return list(payload.get("voices") or [])

    def resolve_voice_id(self, preferred: str = "") -> str:
        if preferred.strip():
            return preferred.strip()
        voices = self.voices()
        if not voices:
            raise RuntimeError("Na koncie ElevenLabs nie znaleziono żadnego głosu.")
        return str(voices[0].get("voice_id") or "")

    def healthcheck(self, preferred_voice_id: str = "") -> str:
        voices = self.voices()
        if not voices:
            raise RuntimeError("Na koncie ElevenLabs nie znaleziono żadnego głosu.")
        available = {str(item.get("voice_id") or "") for item in voices}
        voice_id = preferred_voice_id.strip() or str(voices[0].get("voice_id") or "")
        if preferred_voice_id.strip() and voice_id not in available:
            raise RuntimeError("Wybrany Voice ID nie jest dostępny dla tego klucza ElevenLabs.")
        return f"ElevenLabs: połączono · głos {voice_id}"

    def synthesize(
        self,
        *,
        text: str,
        output_audio: Path,
        output_srt: Path,
        voice_id: str = "",
        model_id: str = "eleven_flash_v2_5",
    ) -> tuple[Path, Path]:
        narration = clean_narration(text)
        if not narration:
            raise RuntimeError("Scenariusz nie zawiera tekstu dla lektora.")
        resolved_voice = self.resolve_voice_id(voice_id)
        payload = self._request(
            f"/text-to-speech/{quote(resolved_voice, safe='')}/with-timestamps?output_format=mp3_44100_128",
            data={
                "text": narration,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.55,
                    "similarity_boost": 0.75,
                    "style": 0.15,
                    "use_speaker_boost": True,
                },
            },
        )
        audio = payload.get("audio_base64")
        if not audio:
            raise RuntimeError("ElevenLabs nie zwrócił pliku audio.")
        output_audio.parent.mkdir(parents=True, exist_ok=True)
        output_audio.write_bytes(base64.b64decode(audio))
        alignment = payload.get("normalized_alignment") or payload.get("alignment")
        if not alignment:
            raise RuntimeError("ElevenLabs nie zwrócił synchronizacji napisów.")
        alignment_to_srt(alignment, output_srt)
        (output_audio.parent / "alignment.json").write_text(
            json.dumps(alignment, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_audio.parent / "narration_clean.txt").write_text(narration, encoding="utf-8")
        return output_audio, output_srt

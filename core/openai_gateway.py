from __future__ import annotations

import base64
from pathlib import Path

from core.config import Settings


class OpenAIGateway:
    """Centralna bramka do OpenAI. Agenci nie przechowują klucza API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def demo_mode(self) -> bool:
        return self.settings.demo_mode

    def _get_client(self):
        if self.demo_mode:
            raise RuntimeError("Wywołanie API w trybie DEMO.")

        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Brakuje biblioteki openai. Uruchom: pip install -r requirements.txt"
                ) from exc
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def ask(self, instructions: str, prompt: str) -> str:
        client = self._get_client()
        response = client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=prompt,
        )
        return response.output_text.strip()

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        model: str,
        size: str,
        quality: str,
    ) -> Path:
        client = self._get_client()
        result = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        image_base64 = result.data[0].b64_json
        if not image_base64:
            raise RuntimeError("OpenAI nie zwrócił danych obrazu.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(image_base64))
        return output_path

    def text_to_speech(
        self,
        *,
        text: str,
        output_path: Path,
        model: str,
        voice: str,
        instructions: str,
    ) -> Path:
        client = self._get_client()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            instructions=instructions,
        ) as response:
            response.stream_to_file(output_path)

        return output_path

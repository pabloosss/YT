from __future__ import annotations

from core.config import Settings


class OpenAIGateway:
    """Centralna bramka do OpenAI. Agenci nie przechowują klucza API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def demo_mode(self) -> bool:
        return self.settings.demo_mode

    def ask(self, instructions: str, prompt: str) -> str:
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

        response = self._client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=prompt,
        )
        return response.output_text.strip()

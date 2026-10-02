from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.config import Settings


class OpenAIGateway:
    """Wspólna bramka AI dla agentów.

    Nazwa klasy została zachowana dla zgodności ze starszym kodem, ale tekst
    może być generowany przez OpenAI albo lokalną Ollamę.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def demo_mode(self) -> bool:
        return self.settings.demo_mode

    @property
    def provider(self) -> str:
        if self.demo_mode:
            return "demo"
        return self.settings.ai_provider

    def ask(self, instructions: str, prompt: str) -> str:
        if self.demo_mode:
            raise RuntimeError("Wywołanie AI w trybie DEMO.")

        if self.settings.ai_provider == "ollama":
            return self._ask_ollama(instructions=instructions, prompt=prompt)

        if self.settings.ai_provider == "openai":
            return self._ask_openai(instructions=instructions, prompt=prompt)

        raise RuntimeError(f"Nieobsługiwany AI_PROVIDER: {self.settings.ai_provider}")

    def healthcheck(self) -> str:
        if self.demo_mode:
            return "Tryb DEMO jest aktywny. Żaden zewnętrzny model nie jest używany."

        if self.settings.ai_provider == "ollama":
            try:
                payload = self._ollama_get("/api/tags", timeout=5)
            except Exception as exc:
                raise RuntimeError(
                    "Nie mogę połączyć się z Ollamą. Upewnij się, że Ollama działa "
                    f"pod {self.settings.ollama_url}. Szczegóły: {exc}"
                ) from exc

            models = []
            for item in payload.get("models", []):
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    models.append(name)

            expected = self.settings.ollama_model
            if expected not in models:
                installed = ", ".join(models) if models else "brak"
                return (
                    f"Ollama działa, ale nie widzę modelu {expected}. "
                    f"Zainstalowane modele: {installed}"
                )

            return f"Ollama działa. Model {expected} jest gotowy."

        if self.settings.ai_provider == "openai":
            if not self.settings.openai_api_key:
                raise RuntimeError("Brakuje OPENAI_API_KEY.")
            return f"OpenAI jest skonfigurowane. Model tekstowy: {self.settings.openai_model}."

        raise RuntimeError(f"Nieobsługiwany AI_PROVIDER: {self.settings.ai_provider}")

    def _ask_openai(self, *, instructions: str, prompt: str) -> str:
        client = self._get_openai_client()
        response = client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=prompt,
        )
        return response.output_text.strip()

    def _ask_ollama(self, *, instructions: str, prompt: str) -> str:
        payload = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "keep_alive": self.settings.ollama_keep_alive,
        }

        try:
            response = self._ollama_post(
                "/api/chat",
                payload,
                timeout=self.settings.ollama_timeout,
            )
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama zwróciła HTTP {exc.code}: {details}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Nie można połączyć się z lokalną Ollamą. "
                f"Sprawdź, czy działa pod {self.settings.ollama_url}."
            ) from exc

        message = response.get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError(f"Ollama zwróciła pustą odpowiedź: {response}")
        return content

    def _ollama_get(self, endpoint: str, *, timeout: int) -> dict:
        request = Request(
            f"{self.settings.ollama_url}{endpoint}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _ollama_post(self, endpoint: str, payload: dict, *, timeout: int) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.settings.ollama_url}{endpoint}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_openai_client(self):
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "Ta funkcja wymaga OPENAI_API_KEY. "
                "Lokalna Ollama obsługuje obecnie agentów tekstowych; "
                "grafika i TTS OpenAI wymagają osobnego klucza."
            )

        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Brakuje biblioteki openai. Uruchom: pip install -r requirements.txt"
                ) from exc
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        model: str,
        size: str,
        quality: str,
    ) -> Path:
        client = self._get_openai_client()
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
        client = self._get_openai_client()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            instructions=instructions,
        ) as response:
            response.stream_to_file(output_path)

        return output_path

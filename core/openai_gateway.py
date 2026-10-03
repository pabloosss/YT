from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.config import Settings
from core.json_utils import strip_thinking
from core.studio_memory import BASE_STUDIO_INSTRUCTIONS
from core.stream_filter import VisibleStream


TraceCallback = Callable[[dict], None]


class OpenAIGateway:
    """Wspólna bramka AI dla agentów."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self._trace_callback: TraceCallback | None = None
        self._active_agent = "AI"
        self.channel_context = ""
        self.studio_context = ""

    @property
    def demo_mode(self) -> bool:
        return self.settings.demo_mode

    @property
    def provider(self) -> str:
        if self.demo_mode:
            return "demo"
        return self.settings.ai_provider

    def set_trace_callback(self, callback: TraceCallback | None) -> None:
        self._trace_callback = callback

    def set_active_agent(self, name: str) -> None:
        self._active_agent = name

    def _trace(self, event_type: str, **data) -> None:
        if not self._trace_callback:
            return
        payload = {
            "type": event_type,
            "agent": self._active_agent,
            **data,
        }
        try:
            self._trace_callback(payload)
        except Exception:
            pass

    def ask(self, instructions: str, prompt: str) -> str:
        instructions = BASE_STUDIO_INSTRUCTIONS + "\n\nINSTRUKCJA BIEŻĄCEGO AGENTA:\n" + instructions
        if self.studio_context:
            instructions += (
                "\n\nPamięć doświadczeń produkcyjnych. Stosuj ją tylko, gdy pasuje do zadania; "
                "nie traktuj jej jako źródła faktów o odcinku:\n" + self.studio_context
            )
        if self.channel_context:
            instructions += "\nProfil kanału podany przez użytkownika (wiedza wymaga weryfikacji):\n" + self.channel_context
        if self.demo_mode:
            raise RuntimeError("Wywołanie AI w trybie DEMO.")

        if self.settings.ai_provider == "ollama":
            return self._ask_ollama(instructions=instructions, prompt=prompt)

        if self.settings.ai_provider == "openai":
            return self._ask_openai(instructions=instructions, prompt=prompt)

        raise RuntimeError(f"Nieobsługiwany AI_PROVIDER: {self.settings.ai_provider}")

    def list_models(self) -> list[str]:
        if self.settings.ai_provider != "ollama":
            return []
        payload = self._ollama_get("/api/tags", timeout=5)
        models: list[str] = []
        for item in payload.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                models.append(name)
        return sorted(models)

    def runtime_status(self) -> dict:
        if self.settings.ai_provider != "ollama":
            return {"models": []}
        return self._ollama_get("/api/ps", timeout=5)

    def unload_model(self) -> None:
        if self.settings.ai_provider != "ollama":
            return
        self._ollama_post(
            "/api/generate",
            {
                "model": self.settings.ollama_model,
                "keep_alive": 0,
                "stream": False,
            },
            timeout=30,
        )

    def healthcheck(self) -> str:
        if self.demo_mode:
            return "Tryb DEMO jest aktywny. Żaden zewnętrzny model nie jest używany."

        if self.settings.ai_provider == "ollama":
            try:
                models = self.list_models()
            except Exception as exc:
                raise RuntimeError(
                    "Nie mogę połączyć się z Ollamą. Upewnij się, że Ollama działa "
                    f"pod {self.settings.ollama_url}. Szczegóły: {exc}"
                ) from exc

            expected = self.settings.ollama_model
            if expected not in models:
                installed = ", ".join(models) if models else "brak"
                return (
                    f"Ollama działa, ale nie widzę modelu {expected}. "
                    f"Zainstalowane modele: {installed}"
                )

            return (
                f"Ollama działa. Model {expected} jest gotowy. "
                f"Kontekst: {self.settings.ollama_num_ctx} tokenów."
            )

        if self.settings.ai_provider == "openai":
            if not self.settings.openai_api_key:
                raise RuntimeError("Brakuje OPENAI_API_KEY.")
            return f"OpenAI jest skonfigurowane. Model tekstowy: {self.settings.openai_model}."

        raise RuntimeError(f"Nieobsługiwany AI_PROVIDER: {self.settings.ai_provider}")

    def _ask_openai(self, *, instructions: str, prompt: str) -> str:
        self._trace(
            "start",
            provider="openai",
            model=self.settings.openai_model,
            message="Wysyłam zadanie do modelu.",
        )
        client = self._get_openai_client()
        response = client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=prompt,
        )
        text = response.output_text.strip()
        self._trace(
            "result",
            text=text,
            chars=len(text),
            message="Odpowiedź gotowa.",
        )
        return text

    def _ask_ollama(self, *, instructions: str, prompt: str) -> str:
        options = {
            "num_ctx": self.settings.ollama_num_ctx,
            "num_predict": self.settings.ollama_num_predict,
        }
        if self.settings.ollama_num_thread > 0:
            options["num_thread"] = self.settings.ollama_num_thread

        keep_alive = (
            "0"
            if self.settings.ollama_unload_after_request
            else self.settings.ollama_keep_alive
        )

        payload = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "think": self.settings.ollama_think,
            "keep_alive": keep_alive,
            "options": options,
        }

        self._trace(
            "start",
            provider="ollama",
            model=self.settings.ollama_model,
            num_ctx=self.settings.ollama_num_ctx,
            num_predict=self.settings.ollama_num_predict,
            message="Model rozpoczął pracę.",
        )

        request = Request(
            f"{self.settings.ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/x-ndjson",
            },
            method="POST",
        )

        chunks: list[str] = []
        visible = VisibleStream()
        thinking_announced = False
        final_event: dict = {}

        try:
            with urlopen(request, timeout=self.settings.ollama_timeout) as response:
                for raw_line in response:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue

                    event = json.loads(raw_line.decode("utf-8"))
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))

                    message = event.get("message") or {}

                    # Ollama może zwracać osobne pole "thinking".
                    # Nie ujawniamy jego treści; pokazujemy tylko status pracy.
                    if message.get("thinking") and not thinking_announced:
                        thinking_announced = True
                        self._trace(
                            "phase",
                            message="Model wykonuje wewnętrzną analizę…",
                        )

                    piece = str(message.get("content") or "")
                    if piece:
                        chunks.append(piece)
                        safe_piece = visible.feed(piece)
                        if safe_piece:
                            self._trace("chunk", text=safe_piece)

                    if event.get("done"):
                        final_event = event

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

        tail = visible.finish()
        if tail:
            self._trace("chunk", text=tail)
        if not final_event:
            raise RuntimeError("Ollama przerwała odpowiedź przed zakończeniem. Spróbuj ponownie.")

        content = strip_thinking("".join(chunks).strip())
        if not content:
            raise RuntimeError("Ollama zwróciła pustą odpowiedź.")

        total_ns = int(final_event.get("total_duration") or 0)
        eval_ns = int(final_event.get("eval_duration") or 0)
        prompt_tokens = int(final_event.get("prompt_eval_count") or 0)
        output_tokens = int(final_event.get("eval_count") or 0)

        total_s = total_ns / 1_000_000_000 if total_ns else 0.0
        eval_s = eval_ns / 1_000_000_000 if eval_ns else 0.0
        tokens_per_second = output_tokens / eval_s if eval_s > 0 else 0.0

        self._trace(
            "metrics",
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_seconds=round(total_s, 2),
            tokens_per_second=round(tokens_per_second, 2),
            message="Odpowiedź gotowa.",
        )

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
                "Lokalna Ollama obsługuje agentów tekstowych; "
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

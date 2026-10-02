from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import time


class VeoClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "veo-3.1-lite-generate-preview",
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        duration_seconds: int = 4,
        poll_seconds: int = 12,
        timeout_seconds: int = 1800,
    ):
        self.api_key = api_key.strip()
        self.model = model
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self.duration_seconds = 4 if duration_seconds not in {4, 6, 8} else duration_seconds
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def _sdk(self):
        if not self.api_key:
            raise RuntimeError("Brak GOOGLE_API_KEY. Wpisz klucz Google AI Studio w Ustawieniach.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Brakuje pakietu google-genai. Uruchom ponownie run_windows.bat.") from exc
        return genai, types

    def healthcheck(self) -> str:
        genai, _types = self._sdk()
        client = genai.Client(api_key=self.api_key)
        names = []
        for item in client.models.list():
            name = str(getattr(item, "name", ""))
            if "veo" in name.lower():
                names.append(name)
        if not names:
            raise RuntimeError("Klucz Google działa, ale nie widać modelu Veo na tym koncie.")
        return "Google Veo: połączono · " + ", ".join(names[:3])

    def generate_clip(self, *, prompt: str, output: Path) -> Path:
        genai, types = self._sdk()
        client = genai.Client(api_key=self.api_key)
        operation = client.models.generate_videos(
            model=self.model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=self.aspect_ratio,
                resolution=self.resolution,
                duration_seconds=self.duration_seconds,
                number_of_videos=1,
            ),
        )
        deadline = time.monotonic() + self.timeout_seconds
        while not operation.done:
            if time.monotonic() >= deadline:
                raise TimeoutError("Veo nie zakończył generowania w ciągu 30 minut.")
            time.sleep(self.poll_seconds)
            operation = client.operations.get(operation)

        error = getattr(operation, "error", None)
        if error:
            raise RuntimeError(f"Veo zakończyło generowanie błędem: {error}")
        response = getattr(operation, "response", None)
        videos = getattr(response, "generated_videos", None) or []
        if not videos:
            raise RuntimeError("Veo nie zwróciło klipu. Sprawdź limity i filtrowanie bezpieczeństwa.")

        video = videos[0].video
        client.files.download(file=video)
        output.parent.mkdir(parents=True, exist_ok=True)
        video.save(str(output))
        if not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError("Pobrany klip Veo jest pusty.")
        return output

    def generate_all(
        self,
        *,
        prompts: list[dict],
        output_dir: Path,
        max_clips: int,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[Path]:
        selected = self.select_prompts(prompts, max_clips)
        results: list[Path] = []
        for index, item in enumerate(selected, start=1):
            shot = item.get("shot") or index
            target = output_dir / f"shot_{int(shot):03d}.mp4"
            if target.exists() and target.stat().st_size >= 1024:
                results.append(target)
                continue
            if progress:
                progress(index, len(selected))
            results.append(self.generate_clip(prompt=str(item.get("prompt") or ""), output=target))
        return results

    @staticmethod
    def select_prompts(prompts: list[dict], max_clips: int) -> list[dict]:
        limit = max(1, max_clips)
        if len(prompts) <= limit:
            return prompts
        elif limit == 1:
            return [prompts[0]]
        # Preserve the hook and finale, then distribute the remaining paid clips evenly.
        indexes = [round(index * (len(prompts) - 1) / (limit - 1)) for index in range(limit)]
        return [prompts[index] for index in indexes]

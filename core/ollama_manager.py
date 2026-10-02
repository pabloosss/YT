from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class OllamaConnectionState:
    installed: bool
    server_running: bool
    model_installed: bool
    model_loaded: bool
    executable: str | None
    models: list[str]
    loaded_models: list[str]
    message: str

    @property
    def connected(self) -> bool:
        return self.server_running and self.model_installed


class OllamaManager:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:30b",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def find_executable(self) -> Path | None:
        candidates: list[Path] = []

        in_path = shutil.which("ollama")
        if in_path:
            candidates.append(Path(in_path))

        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            candidates.extend(
                [
                    Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe",
                    Path(local_app_data) / "Ollama" / "ollama.exe",
                ]
            )

        user_profile = os.getenv("USERPROFILE")
        if user_profile:
            candidates.append(
                Path(user_profile)
                / "AppData"
                / "Local"
                / "Programs"
                / "Ollama"
                / "ollama.exe"
            )

        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate.resolve()
            except OSError:
                continue

        return None

    def server_running(self) -> bool:
        try:
            self._get_json("/api/tags", timeout=2)
            return True
        except Exception:
            return False

    def start_server(self) -> tuple[bool, str]:
        if self.server_running():
            return True, "Serwer Ollamy już działa."

        executable = self.find_executable()
        if not executable:
            return False, "Nie znaleziono ollama.exe. Zainstaluj Ollamę albo dodaj ją do PATH."

        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )

        try:
            subprocess.Popen(
                [str(executable), "serve"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                cwd=str(executable.parent),
            )
        except Exception as exc:
            return False, f"Nie udało się uruchomić Ollamy: {exc}"

        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.server_running():
                return True, "Ollama została uruchomiona przez AI Content Studio."
            time.sleep(0.4)

        return False, "Uruchomiono ollama.exe, ale serwer nie odpowiedział na porcie 11434."

    def list_models(self) -> list[str]:
        payload = self._get_json("/api/tags", timeout=5)
        result: list[str] = []
        for item in payload.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                result.append(name)
        return sorted(set(result))

    def model_size_bytes(self, model: str | None = None) -> int:
        target = model or self.model
        payload = self._get_json("/api/tags", timeout=5)
        target_lower = target.lower()

        for item in payload.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name.lower() == target_lower:
                try:
                    return int(item.get("size") or 0)
                except (TypeError, ValueError):
                    return 0

        return 0

    def loaded_models(self) -> list[str]:
        payload = self._get_json("/api/ps", timeout=5)
        result: list[str] = []
        for item in payload.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                result.append(name)
        return sorted(set(result))

    def load_model(
        self,
        *,
        model: str | None = None,
        keep_alive: str = "15m",
        num_ctx: int = 8192,
    ) -> None:
        target = model or self.model
        self._post_json(
            "/api/generate",
            {
                "model": target,
                "prompt": "",
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"num_ctx": num_ctx},
            },
            timeout=900,
        )

    def unload_model(self, model: str | None = None) -> None:
        target = model or self.model
        self._post_json(
            "/api/generate",
            {
                "model": target,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
            timeout=30,
        )

    def pull_model(self, model: str | None = None) -> tuple[bool, str]:
        target = model or self.model
        executable = self.find_executable()
        if not executable:
            return False, "Nie znaleziono ollama.exe."

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            completed = subprocess.run(
                [str(executable), "pull", target],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                creationflags=creationflags,
                timeout=7200,
            )
        except subprocess.TimeoutExpired:
            return False, f"Pobieranie {target} przekroczyło limit czasu."
        except Exception as exc:
            return False, f"Nie udało się pobrać modelu: {exc}"

        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            return False, output or f"ollama pull zakończyło się kodem {completed.returncode}."

        return True, output or f"Model {target} został pobrany."

    def inspect(self, model: str | None = None) -> OllamaConnectionState:
        target = model or self.model
        executable = self.find_executable()
        installed = executable is not None

        if not self.server_running():
            return OllamaConnectionState(
                installed=installed,
                server_running=False,
                model_installed=False,
                model_loaded=False,
                executable=str(executable) if executable else None,
                models=[],
                loaded_models=[],
                message=(
                    "Ollama jest zainstalowana, ale serwer nie działa."
                    if installed
                    else "Ollama nie została znaleziona."
                ),
            )

        try:
            models = self.list_models()
        except Exception:
            models = []

        try:
            loaded = self.loaded_models()
        except Exception:
            loaded = []

        model_installed = self._model_matches(target, models)
        model_loaded = self._model_matches(target, loaded)

        if not model_installed:
            message = f"Serwer Ollamy działa, ale model {target} nie jest pobrany."
        elif model_loaded:
            message = f"Połączono. {target} jest załadowany i gotowy."
        else:
            message = f"Połączono. {target} jest dostępny; zostanie załadowany przy użyciu."

        return OllamaConnectionState(
            installed=installed,
            server_running=True,
            model_installed=model_installed,
            model_loaded=model_loaded,
            executable=str(executable) if executable else None,
            models=models,
            loaded_models=loaded,
            message=message,
        )

    @staticmethod
    def _model_matches(target: str, names: list[str]) -> bool:
        target_lower = target.lower()
        target_base = target_lower.split(":", 1)[0]

        for name in names:
            lowered = name.lower()
            if lowered == target_lower:
                return True
            if ":" not in target_lower and lowered.split(":", 1)[0] == target_base:
                return True

        return False

    def _get_json(self, endpoint: str, *, timeout: int) -> dict:
        request = Request(
            f"{self.base_url}{endpoint}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, endpoint: str, payload: dict, *, timeout: int) -> dict:
        request = Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(
                f"Nie można połączyć się z Ollamą pod {self.base_url}."
            ) from exc

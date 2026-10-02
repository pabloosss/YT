"""User-owned channel instructions; generated content never becomes trusted memory."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

FIELDS = ("name", "audience", "style", "rules", "knowledge")


class ChannelMemory:
    def __init__(self, root: Path):
        self.path = root / "channel_profile.json"

    def load(self) -> dict:
        if not self.path.exists():
            return {key: "" for key in FIELDS}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Profil musi być obiektem JSON")
            return {key: str(value.get(key, "")) for key in FIELDS}
        except (ValueError, OSError) as exc:
            raise RuntimeError(f"Nie można odczytać pamięci {self.path}. Plik pozostawiono bez zmian: {exc}") from exc

    def save(self, profile: dict) -> None:
        clean = {key: str(profile.get(key, "")).strip() for key in FIELDS}
        if sum(map(len, clean.values())) > 4000:
            raise ValueError("Pamięć może mieć maksymalnie 4000 znaków, aby zostawić kontekst na pracę agentów.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(clean, stream, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def context(self) -> str:
        profile = self.load()
        return "\n".join(f"{key}: {profile[key]}" for key in FIELDS if profile[key])[:4000]

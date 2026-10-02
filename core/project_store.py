from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import re
import unicodedata
from uuid import uuid4


@dataclass(slots=True)
class Project:
    title: str
    path: Path

    def write_text(self, filename: str, content: str) -> Path:
        target = self.path / filename
        target.write_text(content, encoding="utf-8")
        return target

    def write_json(self, filename: str, data: object) -> Path:
        target = self.path / filename
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, title: str) -> Project:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.root / f"{stamp}_{_slugify(title)}_{uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=False)

        metadata = {
            "title": title,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "version": "0.8.0",
        }
        (path / "project.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        for folder in ("images", "audio", "video", "exports"):
            (path / folder).mkdir(exist_ok=True)

        return Project(title=title, path=path)


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return cleaned[:64] or "projekt"


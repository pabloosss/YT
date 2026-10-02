from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def readable_slug(value: str, fallback: str = "ujecie") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
    return cleaned[:70] or fallback


def _metadata_text(metadata: dict, key: str) -> str:
    value = metadata.get(key, {})
    raw = str(value.get("value") or "") if isinstance(value, dict) else str(value or "")
    raw = re.sub(r"<[^>]+>", " ", unescape(raw))
    return re.sub(r"\s+", " ", raw).strip()


class MediaLibrary:
    """Persistent local catalogue of generated and freely licensed shot sources."""

    def __init__(self, projects_root: Path):
        self.root = Path(projects_root) / "_media_library"
        self.images = self.root / "images"
        self.videos = self.root / "videos"
        self.manifest = self.root / "manifest.json"
        self.images.mkdir(parents=True, exist_ok=True)
        self.videos.mkdir(parents=True, exist_ok=True)

    def _records(self) -> list[dict]:
        if not self.manifest.exists():
            return []
        try:
            data = json.loads(self.manifest.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save(self, records: list[dict]) -> None:
        self.manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    def archive(self, source: Path, *, kind: str, description_pl: str, prompt: str = "",
                tags: list[str] | None = None, source_url: str = "", license_name: str = "",
                author: str = "", project: str = "") -> Path:
        payload_hash = sha256(source.read_bytes()).hexdigest()
        records = self._records()
        existing = next((item for item in records if item.get("sha256") == payload_hash), None)
        if existing:
            existing["use_count"] = int(existing.get("use_count") or 0) + 1
            existing["last_used_at"] = datetime.now(timezone.utc).isoformat()
            self._save(records)
            return self.root / str(existing["path"])

        folder = self.videos if kind == "video" else self.images
        suffix = source.suffix.lower() or (".mp4" if kind == "video" else ".jpg")
        target = folder / f"{readable_slug(description_pl)}_{payload_hash[:8]}{suffix}"
        shutil.copy2(source, target)
        now = datetime.now(timezone.utc).isoformat()
        records.append({
            "id": payload_hash[:16],
            "type": kind,
            "path": target.relative_to(self.root).as_posix(),
            "description_pl": description_pl,
            "prompt": prompt,
            "tags": [str(item) for item in (tags or [])],
            "source_url": source_url,
            "license": license_name,
            "author": author,
            "project": project,
            "sha256": payload_hash,
            "use_count": 1,
            "created_at": now,
            "last_used_at": now,
        })
        self._save(records)
        return target

    def commons_image(self, *, query: str, description_pl: str, tags: list[str],
                      work_dir: Path, shot_number: int, excluded_urls: set[str]) -> tuple[Path, dict]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"file:{query[:180]}",
            "gsrnamespace": "6",
            "gsrlimit": "10",
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": "1400",
            "iiextmetadatafilter": "LicenseShortName|Artist|Credit|ImageDescription|UsageTerms",
        }
        request = Request(
            COMMONS_API + "?" + urlencode(params),
            headers={"User-Agent": "AIContentStudio/0.9.6 (local desktop app)"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Wikimedia Commons nie odpowiedziała dla ujęcia {shot_number}: {exc}") from exc

        pages = list((payload.get("query", {}).get("pages") or {}).values())
        for page in pages:
            info_rows = page.get("imageinfo") or []
            if not info_rows:
                continue
            info = info_rows[0]
            mime = str(info.get("mime") or "")
            url = str(info.get("thumburl") or info.get("url") or "")
            parsed = urlparse(url)
            metadata = info.get("extmetadata") or {}
            license_name = _metadata_text(metadata, "LicenseShortName")
            if (
                not mime.startswith("image/")
                or parsed.scheme != "https"
                or parsed.hostname != "upload.wikimedia.org"
                or url in excluded_urls
                or not license_name
            ):
                continue
            image_request = Request(url, headers={"User-Agent": "AIContentStudio/0.9.6"})
            try:
                with urlopen(image_request, timeout=30) as response:
                    data = response.read(MAX_IMAGE_BYTES + 1)
            except Exception:
                continue
            if len(data) > MAX_IMAGE_BYTES:
                continue
            work_dir.mkdir(parents=True, exist_ok=True)
            temporary = work_dir / f"commons_{shot_number:03d}.jpg"
            temporary.write_bytes(data)
            try:
                from PIL import Image
                with Image.open(temporary) as image:
                    image.convert("RGB").save(temporary, "JPEG", quality=92)
            except Exception:
                temporary.unlink(missing_ok=True)
                continue
            details = {
                "source_url": str(info.get("descriptionurl") or url),
                "download_url": url,
                "license": license_name,
                "author": _metadata_text(metadata, "Artist"),
                "credit": _metadata_text(metadata, "Credit"),
                "source_description": _metadata_text(metadata, "ImageDescription"),
                "query": query,
            }
            archived = self.archive(
                temporary,
                kind="image",
                description_pl=description_pl,
                prompt=query,
                tags=tags,
                source_url=details["source_url"],
                license_name=license_name,
                author=details["author"],
            )
            shutil.copy2(archived, temporary)
            return temporary, details
        raise RuntimeError(
            f"Nie znaleziono odpowiedniego, opisanego licencją obrazu Wikimedia dla ujęcia {shot_number}: {query}"
        )

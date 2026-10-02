from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class UploadRequest:
    video_path: Path
    title: str
    description: str
    privacy_status: str = "private"


class YouTubePublisher:
    """Warstwa publikacji.

    v0.2 celowo nie wysyła jeszcze filmu. Następny etap doda OAuth Google
    i wywołanie YouTube Data API. Domyślnie publikacja będzie PRIVATE.
    """

    def validate(self, request: UploadRequest) -> None:
        if not request.video_path.exists():
            raise FileNotFoundError(request.video_path)
        if request.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("Nieprawidłowy privacy_status.")

    def upload(self, request: UploadRequest) -> str:
        self.validate(request)
        raise NotImplementedError("YouTube OAuth nie jest jeszcze skonfigurowany w v0.2.")

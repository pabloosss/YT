from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


@dataclass(slots=True)
class UploadRequest:
    video_path: Path
    title: str
    description: str
    privacy_status: str = "private"
    category_id: str = "22"
    tags: list[str] = field(default_factory=list)
    thumbnail_path: Path | None = None


class YouTubePublisher:
    """OAuth + resumable upload do YouTube Data API v3.

    Wymaga pliku OAuth typu Desktop app z Google Cloud.
    Domyślnie wszystko jest wysyłane jako PRIVATE.
    """

    def __init__(
        self,
        client_secret_file: Path = Path("client_secret.json"),
        token_file: Path = Path("token.json"),
    ):
        self.client_secret_file = client_secret_file
        self.token_file = token_file
        self.last_thumbnail_warning = ""

    def validate(self, request: UploadRequest) -> None:
        if not request.video_path.exists():
            raise FileNotFoundError(request.video_path)
        if request.privacy_status not in {"private", "unlisted", "public"}:
            raise ValueError("Nieprawidłowy privacy_status.")
        if not request.title.strip():
            raise ValueError("Tytuł filmu nie może być pusty.")
        if request.thumbnail_path and not request.thumbnail_path.exists():
            raise FileNotFoundError(request.thumbnail_path)

    def is_configured(self) -> bool:
        return self.client_secret_file.exists()

    def authenticate(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise RuntimeError(
                "Brakuje bibliotek Google. Uruchom: pip install -r requirements.txt"
            ) from exc

        if not self.client_secret_file.exists():
            raise FileNotFoundError(
                f"Brakuje {self.client_secret_file}. Pobierz OAuth Client ID typu Desktop app "
                "z Google Cloud i zapisz go pod tą nazwą."
            )

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_file),
                [YOUTUBE_UPLOAD_SCOPE],
            )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secret_file),
                [YOUTUBE_UPLOAD_SCOPE],
            )
            creds = flow.run_local_server(port=0)
            self.token_file.write_text(creds.to_json(), encoding="utf-8")

        return creds

    def upload(self, request: UploadRequest) -> str:
        self.validate(request)

        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise RuntimeError(
                "Brakuje google-api-python-client. Uruchom: pip install -r requirements.txt"
            ) from exc

        youtube = build("youtube", "v3", credentials=self.authenticate())

        body = {
            "snippet": {
                "title": request.title.strip(),
                "description": request.description,
                "tags": request.tags,
                "categoryId": request.category_id,
            },
            "status": {
                "privacyStatus": request.privacy_status,
            },
        }

        media = MediaFileUpload(
            str(request.video_path),
            chunksize=-1,
            resumable=True,
        )

        operation = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _status, response = operation.next_chunk()

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(f"YouTube nie zwrócił ID filmu: {response}")
        self.last_thumbnail_warning = ""
        if request.thumbnail_path:
            try:
                youtube.thumbnails().set(
                    videoId=str(video_id),
                    media_body=MediaFileUpload(str(request.thumbnail_path), mimetype="image/jpeg"),
                ).execute()
            except Exception as exc:
                self.last_thumbnail_warning = "Film wysłano, ale YouTube odrzucił miniaturę: " + str(exc)
        return str(video_id)

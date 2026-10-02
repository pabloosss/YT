from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from core.config import load_settings
from core.editor import FFmpegEditor
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.youtube_publisher import UploadRequest, YouTubePublisher


AGENTS = [
    "Research",
    "Scenariusz",
    "Showrunner",
    "Grafika",
    "Lektor",
    "Montaż",
    "Kontrola",
    "YouTube Meta",
]


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.3")
        self.geometry("1040x720")
        self.minsize(880, 620)

        self.settings = load_settings()
        self.store = ProjectStore(self.settings.projects_dir)
        self.ai = OpenAIGateway(self.settings)
        self.pipeline = ContentPipeline(self.store, self.ai, self.settings)
        self.editor = FFmpegEditor(self.settings.ffmpeg_path)
        self.publisher = YouTubePublisher()

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_project: Path | None = None
        self.status_vars = {name: tk.StringVar(value="OCZEKUJE") for name in AGENTS}

        self._build_ui()
        self.after(100, self._process_events)

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="AI CONTENT STUDIO", font=("Segoe UI", 20, "bold")).pack(anchor="w")

        mode = "DEMO" if self.settings.demo_mode else f"API · {self.settings.openai_model}"
        ffmpeg = "OK" if self.editor.available() else "BRAK"
        media = "ON" if self.settings.generate_media else "OFF"
        youtube = "GOTOWY" if self.publisher.is_configured() else "BRAK client_secret.json"

        ttk.Label(
            root,
            text=f"Tryb: {mode}    |    Media: {media}    |    FFmpeg: {ffmpeg}    |    YouTube: {youtube}",
        ).pack(anchor="w", pady=(2, 18))

        topic_frame = ttk.LabelFrame(root, text="Nowy projekt", padding=12)
        topic_frame.pack(fill="x")

        self.topic_var = tk.StringVar()
        entry = ttk.Entry(topic_frame, textvariable=self.topic_var, font=("Segoe UI", 12))
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.start_pipeline())
        entry.focus_set()

        self.run_button = ttk.Button(topic_frame, text="Uruchom pipeline", command=self.start_pipeline)
        self.run_button.pack(side="left", padx=(10, 0))

        middle = ttk.Frame(root)
        middle.pack(fill="both", expand=True, pady=14)

        agents_frame = ttk.LabelFrame(middle, text="Agenci", padding=12)
        agents_frame.pack(side="left", fill="y")

        for name in AGENTS:
            row = ttk.Frame(agents_frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=name, width=16).pack(side="left")
            ttk.Label(row, textvariable=self.status_vars[name], width=14).pack(side="left")

        logs_frame = ttk.LabelFrame(middle, text="Log projektu", padding=8)
        logs_frame.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self.log = tk.Text(logs_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)

        bottom = ttk.Frame(root)
        bottom.pack(fill="x")

        self.open_button = ttk.Button(
            bottom,
            text="Otwórz projekt",
            command=self.open_last_project,
            state="disabled",
        )
        self.open_button.pack(side="left")

        ttk.Button(
            bottom,
            text="Katalog projects",
            command=lambda: self._open_folder(self.settings.projects_dir),
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            bottom,
            text="FFmpeg",
            command=self.show_ffmpeg_status,
        ).pack(side="left", padx=(8, 0))

        self.auth_button = ttk.Button(
            bottom,
            text="Połącz YouTube",
            command=self.youtube_auth,
        )
        self.auth_button.pack(side="left", padx=(8, 0))

        self.upload_button = ttk.Button(
            bottom,
            text="Wyślij PRIVATE",
            command=self.publish_last,
            state="disabled",
        )
        self.upload_button.pack(side="left", padx=(8, 0))

        ttk.Label(bottom, text="v0.3").pack(side="right")

    def start_pipeline(self):
        topic = self.topic_var.get().strip()
        if not topic:
            messagebox.showwarning("Brak tematu", "Wpisz temat filmu.")
            return

        self.run_button.configure(state="disabled")
        self.upload_button.configure(state="disabled")
        for var in self.status_vars.values():
            var.set("OCZEKUJE")

        self._write_log(f"Start projektu: {topic}")
        threading.Thread(target=self._pipeline_worker, args=(topic,), daemon=True).start()

    def _pipeline_worker(self, topic: str):
        try:
            project = self.pipeline.run(
                topic,
                status=lambda agent, state: self.events.put(("status", (agent, state))),
            )
            self.events.put(("done", project.path))
        except Exception as exc:
            self.events.put(("pipeline_error", str(exc)))

    def youtube_auth(self):
        if not self.publisher.is_configured():
            messagebox.showwarning(
                "YouTube OAuth",
                "Brakuje client_secret.json. W Google Cloud utwórz OAuth Client ID typu Desktop app "
                "dla YouTube Data API v3 i zapisz pobrany plik jako client_secret.json w katalogu programu.",
            )
            return

        self.auth_button.configure(state="disabled")
        self._write_log("YouTube: uruchamiam OAuth...")
        threading.Thread(target=self._youtube_auth_worker, daemon=True).start()

    def _youtube_auth_worker(self):
        try:
            self.publisher.authenticate()
            self.events.put(("youtube_auth_done", None))
        except Exception as exc:
            self.events.put(("youtube_error", str(exc)))

    def publish_last(self):
        if not self.last_project:
            return

        video = self.last_project / "exports" / "final.mp4"
        metadata_file = self.last_project / "07_youtube.json"

        if not video.exists():
            messagebox.showwarning(
                "Brak filmu",
                "Nie ma exports/final.mp4. Włącz GENERATE_MEDIA=true i upewnij się, że FFmpeg działa.",
            )
            return
        if not metadata_file.exists():
            messagebox.showwarning("Brak metadanych", "Nie znaleziono 07_youtube.json.")
            return

        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        title = str(metadata.get("title") or self.last_project.name)

        if not messagebox.askyesno(
            "Publikacja YouTube",
            f"Wysłać film jako PRIVATE?\n\n{title}",
        ):
            return

        self.upload_button.configure(state="disabled")
        self._write_log("YouTube: rozpoczynam wysyłkę PRIVATE...")
        threading.Thread(
            target=self._upload_worker,
            args=(video, metadata),
            daemon=True,
        ).start()

    def _upload_worker(self, video: Path, metadata: dict):
        try:
            request = UploadRequest(
                video_path=video,
                title=str(metadata.get("title") or video.stem),
                description=str(metadata.get("description") or ""),
                privacy_status="private",
                category_id=str(metadata.get("category_id") or "22"),
                tags=[str(x) for x in metadata.get("tags", [])],
            )
            video_id = self.publisher.upload(request)
            self.events.put(("youtube_uploaded", video_id))
        except Exception as exc:
            self.events.put(("youtube_error", str(exc)))

    def _process_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()

                if kind == "status":
                    agent, state = payload
                    if agent in self.status_vars:
                        self.status_vars[agent].set(state)
                    self._write_log(f"{agent}: {state}")

                elif kind == "done":
                    self.last_project = Path(payload)
                    self._write_log(f"Gotowe: {self.last_project}")
                    self.open_button.configure(state="normal")
                    self.run_button.configure(state="normal")
                    if (self.last_project / "exports" / "final.mp4").exists():
                        self.upload_button.configure(state="normal")
                    messagebox.showinfo("Gotowe", "Pipeline zakończony.")

                elif kind == "pipeline_error":
                    self._write_log(f"BŁĄD PIPELINE: {payload}")
                    self.run_button.configure(state="normal")
                    messagebox.showerror("Błąd pipeline", str(payload))

                elif kind == "youtube_auth_done":
                    self._write_log("YouTube: OAuth zakończony.")
                    self.auth_button.configure(state="normal")
                    messagebox.showinfo("YouTube", "Połączenie z YouTube zostało zapisane w token.json.")

                elif kind == "youtube_uploaded":
                    self._write_log(f"YouTube: wysłano film. ID: {payload}")
                    self.upload_button.configure(state="normal")
                    messagebox.showinfo("YouTube", f"Film wysłany jako PRIVATE.\nID: {payload}")

                elif kind == "youtube_error":
                    self._write_log(f"YouTube BŁĄD: {payload}")
                    self.auth_button.configure(state="normal")
                    if self.last_project and (self.last_project / "exports" / "final.mp4").exists():
                        self.upload_button.configure(state="normal")
                    messagebox.showerror("YouTube", str(payload))

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    def show_ffmpeg_status(self):
        messagebox.showinfo("FFmpeg", self.editor.version())

    def _write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_last_project(self):
        if self.last_project:
            self._open_folder(self.last_project)

    @staticmethod
    def _open_folder(path: Path):
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve()

        if os.name == "nt":
            os.startfile(resolved)  # type: ignore[attr-defined]
        elif os.name == "posix":
            subprocess.Popen(["xdg-open", str(resolved)])


if __name__ == "__main__":
    StudioApp().mainloop()

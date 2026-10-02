from __future__ import annotations

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


AGENTS = ["Research", "Scenariusz", "Showrunner", "Grafika", "Lektor"]


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.2")
        self.geometry("980x680")
        self.minsize(820, 580)

        self.settings = load_settings()
        self.store = ProjectStore(self.settings.projects_dir)
        self.ai = OpenAIGateway(self.settings)
        self.pipeline = ContentPipeline(self.store, self.ai)
        self.editor = FFmpegEditor(self.settings.ffmpeg_path)

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
        ttk.Label(root, text=f"Tryb: {mode}    |    FFmpeg: {ffmpeg}").pack(anchor="w", pady=(2, 18))

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
            row.pack(fill="x", pady=6)
            ttk.Label(row, text=name, width=16).pack(side="left")
            ttk.Label(row, textvariable=self.status_vars[name], width=12).pack(side="left")

        logs_frame = ttk.LabelFrame(middle, text="Log projektu", padding=8)
        logs_frame.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self.log = tk.Text(logs_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)

        bottom = ttk.Frame(root)
        bottom.pack(fill="x")

        self.open_button = ttk.Button(
            bottom,
            text="Otwórz ostatni projekt",
            command=self.open_last_project,
            state="disabled",
        )
        self.open_button.pack(side="left")

        ttk.Button(
            bottom,
            text="Katalog projects",
            command=lambda: self._open_folder(self.settings.projects_dir),
        ).pack(side="left", padx=8)

        ttk.Button(
            bottom,
            text="Sprawdź FFmpeg",
            command=self.show_ffmpeg_status,
        ).pack(side="left")

        ttk.Label(bottom, text="v0.2").pack(side="right")

    def start_pipeline(self):
        topic = self.topic_var.get().strip()
        if not topic:
            messagebox.showwarning("Brak tematu", "Wpisz temat filmu.")
            return

        self.run_button.configure(state="disabled")
        for var in self.status_vars.values():
            var.set("OCZEKUJE")

        self._write_log(f"Start projektu: {topic}")
        threading.Thread(target=self._worker, args=(topic,), daemon=True).start()

    def _worker(self, topic: str):
        try:
            project = self.pipeline.run(
                topic,
                status=lambda agent, state: self.events.put(("status", (agent, state))),
            )
            self.events.put(("done", project.path))
        except Exception as exc:
            self.events.put(("error", str(exc)))

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
                    messagebox.showinfo("Gotowe", "Pipeline zakończony. Pliki projektu zostały zapisane.")
                elif kind == "error":
                    self._write_log(f"BŁĄD: {payload}")
                    self.run_button.configure(state="normal")
                    messagebox.showerror("Błąd", str(payload))
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

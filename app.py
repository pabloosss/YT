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
from core.env_settings import save_ai_settings
from core.openai_gateway import OpenAIGateway
from core.ollama_manager import OllamaManager
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.system_monitor import get_memory_snapshot
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

MEMORY_PROFILES = {
    "Niski RAM": {
        "num_ctx": 4096,
        "num_predict": 1024,
        "keep_alive": "0s",
        "unload": True,
        "think": False,
    },
    "Balans": {
        "num_ctx": 8192,
        "num_predict": 2048,
        "keep_alive": "15m",
        "unload": False,
        "think": True,
    },
    "Jakość": {
        "num_ctx": 16384,
        "num_predict": 4096,
        "keep_alive": "30m",
        "unload": False,
        "think": True,
    },
}


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.6")
        self.geometry("1180x780")
        self.minsize(980, 680)

        self.settings = load_settings()
        self.store = ProjectStore(self.settings.projects_dir)
        self.ai = OpenAIGateway(self.settings)
        self.ai.set_trace_callback(
            lambda event: self.events.put(("trace", event))
        )
        self.pipeline = ContentPipeline(self.store, self.ai, self.settings)
        self.editor = FFmpegEditor(self.settings.ffmpeg_path)
        self.publisher = YouTubePublisher()
        self.ollama = OllamaManager(
            base_url=self.settings.ollama_url,
            model=self.settings.ollama_model,
        )

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_project: Path | None = None
        self.status_vars = {
            name: tk.StringVar(value="OCZEKUJE")
            for name in AGENTS
        }

        self.header_status_var = tk.StringVar()
        self.memory_status_var = tk.StringVar(value="RAM: sprawdzanie...")
        self.ollama_status_var = tk.StringVar(value="Ollama: sprawdzanie...")
        self.trace_metrics_var = tk.StringVar(value="Brak metryk.")
        self.connection_status_var = tk.StringVar(value="AI: sprawdzanie połączenia…")
        self.connection_detail_var = tk.StringVar(
            value="Program automatycznie wykryje i uruchomi lokalną Ollamę."
        )
        self.connection_state = "checking"

        self.provider_var = tk.StringVar(value=self.settings.ai_provider)
        self.model_var = tk.StringVar(value=self.settings.ollama_model)
        self.profile_var = tk.StringVar(value="Balans")
        self.ctx_var = tk.StringVar(value=str(self.settings.ollama_num_ctx))
        self.predict_var = tk.StringVar(value=str(self.settings.ollama_num_predict))
        self.threads_var = tk.StringVar(value=str(self.settings.ollama_num_thread))
        self.keep_alive_var = tk.StringVar(value=self.settings.ollama_keep_alive)
        self.think_var = tk.BooleanVar(value=self.settings.ollama_think)
        self.unload_var = tk.BooleanVar(
            value=self.settings.ollama_unload_after_request
        )

        self._build_ui()
        self._update_header()
        self.after(100, self._process_events)
        self.after(500, self._refresh_memory)
        self.after(250, self.auto_connect_ollama)
        self.after(3000, self._periodic_connection_check)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        ttk.Label(
            root,
            text="AI CONTENT STUDIO",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            root,
            textvariable=self.header_status_var,
        ).pack(anchor="w", pady=(2, 8))

        connection_frame = ttk.LabelFrame(
            root,
            text="Połączenie lokalnego AI",
            padding=10,
        )
        connection_frame.pack(fill="x", pady=(0, 12))

        self.connection_label = tk.Label(
            connection_frame,
            textvariable=self.connection_status_var,
            anchor="w",
            font=("Segoe UI", 12, "bold"),
            padx=10,
            pady=7,
        )
        self.connection_label.pack(side="left", fill="x", expand=True)

        ttk.Label(
            connection_frame,
            textvariable=self.connection_detail_var,
            wraplength=430,
        ).pack(side="left", padx=(12, 8))

        self.connect_ai_button = ttk.Button(
            connection_frame,
            text="Połącz / uruchom AI",
            command=self.connect_ollama,
        )
        self.connect_ai_button.pack(side="right")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        self.production_tab = ttk.Frame(notebook, padding=12)
        self.ai_tab = ttk.Frame(notebook, padding=12)
        self.trace_tab = ttk.Frame(notebook, padding=12)

        notebook.add(self.production_tab, text="Produkcja")
        notebook.add(self.ai_tab, text="AI / RAM")
        notebook.add(self.trace_tab, text="Przebieg AI")

        self._build_production_tab()
        self._build_ai_tab()
        self._build_trace_tab()

    def _build_production_tab(self):
        topic_frame = ttk.LabelFrame(
            self.production_tab,
            text="Nowy projekt",
            padding=12,
        )
        topic_frame.pack(fill="x")

        self.topic_var = tk.StringVar()
        entry = ttk.Entry(
            topic_frame,
            textvariable=self.topic_var,
            font=("Segoe UI", 12),
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.start_pipeline())
        entry.focus_set()

        self.run_button = ttk.Button(
            topic_frame,
            text="Uruchom pipeline",
            command=self.start_pipeline,
        )
        self.run_button.pack(side="left", padx=(10, 0))

        middle = ttk.Frame(self.production_tab)
        middle.pack(fill="both", expand=True, pady=12)

        agents_frame = ttk.LabelFrame(
            middle,
            text="Agenci",
            padding=12,
        )
        agents_frame.pack(side="left", fill="y")

        for name in AGENTS:
            row = ttk.Frame(agents_frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=name, width=16).pack(side="left")
            ttk.Label(
                row,
                textvariable=self.status_vars[name],
                width=14,
            ).pack(side="left")

        logs_frame = ttk.LabelFrame(
            middle,
            text="Log projektu",
            padding=8,
        )
        logs_frame.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(14, 0),
        )

        self.log = tk.Text(
            logs_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
        )
        self.log.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.production_tab)
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
            text="Sprawdź AI",
            command=self.check_ai,
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

        ttk.Label(bottom, text="v0.6").pack(side="right")

    def _build_ai_tab(self):
        info = ttk.Label(
            self.ai_tab,
            text=(
                "Qwen3:30b ma stały koszt pamięci na sam model. "
                "Poniższe ustawienia regulują głównie dodatkową pamięć kontekstu, "
                "długość generowania i czas pozostawania modelu w RAM."
            ),
            wraplength=1050,
        )
        info.pack(fill="x", pady=(0, 12))

        settings_frame = ttk.LabelFrame(
            self.ai_tab,
            text="Ustawienia modelu",
            padding=14,
        )
        settings_frame.pack(fill="x")

        self._setting_row(
            settings_frame,
            0,
            "Silnik AI",
            ttk.Combobox(
                settings_frame,
                textvariable=self.provider_var,
                values=["ollama", "openai", "demo"],
                state="readonly",
                width=24,
            ),
        )

        model_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.model_var,
            width=30,
        )
        self.model_combo = model_combo
        self._setting_row(
            settings_frame,
            1,
            "Model Ollama",
            model_combo,
            extra=ttk.Button(
                settings_frame,
                text="Odśwież modele",
                command=self.refresh_models,
            ),
        )

        profile = ttk.Combobox(
            settings_frame,
            textvariable=self.profile_var,
            values=["Niski RAM", "Balans", "Jakość", "Własny"],
            state="readonly",
            width=24,
        )
        profile.bind("<<ComboboxSelected>>", self._profile_changed)
        self._setting_row(
            settings_frame,
            2,
            "Profil pamięci",
            profile,
        )

        ctx_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.ctx_var,
            values=["2048", "4096", "8192", "16384", "32768"],
            width=24,
        )
        self._setting_row(
            settings_frame,
            3,
            "Kontekst (tokeny)",
            ctx_combo,
        )

        predict_spin = ttk.Spinbox(
            settings_frame,
            from_=128,
            to=8192,
            increment=128,
            textvariable=self.predict_var,
            width=26,
        )
        self._setting_row(
            settings_frame,
            4,
            "Maks. odpowiedź",
            predict_spin,
        )

        threads_spin = ttk.Spinbox(
            settings_frame,
            from_=0,
            to=64,
            increment=1,
            textvariable=self.threads_var,
            width=26,
        )
        self._setting_row(
            settings_frame,
            5,
            "Wątki CPU (0 = auto)",
            threads_spin,
        )

        keep_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.keep_alive_var,
            values=["0s", "30s", "1m", "5m", "15m", "30m", "1h", "-1"],
            width=24,
        )
        self._setting_row(
            settings_frame,
            6,
            "Model zostaje w RAM",
            keep_combo,
        )

        checks = ttk.Frame(settings_frame)
        checks.grid(
            row=7,
            column=1,
            columnspan=2,
            sticky="w",
            pady=8,
        )

        ttk.Checkbutton(
            checks,
            text="Głębsze rozumowanie modelu",
            variable=self.think_var,
        ).pack(anchor="w")

        ttk.Checkbutton(
            checks,
            text="Zwalniaj model z RAM po każdym zapytaniu",
            variable=self.unload_var,
        ).pack(anchor="w", pady=(5, 0))

        controls = ttk.Frame(settings_frame)
        controls.grid(
            row=8,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )

        ttk.Button(
            controls,
            text="Zastosuj i zapisz",
            command=self.save_ai_controls,
        ).pack(side="left")

        ttk.Button(
            controls,
            text="Połącz / uruchom Ollamę",
            command=self.connect_ollama,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Uruchom model",
            command=self.load_model_now,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Zwolnij RAM",
            command=self.unload_model_now,
        ).pack(side="left", padx=(8, 0))

        monitor_frame = ttk.LabelFrame(
            self.ai_tab,
            text="Monitor pamięci",
            padding=14,
        )
        monitor_frame.pack(fill="x", pady=(14, 0))

        ttk.Label(
            monitor_frame,
            textvariable=self.memory_status_var,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        self.memory_progress = ttk.Progressbar(
            monitor_frame,
            orient="horizontal",
            mode="determinate",
            maximum=100,
        )
        self.memory_progress.pack(fill="x", pady=8)

        ttk.Label(
            monitor_frame,
            textvariable=self.ollama_status_var,
            wraplength=1040,
        ).pack(anchor="w")

        ttk.Label(
            monitor_frame,
            text=(
                "Uwaga: nie da się ustawić twardego limitu RAM dla qwen3:30b "
                "z poziomu pojedynczego zapytania. Jeśli sam model nie mieści się "
                "w zadanym budżecie, trzeba wybrać mniejszy model."
            ),
            wraplength=1040,
        ).pack(anchor="w", pady=(10, 0))

    def _build_trace_tab(self):
        ttk.Label(
            self.trace_tab,
            text=(
                "Przebieg pokazuje rezultat generowany na żywo, etap pracy oraz metryki. "
                "Ukrytego toku rozumowania modelu nie wyświetlamy."
            ),
            wraplength=1050,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            self.trace_tab,
            textvariable=self.trace_metrics_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        trace_frame = ttk.Frame(self.trace_tab)
        trace_frame.pack(fill="both", expand=True)

        self.trace_text = tk.Text(
            trace_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
        )
        self.trace_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            trace_frame,
            orient="vertical",
            command=self.trace_text.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.trace_text.configure(yscrollcommand=scrollbar.set)

        ttk.Button(
            self.trace_tab,
            text="Wyczyść przebieg",
            command=self._clear_trace,
        ).pack(anchor="e", pady=(8, 0))

    @staticmethod
    def _setting_row(parent, row: int, label: str, widget, extra=None):
        ttk.Label(parent, text=label, width=24).grid(
            row=row,
            column=0,
            sticky="w",
            pady=5,
        )
        widget.grid(
            row=row,
            column=1,
            sticky="w",
            pady=5,
        )
        if extra is not None:
            extra.grid(
                row=row,
                column=2,
                sticky="w",
                padx=(8, 0),
                pady=5,
            )

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

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
        self._write_trace(
            f"\n=== NOWY PROJEKT: {topic} ===\n"
        )

        threading.Thread(
            target=self._pipeline_worker,
            args=(topic,),
            daemon=True,
        ).start()

    def _pipeline_worker(self, topic: str):
        try:
            project = self.pipeline.run(
                topic,
                status=lambda agent, state: self.events.put(
                    ("status", (agent, state))
                ),
            )
            self.events.put(("done", project.path))
        except Exception as exc:
            self.events.put(("pipeline_error", str(exc)))

    # ------------------------------------------------------------------
    # AI settings / memory
    # ------------------------------------------------------------------

    def _profile_changed(self, _event=None):
        profile = self.profile_var.get()
        values = MEMORY_PROFILES.get(profile)
        if not values:
            return

        self.ctx_var.set(str(values["num_ctx"]))
        self.predict_var.set(str(values["num_predict"]))
        self.keep_alive_var.set(str(values["keep_alive"]))
        self.unload_var.set(bool(values["unload"]))
        self.think_var.set(bool(values["think"]))

    def save_ai_controls(self):
        try:
            provider = self.provider_var.get().strip().lower()
            if provider not in {"ollama", "openai", "demo"}:
                raise ValueError("Nieprawidłowy provider.")

            num_ctx = int(self.ctx_var.get())
            num_predict = int(self.predict_var.get())
            num_thread = int(self.threads_var.get())

            if num_ctx < 2048:
                raise ValueError("Kontekst powinien mieć co najmniej 2048 tokenów.")
            if num_predict < 128:
                raise ValueError("Maksymalna odpowiedź jest zbyt mała.")
            if num_thread < 0:
                raise ValueError("Liczba wątków nie może być ujemna.")

            self.settings.ai_provider = provider
            self.settings.demo_mode = provider == "demo"
            self.settings.ollama_model = self.model_var.get().strip() or "qwen3:30b"
            self.settings.ollama_num_ctx = num_ctx
            self.settings.ollama_num_predict = num_predict
            self.settings.ollama_num_thread = num_thread
            self.settings.ollama_keep_alive = (
                self.keep_alive_var.get().strip() or "5m"
            )
            self.settings.ollama_think = bool(self.think_var.get())
            self.settings.ollama_unload_after_request = bool(
                self.unload_var.get()
            )

            save_ai_settings(self.settings)
            self.profile_var.set("Własny")
            self._update_header()
            self._write_log("Zapisano ustawienia AI / RAM.")

            messagebox.showinfo(
                "Ustawienia AI",
                "Ustawienia zostały zastosowane i zapisane do .env.",
            )
        except Exception as exc:
            messagebox.showerror("Ustawienia AI", str(exc))

    def refresh_models(self):
        threading.Thread(
            target=self._refresh_models_worker,
            daemon=True,
        ).start()

    def _refresh_models_worker(self):
        previous = self.settings.ai_provider
        try:
            self.settings.ai_provider = "ollama"
            models = self.ai.list_models()
            self.events.put(("models_list", models))
        except Exception as exc:
            self.events.put(("ai_check_error", str(exc)))
        finally:
            self.settings.ai_provider = previous

    def unload_model_now(self):
        if self.settings.ai_provider != "ollama":
            messagebox.showinfo(
                "Ollama",
                "Zwalnianie modelu dotyczy tylko Ollamy.",
            )
            return

        self._write_log("Ollama: zwalniam model z pamięci...")
        threading.Thread(
            target=self._unload_model_worker,
            daemon=True,
        ).start()

    def _unload_model_worker(self):
        try:
            self.ai.unload_model()
            self.events.put(("model_unloaded", None))
        except Exception as exc:
            self.events.put(("ai_check_error", str(exc)))

    def _refresh_memory(self):
        try:
            snapshot = get_memory_snapshot()
            self.memory_status_var.set(
                "RAM systemu: "
                f"{snapshot.used_gb:.1f}/{snapshot.total_gb:.1f} GB "
                f"({snapshot.used_percent:.0f}%)  |  "
                f"Wolne: {snapshot.available_gb:.1f} GB  |  "
                f"Procesy Ollama: {snapshot.ollama_ram_gb:.1f} GB"
            )
            self.memory_progress["value"] = snapshot.used_percent

            if self.settings.ai_provider == "ollama":
                try:
                    status = self.ai.runtime_status()
                    models = status.get("models", [])
                    if models:
                        loaded = models[0]
                        size_gb = float(loaded.get("size") or 0) / (1024 ** 3)
                        vram_gb = float(loaded.get("size_vram") or 0) / (1024 ** 3)
                        ctx = loaded.get("context_length") or "?"
                        name = loaded.get("name") or loaded.get("model") or "model"
                        self.ollama_status_var.set(
                            f"Załadowany: {name}  |  "
                            f"rozmiar modelu: {size_gb:.1f} GB  |  "
                            f"VRAM: {vram_gb:.1f} GB  |  "
                            f"kontekst runtime: {ctx}"
                        )
                    else:
                        self.ollama_status_var.set(
                            "Ollama działa, ale żaden model nie jest teraz załadowany."
                        )
                except Exception:
                    self.ollama_status_var.set(
                        "Nie udało się odczytać /api/ps Ollamy."
                    )
        except Exception as exc:
            self.memory_status_var.set(f"Monitor RAM: {exc}")

        self.after(2000, self._refresh_memory)

    # ------------------------------------------------------------------
    # AI health / trace
    # ------------------------------------------------------------------

    def check_ai(self):
        self._write_log("AI: sprawdzam połączenie...")
        threading.Thread(
            target=self._check_ai_worker,
            daemon=True,
        ).start()

    def _check_ai_worker(self):
        try:
            result = self.ai.healthcheck()
            self.events.put(("ai_check_done", result))
        except Exception as exc:
            self.events.put(("ai_check_error", str(exc)))

    def _handle_trace_event(self, event: dict):
        event_type = event.get("type")
        agent = str(event.get("agent") or "AI")

        if event_type == "start":
            self._write_trace(
                f"\n\n--- {agent} ---\n"
                f"Model: {event.get('model', '?')}  |  "
                f"kontekst: {event.get('num_ctx', '?')}  |  "
                f"max output: {event.get('num_predict', '?')}\n"
            )
            self.trace_metrics_var.set(
                f"{agent}: model rozpoczął pracę."
            )

        elif event_type == "phase":
            self._write_trace(
                f"\n[{agent}] {event.get('message', 'Analizuje…')}\n"
            )

        elif event_type == "chunk":
            self._write_trace(str(event.get("text") or ""))

        elif event_type == "result":
            text = str(event.get("text") or "")
            self._write_trace(text)
            self._write_trace("\n")

        elif event_type == "metrics":
            prompt_tokens = int(event.get("prompt_tokens") or 0)
            output_tokens = int(event.get("output_tokens") or 0)
            total_seconds = float(event.get("total_seconds") or 0)
            speed = float(event.get("tokens_per_second") or 0)

            summary = (
                f"{agent}: wejście {prompt_tokens} tok. | "
                f"wyjście {output_tokens} tok. | "
                f"{total_seconds:.1f} s | {speed:.1f} tok/s"
            )
            self.trace_metrics_var.set(summary)
            self._write_trace(f"\n\n[{summary}]\n")

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------

    def youtube_auth(self):
        if not self.publisher.is_configured():
            messagebox.showwarning(
                "YouTube OAuth",
                "Brakuje client_secret.json. W Google Cloud utwórz OAuth Client ID "
                "typu Desktop app dla YouTube Data API v3 i zapisz pobrany plik "
                "jako client_secret.json w katalogu programu.",
            )
            return

        self.auth_button.configure(state="disabled")
        self._write_log("YouTube: uruchamiam OAuth...")
        threading.Thread(
            target=self._youtube_auth_worker,
            daemon=True,
        ).start()

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
                "Nie ma exports/final.mp4. Włącz GENERATE_MEDIA=true "
                "i upewnij się, że FFmpeg działa.",
            )
            return

        if not metadata_file.exists():
            messagebox.showwarning(
                "Brak metadanych",
                "Nie znaleziono 07_youtube.json.",
            )
            return

        metadata = json.loads(
            metadata_file.read_text(encoding="utf-8")
        )
        title = str(
            metadata.get("title") or self.last_project.name
        )

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

    # ------------------------------------------------------------------
    # Event loop
    # ------------------------------------------------------------------

    def _process_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()

                if kind == "status":
                    agent, state = payload
                    if agent in self.status_vars:
                        self.status_vars[agent].set(state)
                    self._write_log(f"{agent}: {state}")

                elif kind == "trace":
                    self._handle_trace_event(payload)

                elif kind == "done":
                    self.last_project = Path(payload)
                    self._write_log(f"Gotowe: {self.last_project}")
                    self.open_button.configure(state="normal")
                    self.run_button.configure(state="normal")

                    if (
                        self.last_project / "exports" / "final.mp4"
                    ).exists():
                        self.upload_button.configure(state="normal")

                    messagebox.showinfo(
                        "Gotowe",
                        "Pipeline zakończony.",
                    )

                elif kind == "pipeline_error":
                    self._write_log(f"BŁĄD PIPELINE: {payload}")
                    self.run_button.configure(state="normal")
                    messagebox.showerror(
                        "Błąd pipeline",
                        str(payload),
                    )

                elif kind == "ai_check_done":
                    self._write_log(f"AI: {payload}")
                    messagebox.showinfo("AI", str(payload))

                elif kind == "ai_check_error":
                    self._write_log(f"AI BŁĄD: {payload}")
                    messagebox.showerror("AI", str(payload))

                elif kind == "models_list":
                    models = list(payload)
                    self.model_combo["values"] = models
                    if models and self.model_var.get() not in models:
                        self.model_var.set(models[0])
                    self._write_log(
                        "Ollama: modele: "
                        + (", ".join(models) if models else "brak")
                    )

                elif kind == "model_unloaded":
                    self._write_log(
                        "Ollama: model został zwolniony z pamięci."
                    )
                    messagebox.showinfo(
                        "Ollama",
                        "Model został zwolniony z RAM/VRAM.",
                    )

                elif kind == "youtube_auth_done":
                    self._write_log("YouTube: OAuth zakończony.")
                    self.auth_button.configure(state="normal")
                    messagebox.showinfo(
                        "YouTube",
                        "Połączenie z YouTube zostało zapisane w token.json.",
                    )

                elif kind == "youtube_uploaded":
                    self._write_log(
                        f"YouTube: wysłano film. ID: {payload}"
                    )
                    self.upload_button.configure(state="normal")
                    messagebox.showinfo(
                        "YouTube",
                        f"Film wysłany jako PRIVATE.\nID: {payload}",
                    )

                elif kind == "youtube_error":
                    self._write_log(f"YouTube BŁĄD: {payload}")
                    self.auth_button.configure(state="normal")

                    if (
                        self.last_project
                        and (
                            self.last_project
                            / "exports"
                            / "final.mp4"
                        ).exists()
                    ):
                        self.upload_button.configure(state="normal")

                    messagebox.showerror(
                        "YouTube",
                        str(payload),
                    )

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_header(self):
        if self.settings.demo_mode:
            mode = "DEMO"
        elif self.settings.ai_provider == "ollama":
            mode = f"OLLAMA · {self.settings.ollama_model}"
        else:
            mode = f"OPENAI · {self.settings.openai_model}"

        ffmpeg = "OK" if self.editor.available() else "BRAK"
        media = "ON" if self.settings.generate_media else "OFF"
        youtube = (
            "GOTOWY"
            if self.publisher.is_configured()
            else "BRAK client_secret.json"
        )

        self.header_status_var.set(
            f"Tryb: {mode}    |    Media: {media}    |    "
            f"FFmpeg: {ffmpeg}    |    YouTube: {youtube}"
        )

    def show_ffmpeg_status(self):
        messagebox.showinfo(
            "FFmpeg",
            self.editor.version(),
        )

    def _write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _write_trace(self, text: str):
        self.trace_text.configure(state="normal")
        self.trace_text.insert("end", text)
        self.trace_text.see("end")
        self.trace_text.configure(state="disabled")

    def _clear_trace(self):
        self.trace_text.configure(state="normal")
        self.trace_text.delete("1.0", "end")
        self.trace_text.configure(state="disabled")
        self.trace_metrics_var.set("Brak metryk.")

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
            subprocess.Popen(
                ["xdg-open", str(resolved)]
            )


if __name__ == "__main__":
    StudioApp().mainloop()

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

class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.7")
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
        self.ram_limit_var = tk.DoubleVar(
            value=float(self.settings.ollama_ram_limit_percent)
        )
        self.ram_limit_text_var = tk.StringVar()
        self.ram_guard_triggered = False
        self.connection_action_in_progress = False
        self.ram_save_after_id = None

        self._build_ui()
        self._update_header()
        self.after(100, self._process_events)
        self.after(500, self._refresh_memory)
        self.after(250, self.probe_ollama_on_start)
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

        ttk.Label(bottom, text="v0.7").pack(side="right")

    def _build_ai_tab(self):
        info = ttk.Label(
            self.ai_tab,
            text=(
                "Sterowanie pamięcią zostało uproszczone do jednego limitu. "
                "Suwak określa maksymalny budżet RAM dla procesów Ollamy. "
                "Jeżeli wybrany model nie mieści się w budżecie, aplikacja go nie uruchomi."
            ),
            wraplength=1050,
        )
        info.pack(fill="x", pady=(0, 12))

        model_frame = ttk.LabelFrame(
            self.ai_tab,
            text="Lokalny model",
            padding=14,
        )
        model_frame.pack(fill="x")

        ttk.Label(model_frame, text="Model", width=18).grid(
            row=0, column=0, sticky="w", pady=5
        )

        self.model_combo = ttk.Combobox(
            model_frame,
            textvariable=self.model_var,
            width=32,
        )
        self.model_combo.grid(row=0, column=1, sticky="w", pady=5)

        ttk.Button(
            model_frame,
            text="Odśwież modele",
            command=self.refresh_models,
        ).grid(row=0, column=2, padx=(8, 0), pady=5)

        controls = ttk.Frame(model_frame)
        controls.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(8, 0),
        )

        ttk.Button(
            controls,
            text="Połącz / uruchom AI",
            command=self.connect_ollama,
        ).pack(side="left")

        ttk.Button(
            controls,
            text="Uruchom model",
            command=self.load_model_now,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Pobierz model",
            command=self.pull_model_now,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            controls,
            text="Zwolnij RAM",
            command=self.unload_model_now,
        ).pack(side="left", padx=(8, 0))

        limit_frame = ttk.LabelFrame(
            self.ai_tab,
            text="Limit pamięci AI",
            padding=14,
        )
        limit_frame.pack(fill="x", pady=(14, 0))

        ttk.Label(
            limit_frame,
            textvariable=self.ram_limit_text_var,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        self.ram_limit_scale = ttk.Scale(
            limit_frame,
            from_=20,
            to=90,
            orient="horizontal",
            variable=self.ram_limit_var,
            command=self._ram_slider_changed,
        )
        self.ram_limit_scale.pack(fill="x", pady=(10, 4))

        marks = ttk.Frame(limit_frame)
        marks.pack(fill="x")
        ttk.Label(marks, text="20%").pack(side="left")
        ttk.Label(marks, text="90%").pack(side="right")

        ttk.Label(
            limit_frame,
            text=(
                "Zmiana suwaka zapisuje się automatycznie. "
                "Strażnik RAM sprawdza budżet przed startem modelu i podczas jego pracy."
            ),
            wraplength=1040,
        ).pack(anchor="w", pady=(10, 0))

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

        self._ram_slider_changed()

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

        if self.settings.ai_provider == "ollama" or self.provider_var.get() == "ollama":
            model = self.model_var.get().strip() or self.settings.ollama_model
            state = self.ollama.inspect(model)
            if not state.connected:
                self.connect_ollama()
                messagebox.showinfo(
                    "Łączenie AI",
                    "Najpierw łączę lokalną Ollamę. Gdy status zmieni się na POŁĄCZONO, uruchom pipeline ponownie.",
                )
                return

            allowed, reason = self._ram_budget_allows_model(model)
            if not allowed:
                messagebox.showwarning("Limit RAM", reason)
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

    def probe_ollama_on_start(self):
        self._set_connection_visual(
            "checking",
            "AI: SPRAWDZAM…",
            "Sprawdzam rzeczywisty stan lokalnej Ollamy. Niczego jeszcze nie uruchamiam.",
        )
        model = self.model_var.get().strip() or self.settings.ollama_model
        threading.Thread(
            target=self._probe_ollama_worker,
            args=(model,),
            daemon=True,
        ).start()

    def _probe_ollama_worker(self, model: str):
        try:
            self.events.put(("startup_probe", self.ollama.inspect(model)))
        except Exception as exc:
            self.events.put(
                ("ollama_connection_error", {
                    "message": str(exc),
                    "silent": True,
                })
            )

    def _auto_start_ollama(self):
        if self.connection_action_in_progress:
            return
        self.connection_action_in_progress = True
        self._set_connection_visual(
            "checking",
            "AI: URUCHAMIAM OLLAMĘ…",
            "Ollama była wyłączona. AI Content Studio uruchamia lokalny serwer.",
        )
        model = self.model_var.get().strip() or self.settings.ollama_model
        threading.Thread(
            target=self._connect_ollama_worker,
            kwargs={"model": model, "load_model": False, "silent": True},
            daemon=True,
        ).start()

    def connect_ollama(self):
        if self.connection_action_in_progress:
            return

        self.connection_action_in_progress = True
        self.connect_ai_button.configure(state="disabled")
        self._set_connection_visual(
            "checking",
            "AI: ŁĄCZENIE…",
            "Uruchamiam Ollamę i sprawdzam wybrany model.",
        )
        model = self.model_var.get().strip() or self.settings.ollama_model
        threading.Thread(
            target=self._connect_ollama_worker,
            kwargs={"model": model, "load_model": True, "silent": False},
            daemon=True,
        ).start()

    def _connect_ollama_worker(self, *, model: str, load_model: bool, silent: bool):
        try:
            self.ollama.model = model
            started, message = self.ollama.start_server()

            if not started:
                self.events.put(
                    ("ollama_connection", {
                        "state": self.ollama.inspect(model),
                        "silent": silent,
                        "error": message,
                    })
                )
                return

            state = self.ollama.inspect(model)
            if not state.model_installed:
                self.events.put(
                    ("ollama_connection", {
                        "state": state,
                        "silent": silent,
                        "error": None,
                    })
                )
                return

            self.settings.ai_provider = "ollama"
            self.settings.demo_mode = False
            self.settings.ollama_model = model
            save_ai_settings(self.settings)

            if load_model and not state.model_loaded:
                allowed, reason = self._ram_budget_allows_model(model)
                if not allowed:
                    self.events.put(
                        ("ram_budget_block", {
                            "message": reason,
                            "silent": silent,
                        })
                    )
                    return

                self.ollama.load_model(
                    model=model,
                    keep_alive=self.settings.ollama_keep_alive,
                    num_ctx=self.settings.ollama_num_ctx,
                )
                state = self.ollama.inspect(model)

            self.events.put(
                ("ollama_connection", {
                    "state": state,
                    "silent": silent,
                    "error": None,
                })
            )
        except Exception as exc:
            self.events.put(
                ("ollama_connection_error", {
                    "message": str(exc),
                    "silent": silent,
                })
            )

    def load_model_now(self):
        if self.connection_action_in_progress:
            return

        model = self.model_var.get().strip() or self.settings.ollama_model
        allowed, reason = self._ram_budget_allows_model(model)
        if not allowed:
            messagebox.showwarning("Limit RAM", reason)
            return

        self.connection_action_in_progress = True
        self.connect_ai_button.configure(state="disabled")
        self._set_connection_visual(
            "checking",
            "AI: URUCHAMIAM MODEL…",
            f"Ładuję {model} do pamięci w ramach ustawionego limitu RAM.",
        )
        threading.Thread(
            target=self._load_model_worker,
            args=(model,),
            daemon=True,
        ).start()

    def _load_model_worker(self, model: str):
        try:
            started, message = self.ollama.start_server()
            if not started:
                raise RuntimeError(message)

            state = self.ollama.inspect(model)
            if not state.model_installed:
                self.events.put(("model_missing", state))
                return

            allowed, reason = self._ram_budget_allows_model(model)
            if not allowed:
                self.events.put(
                    ("ram_budget_block", {
                        "message": reason,
                        "silent": False,
                    })
                )
                return

            self.settings.ai_provider = "ollama"
            self.settings.demo_mode = False
            self.settings.ollama_model = model
            save_ai_settings(self.settings)

            self.ollama.load_model(
                model=model,
                keep_alive=self.settings.ollama_keep_alive,
                num_ctx=self.settings.ollama_num_ctx,
            )
            self.events.put(("ollama_state", self.ollama.inspect(model)))
        except Exception as exc:
            self.events.put(
                ("ollama_connection_error", {
                    "message": str(exc),
                    "silent": False,
                })
            )

    def pull_model_now(self):
        model = self.model_var.get().strip() or self.settings.ollama_model
        if not messagebox.askyesno(
            "Pobieranie modelu",
            f"Pobrać model {model}? Może to zająć kilkanaście lub kilkadziesiąt GB.",
        ):
            return

        self.connection_action_in_progress = True
        self.connect_ai_button.configure(state="disabled")
        self._set_connection_visual(
            "checking",
            "AI: POBIERANIE MODELU…",
            f"Pobieram {model}. Nie zamykaj programu.",
        )
        threading.Thread(
            target=self._pull_model_worker,
            args=(model,),
            daemon=True,
        ).start()

    def _pull_model_worker(self, model: str):
        try:
            started, message = self.ollama.start_server()
            if not started:
                raise RuntimeError(message)

            ok, output = self.ollama.pull_model(model)
            if not ok:
                raise RuntimeError(output)

            self.events.put(("model_pulled", self.ollama.inspect(model)))
        except Exception as exc:
            self.events.put(
                ("ollama_connection_error", {
                    "message": str(exc),
                    "silent": False,
                })
            )

    def _periodic_connection_check(self):
        if not self.connection_action_in_progress:
            threading.Thread(
                target=self._connection_status_worker,
                daemon=True,
            ).start()
        self.after(5000, self._periodic_connection_check)

    def _connection_status_worker(self):
        try:
            self.events.put(
                ("ollama_state", self.ollama.inspect(self.settings.ollama_model))
            )
        except Exception:
            pass

    def _ram_slider_changed(self, _value=None):
        try:
            percent = int(round(float(self.ram_limit_var.get())))
        except (TypeError, ValueError):
            percent = self.settings.ollama_ram_limit_percent

        percent = max(20, min(90, percent))
        self.settings.ollama_ram_limit_percent = percent

        try:
            snapshot = get_memory_snapshot()
            budget_gb = snapshot.total_gb * percent / 100.0
            self.ram_limit_text_var.set(
                f"Maks. RAM dla AI: {percent}% = {budget_gb:.1f} GB"
            )
        except Exception:
            self.ram_limit_text_var.set(
                f"Maks. RAM dla AI: {percent}%"
            )

        if self.ram_save_after_id is not None:
            try:
                self.after_cancel(self.ram_save_after_id)
            except Exception:
                pass

        self.ram_save_after_id = self.after(
            350,
            self._save_ram_limit,
        )

    def _save_ram_limit(self):
        self.ram_save_after_id = None
        save_ai_settings(self.settings)

    def _ram_budget(self) -> tuple[float, float]:
        snapshot = get_memory_snapshot()
        total_gb = snapshot.total_gb
        budget_gb = total_gb * self.settings.ollama_ram_limit_percent / 100.0
        return total_gb, budget_gb

    def _ram_budget_allows_model(self, model: str) -> tuple[bool, str]:
        try:
            total_gb, budget_gb = self._ram_budget()
            size_bytes = self.ollama.model_size_bytes(model)
            model_gb = size_bytes / (1024 ** 3)

            if model_gb <= 0:
                return True, ""

            # Zostawiamy zapas na KV cache, runtime i narzut procesu.
            required_gb = model_gb + max(1.5, model_gb * 0.08)

            if required_gb > budget_gb:
                required_percent = int((required_gb / total_gb) * 100) + 1
                return (
                    False,
                    f"Limit {self.settings.ollama_ram_limit_percent}% daje {budget_gb:.1f} GB, "
                    f"a {model} potrzebuje bezpiecznie około {required_gb:.1f} GB. "
                    f"Ustaw co najmniej około {required_percent}% albo wybierz mniejszy model.",
                )

            return True, ""
        except Exception:
            return True, ""

    def refresh_models(self):
        threading.Thread(
            target=self._refresh_models_worker,
            daemon=True,
        ).start()

    def _refresh_models_worker(self):
        try:
            started, message = self.ollama.start_server()
            if not started:
                raise RuntimeError(message)
            models = self.ollama.list_models()
            self.events.put(("models_list", models))
        except Exception as exc:
            self.events.put(("ai_check_error", str(exc)))

    def unload_model_now(self):
        model = self.model_var.get().strip() or self.settings.ollama_model
        self._write_log("Ollama: zwalniam model z pamięci...")
        threading.Thread(
            target=self._unload_model_worker,
            args=(model,),
            daemon=True,
        ).start()

    def _unload_model_worker(self, model: str):
        try:
            self.ollama.unload_model(model)
            self.events.put(("model_unloaded", self.ollama.inspect(model)))
        except Exception as exc:
            self.events.put(("ai_check_error", str(exc)))

    def _refresh_memory(self):
        try:
            snapshot = get_memory_snapshot()
            budget_gb = (
                snapshot.total_gb
                * self.settings.ollama_ram_limit_percent
                / 100.0
            )

            self.memory_status_var.set(
                "RAM systemu: "
                f"{snapshot.used_gb:.1f}/{snapshot.total_gb:.1f} GB "
                f"({snapshot.used_percent:.0f}%)  |  "
                f"AI: {snapshot.ollama_ram_gb:.1f}/{budget_gb:.1f} GB"
            )

            ai_percent_of_budget = (
                (snapshot.ollama_ram_gb / budget_gb) * 100.0
                if budget_gb > 0
                else 0.0
            )
            self.memory_progress["value"] = min(ai_percent_of_budget, 100.0)

            if snapshot.ollama_ram_gb > budget_gb and snapshot.ollama_ram_gb > 0.5:
                if not self.ram_guard_triggered:
                    self.ram_guard_triggered = True
                    self._set_connection_visual(
                        "warning",
                        "AI: LIMIT RAM PRZEKROCZONY",
                        (
                            f"Ollama używa {snapshot.ollama_ram_gb:.1f} GB, "
                            f"a limit to {budget_gb:.1f} GB. Zwalniam model z pamięci."
                        ),
                    )
                    self._write_log(
                        "STRAŻNIK RAM: "
                        f"{snapshot.ollama_ram_gb:.1f} GB > {budget_gb:.1f} GB. "
                        "Wymuszam zwolnienie modelu."
                    )
                    threading.Thread(
                        target=self._ram_guard_unload_worker,
                        daemon=True,
                    ).start()
            elif snapshot.ollama_ram_gb <= budget_gb * 0.95:
                self.ram_guard_triggered = False

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
                            f"model: {size_gb:.1f} GB  |  "
                            f"VRAM: {vram_gb:.1f} GB  |  "
                            f"kontekst: {ctx}  |  "
                            f"limit AI: {self.settings.ollama_ram_limit_percent}%"
                        )
                    else:
                        self.ollama_status_var.set(
                            "Ollama działa, ale żaden model nie jest teraz załadowany."
                        )
                except Exception:
                    self.ollama_status_var.set(
                        "Nie udało się odczytać stanu pamięci Ollamy."
                    )
        except Exception as exc:
            self.memory_status_var.set(f"Monitor RAM: {exc}")

        self.after(1000, self._refresh_memory)

    def _ram_guard_unload_worker(self):
        try:
            model = self.settings.ollama_model
            self.ollama.unload_model(model)
            self.events.put(
                ("ram_guard_unloaded", self.ollama.inspect(model))
            )
        except Exception as exc:
            self.events.put(
                ("ollama_connection_error", {
                    "message": f"Strażnik RAM nie mógł zwolnić modelu: {exc}",
                    "silent": True,
                })
            )

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
            state = self.ollama.inspect(self.settings.ollama_model)
            self.events.put(("ollama_state", state))
            self.events.put(("ai_check_done", state.message))
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

                elif kind == "ollama_connection":
                    data = dict(payload)
                    state = data["state"]
                    silent = bool(data.get("silent"))
                    error = data.get("error")

                    self.connect_ai_button.configure(state="normal")
                    self._apply_ollama_state(state)

                    if state.connected:
                        self.settings.ai_provider = "ollama"
                        self.settings.demo_mode = False
                        self.settings.ollama_model = (
                            self.model_var.get().strip()
                            or self.settings.ollama_model
                        )
                        self.provider_var.set("ollama")
                        self.model_var.set(self.settings.ollama_model)
                        self.model_combo["values"] = state.models
                        self._update_header()
                        self._write_log(f"Ollama: {state.message}")
                        if not silent:
                            messagebox.showinfo("Lokalne AI", state.message)
                    else:
                        detail = str(error or state.message)
                        self._write_log(f"Ollama: {detail}")
                        if not silent:
                            messagebox.showwarning("Lokalne AI", detail)

                elif kind == "ollama_connection_error":
                    data = dict(payload)
                    message = str(data.get("message") or "Nieznany błąd Ollamy.")
                    silent = bool(data.get("silent"))
                    self.connect_ai_button.configure(state="normal")
                    self._set_connection_visual(
                        "error",
                        "AI: NIE POŁĄCZONO",
                        message,
                    )
                    self._write_log(f"Ollama BŁĄD: {message}")
                    if not silent:
                        messagebox.showerror("Lokalne AI", message)

                elif kind == "ollama_state":
                    self._apply_ollama_state(payload)

                elif kind == "model_missing":
                    self.connect_ai_button.configure(state="normal")
                    self._apply_ollama_state(payload)
                    messagebox.showwarning(
                        "Brak modelu",
                        f"Nie znaleziono {self.settings.ollama_model}. Kliknij „Pobierz model”.",
                    )

                elif kind == "model_pulled":
                    self.connect_ai_button.configure(state="normal")
                    self._apply_ollama_state(payload)
                    self._write_log("Ollama: model został pobrany.")
                    self.connect_ollama()

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
                    self._apply_ollama_state(payload)
                    self._write_log(
                        "Ollama: model został zwolniony z pamięci."
                    )
                    messagebox.showinfo(
                        "Ollama",
                        "Model został zwolniony z RAM/VRAM. Połączenie z serwerem nadal działa.",
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

    def _set_connection_visual(
        self,
        state: str,
        title: str,
        detail: str,
    ):
        self.connection_state = state
        self.connection_status_var.set(title)
        self.connection_detail_var.set(detail)

        palette = {
            "connected_loaded": ("#176b32", "#ffffff"),
            "connected": ("#2e7d32", "#ffffff"),
            "warning": ("#a35a00", "#ffffff"),
            "error": ("#a12622", "#ffffff"),
            "checking": ("#5b6470", "#ffffff"),
        }
        background, foreground = palette.get(
            state,
            ("#5b6470", "#ffffff"),
        )
        self.connection_label.configure(
            background=background,
            foreground=foreground,
        )

    def _apply_ollama_state(self, state):
        if state.server_running and state.model_installed:
            if state.model_loaded:
                self._set_connection_visual(
                    "connected_loaded",
                    "AI: POŁĄCZONO · MODEL ZAŁADOWANY",
                    state.message,
                )
            else:
                self._set_connection_visual(
                    "connected",
                    "AI: POŁĄCZONO · MODEL GOTOWY",
                    state.message,
                )

            self.provider_var.set("ollama")
            if state.models:
                self.model_combo["values"] = state.models
            return

        if state.server_running and not state.model_installed:
            self._set_connection_visual(
                "warning",
                "AI: OLLAMA DZIAŁA · BRAK MODELU",
                state.message,
            )
            return

        if state.installed:
            self._set_connection_visual(
                "error",
                "AI: OLLAMA WYŁĄCZONA",
                state.message,
            )
        else:
            self._set_connection_visual(
                "error",
                "AI: OLLAMA NIEZNALEZIONA",
                state.message,
            )

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

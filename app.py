from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from agents.topics import TopicsAgent
from core.channel_memory import ChannelMemory, FIELDS
from core.config import load_settings
from core.editor import FFmpegEditor
from core.env_settings import save_ai_settings
from core.ollama_manager import OllamaManager
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.system_monitor import get_memory_snapshot
from core.web_research import search_web, source_text
from core.youtube_publisher import UploadRequest, YouTubePublisher

AGENTS = ["Research", "Scenariusz", "Showrunner", "Grafika", "Lektor", "Montaż", "Kontrola", "YouTube Meta"]


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.8.1")
        self.geometry("1180x820")
        self.minsize(960, 700)
        self.settings = load_settings()
        self.store = ProjectStore(self.settings.projects_dir)
        self.memory = ChannelMemory(self.settings.projects_dir / "_memory")
        self.events = queue.Queue()
        self.ai = OpenAIGateway(self.settings)
        self.ai.set_trace_callback(lambda event: self.events.put(("trace", event)))
        self.pipeline = ContentPipeline(self.store, self.ai, self.settings)
        self.ollama = OllamaManager(base_url=self.settings.ollama_url, model=self.settings.ollama_model)
        self.editor = FFmpegEditor(self.settings.ffmpeg_path)
        self.publisher = YouTubePublisher()
        self.busy = False
        self.polling = False
        self.cancel = threading.Event()
        self.last_project = None
        self.project_paths = []
        self.file_paths = []
        self.actions = []
        self.probed = False
        self.guard_pending = False
        self.topic = tk.StringVar()
        self.online = tk.BooleanVar(value=True)
        self.media = tk.BooleanVar(value=self.settings.generate_media)
        self.provider = tk.StringVar(value=self.settings.ai_provider)
        self.model = tk.StringVar(value=self.settings.ollama_model)
        self.ram = tk.DoubleVar(value=self.settings.ollama_ram_limit_percent)
        self.ram_label = tk.StringVar()
        self.connection = tk.StringVar(value="AI: sprawdzam rzeczywisty stan…")
        self.summary = tk.StringVar(value="Wpisz temat lub znajdź inspiracje w internecie.")
        self.monitor = tk.StringVar(value="RAM: sprawdzanie…")
        self.metrics = tk.StringVar(value="Agenci pracują kolejno na jednym modelu.")
        self.statuses = {name: tk.StringVar(value="—") for name in AGENTS}
        self._build_ui()
        self._refresh_projects()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._events)
        self.after(200, self._poll)

    def _button(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side="left", padx=(0, 8), pady=4)
        self.actions.append(button)
        return button

    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("TButton", padding=(10, 7))
        style.configure("TNotebook.Tab", padding=(16, 8))
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="AI Content Studio", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        connection_row = ttk.Frame(root)
        connection_row.pack(fill="x", pady=6)
        ttk.Label(connection_row, textvariable=self.connection, font=("Segoe UI", 11, "bold")).pack(side="left", fill="x", expand=True)
        self._button(connection_row, "Włącz / połącz Ollamę", self.connect_ollama)
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        self.studio, self.projects, self.channel, self.settings_tab = [ttk.Frame(self.tabs, padding=12) for _ in range(4)]
        for frame, title in zip((self.studio, self.projects, self.channel, self.settings_tab),
                                ("Tworzenie", "Projekty", "Pamięć kanału", "Ustawienia")):
            self.tabs.add(frame, text=title)
        self._studio_ui()
        self._projects_ui()
        self._memory_ui()
        self._settings_ui()
        ttk.Label(root, textvariable=self.monitor).pack(anchor="w", pady=(8, 0))

    def _studio_ui(self):
        ttk.Label(self.studio, text="O czym ma być film? Wpisz temat albo dziedzinę, np. historia Polski.").pack(anchor="w")
        entry = ttk.Entry(self.studio, textvariable=self.topic, font=("Segoe UI", 13))
        entry.pack(fill="x", pady=8)
        entry.bind("<Return>", lambda _: self.start_pipeline())
        entry.focus_set()
        row = ttk.Frame(self.studio)
        row.pack(fill="x")
        self._button(row, "AI: znajdź tematy", self.find_topics)
        self._button(row, "Przygotuj projekt", self.start_pipeline)
        self.stop_button = ttk.Button(row, text="Zatrzymaj po etapie", state="disabled", command=self._stop)
        self.stop_button.pack(side="left", padx=8)
        self.internet_check = ttk.Checkbutton(row, text="Research w internecie", variable=self.online)
        self.internet_check.pack(side="left")
        ttk.Label(self.studio, textvariable=self.summary, wraplength=1000).pack(anchor="w", pady=8)
        stages = ttk.Frame(self.studio)
        stages.pack(fill="x", pady=4)
        for i, name in enumerate(AGENTS):
            cell = ttk.Frame(stages)
            cell.grid(row=i // 4, column=i % 4, sticky="w", padx=(0, 22), pady=3)
            ttk.Label(cell, text=name + ": ").pack(side="left")
            ttk.Label(cell, textvariable=self.statuses[name]).pack(side="left")
        self.output_tabs = ttk.Notebook(self.studio)
        self.output_tabs.pack(fill="both", expand=True, pady=8)
        self.results = ScrolledText(self.output_tabs, height=10, wrap="word", font=("Segoe UI", 11), state="disabled")
        self.trace = ScrolledText(self.output_tabs, height=10, wrap="word", font=("Consolas", 10), state="disabled")
        self.output_tabs.add(self.results, text="Wyniki / tematy")
        self.output_tabs.add(self.trace, text="Przebieg AI")
        ttk.Label(self.studio, textvariable=self.metrics).pack(anchor="w")

    def _projects_ui(self):
        top = ttk.Frame(self.projects)
        top.pack(fill="x")
        self.project_combo = ttk.Combobox(top, state="readonly", width=70)
        self.project_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.project_combo.bind("<<ComboboxSelected>>", self._select_project)
        self._button(top, "Odśwież", self._refresh_projects)
        self._button(top, "Otwórz folder", self.open_project)
        self.file_combo = ttk.Combobox(self.projects, state="readonly")
        self.file_combo.pack(fill="x", pady=8)
        self.file_combo.bind("<<ComboboxSelected>>", self._preview_file)
        self.preview = ScrolledText(self.projects, height=10, wrap="word", state="disabled")
        self.preview.pack(fill="both", expand=True)
        bottom = ttk.Frame(self.projects)
        bottom.pack(fill="x")
        self._button(bottom, "Połącz YouTube", self.youtube_auth)
        self._button(bottom, "Wyślij film jako PRIVATE", self.publish_last)
        ttk.Label(bottom, text="Najpierw sprawdź źródła, treść i gotowy film.").pack(side="left", padx=8)

    def _memory_ui(self):
        ttk.Label(self.channel, text="Tutaj uczysz aplikację swoich zasad. Pamięć trafia do agentów przy każdym nowym projekcie.\n"
                  "To zapisany profil, nie trening modelu. Wyniki AI nie są automatycznie zapamiętywane jako fakty.",
                  wraplength=1000).pack(anchor="w", pady=(0, 8))
        self.memory_fields = {}
        try:
            profile = self.memory.load()
        except RuntimeError as exc:
            profile = {}
            self.after(100, lambda error=str(exc): messagebox.showerror("Pamięć", error))
        labels = ["Nazwa kanału", "Odbiorcy i tematyka", "Styl narracji i obrazu", "Zasady / czego unikać", "Własna wiedza i poprawki (podaj źródła)"]
        for key, label in zip(FIELDS, labels):
            ttk.Label(self.channel, text=label).pack(anchor="w")
            widget = ScrolledText(self.channel, height=1 if key == "name" else 2, wrap="word")
            widget.insert("1.0", profile.get(key, ""))
            widget.pack(fill="both", expand=key != "name", pady=(2, 6))
            self.memory_fields[key] = widget
        row = ttk.Frame(self.channel)
        row.pack(fill="x")
        self._button(row, "Zapisz pamięć", self.save_memory)
        ttk.Label(row, text="Maks. 4000 znaków. Zapis lokalny: projects/_memory/channel_profile.json").pack(side="left")

    def _settings_ui(self):
        ttk.Label(self.settings_tab, text="Lokalne AI: Ollama · qwen3:8b",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(self.settings_tab, text="Projekt zawsze używa tego modelu. Nie trzeba wybierać silnika ani wpisywać nazwy modelu.").pack(anchor="w", pady=(2, 8))
        ttk.Label(self.settings_tab, textvariable=self.ram_label, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(12, 0))
        self.ram_scale = ttk.Scale(self.settings_tab, from_=20, to=90, variable=self.ram, command=self._ram_text)
        self.ram_scale.pack(fill="x", pady=8)
        self._ram_text()
        ttk.Label(self.settings_tab, text="Dla 32 GB i Qwen 8B: domyślnie 50% RAM, kontekst 4096.\n"
                  "To budżet kontrolowany przez aplikację, nie twardy limit systemowy. Inne programy też potrzebują RAM.\n"
                  "Model uruchamia się automatycznie przy wyszukiwaniu lub tworzeniu projektu.", wraplength=1000).pack(anchor="w")
        row = ttk.Frame(self.settings_tab)
        row.pack(fill="x", pady=8)
        self._button(row, "Zapisz ustawienia", self.save_settings)
        self._button(row, "Połącz / załaduj qwen3:8b", lambda: self.model_action("load"))
        row = ttk.Frame(self.settings_tab)
        row.pack(fill="x")
        self._button(row, "Pobierz model", lambda: self.model_action("pull"))
        self._button(row, "Zwolnij RAM", lambda: self.model_action("unload"))
        self._button(row, "Sprawdź AI", self.check_ai)
        self._button(row, "Sprawdź FFmpeg", lambda: self._job("FFmpeg", self.editor.version, lambda value: messagebox.showinfo("FFmpeg", value)))
        self.media_check = ttk.Checkbutton(self.settings_tab, text="Generuj obrazy i głos przez płatne API OpenAI oraz montuj wideo", variable=self.media)
        self.media_check.pack(anchor="w", pady=12)
        ttk.Label(self.settings_tab, text="Domyślnie powstaje pakiet tekstowy: research, scenariusz, ujęcia, prompty, narracja i metadata.\n"
                  "Obrazy i głos wymagają OPENAI_API_KEY w .env. Montaż wymaga FFmpeg.\n"
                  "Lokalna generacja obrazów/TTS i pełny autopilot nie są jeszcze zaimplementowane.", wraplength=1000).pack(anchor="w")

    def _ram_text(self, _=None):
        self.ram_label.set(f"Maks. RAM dla AI: {round(self.ram.get())}% (zakres 20–90%)")

    def ram_preset(self):
        self.ram.set(50)
        self._ram_text()
        self.settings.ollama_num_ctx = 4096
        self.save_settings()

    def save_settings(self):
        if self.busy:
            return False
        self.settings.ai_provider = "ollama"
        self.settings.demo_mode = False
        self.settings.ollama_model = "qwen3:8b"
        self.provider.set("ollama")
        self.model.set("qwen3:8b")
        self.settings.ollama_ram_limit_percent = max(20, min(90, round(self.ram.get())))
        self.settings.generate_media = self.media.get()
        try:
            save_ai_settings(self.settings)
        except Exception as exc:
            messagebox.showerror("Ustawienia", str(exc))
            return False
        self.summary.set("Ustawienia zapisane. " + ("Tryb: pakiet tekstowy." if not self.media.get() else "Tryb: tekst i płatne media API."))
        return True

    def save_memory(self):
        try:
            self.memory.save({key: field.get("1.0", "end-1c") for key, field in self.memory_fields.items()})
            self.summary.set("Pamięć zapisana. Nowe projekty otrzymają te zasady.")
            messagebox.showinfo("Pamięć", "Zapisano. Zasady będą użyte w nowych projektach.")
        except Exception as exc:
            messagebox.showerror("Pamięć", str(exc))

    def _set_busy(self, busy):
        self.busy = busy
        for button in self.actions:
            button.configure(state="disabled" if busy else "normal")
        for widget in (self.ram_scale, self.media_check, self.internet_check):
            widget.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state="disabled")

    def _job(self, label, work, done):
        if self.busy:
            return
        self._set_busy(True)
        self.summary.set(label + "…")
        def worker():
            try:
                self.events.put(("job_done", (done, work())))
            except Exception as exc:
                self.events.put(("job_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _prepare_ai(self):
        if self.settings.ai_provider != "ollama":
            return
        self.events.put(("connection", "AI: URUCHAMIAM / ŁĄCZĘ OLLAMĘ…"))
        ok, message = self.ollama.start_server()
        if not ok:
            raise RuntimeError(message)
        model = self.settings.ollama_model
        state = self.ollama.inspect(model)
        if not state.connected:
            raise RuntimeError(state.message + " Otwórz Ustawienia → Pobierz model.")
        snapshot = get_memory_snapshot()
        size = self.ollama.model_size_bytes(model) / 1024**3
        if size <= 0:
            raise RuntimeError("Nie można odczytać rozmiaru modelu. Wybierz pełną nazwę z listy modeli.")
        required = size + max(2, size * .12)
        budget = snapshot.total_gb * self.settings.ollama_ram_limit_percent / 100
        if required > budget:
            raise RuntimeError(f"AI: LIMIT RAM ZA NISKI. Budżet {budget:.1f} GB, szacowane minimum {required:.1f} GB. "
                               "Zwiększ limit RAM w Ustawieniach.")
        additional = max(0, required - snapshot.ollama_ram_gb) if state.model_loaded else required
        if additional > snapshot.available_gb:
            self.events.put(("progress", "Mało wolnego RAM. Ładuję model w ustawionym budżecie; zamknij zbędne programy, jeśli system zwalnia."))
        self.events.put(("connection", "AI: ŁADUJĘ MODEL…"))
        self.ollama.load_model(model=model, num_ctx=self.settings.ollama_num_ctx,
                               keep_alive=self.settings.ollama_keep_alive)
        confirmed = self.ollama.inspect(model)
        if not confirmed.connected or not confirmed.model_loaded:
            raise RuntimeError("Ollama nie potwierdziła załadowania modelu. " + confirmed.message)
        self.events.put(("connection", "AI: POŁĄCZONO · MODEL ZAŁADOWANY"))

    def start_pipeline(self):
        if self.busy:
            return
        topic = self.topic.get().strip()
        if not topic:
            messagebox.showwarning("Temat", "Wpisz temat filmu.")
            return
        if not self.save_settings():
            return
        if self.media.get() and (self.settings.demo_mode or not self.settings.openai_api_key or not self.editor.available()):
            messagebox.showwarning("Media", "Media wymagają aktywnego AI, OPENAI_API_KEY oraz FFmpeg. Wyłącz media, aby przygotować tekst.")
            return
        self.cancel.clear()
        online = self.online.get()
        for value in self.statuses.values():
            value.set("OCZEKUJE")
        def work():
            self._prepare_ai()
            return self.pipeline.run(topic, online=online, cancel=self.cancel,
                                     status=lambda a, s: self.events.put(("stage", (a, s))))
        def done(project):
            self.last_project = project.path
            self._refresh_projects()
            has_video = (project.path / "exports/final.mp4").exists()
            self.summary.set("Gotowy film — sprawdź go w zakładce Projekty." if has_video else "Pakiet tekstowy gotowy. Film nie został wygenerowany. Otwórz Projekty.")
            self._text(self.results, (project.path / "02_script.txt").read_text(encoding="utf-8"))
        self._job("Przygotowuję projekt", work, done)
        self.stop_button.configure(state="normal")

    def _stop(self):
        self.cancel.set()
        self.summary.set("Zatrzymam po bieżącym etapie. Trwające generowanie musi się zakończyć.")
        self.stop_button.configure(state="disabled")

    def find_topics(self):
        query = self.topic.get().strip()
        if not query:
            messagebox.showwarning("Tematy", "Wpisz dziedzinę, np. historia Polski.")
            return
        if not self.save_settings():
            return
        if self.settings.demo_mode:
            messagebox.showwarning("AI", "Włącz Ollamę przyciskiem na górze okna. Tryb DEMO nie wyszukuje tematów przez AI.")
            return
        def work():
            self._prepare_ai()
            project = self.store.create("Tematy AI: " + query)
            try:
                self.ai.channel_context = self.memory.context()
                project.write_text("00_channel_profile.txt", self.ai.channel_context)
                def progress(message):
                    project.write_json("state.json", {"status": "running", "agent": "Research", "message": message})
                    self.events.put(("progress", message))
                text = TopicsAgent(self.ai).run(subject=query, progress=progress, save=project.write_json)
                project.write_text("00_inspiracje.txt", text)
                project.write_json("state.json", {"status": "completed", "agent": "Research"})
                return project, text
            except Exception as exc:
                project.write_json("state.json", {"status": "failed", "agent": "Research", "error": str(exc)})
                raise
            finally:
                self.ai.channel_context = ""
        def done(result):
            project, text = result
            self.last_project = project.path
            self._text(self.results, text)
            self.output_tabs.select(self.results)
            self._refresh_projects()
            self.summary.set("AI opracowało tematy i zapisało źródła. Wpisz wybrany temat i przygotuj projekt.")
        self._job("Szukam tematów w internecie", work, done)

    def connect_ollama(self):
        if self.busy:
            return
        self.provider.set("ollama")
        self.model.set("qwen3:8b")
        self.model_action("connect")

    def model_action(self, action):
        if self.busy or not self.save_settings():
            return
        model = self.settings.ollama_model
        if action == "pull" and not messagebox.askyesno("Pobieranie", f"Pobrać {model}? Model może zajmować wiele GB."):
            return
        def work():
            if action == "connect":
                self.events.put(("connection", "AI: URUCHAMIAM / ŁĄCZĘ OLLAMĘ…"))
                ok, msg = self.ollama.start_server()
                if not ok:
                    raise RuntimeError(msg)
            elif action == "unload":
                self.ollama.unload_model(model)
            elif action == "pull":
                ok, msg = self.ollama.start_server()
                if not ok:
                    raise RuntimeError(msg)
                ok, msg = self.ollama.pull_model(model)
                if not ok:
                    raise RuntimeError(msg)
            else:
                if self.settings.ai_provider != "ollama":
                    raise RuntimeError("Wybierz silnik ollama, aby załadować lokalny model.")
                self._prepare_ai()
            return self.ollama.inspect(model)
        self._job("Operacja Ollama: " + action, work, lambda state: self._show_state(state))

    def check_ai(self):
        self._job("Sprawdzam AI", self.ai.healthcheck, lambda msg: messagebox.showinfo("AI", msg))

    def _poll(self):
        if not self.polling:
            self.polling = True
            provider, model, busy = self.settings.ai_provider, self.settings.ollama_model, self.busy
            def work():
                try:
                    snapshot = get_memory_snapshot()
                except Exception:
                    snapshot = None
                try:
                    state = self.ollama.inspect(model) if provider == "ollama" and not busy else None
                except Exception:
                    state = None
                self.events.put(("poll", (snapshot, state, provider)))
            threading.Thread(target=work, daemon=True).start()
        self.after(4000, self._poll)

    def _show_state(self, state):
        if state.connected:
            text = "AI: POŁĄCZONO · MODEL " + ("ZAŁADOWANY" if state.model_loaded else "GOTOWY")
        elif state.server_running:
            text = "AI: OLLAMA DZIAŁA · BRAK MODELU"
        else:
            text = "AI: OLLAMA WYŁĄCZONA" if state.installed else "AI: OLLAMA NIEZNALEZIONA"
        self.connection.set(text)

    def _handle_poll(self, snapshot, state, provider):
        self.polling = False
        if snapshot:
            budget = snapshot.total_gb * self.settings.ollama_ram_limit_percent / 100
            self.monitor.set(f"RAM: {snapshot.used_gb:.1f}/{snapshot.total_gb:.1f} GB · Ollama: {snapshot.ollama_ram_gb:.1f} GB · budżet AI: {budget:.1f} GB")
            if provider == "ollama" and snapshot.ollama_ram_gb > budget and not self.guard_pending:
                self.guard_pending = True
                self.cancel.set()
                self.connection.set("AI: LIMIT RAM PRZEKROCZONY — próbuję zwolnić model")
                model = self.settings.ollama_model
                def release():
                    try:
                        self.ollama.unload_model(model)
                        self.events.put(("guard", "Próba zwolnienia modelu zakończona; trwa sprawdzanie RAM."))
                    except Exception as exc:
                        self.events.put(("guard", "Nie udało się zwolnić modelu: " + str(exc)))
                threading.Thread(target=release, daemon=True).start()
            elif snapshot.ollama_ram_gb < budget * .95:
                self.guard_pending = False
        if provider != self.settings.ai_provider:
            return
        if provider != "ollama":
            self.connection.set("AI: DEMO — przykładowe wyniki" if self.settings.demo_mode else "AI: OPENAI — skonfigurowane API; połączenie sprawdzane przy żądaniu")
        elif state and not self.busy and not self.guard_pending:
            self._show_state(state)
            if not self.probed:
                self.probed = True
                if state.installed and not state.server_running:
                    self.after(900, self._autostart)

    def _autostart(self):
        if self.busy or self.settings.ai_provider != "ollama":
            return
        self.connection.set("AI: URUCHAMIAM OLLAMĘ…")
        def work():
            ok, msg = self.ollama.start_server()
            if not ok:
                raise RuntimeError(msg)
            return self.ollama.inspect(self.settings.ollama_model)
        self._job("Uruchamiam Ollamę", work, self._show_state)

    def _refresh_projects(self):
        self.project_paths = sorted((p for p in self.settings.projects_dir.iterdir() if p.is_dir() and (p / "project.json").exists()), reverse=True)
        self.project_combo["values"] = [p.name for p in self.project_paths]
        if self.project_paths:
            index = self.project_paths.index(self.last_project) if self.last_project in self.project_paths else 0
            self.project_combo.current(index)
            self._select_project()

    def _select_project(self, _=None):
        index = self.project_combo.current()
        if index < 0:
            return
        self.last_project = self.project_paths[index]
        self.file_paths = sorted(p for p in self.last_project.iterdir() if p.is_file() and p.suffix in {".txt", ".md", ".json"})
        self.file_combo["values"] = [p.name for p in self.file_paths]
        if self.file_paths:
            preferred = next((i for i, p in enumerate(self.file_paths) if p.name == "02_script.txt"), 0)
            self.file_combo.current(preferred)
            self._preview_file()

    def _preview_file(self, _=None):
        index = self.file_combo.current()
        if index >= 0:
            try:
                self._text(self.preview, self.file_paths[index].read_text(encoding="utf-8"))
            except OSError as exc:
                messagebox.showerror("Podgląd", str(exc))

    def open_project(self):
        path = (self.last_project or self.settings.projects_dir).resolve()
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def youtube_auth(self):
        if not self.publisher.is_configured():
            messagebox.showwarning("YouTube", "Brak client_secret.json. Instrukcja: docs/YOUTUBE_SETUP.md")
            return
        self._job("Łączę YouTube", self.publisher.authenticate, lambda _: messagebox.showinfo("YouTube", "Połączenie zapisane w token.json."))

    def publish_last(self):
        if not self.last_project:
            return
        video = self.last_project / "exports/final.mp4"
        if not video.exists():
            messagebox.showwarning("Brak filmu", "Ten projekt nie zawiera gotowego filmu exports/final.mp4.")
            return
        try:
            meta = json.loads((self.last_project / "07_youtube.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Metadata", str(exc))
            return
        if not messagebox.askyesno("YouTube PRIVATE", f"Czy sprawdziłeś treść i film? Wysłać jako PRIVATE?\n{meta.get('title', video.stem)}"):
            return
        request = UploadRequest(video_path=video, title=str(meta.get("title") or video.stem),
                                description=str(meta.get("description") or ""), privacy_status="private",
                                category_id=str(meta.get("category_id") or "22"), tags=[str(t) for t in meta.get("tags", [])])
        project = self.last_project
        def work():
            video_id = self.publisher.upload(request)
            (project / "08_upload.json").write_text(json.dumps({"video_id": video_id, "privacy": "private"}), encoding="utf-8")
            return video_id
        self._job("Wysyłam PRIVATE", work, lambda vid: messagebox.showinfo("YouTube", "Wysłano PRIVATE. ID: " + vid))

    def _events(self):
        # Bound work per tick so a fast stream cannot starve Tk's event loop.
        for _ in range(100):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                if kind == "job_done":
                    self._set_busy(False)
                    done, result = value
                    self.summary.set("Operacja zakończona.")
                    done(result)
                elif kind == "job_error":
                    self._set_busy(False)
                    self.summary.set("Operacja zatrzymana. Sprawdź komunikat; częściowe wyniki są w Projektach.")
                    if self.settings.ai_provider == "ollama":
                        self.connection.set("AI: OPERACJA NIEUDANA — " + value.split("\n")[0][:160])
                    self._refresh_projects()
                    messagebox.showerror("Operacja nie została ukończona", value)
                elif kind == "stage":
                    agent, status = value
                    if agent in self.statuses:
                        self.statuses[agent].set(status)
                    self.summary.set(f"{agent}: {status}")
                elif kind == "progress":
                    self.summary.set(value)
                elif kind == "connection":
                    self.connection.set(value)
                elif kind == "poll":
                    self._handle_poll(*value)
                elif kind == "guard":
                    self.summary.set(value)
                elif kind == "trace":
                    event = value.get("type")
                    if event == "start":
                        self._text(self.trace, f"\n--- {value.get('agent')} / {value.get('model')} ---\n", append=True)
                    elif event in {"chunk", "result"}:
                        self._text(self.trace, str(value.get("text", "")), append=True)
                    elif event == "phase":
                        self.metrics.set(value.get("message", "Model analizuje…"))
                    elif event == "metrics":
                        self.metrics.set(f"Wejście: {value.get('prompt_tokens', 0)} tok. · Wyjście: {value.get('output_tokens', 0)} tok. · {value.get('total_seconds', 0)} s · {value.get('tokens_per_second', 0)} tok/s")
            except Exception as exc:
                self.summary.set("Błąd interfejsu: " + str(exc))
        self.after(100, self._events)

    @staticmethod
    def _text(widget, text, append=False):
        widget.configure(state="normal")
        if not append:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        if append:
            if int(widget.index("end-1c").split(".")[0]) > 3000:
                widget.delete("1.0", "500.0")
            widget.see("end")
        widget.configure(state="disabled")

    def _close(self):
        if self.busy:
            messagebox.showinfo("Trwa praca", "Poczekaj na zakończenie operacji. Produkcję możesz zatrzymać przyciskiem „Zatrzymaj po etapie”.")
            return
        self.destroy()


if __name__ == "__main__":
    # Stable paths even when launched from a Windows shortcut or another directory.
    os.chdir(Path(__file__).resolve().parent)
    StudioApp().mainloop()

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from agents.topics import TopicsAgent
from core.channel_memory import ChannelMemory, FIELDS
from core.config import load_settings
from core.editor import FFmpegEditor
from core.elevenlabs_client import ElevenLabsClient
from core.env_settings import save_ai_settings
from core.ollama_manager import OllamaManager
from core.openai_gateway import OpenAIGateway
from core.pipeline import ContentPipeline
from core.project_store import ProjectStore
from core.system_monitor import get_memory_snapshot
from core.veo_client import VeoClient
from core.web_research import search_web, source_text
from core.youtube_publisher import UploadRequest, YouTubePublisher

AGENTS = ["Research", "Scenariusz", "Showrunner", "Lektor", "Grafika", "Montaż", "Kontrola", "YouTube Meta"]


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Content Studio v0.9.3 · Shorts 30 s")
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
        self.google_key = tk.StringVar(value=self.settings.google_api_key)
        self.elevenlabs_key = tk.StringVar(value=self.settings.elevenlabs_api_key)
        self.elevenlabs_voice = tk.StringVar(value=self.settings.elevenlabs_voice_id)
        self.video_format = tk.StringVar(value=self.settings.veo_aspect_ratio)
        self.max_clips = tk.IntVar(value=self.settings.veo_max_clips)
        self.media_status = tk.StringVar(value="Veo i ElevenLabs: jeszcze nie sprawdzono")
        self.music_path = tk.StringVar(value=self.settings.music_path)
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
        self._button(row, "Generuj projekt / film", self.start_pipeline)
        self.stop_button = ttk.Button(row, text="Zatrzymaj po etapie", state="disabled", command=self._stop)
        self.stop_button.pack(side="left", padx=8)
        self.internet_check = ttk.Checkbutton(row, text="Research w internecie", variable=self.online)
        self.internet_check.pack(side="left")
        resume_row = ttk.Frame(self.studio)
        resume_row.pack(fill="x")
        self._button(resume_row, "WZNÓW / NAPRAW OSTATNI PROJEKT", self.finish_last_project)
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
        self._button(top, "Importuj scenariusz", self.import_script)
        self._button(top, "Otwórz folder", self.open_project)
        self.file_combo = ttk.Combobox(self.projects, state="readonly")
        self.file_combo.pack(fill="x", pady=8)
        self.file_combo.bind("<<ComboboxSelected>>", self._preview_file)
        self.preview = ScrolledText(self.projects, height=10, wrap="word", state="disabled")
        self.preview.pack(fill="both", expand=True)
        resume = ttk.Frame(self.projects)
        resume.pack(fill="x", pady=(0, 8))
        self._button(resume, "WZNÓW / NAPRAW WYBRANY PROJEKT", self.finish_last_project)
        ttk.Label(resume, text="Kontynuuje od pierwszego brakującego etapu i zachowuje gotowe klipy.").pack(side="left", padx=8)
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
        ttk.Label(self.settings_tab, text="Qwen lokalnie wykonuje research, scenariusz, kontrolę i plan montażu.").pack(anchor="w")
        ttk.Label(self.settings_tab, textvariable=self.ram_label, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 0))
        self.ram_scale = ttk.Scale(self.settings_tab, from_=20, to=90, variable=self.ram, command=self._ram_text)
        self.ram_scale.pack(fill="x", pady=(2, 6))
        self._ram_text()

        ttk.Separator(self.settings_tab).pack(fill="x", pady=8)
        ttk.Label(self.settings_tab, text="Pionowy film 30 s · TikTok / YouTube Shorts", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.media_check = ttk.Checkbutton(
            self.settings_tab,
            text="Generuj pionowy film 9:16: Veo + lektor + napisy + MP4",
            variable=self.media,
        )
        self.media_check.pack(anchor="w", pady=(4, 6))

        keys = ttk.Frame(self.settings_tab)
        keys.pack(fill="x")
        ttk.Label(keys, text="Klucz Google AI Studio / Veo").grid(row=0, column=0, sticky="w")
        self.google_key_entry = ttk.Entry(keys, textvariable=self.google_key, show="*", width=54)
        self.google_key_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(keys, text="Klucz ElevenLabs").grid(row=0, column=1, sticky="w")
        self.elevenlabs_key_entry = ttk.Entry(keys, textvariable=self.elevenlabs_key, show="*", width=54)
        self.elevenlabs_key_entry.grid(row=1, column=1, sticky="ew")
        keys.columnconfigure(0, weight=1)
        keys.columnconfigure(1, weight=1)

        options = ttk.Frame(self.settings_tab)
        options.pack(fill="x", pady=8)
        ttk.Label(options, text="Format").grid(row=0, column=0, sticky="w")
        self.format_combo = ttk.Combobox(
            options, textvariable=self.video_format, state="readonly", values=("9:16",), width=10
        )
        self.format_combo.grid(row=1, column=0, sticky="w", padx=(0, 18))
        ttk.Label(options, text="Tryb oszczędny: 1 klip Veo Lite × 4 s").grid(row=0, column=1, sticky="w")
        self.clips_spin = ttk.Spinbox(options, from_=1, to=1, textvariable=self.max_clips, width=8, state="readonly")
        self.clips_spin.grid(row=1, column=1, sticky="w", padx=(0, 18))
        ttk.Label(options, text="Voice ID ElevenLabs (opcjonalnie)").grid(row=0, column=2, sticky="w")
        self.voice_entry = ttk.Entry(options, textvariable=self.elevenlabs_voice, width=34)
        self.voice_entry.grid(row=1, column=2, sticky="w")
        ttk.Label(options, text="Muzyka w tle (opcjonalnie, własny plik)").grid(row=2, column=0, columnspan=3, sticky="w", pady=(7, 0))
        self.music_entry = ttk.Entry(options, textvariable=self.music_path)
        self.music_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        ttk.Button(options, text="Wybierz plik", command=self.choose_music).grid(row=3, column=2, sticky="w")
        options.columnconfigure(1, weight=1)

        ttk.Label(
            self.settings_tab,
            text="Klucze są zapisywane tylko w lokalnym .env (ignorowanym przez Git). "
                 "Jeśli Voice ID jest puste, program wybierze pierwszy dostępny głos. "
                 "Każdy klip Veo może generować koszt.",
            wraplength=1000,
        ).pack(anchor="w")
        ttk.Label(self.settings_tab, textvariable=self.media_status).pack(anchor="w", pady=(4, 0))

        row = ttk.Frame(self.settings_tab)
        row.pack(fill="x", pady=8)
        self._button(row, "Zapisz ustawienia", self.save_settings)
        self._button(row, "Sprawdź Veo + głos + FFmpeg", self.test_media)
        self._button(row, "Połącz / załaduj qwen3:8b", lambda: self.model_action("load"))
        row = ttk.Frame(self.settings_tab)
        row.pack(fill="x")
        self._button(row, "Pobierz model", lambda: self.model_action("pull"))
        self._button(row, "Zwolnij RAM", lambda: self.model_action("unload"))
        self._button(row, "Sprawdź AI", self.check_ai)

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
        self.settings.google_api_key = self.google_key.get().strip()
        self.settings.elevenlabs_api_key = self.elevenlabs_key.get().strip()
        self.settings.elevenlabs_voice_id = self.elevenlabs_voice.get().strip()
        self.settings.veo_aspect_ratio = "9:16"
        self.video_format.set("9:16")
        self.settings.veo_model = "veo-3.1-lite-generate-preview"
        self.settings.veo_max_clips = 1
        self.settings.veo_duration_seconds = 4
        self.settings.elevenlabs_model = "eleven_flash_v2_5"
        self.max_clips.set(1)
        self.settings.music_path = self.music_path.get().strip()
        try:
            save_ai_settings(self.settings)
        except Exception as exc:
            messagebox.showerror("Ustawienia", str(exc))
            return False
        self.summary.set("Ustawienia zapisane. " + ("Tryb: pakiet tekstowy." if not self.media.get() else "Tryb: pełny film Veo."))
        return True

    def choose_music(self):
        path = filedialog.askopenfilename(
            title="Wybierz muzykę do filmu",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.flac"), ("Wszystkie pliki", "*.*")],
        )
        if path:
            self.music_path.set(path)

    def test_media(self):
        if not self.save_settings():
            return
        def work():
            results = [
                VeoClient(
                    self.settings.google_api_key,
                    model=self.settings.veo_model,
                    aspect_ratio=self.settings.veo_aspect_ratio,
                    resolution=self.settings.veo_resolution,
                    duration_seconds=self.settings.veo_duration_seconds,
                ).healthcheck(),
                ElevenLabsClient(self.settings.elevenlabs_api_key).healthcheck(
                    self.settings.elevenlabs_voice_id
                ),
                self.editor.version(),
            ]
            if not self.editor.available():
                raise RuntimeError("FFmpeg nie jest dostępny.")
            return "\n".join(results)
        def done(value):
            self.media_status.set("MEDIA: GOTOWE")
            messagebox.showinfo("Test mediów", value)
        self._job("Sprawdzam Veo, ElevenLabs i FFmpeg", work, done)

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
        for widget in (self.ram_scale, self.media_check, self.internet_check,
                       self.google_key_entry, self.elevenlabs_key_entry, self.voice_entry,
                       self.music_entry, self.clips_spin):
            widget.configure(state="disabled" if busy else "normal")
        self.format_combo.configure(state="disabled" if busy else "readonly")
        self.clips_spin.configure(state="disabled" if busy else "readonly")
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
        if self.media.get():
            missing = []
            if not self.settings.google_api_key:
                missing.append("klucz Google AI Studio / Veo")
            if not self.settings.elevenlabs_api_key:
                missing.append("klucz ElevenLabs")
            if not self.editor.available():
                missing.append("FFmpeg")
            if missing:
                messagebox.showwarning(
                    "Pełny film",
                    "Brakuje: " + ", ".join(missing) + ". Uzupełnij Ustawienia albo wyłącz pełny film.",
                )
                return
            if not messagebox.askyesno(
                "Koszt Veo",
                "Tryb oszczędny wygeneruje 1 płatny klip Veo Lite o długości 4 sekund. "
                "Montaż wykorzysta je ponownie do złożenia 30 sekund. Kontynuować?",
            ):
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
            if has_video:
                self._publish_project_private(project.path, automatic=True)
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
        markers = ("project.json", "state.json", "01_research.md", "02_script.txt", "03_shots.json")
        self.project_paths = sorted(
            (p for p in self.settings.projects_dir.iterdir()
             if p.is_dir() and p.name != "_memory" and any((p / name).exists() for name in markers)),
            reverse=True,
        )
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

    def import_script(self):
        source = filedialog.askopenfilename(
            title="Wybierz stary scenariusz",
            filetypes=[("Scenariusz", "*.txt *.md"), ("Wszystkie pliki", "*.*")],
        )
        if not source:
            return
        try:
            path = Path(source)
            script = path.read_text(encoding="utf-8-sig").strip()
            if not script:
                raise ValueError("Wybrany plik jest pusty.")
            project = self.store.create("Import: " + path.stem)
            project.write_text("02_script.txt", script)
            project.write_json(
                "state.json",
                {"status": "imported", "agent": "Scenariusz", "source_file": str(path)},
            )
            self.last_project = project.path
            self._refresh_projects()
            self.summary.set("Scenariusz zaimportowany. Kliknij „Dokończ wybrany projekt”.")
            messagebox.showinfo(
                "Import zakończony",
                "Scenariusz dodano do Projektów. Teraz wybierz „Dokończ wybrany projekt”.",
            )
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("Import scenariusza", str(exc))

    def finish_last_project(self):
        if not self.last_project:
            messagebox.showwarning("Projekt", "Wybierz projekt w zakładce Projekty.")
            return
        project = self.last_project
        script = project / "02_script.txt"
        clips = [
            path for path in list((project / "video_clips").glob("*.mp4")) + list((project / "video").glob("*.mp4"))
            if path.is_file() and path.stat().st_size >= 1024
        ]
        audio = project / "audio" / "narration.mp3"
        audio_ready = audio.exists() and audio.stat().st_size >= 1024
        if not self.save_settings():
            return

        missing = []
        if not audio_ready and not self.settings.elevenlabs_api_key:
            missing.append("klucz ElevenLabs")
        if not clips and not self.settings.google_api_key:
            missing.append("klucz Google/Veo")
        if missing:
            messagebox.showwarning("Dokańczanie", "Brakuje: " + ", ".join(missing) + ".")
            return

        if clips:
            question = (
                f"Znaleziono {len(clips)} zapisanych klipów. Użyję ich ponownie — Veo nie zostanie wywołane "
                "i nie naliczy nowego kosztu. Brakujące etapy zostaną odtworzone. Dokończyć?"
            )
        else:
            question = (
                "Projekt nie ma prawidłowych klipów. Program wznowi go od pierwszego brakującego etapu, "
                "a następnie wygeneruje 1 płatny klip Veo Lite o długości 4 sekund. Kontynuować?"
            )
        if not messagebox.askyesno("Dokończ projekt", question):
            return

        generate_veo = not bool(clips)
        def work():
            text_ready = script.exists() and (project / "07_youtube.json").exists()
            prompt_exists = (project / "04_video_prompts.json").exists() or (project / "04_image_prompts.json").exists()
            if not text_ready or (generate_veo and not prompt_exists):
                self._prepare_ai()
            return self.pipeline.finish_existing(
                project,
                allow_generate_veo=generate_veo,
                online=self.online.get(),
                status=lambda agent, state: self.events.put(("stage", (agent, state))),
            )
        def done(output):
            self._refresh_projects()
            detail = "Wykorzystano zapisane klipy bez nowego kosztu Veo." if clips else "Wygenerowano klipy ze starego scenariusza."
            self.summary.set("Film gotowy: " + str(output))
            self._publish_project_private(project, automatic=True)
        self._job("Dokańczam zapisany projekt", work, done)

    def youtube_auth(self):
        if not self.publisher.is_configured():
            messagebox.showwarning("YouTube", "Brak client_secret.json. Instrukcja: docs/YOUTUBE_SETUP.md")
            return
        self._job("Łączę YouTube", self.publisher.authenticate, lambda _: messagebox.showinfo("YouTube", "Połączenie zapisane w token.json."))

    def publish_last(self):
        if not self.last_project:
            return
        self._publish_project_private(self.last_project, automatic=False)

    def _publish_project_private(self, project: Path, *, automatic: bool):
        video = project / "exports/final.mp4"
        if not video.exists():
            messagebox.showwarning("Brak filmu", "Ten projekt nie zawiera gotowego filmu exports/final.mp4.")
            return
        uploaded = project / "08_upload.json"
        if uploaded.exists():
            try:
                video_id = str(json.loads(uploaded.read_text(encoding="utf-8")).get("video_id") or "")
            except (OSError, ValueError):
                video_id = ""
            if video_id:
                messagebox.showinfo("YouTube", "Ten projekt jest już wysłany jako PRIVATE.\nhttps://youtu.be/" + video_id)
                return
        if automatic and (not self.publisher.is_configured() or not self.publisher.token_file.exists()):
            messagebox.showinfo("Film gotowy", "Film zapisano lokalnie. Połącz YouTube, aby kolejne filmy wysyłały się automatycznie jako PRIVATE.")
            return
        try:
            meta = json.loads((project / "07_youtube.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Metadata", str(exc))
            return
        if not automatic and not messagebox.askyesno("YouTube PRIVATE", f"Wysłać jako PRIVATE?\n{meta.get('title', video.stem)}"):
            return
        request = UploadRequest(video_path=video, title=str(meta.get("title") or video.stem),
                                description=str(meta.get("description") or ""), privacy_status="private",
                                category_id=str(meta.get("category_id") or "22"), tags=[str(t) for t in meta.get("tags", [])])
        def work():
            video_id = self.publisher.upload(request)
            uploaded.write_text(
                json.dumps({"video_id": video_id, "privacy": "private", "url": "https://youtu.be/" + video_id}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return video_id
        self._job(
            "Automatycznie wysyłam film jako PRIVATE" if automatic else "Wysyłam PRIVATE",
            work,
            lambda vid: messagebox.showinfo("YouTube", "Wysłano jako PRIVATE.\nhttps://youtu.be/" + vid),
        )

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

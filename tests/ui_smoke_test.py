"""Run on a Windows desktop runner (Tk requires a display). No network/model calls."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

with TemporaryDirectory() as temp:
    with patch.dict(os.environ, {"PROJECTS_DIR": temp}):
        from app import StudioApp
        with patch.object(StudioApp, "_poll"), patch.object(StudioApp, "_events"):
            app = StudioApp()
            try:
                app.update_idletasks()
                assert len(app.tabs.tabs()) == 4
                app._set_busy(True)
                # Enter/callback path must not bypass the busy lock.
                with patch.object(app, "save_settings", side_effect=AssertionError("duplicate job")):
                    app.start_pipeline()
                app._set_busy(False)
                # A 32 GB machine with 22 GB free must not be rejected by a fixed +3 GB reserve.
                app.settings.ai_provider = "ollama"
                app.settings.ollama_ram_limit_percent = 50
                with patch("app.get_memory_snapshot", return_value=SimpleNamespace(total_gb=32, available_gb=22, ollama_ram_gb=0)), \
                     patch.object(app.ollama, "start_server", return_value=(True, "ok")), \
                     patch.object(app.ollama, "model_size_bytes", return_value=19 * 1024**3), \
                     patch.object(app.ollama, "inspect", side_effect=[SimpleNamespace(connected=True, model_loaded=False), SimpleNamespace(connected=True, model_loaded=True)]), \
                     patch.object(app.ollama, "load_model") as load:
                    app._prepare_ai()
                    load.assert_called_once()
                # Connecting the server itself never invokes the model/RAM preflight.
                with patch.object(app, "save_settings", return_value=True), \
                     patch.object(app, "_job", side_effect=lambda label, work, done: work()), \
                     patch.object(app, "_prepare_ai", side_effect=AssertionError("connection must not load model")), \
                     patch.object(app.ollama, "start_server", return_value=(True, "ok")), \
                     patch.object(app.ollama, "inspect"):
                    app.model_action("connect")
                app.memory.save({"rules": "test"})
                project = app.store.create("preview")
                project.write_text("02_script.txt", "hello")
                app.last_project = project.path
                app._refresh_projects()
                assert "hello" in app.preview.get("1.0", "end")
                for size in ("1180x820", "960x700"):
                    app.geometry(size)
                    for tab in app.tabs.tabs():
                        app.tabs.select(tab)
                        app.update_idletasks()
                        frame = app.nametowidget(tab)
                        for child in frame.winfo_children():
                            assert child.winfo_y() + child.winfo_height() <= frame.winfo_height() + 5, (size, tab, child)
                print("WINDOWS UI SMOKE OK")
            finally:
                app.destroy()

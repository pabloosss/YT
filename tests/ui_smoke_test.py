"""Run on a Windows desktop runner (Tk requires a display). No network/model calls."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

with TemporaryDirectory() as temp:
    with patch.dict(os.environ, {"PROJECTS_DIR": temp, "AI_PROVIDER": "demo", "AI_STUDIO_DEMO": "true"}):
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
                assert str(app.model_combo.cget("state")) == "disabled"
                app._set_busy(False)
                assert str(app.model_combo.cget("state")) == "normal"
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

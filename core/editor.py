from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


class FFmpegEditor:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def available(self) -> bool:
        return bool(shutil.which(self.ffmpeg_path))

    def version(self) -> str:
        if not self.available():
            return "FFmpeg nie znaleziony"
        result = subprocess.run(
            [self.ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.splitlines()[0] if result.stdout else "FFmpeg"

    def create_preview_from_image(
        self,
        *,
        image: Path,
        output: Path,
        duration_sec: int = 5,
    ) -> Path:
        if not self.available():
            raise RuntimeError("FFmpeg nie jest dostępny. Zainstaluj FFmpeg lub ustaw FFMPEG_PATH.")

        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-loop", "1",
            "-i", str(image),
            "-t", str(duration_sec),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            str(output),
        ]
        subprocess.run(cmd, check=True)
        return output

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


class FFmpegEditor:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def available(self) -> bool:
        if Path(self.ffmpeg_path).is_file():
            return True
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

    def render_storyboard(
        self,
        *,
        images: list[Path],
        durations: list[int],
        output: Path,
        audio: Path | None = None,
    ) -> Path:
        if not self.available():
            raise RuntimeError("FFmpeg nie jest dostępny. Zainstaluj FFmpeg lub ustaw FFMPEG_PATH.")
        if not images:
            raise ValueError("Brak obrazów do montażu.")
        if len(images) != len(durations):
            raise ValueError("Liczba obrazów i czasów ujęć musi być taka sama.")

        output.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output.parent / "_storyboard_concat.txt"

        lines: list[str] = []
        for image, duration in zip(images, durations):
            normalized = image.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{normalized}'")
            lines.append(f"duration {max(int(duration), 1)}")

        last = images[-1].resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{last}'")
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        command = [
            self.ffmpeg_path,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
        ]

        if audio and audio.exists():
            command += ["-i", str(audio)]

        command += [
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p",
            "-r", "30",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
        ]

        if audio and audio.exists():
            command += ["-c:a", "aac", "-shortest"]

        command += ["-movflags", "+faststart", str(output)]

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg zakończył się błędem:\n{result.stderr[-3000:]}")

        try:
            concat_file.unlink()
        except OSError:
            pass

        return output

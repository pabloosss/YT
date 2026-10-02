from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


class FFmpegEditor:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def _executable(self) -> str | None:
        if Path(self.ffmpeg_path).is_file():
            return str(Path(self.ffmpeg_path))
        system = shutil.which(self.ffmpeg_path)
        if system:
            return system
        try:
            import imageio_ffmpeg
            bundled = imageio_ffmpeg.get_ffmpeg_exe()
            return bundled if bundled and Path(bundled).is_file() else None
        except (ImportError, RuntimeError, OSError):
            return None

    def available(self) -> bool:
        return self._executable() is not None

    def version(self) -> str:
        executable = self._executable()
        if not executable:
            return "FFmpeg nie znaleziony"
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
        first = result.stdout.splitlines()[0] if result.stdout else "FFmpeg"
        return first + (" · wersja dołączona do aplikacji" if "imageio" in executable.lower() else "")

    @staticmethod
    def _concat_path(path: Path) -> str:
        return path.resolve().as_posix().replace("'", "'\\''")

    @staticmethod
    def _subtitle_filter(path: Path) -> str:
        value = path.resolve().as_posix().replace("\\", "/")
        value = value.replace(":", "\\:").replace("'", "\\'")
        style = "FontName=Arial,FontSize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=90"
        return f"subtitles='{value}':force_style='{style}'"

    def render_clips(
        self,
        *,
        clips: list[Path],
        output: Path,
        audio: Path | None = None,
        subtitles: Path | None = None,
        music: Path | None = None,
        aspect_ratio: str = "16:9",
    ) -> Path:
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny. Uruchom ponownie run_windows.bat.")
        existing = [path for path in clips if path.exists()]
        if not existing:
            raise ValueError("Brak klipów Veo do montażu.")

        output.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output.parent / "_video_concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{self._concat_path(path)}'" for path in existing) + "\n",
            encoding="utf-8",
        )

        has_audio = bool(audio and audio.exists())
        has_music = bool(music and music.exists())
        command = [executable, "-y"]
        if has_audio:
            command += ["-stream_loop", "-1"]
        command += ["-f", "concat", "-safe", "0", "-i", str(concat_file)]
        if has_audio:
            command += ["-i", str(audio)]
        if has_music:
            command += ["-stream_loop", "-1", "-i", str(music)]

        width, height = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
        ]
        if subtitles and subtitles.exists():
            filters.append(self._subtitle_filter(subtitles))
        filters.append("format=yuv420p")

        command += ["-map", "0:v:0", "-vf", ",".join(filters), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if has_audio and has_music:
            command += [
                "-filter_complex",
                "[1:a]apad=pad_dur=30,atrim=0:30,volume=1.0[voice];[2:a]volume=0.12[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[aout]", "-c:a", "aac", "-t", "30",
            ]
        elif has_audio:
            command += ["-map", "1:a:0", "-af", "apad=pad_dur=30,atrim=0:30", "-c:a", "aac", "-t", "30"]
        else:
            command += ["-an", "-t", "30"]
        command += ["-movflags", "+faststart", str(output)]

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        try:
            concat_file.unlink()
        except OSError:
            pass
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg zakończył się błędem:\n{result.stderr[-3000:]}")
        return output

    def render_storyboard(
        self,
        *,
        images: list[Path],
        durations: list[int],
        output: Path,
        audio: Path | None = None,
    ) -> Path:
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny. Uruchom ponownie run_windows.bat.")
        if not images:
            raise ValueError("Brak obrazów do montażu.")
        if len(images) != len(durations):
            raise ValueError("Liczba obrazów i czasów ujęć musi być taka sama.")

        output.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output.parent / "_storyboard_concat.txt"
        lines: list[str] = []
        for image, duration in zip(images, durations):
            lines.append(f"file '{self._concat_path(image)}'")
            lines.append(f"duration {max(int(duration), 1)}")
        lines.append(f"file '{self._concat_path(images[-1])}'")
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        command = [executable, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        if audio and audio.exists():
            command += ["-i", str(audio)]
        command += [
            "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p",
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ]
        if audio and audio.exists():
            command += ["-c:a", "aac", "-shortest"]
        command += ["-movflags", "+faststart", str(output)]

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        try:
            concat_file.unlink()
        except OSError:
            pass
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg zakończył się błędem:\n{result.stderr[-3000:]}")
        return output

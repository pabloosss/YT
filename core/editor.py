from __future__ import annotations

from pathlib import Path
import re
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

    def inspect_short(self, video: Path) -> dict:
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny.")
        result = subprocess.run(
            [executable, "-hide_banner", "-i", str(video)],
            capture_output=True, text=True, check=False,
        )
        details = result.stderr + "\n" + result.stdout
        dimensions = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", details)
        duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
        if not dimensions or not duration:
            raise RuntimeError("Nie można odczytać parametrów gotowego filmu.")
        width, height = int(dimensions.group(1)), int(dimensions.group(2))
        seconds = int(duration.group(1)) * 3600 + int(duration.group(2)) * 60 + float(duration.group(3))
        return {
            "width": width,
            "height": height,
            "duration_seconds": round(seconds, 2),
            "vertical": height > width,
            "short_eligible": height > width and 1 <= seconds <= 180,
        }

    def create_thumbnail(self, video: Path, output: Path) -> Path:
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny.")
        output.parent.mkdir(parents=True, exist_ok=True)
        filters = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,gblur=sigma=24[back];"
            "[fg]scale=-2:720[front];[back][front]overlay=(W-w)/2:0"
        )
        result = subprocess.run(
            [executable, "-y", "-ss", "2", "-i", str(video), "-frames:v", "1",
             "-filter_complex", filters, "-q:v", "2", str(output)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0 or not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError(f"Nie udało się utworzyć miniatury:\n{result.stderr[-1500:]}")
        return output

    def media_duration(self, media: Path) -> float:
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny.")
        result = subprocess.run(
            [executable, "-hide_banner", "-i", str(media)],
            capture_output=True, text=True, check=False,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr + result.stdout)
        if not match:
            raise RuntimeError("Nie można odczytać długości lektora.")
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))

    def prepare_shot(self, *, source: Path, output: Path, duration_seconds: float,
                     is_image: bool = False, movement: int = 0) -> Path:
        """Create one exact-duration vertical shot without looping its source."""
        executable = self._executable()
        if not executable:
            raise RuntimeError("FFmpeg nie jest dostępny.")
        duration = max(1.0, float(duration_seconds))
        output.parent.mkdir(parents=True, exist_ok=True)
        if is_image:
            zoom = "min(zoom+0.0007,1.12)" if movement % 2 == 0 else "if(lte(zoom,1.0),1.12,max(1.0,zoom-0.0007))"
            x = "iw/2-(iw/zoom/2)" if movement % 3 == 0 else "min(iw-iw/zoom,on*0.35)"
            filters = (
                "scale=900:1600:force_original_aspect_ratio=increase,crop=900:1600,"
                f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':"
                f"d={max(1, round(duration * 30))}:s=720x1280:fps=30,format=yuv420p"
            )
            command = [
                executable, "-y", "-loop", "1", "-i", str(source), "-vf", filters,
                "-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an", str(output),
            ]
        else:
            source_duration = max(0.1, self.media_duration(source))
            speed_factor = duration / source_duration
            filters = (
                f"setpts={speed_factor:.6f}*PTS,scale=720:1280:force_original_aspect_ratio=increase,"
                "crop=720:1280,fps=30,format=yuv420p"
            )
            command = [
                executable, "-y", "-i", str(source), "-vf", filters,
                "-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an", str(output),
            ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists() or output.stat().st_size < 1024:
            raise RuntimeError(f"Nie udało się przygotować ujęcia {output.name}:\n{result.stderr[-1800:]}")
        return output

    @staticmethod
    def _concat_path(path: Path) -> str:
        return path.resolve().as_posix().replace("'", "'\\''")

    @staticmethod
    def subtitle_profile() -> dict:
        return {
            "font": "Arial",
            "font_size": 20,
            "alignment": "bottom_center",
            "bottom_margin": 45,
            "max_words": 4,
            "safe_for_vertical_video": True,
        }

    @staticmethod
    def _subtitle_filter(path: Path) -> str:
        value = path.resolve().as_posix().replace("\\", "/")
        value = value.replace(":", "\\:").replace("'", "\\'")
        style = (
            "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginL=48,MarginR=48,MarginV=45"
        )
        return f"subtitles='{value}':force_style='{style}':original_size=720x1280"

    def render_clips(
        self,
        *,
        clips: list[Path],
        output: Path,
        audio: Path | None = None,
        subtitles: Path | None = None,
        music: Path | None = None,
        aspect_ratio: str = "16:9",
        duration_seconds: int = 30,
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

        duration_seconds = max(30, min(60, int(duration_seconds)))
        fade_start = max(0, duration_seconds - 2)
        width, height = (720, 1280) if aspect_ratio == "9:16" else (1280, 720)
        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
        ]
        if subtitles and subtitles.exists():
            filters.append(self._subtitle_filter(subtitles))
        filters.append(f"fade=t=out:st={duration_seconds - 1.5}:d=1.5")
        filters.append("format=yuv420p")

        command += ["-map", "0:v:0", "-vf", ",".join(filters), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if has_audio and has_music:
            command += [
                "-filter_complex",
                f"[1:a]apad=pad_dur={duration_seconds},atrim=0:{duration_seconds},afade=t=out:st={fade_start}:d=2,volume=1.0[voice];[2:a]volume=0.12,afade=t=out:st={fade_start}:d=2[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[aout]", "-c:a", "aac", "-t", str(duration_seconds),
            ]
        elif has_audio:
            command += ["-map", "1:a:0", "-af", f"apad=pad_dur={duration_seconds},atrim=0:{duration_seconds},afade=t=out:st={fade_start}:d=2", "-c:a", "aac", "-t", str(duration_seconds)]
        else:
            command += ["-an", "-t", str(duration_seconds)]
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

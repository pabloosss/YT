from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MemorySnapshot:
    total_gb: float
    used_gb: float
    available_gb: float
    ollama_ram_gb: float

    @property
    def used_percent(self) -> float:
        if self.total_gb <= 0:
            return 0.0
        return (self.used_gb / self.total_gb) * 100.0


def get_memory_snapshot() -> MemorySnapshot:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError(
            "Brakuje psutil. Uruchom ponownie run_windows.bat, aby doinstalować zależności."
        ) from exc

    vm = psutil.virtual_memory()
    ollama_rss = 0

    for process in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (process.info.get("name") or "").lower()
            if "ollama" in name:
                memory_info = process.info.get("memory_info")
                if memory_info:
                    ollama_rss += int(memory_info.rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    gb = 1024 ** 3
    return MemorySnapshot(
        total_gb=vm.total / gb,
        used_gb=vm.used / gb,
        available_gb=vm.available / gb,
        ollama_ram_gb=ollama_rss / gb,
    )

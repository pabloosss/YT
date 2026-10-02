# AI Content Studio

Lokalna aplikacja Windows do budowy wieloagentowego środowiska produkcji materiałów na YouTube.

## Stan projektu: v0.2

Aktualny pipeline:

```text
Temat
  ↓
Research Agent
  ↓
Script Agent
  ↓
Showrunner
  ↓
Graphics Agent
  ↓
Voice preparation
  ↓
lokalny folder projektu
```

Każdy projekt zapisuje się osobno w `projects/` i zawiera:

- `project.json`
- `01_research.md`
- `02_script.txt`
- `03_shots.json`
- `04_image_prompts.json`
- `05_narration.txt`
- `images/`
- `audio/`
- `video/`
- `exports/`

## Najprostszy start na Windows

1. Zainstaluj Python 3.11 lub nowszy.
2. Sklonuj repozytorium.
3. Kliknij:
   ```text
   run_windows.bat
   ```

Przy pierwszym uruchomieniu skrypt utworzy `.venv` i zainstaluje zależności.

## Tryb DEMO

Bez żadnego klucza API program może przejść przez cały pipeline na przykładowych danych.

Domyślnie:

```env
AI_STUDIO_DEMO=true
```

## OpenAI API

Skopiuj:

```text
.env.example
```

jako:

```text
.env
```

i ustaw:

```env
OPENAI_API_KEY=TWÓJ_KLUCZ
OPENAI_MODEL=gpt-5.6-sol
AI_STUDIO_DEMO=false
```

Nie wrzucaj pliku `.env` na GitHub.

## FFmpeg

Aplikacja wykrywa FFmpeg przez PATH. Można też podać własną ścieżkę:

```env
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
```

Moduł `core/editor.py` jest już przygotowany pod lokalny montaż.

## Test pipeline'u

```bash
python tests/smoke_test.py
```

Poprawny wynik:

```text
SMOKE TEST OK
```

## Architektura

```text
AI Content Studio
├── app.py
├── agents/
│   ├── research.py
│   ├── script.py
│   ├── showrunner.py
│   ├── graphics.py
│   └── voice.py
├── core/
│   ├── config.py
│   ├── openai_gateway.py
│   ├── pipeline.py
│   ├── project_store.py
│   ├── editor.py
│   └── youtube_publisher.py
└── projects/
```

## Kolejne etapy

1. prawdziwe generowanie grafik,
2. TTS / lektor,
3. automatyczny montaż FFmpeg,
4. Quality Control Agent,
5. Google OAuth + YouTube Publisher,
6. miniatury,
7. Analytics Agent,
8. kolejka wielu kanałów i pełny autopilot.

Docelowo główny program działa lokalnie, a tylko wybrane zadania wychodzą do skonfigurowanych API.

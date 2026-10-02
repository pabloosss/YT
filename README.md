# AI Content Studio

Lokalne środowisko wieloagentowe do produkcji filmów na YouTube.

## v0.3

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
Voice Agent
  ↓
FFmpeg Editor
  ↓
Quality Agent
  ↓
YouTube Metadata Agent
  ↓
YouTube Publisher
```

## Co już działa

- aplikacja desktopowa Windows w Python/Tkinter,
- osobny lokalny katalog dla każdego projektu,
- Research Agent,
- Script Agent,
- Showrunner rozbijający scenariusz na ujęcia,
- prompty graficzne,
- generowanie obrazów przez OpenAI,
- lektor OpenAI TTS,
- lokalny montaż FFmpeg,
- Quality Control,
- automatyczne metadata YouTube,
- OAuth YouTube,
- upload filmu przez YouTube Data API,
- upload z aplikacji jest obecnie wymuszony jako **PRIVATE**,
- tryb DEMO bez używania płatnych API.

## Uruchomienie na Windows

Zainstaluj Python 3.11+ i uruchom:

```text
run_windows.bat
```

Przy pierwszym starcie program sam tworzy `.venv` i instaluje zależności.

## Konfiguracja

Skopiuj:

```text
.env.example
```

do:

```text
.env
```

### Sam AI tekstowy

```env
OPENAI_API_KEY=TWÓJ_KLUCZ
OPENAI_MODEL=gpt-5.6
AI_STUDIO_DEMO=false
GENERATE_MEDIA=false
```

### Pełne generowanie mediów

```env
OPENAI_API_KEY=TWÓJ_KLUCZ
OPENAI_MODEL=gpt-5.6
AI_STUDIO_DEMO=false
GENERATE_MEDIA=true

OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=low

OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=coral
```

Generowanie mediów jest domyślnie wyłączone, żeby przypadkowe uruchomienie pipeline'u nie generowało kosztów API.

## FFmpeg

FFmpeg powinien znajdować się w PATH albo można podać pełną ścieżkę:

```env
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
```

## YouTube

Instrukcja:

```text
docs/YOUTUBE_SETUP.md
```

Do uploadu potrzebny jest OAuth Client ID typu **Desktop app** i plik `client_secret.json`.

## Pliki projektu

```text
projects/
└── 20261002_120000_temat/
    ├── project.json
    ├── 01_research.md
    ├── 02_script.txt
    ├── 03_shots.json
    ├── 04_image_prompts.json
    ├── 05_narration.txt
    ├── 06_quality.json
    ├── 07_youtube.json
    ├── pipeline_result.json
    ├── images/
    ├── audio/
    ├── video/
    └── exports/
        └── final.mp4
```

## Test

```bash
python tests/smoke_test.py
```

## Bezpieczeństwo

Nigdy nie commituj:
- `.env`,
- `client_secret.json`,
- `token.json`,
- kluczy OpenAI ani innych dostawców.

## Następne kroki

- edytor ustawień z poziomu GUI,
- podgląd storyboardu,
- generator miniatur,
- napisy,
- muzyka i automatyczny ducking,
- obsługa generatorów wideo,
- Analytics Agent,
- wiele kanałów,
- kolejka projektów,
- pełny autopilot z etapem ręcznej akceptacji.

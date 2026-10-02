# AI Content Studio

Lokalne środowisko wieloagentowe do produkcji filmów na YouTube.

## v0.6

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
- tryb DEMO bez używania płatnych API,
- lokalny backend Ollama (`qwen3:30b`) bez klucza API,
- przycisk `Sprawdź AI` do testowania połączenia z lokalnym modelem.

## Uruchomienie na Windows

Zainstaluj Python 3.11+ i uruchom:

```text
run_windows.bat
```

Przy pierwszym starcie program sam tworzy `.venv` i instaluje zależności.

## Szybka konfiguracja lokalnego Qwen3 przez Ollamę

Od v0.6 nie trzeba ręcznie uruchamiać `ollama serve` ani przełączać programu z DEMO.

Po starcie AI Content Studio:
- wykrywa `ollama.exe`,
- uruchamia lokalny serwer Ollamy, jeśli nie działa,
- sprawdza, czy `qwen3:30b` jest pobrany,
- automatycznie przełącza tekstowych agentów na Ollamę,
- zapisuje poprawną konfigurację do `.env`,
- pokazuje stały status połączenia u góry aplikacji.

Jeśli model nie jest pobrany, można użyć przycisku **Pobierz model** bez otwierania PowerShella.

Dla istniejącej instalacji wystarczy:

```text
run_windows.bat
```

Skrypt utworzy lokalny `.env`:

```env
AI_PROVIDER=ollama
AI_STUDIO_DEMO=false
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:30b
OLLAMA_TIMEOUT=900
OLLAMA_KEEP_ALIVE=15m
GENERATE_MEDIA=false
```

Potem uruchom `run_windows.bat`. Na górze aplikacji powinno pojawić się:

```text
Tryb: OLLAMA · qwen3:30b
```

Przycisk **Sprawdź AI** sprawdza, czy lokalny serwer Ollamy odpowiada i czy model jest zainstalowany.

Tekstowi agenci działają wtedy lokalnie:

```text
Research → qwen3:30b
Scenariusz → qwen3:30b
Showrunner → qwen3:30b
Graphics prompts → qwen3:30b
YouTube Meta → qwen3:30b
```

`GENERATE_MEDIA=false` oznacza, że na tym etapie Qwen generuje tekst i prompty, ale nie obrazy ani audio.

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


## Sterowanie RAM-em i przebieg AI

W zakładce **AI / RAM** można teraz ustawić:
- model Ollama,
- profil pamięci: Niski RAM / Balans / Jakość,
- długość kontekstu `num_ctx`,
- maksymalną długość odpowiedzi `num_predict`,
- liczbę wątków CPU,
- czas pozostawania modelu w RAM,
- głębsze rozumowanie,
- automatyczne zwalnianie modelu po każdym zapytaniu.

Aplikacja pokazuje też rzeczywiste użycie RAM przez procesy Ollamy oraz dane z `/api/ps`.

Zakładka **Przebieg AI** pokazuje na żywo generowany wynik, aktualny etap oraz metryki: tokeny wejściowe/wyjściowe, czas i prędkość generowania. Ukryty tok rozumowania modelu nie jest wyświetlany.

### Ważne o RAM

Nie istnieje twardy limit RAM ustawiany pojedynczym parametrem zapytania. Wagi modelu mają stały koszt pamięci. Największy wpływ na dodatkową pamięć mają długość kontekstu oraz to, jak długo model pozostaje załadowany. Jeśli wymagany budżet RAM jest mniejszy niż sam model, trzeba użyć mniejszego modelu.


## Status połączenia v0.6

Górny panel pokazuje rzeczywisty stan lokalnego AI:
- **AI: POŁĄCZONO · MODEL ZAŁADOWANY** — serwer działa i model jest w RAM,
- **AI: POŁĄCZONO · MODEL GOTOWY** — serwer działa, model jest pobrany i załaduje się przy użyciu,
- **AI: OLLAMA DZIAŁA · BRAK MODELU** — Ollama działa, ale wybranego modelu nie ma,
- **AI: OLLAMA WYŁĄCZONA** — aplikacja widzi instalację, ale serwer nie odpowiada,
- **AI: OLLAMA NIEZNALEZIONA** — aplikacja nie znalazła instalacji.

Przycisk **Połącz / uruchom AI** uruchamia serwer i ładuje wybrany model. Status jest odświeżany automatycznie co kilka sekund.

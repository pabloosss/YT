# AI Content Studio v0.9.1 — TikTok / YouTube Shorts

Windowsowa aplikacja, która prowadzi projekt od tematu do gotowego pionowego filmu 9:16 o długości 30 sekund. Tekst i decyzje agentów wykonuje lokalny qwen3:8b w Ollamie. Klipy powstają w Google Veo, lektor i dokładne znaczniki napisów w ElevenLabs, a FFmpeg lokalnie składa final.mp4.

## Uruchomienie

Wymagane: Windows, Python 3.11+, Ollama oraz model qwen3:8b.

    cd "C:\Users\Pablo\Desktop\gra test\YT"
    git pull
    .\run_windows.bat

Launcher tworzy .venv, instaluje zależności (w tym awaryjną wersję FFmpeg) i uruchamia aplikację.

## Pierwsza konfiguracja

1. Otwórz **Ustawienia** i połącz Ollamę.
2. Wklej lokalnie nowy klucz Google AI Studio z dostępem do Veo.
3. Wklej lokalnie nowy klucz ElevenLabs. Nie używaj klucza ujawnionego wcześniej w rozmowie.
4. Opcjonalnie podaj Voice ID; bez niego aplikacja wybierze pierwszy głos dostępny na koncie.
5. Wybierz 16:9 dla YouTube albo 9:16 dla Shorts/TikToka.
6. Ustaw maksymalną liczbę płatnych klipów Veo.
7. Opcjonalnie wybierz własny plik muzyczny, do którego masz prawa.
8. Kliknij **Sprawdź Veo + głos + FFmpeg**, a potem zapisz ustawienia.

Klucze zapisują się wyłącznie w lokalnym .env, który jest ignorowany przez Git.

## Jak powstaje film

1. Research internetowy zbiera wyniki i adresy źródeł.
2. Lokalny Qwen przygotowuje research, scenariusz i plan ujęć.
3. Qwen tworzy po angielsku prompty filmowe dla Veo.
4. Veo generuje 4 pionowe klipy po około 8 sekund.
5. ElevenLabs tworzy jednego spójnego lektora i znaczniki czasu.
6. Aplikacja buduje plik SRT.
7. FFmpeg łączy klipy, dodaje lektora, cichą muzykę oraz duże wtopione napisy i kończy film dokładnie w 30. sekundzie.
8. Gotowy film trafia do projects/<projekt>/exports/final.mp4.
9. Metadata Agent przygotowuje tytuł, opis i tagi. Film można wysłać na YouTube wyłącznie jako PRIVATE.

Bez włączonej opcji pełnego filmu aplikacja nadal przygotowuje bezpłatny pakiet tekstowy.

## Pliki projektu

- 00_sources.json — wyniki wyszukiwania i linki;
- 01_research.md — research;
- 02_script.txt — scenariusz;
- 03_shots.json — plan ujęć;
- 04_video_prompts.json — prompty Veo;
- video_clips/ — klipy Veo;
- audio/narration.mp3 — lektor;
- subtitles/narration.srt — zsynchronizowane napisy;
- exports/final.mp4 — gotowy film;
- 06_quality.json, 07_youtube.json, pipeline_result.json — kontrola i metadata.

## Koszty i bezpieczeństwo

Ollama, planowanie, napisy i montaż FFmpeg są lokalne. Koszt generują Veo i ElevenLabs. Stała liczba 4 klipów ogranicza przypadkowe uruchomienie zbyt wielu generacji, ale aplikacja nie zna salda ani aktualnej ceny planu. Nie zamieszczaj .env, client_secret.json ani token.json na GitHubie.

Veo może odrzucić prompt przez zasady bezpieczeństwa albo limit konta. Częściowe wyniki zostają w folderze projektu. Pierwszy pełny test tworzy 4 klipy Veo, dlatego przed uruchomieniem sprawdź dostęp i koszt na swoim koncie.

## Pamięć kanału

Zakładka **Pamięć kanału** zapisuje lokalnie nazwę kanału, odbiorców, styl i własne zasady w projects/_memory/channel_profile.json. Profil jest dołączany do instrukcji agentów. Jest to pamięć kontekstowa, nie trenowanie wag Qwena.

## RAM

Projekt zawsze używa qwen3:8b. Domyślny budżet to 50% z 32 GB RAM, a kontekst 4096. Strażnik RAM jest miękkim zabezpieczeniem aplikacji, nie twardym limitem Windows.

## Testy

    python -m compileall -q app.py agents core tests
    $env:PYTHONPATH="."
    python tests/smoke_test.py
    python -m unittest discover -s tests -p "test_*.py" -v
    python tests/ui_smoke_test.py

CI uruchamia testy na Linuxie i Windowsie bez wywoływania płatnych API.

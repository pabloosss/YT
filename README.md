# AI Content Studio v0.9.5 — TikTok / YouTube Shorts

Windowsowa aplikacja, która prowadzi projekt od tematu do kompletnego pionowego filmu 9:16. Domyślny qwen3:14b dobiera długość opowieści od 30 do 60 sekund, redaguje tekst lektora i wykonuje kontrolę planu obrazu oraz końcową kontrolę. Klipy powstają w Google Veo, lektor i dokładne znaczniki napisów w ElevenLabs, a FFmpeg lokalnie składa final.mp4.

## Uruchomienie

Wymagane: Windows, Python 3.11+, Ollama oraz model qwen3:14b. W ustawieniach można przełączyć tryb na szybszy qwen3:8b.

    cd "C:\Users\Pablo\Desktop\gra test\YT"
    git pull
    .\run_windows.bat

Launcher tworzy .venv, instaluje zależności (w tym awaryjną wersję FFmpeg) i uruchamia aplikację.

## Pierwsza konfiguracja

1. Otwórz **Ustawienia** i połącz Ollamę.
2. Wklej lokalnie nowy klucz Google AI Studio z dostępem do Veo.
3. Wklej lokalnie nowy klucz ElevenLabs. Nie używaj klucza ujawnionego wcześniej w rozmowie.
4. Opcjonalnie podaj Voice ID; bez niego aplikacja wybierze pierwszy głos dostępny na koncie.
5. Format jest ustawiony na pionowe 9:16 dla Shorts i TikToka.
6. Tryb zbalansowany dobiera 2–3 płatne klipy Veo do długości historii.
7. Opcjonalnie wybierz własny plik muzyczny, do którego masz prawa.
8. Kliknij **Sprawdź Veo + głos + FFmpeg**, a potem zapisz ustawienia.

Klucze zapisują się wyłącznie w lokalnym .env, który jest ignorowany przez Git.

## Jak powstaje film

1. Research internetowy zbiera wyniki i adresy źródeł.
2. Lokalny Qwen przygotowuje research, scenariusz i plan ujęć.
3. Qwen tworzy po angielsku prompty filmowe dla Veo, a osobny przebieg lokalnej kontroli poprawia ich spójność, kadr 9:16 i wolne miejsce pod napisy.
4. Lokalny redaktor sprawdza, czy opowieść ma hook, logiczne rozwinięcie i pełny finał, bez urwanych zdań.
5. Veo 3.1 Lite generuje 2 lub 3 pionowe klipy po 4 sekundy — zależnie od długości historii.
6. ElevenLabs Turbo v2.5 tworzy jednego spójnego lektora i znaczniki czasu.
7. Aplikacja buduje plik SRT.
8. FFmpeg łączy klipy, dodaje lektora, cichą muzykę, małe napisy przy dolnej krawędzi oraz łagodne wygaszenie obrazu i dźwięku.
9. Gotowy film trafia do projects/<projekt>/exports/final.mp4, a klatka podglądowa do thumbnail/thumbnail.jpg.
10. Metadata Agent przygotowuje tytuł z #Shorts, opis i tagi. Końcowa kontrola Qwen podsumowuje całość i może zablokować automatyczny upload.

Po połączeniu YouTube zatwierdzony film jest automatycznie wysyłany jako PRIVATE razem z miniaturą. Aplikacja zapisuje ID i link w `09_upload.json` i nie wysyła drugi raz tego samego projektu. Widoczny przycisk **WZNÓW / NAPRAW PROJEKT** kontynuuje starszy lub przerwany projekt od pierwszego brakującego etapu, zachowując prawidłowe gotowe media.

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

Ollama, planowanie, napisy, kontrola i montaż FFmpeg są lokalne. Koszt generują Veo i ElevenLabs. Tryb zbalansowany używa 2–3 klipów Veo 3.1 Lite 720p po 4 sekundy oraz Eleven Turbo v2.5. Nie ucina mechanicznie tekstu: Qwen skraca lub rozwija go jako zamkniętą historię. Przed płatną generacją aplikacja pyta o zgodę, a przy ponowieniu wykorzystuje prawidłowe pliki już zapisane na dysku. Aplikacja nie zna salda ani aktualnej ceny planu. Nie zamieszczaj .env, client_secret.json ani token.json na GitHubie.

Veo może odrzucić prompt przez zasady bezpieczeństwa albo limit konta. Częściowe wyniki zostają w folderze projektu i są ponownie używane podczas wznowienia. Pełny projekt tworzy 2 albo 3 czterosekundowe klipy Veo Lite, dlatego przed uruchomieniem sprawdź dostęp i koszt na swoim koncie.

## Pamięć kanału

Zakładka **Pamięć kanału** zapisuje lokalnie nazwę kanału, odbiorców, styl i własne zasady w projects/_memory/channel_profile.json. Profil jest dołączany do instrukcji agentów. Jest to pamięć kontekstowa, nie trenowanie wag Qwena.

## RAM

Domyślny tryb dokładny używa qwen3:14b, a tryb szybki qwen3:8b. Przy zmianie aplikacja zwalnia drugi model, aby nie trzymać obu jednocześnie. Ustawienia serwera ograniczają Ollamę do jednego modelu i jednego zapytania naraz, włączają Flash Attention i cache q8_0. Domyślny budżet to 50% z 32 GB RAM, a kontekst 4096. Strażnik RAM jest miękkim zabezpieczeniem aplikacji, nie twardym limitem Windows.

Qwen3 jest modelem tekstowym: kontroluje scenariusz, opis ujęć, prompty, bezpieczne strefy napisów i parametry techniczne. Nie ogląda rzeczywistych klatek wygenerowanego filmu. Pionowy format, długość oraz stały profil małych napisów są sprawdzane i egzekwowane przez aplikację oraz FFmpeg.

## Testy

    python -m compileall -q app.py agents core tests
    $env:PYTHONPATH="."
    python tests/smoke_test.py
    python -m unittest discover -s tests -p "test_*.py" -v
    python tests/ui_smoke_test.py

CI uruchamia testy na Linuxie i Windowsie bez wywoływania płatnych API.

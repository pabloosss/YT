# AI Content Studio v0.10.0 — TikTok / YouTube Shorts

Windowsowa aplikacja, która prowadzi projekt od tematu do kompletnego pionowego filmu 9:16. Domyślny qwen3:14b działa jako lokalny reżyser: planuje, wykonuje niezależne kontrole, poprawia wyniki i korzysta z lokalnej pamięci doświadczeń. Klipy powstają w Google Veo, lektor i dokładne znaczniki napisów w ElevenLabs, a FFmpeg lokalnie składa final.mp4.

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
2. Lokalny Qwen przygotowuje research, a osobny przebieg fact-checkera usuwa twierdzenia niepoparte dostarczonymi materiałami.
3. Qwen przygotowuje scenariusz i plan ujęć według stałych zasad studia oraz zapisanych doświadczeń z zatwierdzonych filmów.
4. Qwen tworzy po angielsku prompty filmowe dla Veo, a osobny przebieg lokalnej kontroli poprawia ich spójność, kadr 9:16 i wolne miejsce pod napisy.
5. Lokalny supervisor sprawdza, czy opowieść ma hook, logiczne rozwinięcie i pełny finał; może przeprowadzić dwie rundy poprawy.
6. Program dobiera darmowe ilustracje z Wikimedia Commons wraz z autorem, źródłem i licencją.
7. ElevenLabs Turbo v2.5 tworzy lektora dopiero po zatwierdzeniu planu obrazu. Daty i lata są wcześniej zapisywane słownie po polsku.
8. Veo 3.1 Lite generuje 2 lub 3 najważniejsze pionowe klipy po 4 sekundy — dopiero po poprawnym lektorze.
9. FFmpeg tworzy 8–12 niepowtarzających się ujęć, animuje ilustracje i składa je bez zapętlania źródeł.
10. Aplikacja dodaje cichą muzykę, małe napisy przy dolnej krawędzi oraz łagodne wygaszenie obrazu i dźwięku.
11. Gotowy film trafia do projects/<projekt>/exports/final.mp4, a klatka podglądowa do thumbnail/thumbnail.jpg.
12. Metadata Agent przygotowuje tytuł z #Shorts, opis i tagi. Końcowa kontrola Qwen podsumowuje całość i może zablokować automatyczny upload.
13. Po zatwierdzonym filmie Qwen zapisuje maksymalnie trzy ogólne wnioski produkcyjne dla następnych projektów.

Po połączeniu YouTube zatwierdzony film jest automatycznie wysyłany jako PRIVATE razem z miniaturą. Aplikacja zapisuje ID i link w `09_upload.json` i nie wysyła drugi raz tego samego projektu. Widoczny przycisk **WZNÓW / NAPRAW PROJEKT** kontynuuje starszy lub przerwany projekt od pierwszego brakującego etapu, zachowując prawidłowe gotowe media.

Bez włączonej opcji pełnego filmu aplikacja nadal przygotowuje bezpłatny pakiet tekstowy.

## Pliki projektu

- 00_sources.json — wyniki wyszukiwania i linki;
- 00_studio_memory.txt — zasady produkcyjne użyte w danym projekcie;
- 01_research.md — research;
- 01_research_review.json — wynik niezależnej kontroli researchu;
- 02_script.txt — scenariusz;
- 03_shots.json — plan ujęć;
- 04_video_prompts.json — prompty Veo;
- video_clips/ — klipy Veo;
- shots/ — wszystkie gotowe ujęcia nazwane po polsku oraz pliki OPIS_UJEC.txt i ATRYBUCJE_WIKIMEDIA.txt;
- 05_shot_manifest.json — kolejność, opis, czas, pochodzenie i tagi każdego ujęcia;
- projects/_media_library/ — wspólna biblioteka materiałów do późniejszego ponownego użycia;
- audio/narration.mp3 — lektor;
- subtitles/narration.srt — zsynchronizowane napisy;
- exports/final.mp4 — gotowy film;
- 06_quality.json, 07_youtube.json, pipeline_result.json — kontrola i metadata.
- 10_studio_learning.json — propozycje i wnioski zapisane przez lokalne AI po zatwierdzeniu filmu.

## Koszty i bezpieczeństwo

Ollama, planowanie, pobieranie materiałów Commons, napisy, kontrola i montaż FFmpeg są lokalne lub bezpłatne. Koszt generują Veo i ElevenLabs. Tryb hybrydowy używa 2–3 klipów Veo 3.1 Lite 720p po 4 sekundy i uzupełnia je różnymi ilustracjami Wikimedia zamiast zapętlać film. Nie ucina mechanicznie tekstu: Qwen skraca lub rozwija go jako zamkniętą historię. Przed płatną generacją aplikacja pyta o zgodę, a przy ponowieniu wykorzystuje prawidłowe pliki już zapisane na dysku. Aplikacja nie zna salda ani aktualnej ceny planu. Nie zamieszczaj .env, client_secret.json ani token.json na GitHubie.

Veo może odrzucić prompt przez zasady bezpieczeństwa albo limit konta. Częściowe wyniki zostają w folderze projektu i są ponownie używane podczas wznowienia. Pełny projekt tworzy 2 albo 3 czterosekundowe klipy Veo Lite, dlatego przed uruchomieniem sprawdź dostęp i koszt na swoim koncie.

## Pamięć kanału

Zakładka **Pamięć kanału** zapisuje lokalnie nazwę kanału, odbiorców, styl i własne zasady w projects/_memory/channel_profile.json. Profil jest dołączany do instrukcji agentów. Jest to pamięć kontekstowa, nie trenowanie wag Qwena.

Każdy agent otrzymuje również stałe podstawowe instrukcje AI Content Studio: weryfikowanie źródeł, pełne zakończenie historii, brak powtarzanych ujęć, pionowy kadr, poprawną wymowę i oszczędzanie płatnych generacji. Po zatwierdzonym filmie model może zapisać do `projects/_memory/studio_lessons.json` maksymalnie trzy ogólne wnioski. Pamięć ma limit 20 wpisów, odrzuca sekrety, linki i kategorie faktograficzne. Można ją podejrzeć albo wyczyścić w GUI. Nie jest to fine-tuning modelu.

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

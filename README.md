# AI Content Studio v0.8

Lokalna aplikacja Windows do przygotowywania filmów YouTube/TikTok. Python + Tkinter, tekst przez Ollamę lub opcjonalnie OpenAI. Agenci pracują **kolejno, na jednym modelu**, aby nie mnożyć zużycia RAM.

## Uruchomienie

Wymagany Python 3.11+ i Ollama dla lokalnego tekstu. Kliknij `run_windows.bat`. Launcher tworzy `.venv`, sprawdza zależności i uruchamia okno. Aktualizacja istniejącej instalacji:

```powershell
cd "C:\Users\Pablo\Desktop\gra test\YT"
git pull
.\run_windows.bat
```

## Prosta obsługa

1. **Ustawienia**: wybierz `ollama`, model i zapisz. Dla 32 GB RAM + `qwen3:30b` użyj „Zastosuj profil 32 GB”: budżet 75%, kontekst 4096. Stare `.env` nie jest automatycznie nadpisywane nowymi limitami.
2. **Pamięć kanału**: wpisz odbiorców, styl, zasady i własną wiedzę; kliknij „Zapisz pamięć”.
3. **Tworzenie**: wpisz temat. Możesz wcześniej kliknąć „Znajdź tematy w internecie” — dostaniesz inspiracje z linkami. Wpisz wybrany temat i kliknij „Przygotuj projekt”.
4. **Projekty**: przeglądaj wyniki także po ponownym uruchomieniu aplikacji. Otwórz folder, sprawdź pliki, a gotowy film możesz wysłać jako PRIVATE.

Zakładka „Przebieg AI” znajduje się wewnątrz Tworzenia. Pokazuje wynik na żywo i metryki; ukryte rozumowanie nie jest wyświetlane.

## Co działa

- Research internetowy: wyszukiwanie DDGS bez klucza API, fragmenty wyników, linki i data pobrania. Internet jest wymagany. Zapytanie trafia do usług wyszukiwania, ale generowanie tekstu w trybie Ollama pozostaje lokalne.
- Błąd wyszukiwarki zatrzymuje etap. Nie ma cichego zastępowania źródeł wiedzą modelu. Można jawnie odznaczyć Internet, aby zrobić oznaczony szkic offline.
- To **research na podstawie fragmentów wyników**, nie pobieranie pełnych artykułów ani gwarantowany fact-check. Źródła i twierdzenia wymagają oceny człowieka. Nie ma jeszcze rankingu trendów ani autonomicznego wyboru strategii kanału.
- Research → Scenariusz → Showrunner → Grafika → Lektor → Montaż → Kontrola → YouTube Meta.
- Domyślnie powstaje **pakiet tekstowy**, nie film: research, scenariusz, ujęcia, prompty grafik, tekst narracji i metadata.
- Opcjonalne obrazy i głos z płatnego API OpenAI; montaż przez FFmpeg. Włącz media w Ustawieniach. Wymagane `OPENAI_API_KEY` w `.env` i FFmpeg. Modele API można zmienić w `.env`; dostępność zależy od konta.
- OAuth YouTube i upload zawsze PRIVATE; instrukcja: [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md).
- Zatrzymanie po bieżącym etapie, zapis częściowych wyników i stanu błędu. Bieżące żądanie kończy się przed zatrzymaniem; nie ma jeszcze wznawiania od dowolnego etapu.
- Kontrola sprawdza pliki i plan ujęć, **nie prawdziwość faktów ani jakość gotowego filmu**.

## Pamięć i „uczenie”

Profil zapisuje się lokalnie w `projects/_memory/channel_profile.json` (lub w odpowiednim `PROJECTS_DIR`). Maksymalnie 4000 znaków, żeby nie zapełniać kontekstu modelu. Obejmuje nazwę, odbiorców, styl, zasady i wiedzę. Zapis jest atomowy; uszkodzony plik nie jest po cichu zastępowany pustą pamięcią.

Profil jest dołączany do instrukcji agentów tekstowych przy każdym projekcie. Przykład: „Narracja po polsku, krótkie zdania. Nie wymyślaj cytatów. Oddzielaj legendy od źródeł historycznych.” Własne poprawki dopisz ręcznie i zapisz.

To **pamięć w kontekście, nie trening wag Qwena**. Nie modyfikuje modelu w Ollamie. Dawne projekty są dostępne w historii, ale nie są automatycznie wczytywane do modelu. Wygenerowane fakty nie stają się samoczynnie zaufaną wiedzą. Nie ma jeszcze RAG, importowania książek ani automatycznej pamięci ocen i statystyk kanału.

Każdy projekt zapisuje m.in.:

- `00_channel_profile.txt` — profil użyty dla tego projektu;
- `00_sources.json` — wyniki wyszukiwania, linki, fragmenty i czas;
- `01_research.md` do `07_youtube.json` — wyniki agentów;
- `state.json` — etap i stan completed/failed/cancelled;
- `pipeline_result.json` — informacja, czy faktycznie powstały media;
- `08_upload.json` — identyfikator wysłanego filmu, gdy upload się powiedzie.

Przy zmianie `PROJECTS_DIR` pamięć i historia są odczytywane z nowej lokalizacji. `projects/`, `.env`, `client_secret.json` i `token.json` są ignorowane przez Git. Przy własnym katalogu poza `projects/` nie dodawaj go do repozytorium. Warto tworzyć kopię zapasową projektów i profilu.

## RAM i stabilność

Domyślny budżet: 75%, suwak 20–90%, kontekst 4096. 75% z 32 GB to około 24 GB. To punkt startowy, nie gwarancja zmieszczenia każdego modelu: rozmiar zależy od wariantu, kontekstu i pozostałych procesów. Aplikacja sprawdza oszacowanie rozmiaru oraz dostępny RAM z zapasem dla systemu. Gdy model nie mieści się, wybierz np. `qwen3:8b` i pobierz go z GUI.

Monitor sprawdza procesy Ollamy co kilka sekund. Po przekroczeniu budżetu sygnalizuje zatrzymanie produkcji i próbuje zwolnić wybrany model. To **miękki strażnik**, nie limit systemowy ani gwarancja zapobieżenia wyczerpaniu RAM. Zwalnianie aktywnego modelu może poczekać na zakończenie żądania. Monitor obejmuje również inne procesy Ollamy, ale nie zarządza ich zadaniami.

Sprawdzanie połączenia i żądania modelu odbywają się poza wątkiem interfejsu. Powtórne kliknięcie/Enter nie uruchamia równoległej produkcji. Silnik nie przełącza się sam z OpenAI/demo na Ollamę. Dla skonfigurowanej Ollamy start najpierw pokazuje realny stan, a potem próbuje uruchomić serwer.

## Granice wersji

Brak lokalnego generatora obrazów i TTS, automatycznych miniatur, napisów, Analytics Agenta, wielu profili kanałów, kolejki i pełnego autopilota. To dalsze moduły, a nie działające opcje w GUI. Obecny montaż jest prostym storyboardem 1280×720; nie jest jeszcze edytorem pionowych TikToków.

## Testy

```powershell
python -m compileall -q app.py agents core tests
$env:PYTHONPATH="."
python tests/smoke_test.py
python -m unittest discover -s tests -p "test_*.py" -v
python tests/ui_smoke_test.py
```

GitHub Actions wykonuje testy na Linux i Windows, a test interfejsu na Windows. Testy regresji nie pobierają modeli, nie wywołują płatnych API i nie publikują filmów. Połączenie z Twoją Ollamą, realne obciążenie 32 GB RAM i media wymagają testu na docelowym komputerze.

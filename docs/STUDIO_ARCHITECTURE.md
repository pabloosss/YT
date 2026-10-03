# Przebudowa studia — v0.11

## Cel

Jedna lokalna aplikacja prowadzi projekt, przechowuje stan, instrukcje i media oraz ogranicza koszty. „Zamknięte środowisko” oznacza wspólne miejsce pracy, nie pełny offline: research, Veo, ElevenLabs i YouTube nadal komunikują się z internetem.

## Podział odpowiedzialności

| Rola | Odpowiedzialność | Ograniczenie |
| --- | --- | --- |
| Dyrektor | Cel odcinka, kąt narracji, pytania do researchu, kryteria odbioru | Nie zmienia uprawnień ani kosztów |
| Research | Materiał źródłowy | Fragmenty wyszukiwarki nie są pełną weryfikacją artykułów |
| Scenariusz | Zamknięta opowieść i tekst lektora | Nie dodaje nowych faktów |
| Showrunner | Plan ujęć | Ciągłość historii i różnorodność kadru |
| Grafika | Prompty i dobór materiałów | Budżet wykonania jest w kodzie |
| Lektor | Normalizacja i zlecenie TTS | Głos trzeba odsłuchać |
| Montaż | Wykonanie przez FFmpeg | Nie jest generatywnym modelem |
| Kontrola | Osobne przebiegi oceny tekstu/planu i pomiary plików | Ten sam model może powtórzyć swoje błędy |
| YouTube Meta | Tytuł, opis, tagi | Upload produkcyjny pozostaje prywatny |

Role tekstowe używają jednego modelu sekwencyjnie. Nie zwiększamy RAM przez uruchomienie wielu modeli jednocześnie. Model nie może sam uruchamiać dowolnych poleceń systemowych, zmieniać kodu, kasować projektów ani dokupywać kredytów.

## Kontrola jakości

Dyrektor zapisuje plan przed researchem. Kolejne zapytania otrzymują skrócony plan. Research ma kontrolę zgodności z dostarczonym materiałem, scenariusz ma maksymalnie dwie rundy oceny i korekty. Tryb dokładny wymaga obu rund, standardowy może zakończyć się po pierwszej pozytywnej. Kontrola planu obrazów odbywa się przed Veo, a końcowa ocena tekstu i parametrów przed publikacją.

To ograniczone przebiegi, nie niekończąca się pętla „myślenia”. Sama dłuższa praca ani samoocena AI nie gwarantują poprawy. Model tekstowy nie ogląda klatek ani nie odsłuchuje głosu.

## Pamięć i poprawianie działania

1. Instrukcje podstawowe: jawne zasady studia.
2. Profil kanału: preferencje i poprawki zapisane przez użytkownika.
3. Dokumenty projektu: plan, źródła, recenzje i parametry.
4. Propozycje lekcji: samodzielnie formułowane przez AI po zakończonym filmie.
5. Zatwierdzone lekcje: użytkownik ocenia propozycję, dopiero wtedy jest używana dalej.

Starsza wersja automatycznie nadawała wnioskom rangę „sprawdzonych”. To zostało zmienione: stare wpisy bez statusu czekają na zatwierdzenie. Nie trenujemy wag, nie obiecujemy autonomicznej poprawy jakości. Nowe propozycje nie wypierają zatwierdzonych zasad. Nie zapisujemy propozycji z próbki technicznej. Brak sukcesu opcjonalnego etapu uczenia nie wymusza ponownej płatnej produkcji.

## Próbka 4 sekundy

Osobna ścieżka w `core/test_clip.py`: test połączeń → prompt → kontrola promptu → krótki lektor → pomiar długości → jeden klip 4 s → napisy i montaż → pomiar MP4. Stały tekst testowy eliminuje konieczność researchu. Brak automatycznej publikacji, pamięci i ponowień płatnych generacji. Marker `test_mode.json` blokuje także ręczny upload w GUI i wznowienie w produkcyjnym pipeline. Próbka służy do oględzin obrazu, wymowy i napisów; nie ocenia jakości opowieści.

## Następne etapy — jeszcze niewdrożone

- Ocena człowieka przy konkretnym filmie (wymowa, tempo, fakty, kadry) jako dane do proponowania lekcji także z porażek.
- Stały zestaw kilku tych samych zadań i porównanie wyników przed/po zmianie modelu lub zasad. Mierzyć błędy, liczbę poprawek, czas oraz koszt, nie samoocenę modelu.
- Dopiero poprawa na tych zadaniach może pozwalać na automatyczne promowanie reguł, z historią wersji i możliwością cofnięcia.
- Model wizualny do kontroli klatek i transkrypcja głosu do kontroli wymowy, z uwzględnieniem RAM.
- Kontrola budżetu całego projektu, utrwalanie identyfikatorów operacji płatnych i precyzyjne wznawianie każdego etapu.
- Analytics Agent z rzeczywistymi statystykami kanału; bez danych nie wolno wymyślać trendów.

Nowy model wybieramy po porównaniu na tych samych zadaniach. W tej wersji pozostawiamy domyślny Qwen 14B i umożliwiamy wybór innego już zainstalowanego modelu. Nie jest to rekomendacja dowolnego większego modelu na 32 GB RAM.

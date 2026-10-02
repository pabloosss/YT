# Konfiguracja YouTube OAuth

AI Content Studio używa OAuth 2.0 do działań na Twoim kanale.

## 1. Google Cloud

1. Utwórz lub wybierz projekt w Google Cloud Console.
2. Włącz **YouTube Data API v3**.
3. Skonfiguruj ekran zgody OAuth.
4. Utwórz **OAuth Client ID** typu **Desktop app**.
5. Pobierz plik JSON z danymi OAuth.
6. Zmień jego nazwę na:

```text
client_secret.json
```

7. Umieść go w głównym katalogu AI Content Studio.

## 2. Połączenie kanału

Uruchom:

```text
run_windows.bat
```

Następnie kliknij:

```text
Połącz YouTube
```

Program otworzy przeglądarkę i poprosi o zgodę na zakres `youtube.upload`.

Po poprawnym logowaniu powstanie lokalny plik:

```text
token.json
```

`client_secret.json` i `token.json` są ignorowane przez Git i nie powinny trafiać do repozytorium.

## 3. Upload

Po wygenerowaniu pliku:

```text
projects/.../exports/final.mp4
```

przycisk **Wyślij PRIVATE** stanie się aktywny.

Na obecnym etapie aplikacja wymusza publikację jako **private**. Dzięki temu film nie zostanie przypadkiem opublikowany publicznie bez sprawdzenia.

## Ważne

Przed uruchomieniem automatycznej publikacji sprawdź:
- scenariusz,
- fakty,
- prawa do materiałów,
- miniaturę,
- audio,
- opis filmu,
- zasady YouTube dotyczące treści syntetycznych/AI.

# Pobieranie Danych Historycznych - Przewodnik

**Data:** 2026-02-18  
**Cel:** Pobranie danych tick dla lat 2021-2023  
**Potrzebne do:** Walk-forward validation

---

## 🎯 CEL

Uzupełnić brakujące dane historyczne aby zakończyć pełną walidację walk-forward 2021-2024.

**Obecnie mamy:**
- ✅ 2024 (Jun-Dec)

**Potrzebujemy:**
- ❌ 2021 (cały rok)
- ❌ 2022 (cały rok)
- ❌ 2023 (cały rok)

---

## 📥 PROCES POBIERANIA

### Skrypt Utworzony:

```
scripts/download_historical_data.py
```

**Co robi:**
1. Pobiera dane tick EURUSD z Dukascopy
2. Dla każdego roku: 01-01 do 12-31
3. Format: CSV z bid/ask/timestamp
4. Zapisuje w `data/raw/`

### Użycie:

```powershell
python scripts/download_historical_data.py
```

**Automatycznie:**
- Sprawdza czy plik już istnieje (nie pobiera ponownie)
- Pobiera 2021, 2022, 2023
- Raportuje postęp

---

## ⏱️ SZACOWANY CZAS

**Pojedynczy rok:**
- Rozmiar: ~2-4 GB
- Czas: ~10-30 minut (zależy od połączenia)

**Wszystkie 3 lata:**
- Rozmiar: ~6-12 GB
- Czas: ~30-90 minut

**Uwaga:** Dukascopy może ograniczać prędkość. Bądź cierpliwy.

---

## 📊 STRUKTURA DANYCH

### Po Pobraniu:

```
data/raw/
  eurusd-tick-2021-01-01-2021-12-31.csv  (~3-4 GB)
  eurusd-tick-2022-01-01-2022-12-31.csv  (~3-4 GB)
  eurusd-tick-2023-01-01-2023-12-31.csv  (~3-4 GB)
  eurusd-tick-2024-06-01-2024-12-31.csv  (~2 GB) ✅ już mamy
```

### Format CSV:

```
timestamp,ask,bid,askVolume,bidVolume
1609459200000,1.22150,1.22140,0.75,1.5
1609459200100,1.22151,1.22141,1.0,0.5
...
```

---

## 🔄 NASTĘPNE KROKI (PO POBRANIU)

### 1. Budowa H1 Bars

Dla każdego roku, zbuduj H1 bars:

```powershell
# Zaktualizuj config.yaml z odpowiednimi datami
# Lub użyj skryptu bezpośrednio

python scripts/build_h1_bars.py
```

**Alternatywnie:** Zmodyfikuj `build_h1_bars.py` aby automatycznie wykrywał wszystkie pliki tick i budował H1 dla każdego.

### 2. Uruchom Walk-Forward Validation

```powershell
python scripts/run_walkforward_validation.py
```

**Teraz powinno:**
- Wykryć lata 2021, 2022, 2023, 2024
- Uruchomić backtest dla każdego roku
- Wygenerować pełny raport

### 3. Przeanalizuj Wyniki

```powershell
cat data/outputs/walkforward_H1_summary.md
```

**Sprawdź:**
- Czy 3+ lata mają positive expectancy
- Czy średnia 4-letnia > 0
- Czy wyniki są stabilne

---

## ⚠️ MOŻLIWE PROBLEMY

### 1. Brak npx/dukascopy-node

**Błąd:** `'npx' is not recognized`

**Rozwiązanie:**
```powershell
npm install -g dukascopy-node
```

### 2. Timeout/Connection Issues

**Błąd:** Download fails or hangs

**Rozwiązanie:**
- Sprawdź internet
- Spróbuj ponownie (skrypt pomija istniejące pliki)
- Pobierz lata pojedynczo jeśli trzeba

### 3. Niewystarczająca Pamięć Dysku

**Błąd:** Not enough disk space

**Rozwiązanie:**
- Zwolnij ~15 GB miejsca
- Usuń niepotrzebne pliki

### 4. Corrupt Download

**Błąd:** CSV parsing errors later

**Rozwiązanie:**
- Usuń uszkodzony plik
- Pobierz ponownie

---

## 🔧 ALTERNATYWNE ŹRÓDŁA DANYCH

Jeśli Dukascopy nie działa:

### 1. Broker Historical Data
- Większość brokerów oferuje historię
- Format może być inny (wymaga konwersji)

### 2. TrueFX
- Darmowe dane tick
- Wymaga rejestracji

### 3. HistData.com
- Płatne ale niezawodne
- Już w formacie CSV

### 4. Własny Broker
- Jeśli masz konto z historią
- Export do CSV

---

## 📈 ROZSZERZENIE build_h1_bars.py

Możesz zmodyfikować aby automatycznie przetwarzał wszystkie lata:

```python
# W build_h1_bars.py
import glob

def build_all_years():
    raw_dir = "data/raw"
    tick_files = glob.glob(f"{raw_dir}/*-tick-*.csv")
    
    for tick_file in tick_files:
        print(f"Processing {tick_file}...")
        # Extract year from filename
        # Build H1 bars
        # Save separately or append
```

---

## 💾 ZARZĄDZANIE PLIKAMI

### Po Zakończeniu Testów:

**Opcja 1: Zachowaj Wszystko**
- Pro: Możesz powtórzyć testy
- Con: ~15 GB miejsca

**Opcja 2: Usuń Ticki, Zachowaj H1**
- Pro: Oszczędność miejsca (~90%)
- Con: Musisz ponownie pobrać jeśli chcesz inne TF

**Opcja 3: Skompresuj**
```powershell
# Zip tick files
7z a ticks_2021-2023.7z data/raw/*.csv
```

---

## 🎯 CEL KOŃCOWY

Po pobraniu wszystkich danych i zakończeniu walk-forward:

**Jeśli 3+ lata pozytywne:**
✅ Strategia ZWALIDOWANA
→ Przejdź do demo testing
→ Potencjalnie deploy

**Jeśli 2 lata pozytywne:**
⚠️ Wyniki MIESZANE
→ Extended demo (6-12 miesięcy)
→ Obserwuj stabilność

**Jeśli 0-1 lat pozytywnych:**
❌ Strategia NIE zwalidowana
→ 2024 był outlier
→ NIE deploy
→ Back to optimization

---

## 📊 PRZEWIDYWANE WYNIKI

### Optymistyczny Scenariusz:

```
2021: 12 trades, +0.25R
2022: 15 trades, +0.30R
2023: 13 trades, +0.20R
2024: 11 trades, +0.30R

Średnia: +0.26R ✅
Pozytywne: 4/4 lata ✅
→ ZWALIDOWANE!
```

### Realistyczny Scenariusz:

```
2021: 10 trades, +0.10R
2022: 14 trades, +0.25R
2023: 12 trades, -0.05R
2024: 11 trades, +0.30R

Średnia: +0.15R ✅
Pozytywne: 3/4 lata ✅
→ ZWALIDOWANE (z zastrzeżeniami)
```

### Pesymistyczny Scenariusz:

```
2021: 9 trades,  -0.15R
2022: 13 trades, -0.10R
2023: 11 trades, +0.05R
2024: 11 trades, +0.30R

Średnia: +0.025R ⚠️
Pozytywne: 2/4 lata ❌
→ NIE zwalidowane
```

---

## 🚀 QUICK START

**Wszystko w jednym:**

```powershell
# 1. Pobierz dane
python scripts/download_historical_data.py

# Poczekaj ~30-90 minut...

# 2. Zbuduj H1 bars (może wymagać modyfikacji skryptu)
python scripts/build_h1_bars.py

# 3. Uruchom walk-forward
python scripts/run_walkforward_validation.py

# 4. Zobacz wyniki
cat data/outputs/walkforward_H1_summary.md
```

**Total Time:** 3-4 godziny (większość to pobieranie)

---

## ✅ CHECKLIST

Przed uruchomieniem walk-forward:

- [ ] Dane 2021 pobrane
- [ ] Dane 2022 pobrane
- [ ] Dane 2023 pobrane
- [ ] Dane 2024 dostępne (już mamy)
- [ ] H1 bars zbudowane dla wszystkich lat
- [ ] Wystarczająco miejsca na dysku (~15 GB)
- [ ] Internet stabilny (do pobierania)

Po zakończeniu:

- [ ] Sprawdź walkforward_H1_summary.md
- [ ] Przeanalizuj wyniki per rok
- [ ] Podejmij decyzję o deployment
- [ ] Zachowaj lub usuń surowe dane tick

---

## 📝 STATUS

**Aktualnie:**
- ⏳ Pobieranie danych w toku
- ⏳ Szacowany czas: 30-90 minut

**Po zakończeniu:**
- Będziemy mieli kompletne dane 2021-2024
- Będziemy mogli wykonać pełną walidację
- Będziemy wiedzieć czy strategia jest profitable long-term

---

**Utworzono:** 2026-02-18  
**Status:** Pobieranie w toku  
**ETA do pełnej walidacji:** 3-4 godziny

---

*"Dane historyczne to fundament każdej solidnej walidacji. Bez nich to tylko zgadywanie."*

**Pobieramy dane. Niebawem będziemy wiedzieć prawdę o strategii!** 📊


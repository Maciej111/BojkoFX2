# 🚀 GRID SEARCH - INSTRUKCJE

**Status:** Grid search uruchomiony (30 konfiguracji)  
**ETA:** ~15-20 minut  
**Output:** Zapisywany do `grid_output.txt`

---

## ⏳ CO SIĘ DZIEJE

Grid search testuje 30 losowych kombinacji parametrów:
- entry_offset_atr_mult: 0.0-0.5
- pullback_max_bars: 10-40
- risk_reward: 1.5-2.5
- sl_anchor: last_pivot / pre_bos_pivot
- sl_buffer_atr_mult: 0.1-0.5

**Train:** 2021-2022  
**Test:** 2023-2024 (validation)

---

## 📊 SPRAWDZENIE POSTĘPU

```powershell
# Zobacz output
cat grid_output.txt

# lub tail aby zobaczyć koniec
Get-Content grid_output.txt -Tail 50
```

---

## 📁 WYNIKI (po zakończeniu)

### 1. Surowe dane:
```
data/outputs/trend_grid_results.csv
```

### 2. Raport:
```
reports/trend_grid_summary.md
```

### 3. Wykresy:
```
reports/grid_expectancy_vs_trades.png
reports/grid_expectancy_vs_missed.png
reports/grid_pareto.png
```

---

## 🔍 JAK PRZEANALIZOWAĆ WYNIKI

### Krok 1: Otwórz raport

```powershell
cat reports/trend_grid_summary.md
```

### Krok 2: Szukaj "Top 20 by Test Expectancy"

Wybierz konfiguracje z:
- ✅ test_expectancy_R > +0.10R
- ✅ test_trades >= 40
- ✅ test_max_dd_pct <= 15%

### Krok 3: Sprawdź train-test consistency

Jeśli train +0.30R, test +0.05R → **Overfit!**  
Jeśli train +0.15R, test +0.12R → **Good!**

---

## 🎯 WYBÓR NAJLEPSZEJ KONFIGURACJI

**Przykład dobrego wyniku:**
```
entry_offset_atr: 0.2
pullback_max_bars: 30
risk_reward: 2.0
sl_anchor: last_pivot
sl_buffer_atr: 0.3

Test: 52 trades, +0.18R, 45% WR, 12% DD
Train: 48 trades, +0.21R (podobne!)
```

**Użyj tej konfiguracji w `config/config.yaml`!**

---

## ⚡ JEŚLI CHCESZ WIĘCEJ KONFIGURACJI

### Opcja 1: Szybki test (50 configs, ~25 min)
```powershell
python scripts/run_trend_grid.py --max_runs 50 --random_sample true
```

### Opcja 2: Dokładny search (100 configs, ~50 min)
```powershell
python scripts/run_trend_grid.py --max_runs 100 --random_sample true
```

### Opcja 3: Bardzo dokładny (200 configs, ~2 hours)
```powershell
python scripts/run_trend_grid.py --max_runs 200 --random_sample true
```

### Opcja 4: FULL GRID (768 configs, ~6-8 hours)
```powershell
python scripts/run_trend_grid.py --max_runs 768 --random_sample false
```

---

## 🎓 INTERPRETACJA WYNIKÓW

### Świetny Wynik:
- Positive test expectancy: 30-50%
- Best config: +0.20R to +0.35R
- Low DD: <15%
- **Action:** Deploy!

### Dobry Wynik:
- Positive test expectancy: 15-30%
- Best config: +0.10R to +0.20R
- Moderate DD: 15-20%
- **Action:** Extended demo

### Słaby Wynik:
- Positive test expectancy: <10%
- Best config: <+0.10R
- High DD: >20%
- **Action:** Strategy needs work

---

## 📝 NASTĘPNE KROKI

### 1. Po zakończeniu grid search:

```powershell
# Zobacz wyniki
cat reports/trend_grid_summary.md
cat data/outputs/trend_grid_results.csv

# Zobacz wykresy
start reports/grid_pareto.png
```

### 2. Wybierz najlepszą konfigurację

Z raportu "Top 20 by Test Expectancy"

### 3. Zaktualizuj config.yaml

```yaml
trend_strategy:
  entry_offset_atr_mult: <best_value>
  pullback_max_bars: <best_value>
  risk_reward: <best_value>
  sl_anchor: <best_value>
  sl_buffer_atr_mult: <best_value>
```

### 4. Uruchom pełny backtest

```powershell
python scripts/run_backtest_trend.py --start 2021-01-01 --end 2024-12-31
```

### 5. Porównaj z baseline

Baseline (default params): 0.000R, 56 trades, 30% WR  
Optimized (best params): ???

---

## ⏰ SZACOWANY CZAS

**Obecnie uruchomione:** 30 configs  
**Start:** ~8 minut temu  
**Pozostało:** ~10-12 minut  

**Sprawdź za 5 minut:**
```powershell
Get-Content grid_output.txt -Tail 20
```

---

## 🆘 JEŚLI COŚ PÓJDZIE NIE TAK

### Problem: Brak outputu
```powershell
# Sprawdź czy proces działa
Get-Process python

# Zobacz plik output
ls grid_output.txt
```

### Problem: Błędy w grid_output.txt
```powershell
# Zobacz błędy
cat grid_output.txt | Select-String "Error"
cat grid_output.txt | Select-String "Traceback"
```

### Problem: Zbyt długo trwa
- 30 configs = ~15-20 min (normalnie)
- Jeśli >30 min, może być problem

---

**Current Status:** ⏳ **RUNNING**  
**ETA:** ~10-12 minut  
**Action:** Poczekaj na zakończenie, potem sprawdź wyniki!

---

*Grid search w toku... Znajdę najlepszą konfigurację!* 🔍📊


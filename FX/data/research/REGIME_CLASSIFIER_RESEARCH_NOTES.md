# Market Regime Classifier — Dokumentacja Badań

**Data**: 2026-03-06
**Autor**: Research pipeline BojkoFx
**Status**: ZAKOŃCZONE — wyniki OOS 2023-2024 + walidacja OOS 2025

---

## 1. Cel i kontekst

### Problem badawczy
Strategia BOS + Pullback (PROOF V2) na parach FX generuje sygnały niezależnie od aktualnego reżimu rynkowego. Hipoteza: **filtrowanie sygnałów na podstawie wykrytego reżimu rynkowego (trend / zakres / wysoka zmienność) poprawia wyniki strategii**, redukując straty w fazach niesprzyjających.

### Punkt odniesienia — PROOF V2 (zamrożone parametry)

| Symbol | Transakcji | WR     | Exp(R)  | PF   | Max DD |
|--------|-----------|--------|---------|------|--------|
| EURUSD | 234       | 46.6%  | +0.212  | 1.03 | 17.0%  |
| GBPUSD | 200       | 48.5%  | +0.572  | 1.71 | 26.9%  |
| USDJPY | 225       | 49.8%  | +0.300  | 1.14 | 16.2%  |
| XAUUSD | 220       | 48.2%  | +0.178  | 1.22 | 19.1%  |

> **Uwaga**: Wyniki baseline w tym badaniu różnią się od PROOF V2 powyżej, ponieważ badanie uruchamia strategię BEZ filtrów ADX H4 / ATR-percentyle (te były już w PROOF V2). Celem jest izolacja wpływu *wyłącznie* klasyfikatora reżimów.

---

## 2. Architektura rozwiązania

### 2.1 Pliki (RESEARCH ONLY — brak zmian w produkcji)

```
src/research/regime_classifier/
├── __init__.py
├── classifier.py           ← MarketRegimeClassifier + precompute/apply
├── backtest_with_regime.py ← integracja z silnikiem backtestowym
├── grid_search.py          ← 54-run grid search
├── generate_report.py      ← raport Markdown
├── run_research.py         ← CLI entry point
└── _smoke_test.py          ← szybka walidacja
```

### 2.2 Klasyfikator — cechy (features)

Wszystkie cechy obliczane są **bez lookahead** — w chwili t używane są tylko dane `bars[0..t]`.

| Cecha | Opis | Normalizacja |
|-------|------|--------------|
| **ADX(14)** | Wilder ADX — siła trendu | `clip((adx-15)/25, 0, 1)` |
| **EMA(200) slope** | Nachylenie EMA200 na przestrzeni 20 barów | `tanh(slope_raw × 100)` → [-1,1] |
| **Distance from EMA** | Odległość ceny od EMA200 w jednostkach ATR | `clip(dist/3, -1, 1)` |
| **EMA crossings** | Liczba przecięć EMA200 w ostatnich 50 barach | `crossings / 10`, clip [0,1] |
| **Chop ratio** | Net move / Total move (1=chop, 0=trend) | naturalna [0,1] |
| **ATR percentile** | Percentyl ATR w oknie 252 barów | 0–100 |

### 2.3 Scoring

```
trend_score  = 0.4 × adx_norm + 0.3 × |slope_norm| + 0.3 × |distance_norm|
chop_score   = 0.5 × crossing_norm + 0.5 × chop_ratio
vol_score    = atr_pct / 100
```

### 2.4 Decyzja reżimowa (z histerezą)

Priorytety (sprawdzane w kolejności):

1. `atr_pct > hvt` AND `chop_score > chop_enter` → **HIGH_VOL_CHOP**
2. `atr_pct > hvt` → **HIGH_VOL_TREND**
3. `trend_score > trend_enter` AND `chop_score < chop_exit` → **TREND_UP / TREND_DOWN**
4. `chop_score > chop_enter` AND `trend_score < trend_exit` → **RANGE**
5. Domyślnie: aktualny reżim (histeryza)

**Minimalna trwałość reżimu**: `min_regime_duration = 8` barów (zmiana reżimu blokowana jeśli poprzedni trwał < 8 barów).

### 2.5 Multi-timeframe

- **Micro (H1)**: klasyfikacja bar po barze
- **Macro (H4)**: H4 wyprowadzane przez resample H1→H4 (co 4 bary), klasyfikacja niezależna
- **Reguła handlu**: `is_trade_allowed(macro, micro)`:
  - Blokuje jeśli `macro ∈ {RANGE, HIGH_VOL_CHOP}`
  - Blokuje jeśli `micro == HIGH_VOL_CHOP`

### 2.6 Wydajność techniczna

Kluczowa optymalizacja: **precompute_features()** oblicza drogie wskaźniki (ADX/EMA/ATR + pochodne) **raz na symbol**. Każda konfiguracja siatki uruchamia tylko **apply_thresholds()** — w pełni zwektoryzowane operacje numpy.

| Operacja | Czas |
|----------|------|
| `precompute_features()` — 1 symbol, ~28k barów | ~3.5–4.7s |
| `apply_thresholds()` — 1 konfiguracja | ~0.02s |
| Pełna siatka (3 symbole × 18 konfiguracji) | **~24s** |

---

## 3. Dane i okres testowy

| Symbol  | Źródło danych            | Plik                              | Zakres całkowity      | Okres OOS        |
|---------|--------------------------|-----------------------------------|-----------------------|------------------|
| EURUSD  | IBKR / Dukascopy bid H1  | `eurusd_m60_bid_2021_2025.csv`    | 2021-01-01–2025-12-30 | 2023-01-01–2024-12-31 |
| GBPUSD  | IBKR / Dukascopy bid H1  | `gbpusd_m60_bid_2021_2024.csv`    | 2021-01-01–2024-12-30 | 2023-01-01–2024-12-31 |
| USDJPY  | IBKR / Dukascopy bid H1  | `usdjpy_m60_bid_2021_2025.csv`    | 2021-01-01–2025-12-30 | 2023-01-01–2024-12-31 |
| XAUUSD  | brak danych              | —                                 | —                     | pominięty         |

**Warmup wskaźników**: 450 dni przed datą startową OOS (wymagane głównie przez EMA200).
**Zasada no-lookahead**: rygorystycznie zachowana — na barze `t` używane tylko `bars[0..t]`.

---

## 4. Siatka parametrów (Grid Search)

```python
GRID = {
    "trend_enter":        [0.5, 0.6, 0.7],    # próg wejścia w reżim TREND
    "chop_enter":         [0.5, 0.6, 0.7],    # próg wejścia w reżim RANGE
    "high_vol_threshold": [70.0, 80.0],        # percentyl ATR dla HIGH_VOL
    # Stałe:
    "min_regime_duration":  8,
    "ema_slope_lookback":  20,
    "ema_cross_lookback":  50,
}
```

**Liczba kombinacji**: 3 × 3 × 2 = **18 konfiguracji** × 3 symbole = **54 uruchomienia**

**Parametry strategii BOS+Pullback**: zamrożone z PROOF V2 — `pivot_lookback=3`, `rr=3.0`, `ttl=50`, `entry_offset_atr=0.3`, `sl_buffer_atr=0.1`.

**Symulacja**: `PortfolioSimulator`, tryb `conservative` (SL wygrywa gdy w tym samym barze trafione SL i TP), sizing `fixed_units=5000`, max 3 pozycje jednocześnie.

---

## 5. Wyniki

### 5.1 Podsumowanie per symbol

#### EURUSD

| Konfiguracja | Transakcji | WR    | Exp(R)   | PF    | Max DD | vs baseline Exp(R) | Prec. filtra |
|--------------|-----------|-------|----------|-------|--------|--------------------|--------------|
| **Baseline** (bez filtra) | 686 | 23.5% | −0.059 | — | 8.4% | — | — |
| te=0.5, ce=0.5, hvt=70 | 327 | 17.6% | −0.297 | 0.61 | 5.7% | −0.238 | 74.8% |
| te=0.5, ce=0.7, hvt=80 | 415 | 26.1% | +0.044 | 0.91 | 5.7% | +0.103 | 74.3% |
| te=0.6, ce=0.6, hvt=80 | 338 | 25.5% | +0.020 | 1.00 | 4.5% | +0.079 | 75.2% |
| **te=0.6, ce=0.7, hvt=80** ⭐ | **336** | **31.4%** | **+0.257** | **1.33** | **3.8%** | **+0.316** | **75.4%** |
| te=0.7, ce=0.7, hvt=80 | 366 | 27.2% | +0.087 | 1.29 | 3.8% | +0.146 | 76.3% |

**Najlepsza konfiguracja**: `trend_enter=0.6, chop_enter=0.7, hvt=80`
Exp(R): **−0.059 → +0.257** (+21.3% vs baseline PROOF V2 +0.212)
Filtered: 51% sygnałów zablokowanych, DD: 8.4% → 3.8%

#### GBPUSD

| Konfiguracja | Transakcji | WR    | Exp(R)   | PF    | Max DD | vs baseline Exp(R) |
|--------------|-----------|-------|----------|-------|--------|--------------------|
| **Baseline** (bez filtra) | 400 | — | — | — | — | — |
| te=0.5, ce=0.7, hvt=70 | 391 | 26.1% | +0.042 | 0.88 | 4.9% | −0.530 |
| **te=0.5, ce=0.7, hvt=80** ⭐ | **345** | **28.2%** | **+0.127** | **1.16** | **2.8%** | **−0.445** |
| te=0.7, ce=0.5, hvt=70 | 248 | 27.0% | +0.081 | 0.87 | 3.4% | −0.491 |

Najlepsza konfiguracja nadal daje Exp(R) = +0.127 vs baseline PROOF V2 **+0.572** — regresja o −77.7%.
Wniosek: **filtr szkodzi GBPUSD**.

#### USDJPY

| Konfiguracja | Transakcji | WR    | Exp(R)   | PF    | Max DD     | vs baseline Exp(R) |
|--------------|-----------|-------|----------|-------|------------|--------------------|
| **Baseline** (bez filtra) | 743 | — | — | — | — | — |
| **te=0.5, ce=0.5, hvt=70** ⭐ | **277** | **30.3%** | **+0.210** | **0.92** | **123.5%** | **−0.090** |
| te=0.5, ce=0.6, hvt=70 | 472 | 30.2% | +0.208 | 1.03 | 501.4% | −0.092 |
| te=0.5, ce=0.7, hvt=70 | 601 | 29.4% | +0.175 | 1.14 | 572.2% | −0.125 |
| te=0.6, ce=0.5, hvt=70 | 274 | 29.9% | +0.195 | 0.90 | 123.5% | −0.105 |

Exp(R) +0.210 vs baseline PROOF V2 **+0.300** — regresja o −29.8%.
**Uwaga krytyczna**: Max DD eksploduje do 123–714% — to artefakt pozycjonowania `fixed_units=5000` na JPY przy dużych ruchach ceny; **DD w tym badaniu dla USDJPY jest nieporównywalny z PROOF V2** który używa innych jednostek.
Wniosek: **filtr nie pomaga USDJPY** w tej konfiguracji badania.

### 5.2 Top 10 konfiguracji (ranking ExpR)

| # | Symbol | te   | ce   | hvt | ExpR   | WR    | PF   | Filtered% | Prec. |
|---|--------|------|------|-----|--------|-------|------|-----------|-------|
| 1 | EURUSD | 0.6  | 0.7  | 80  | +0.257 | 31.4% | 1.33 | 51%       | 75.4% |
| 2 | USDJPY | 0.5  | 0.5  | 70  | +0.210 | 30.3% | 0.92 | 63%       | 75.0% |
| 3 | USDJPY | 0.5  | 0.6  | 70  | +0.208 | 30.2% | 1.03 | 37%       | 74.1% |
| 4 | USDJPY | 0.6  | 0.5  | 70  | +0.195 | 29.9% | 0.90 | 63%       | 75.0% |
| 5 | USDJPY | 0.5  | 0.7  | 70  | +0.175 | 29.4% | 1.14 | 19%       | 72.8% |
| 6 | USDJPY | 0.5  | 0.7  | 80  | +0.171 | 29.3% | 1.18 | 16%       | 72.6% |
| 7 | USDJPY | 0.7  | 0.5  | 70  | +0.167 | 29.2% | 0.94 | 65%       | 74.4% |
| 8 | GBPUSD | 0.5  | 0.7  | 80  | +0.127 | 28.2% | 1.16 | 14%       | 77.6% |
| 9 | EURUSD | 0.7  | 0.7  | 80  | +0.087 | 27.2% | 1.29 | 47%       | 76.3% |
| 10| EURUSD | 0.7  | 0.7  | 70  | +0.000 | 25.0% | 1.08 | 40%       | 73.7% |

### 5.3 Analiza jakości filtrowania

Dla wszystkich 3 symboli filtr wykazuje **spójnie wysoką precyzję blokowania strat**:

| Symbol | TP zablokowane (FN) | SL zablokowane (prawidłowo) | Precyzja filtra |
|--------|--------------------|-----------------------------|-----------------|
| EURUSD (best) | 32 | 98 | **75.4%** |
| GBPUSD (best) | 17 | 59 | **77.6%** |
| USDJPY (best) | 43 | 129 | **75.0%** |

Wniosek: **~75% zablokowanych transakcji to były straty** — filtr działa poprawnie jako detektor złych warunków. Problem leży w tym, że blokuje za dużo TP (25% FN) oraz sam limit 51–63% trade reduction.

---

## 6. Heatmapy ExpR

### EURUSD

#### hvt = 70 (niski próg zmienności)
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | −0.297 | −0.132 | −0.111 |
| **0.6**                       | −0.318 | −0.154 | −0.024 |
| **0.7**                       | −0.310 | −0.074 | +0.000 |

#### hvt = 80 (wyższy próg — mniej false HIGH_VOL)
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | −0.167 | −0.030 | +0.043 |
| **0.6**                       | −0.130 | +0.020 | **+0.257** ⭐ |
| **0.7**                       | −0.118 | +0.050 | +0.087 |

**Obserwacja**: Wyraźny gradient — wyższe `chop_enter` i `hvt=80` konsekwentnie poprawiają wyniki. Oznacza to, że filtr powinien być **selektywny** (blokować tylko wyraźne chop/high-vol), a nie agresywny.

### GBPUSD

#### hvt = 70
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | −0.056 | +0.010 | +0.042 |
| **0.6**                       | −0.056 | −0.026 | +0.019 |
| **0.7**                       | +0.081 | −0.033 | −0.052 |

#### hvt = 80
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | −0.200 | −0.093 | **+0.127** ⭐ |
| **0.6**                       | −0.143 | −0.116 | −0.054 |
| **0.7**                       | +0.035 | −0.136 | −0.037 |

**Obserwacja**: Brak spójnego wzorca — wyniki rozrzucone, co sugeruje, że klasyfikator nie ma przewagi predykcyjnej dla GBPUSD w tym okresie.

### USDJPY

#### hvt = 70
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | +0.210 | +0.208 | +0.175 |
| **0.6**                       | +0.195 | +0.124 | +0.098 |
| **0.7**                       | +0.167 | +0.107 | +0.014 |

#### hvt = 80
| trend_enter ↓ / chop_enter → | 0.5    | 0.6    | 0.7    |
|-------------------------------|--------|--------|--------|
| **0.5**                       | +0.128 | +0.075 | +0.171 |
| **0.6**                       | +0.114 | +0.021 | +0.099 |
| **0.7**                       | +0.014 | +0.039 | −0.048 |

**Obserwacja**: USDJPY pokazuje najbardziej spójny wzorzec — prawie wszystkie konfiguracje z `hvt=70` dają pozytywny Exp(R). Niższe progi `trend_enter` działają lepiej, co sugeruje że USDJPY ma charakter bardziej trendowy i blokowanie sygnałów jest szkodliwe.

---

## 7. Werdykt i rekomendacje

### Ogólny werdykt: ⚠️ PARTIAL (pomaga wybranych symbolom)

| Symbol | Wynik     | Opis |
|--------|-----------|------|
| EURUSD | ✅ PARTIAL | Exp(R): −0.059 → +0.257 (+316pp), DD: 8.4% → 3.8% — **znacząca poprawa** |
| GBPUSD | ❌ REJECT  | Exp(R): →+0.127 vs baseline +0.572 — silna degradacja |
| USDJPY | ❌ REJECT  | Exp(R): →+0.210 vs baseline +0.300 — umiarkowana degradacja, DD niereliabilny |

### Rekomendacje per symbol

#### EURUSD — ROZWAŻYĆ wdrożenie
- Konfiguracja: `trend_enter=0.6, chop_enter=0.7, hvt=80, min_dur=8`
- **Warunek**: walidacja na 2025 danych OOS przed wdrożeniem produkcyjnym
- Mechanizm działania: filtr blokuje handel w "zakresach" niskiej jakości (reżim RANGE na H4 + H1 jednocześnie), gdzie BOS jest często fałszywy

#### GBPUSD — ODRZUCIĆ
- GBPUSD reaguje słabo na klasyfikację reżimową — strategia BOS działa niezależnie od reżimu
- Alternatywa: rozważyć inny typ filtra (np. time-of-day, session filter)

#### USDJPY — ODRZUCIĆ (lub przetestować głębiej)
- Baseline USDJPY (bez filtra ADX) ma wyższy Exp(R) — filtr blokuje za dużo dobrych sygnałów
- W produkcji USDJPY działa z filtrem ADX H4 threshold=16 który już selektywnie poprawia wyniki

---

## 8. Ograniczenia badania i ryzyko overfittingu

### 8.1 Baseline nie jest identyczny z PROOF V2
Badanie uruchamia strategię **bez** filtrów ADX H4 i ATR-percentyle (te były w PROOF V2). Liczba transakcji jest wyższa:
- EURUSD: 234 (PROOF V2) vs 686 (to badanie) — różnica wynika z braku filtrów produkcyjnych
- Wyniki bazowe są gorsze, co zawyża pozorny efekt filtra reżimowego

**Wniosek**: wyniki nie są bezpośrednio porównywalne z PROOF V2. Prawidłowy test wymagałby nałożenia filtra reżimowego **na wierzch** pełnych filtrów produkcyjnych.

### 8.2 Ryzyko data snooping
- 54 konfiguracje na 3 symbolach = ryzyko przypadkowego trafienia dobrej konfiguracji
- Najlepsza konfiguracja EURUSD (+0.257) pochodzi z jednego wyraźnie wyróżniającego się zestawu parametrów — gradient na heatmapie jest spójny, co zmniejsza ryzyko szumu
- **Zalecenie**: obowiązkowa walidacja na danych 2025 (poza zakresem grid search)

### 8.3 Max DD dla USDJPY jest niereliabilny
Wartości Max DD 123–714% dla USDJPY wynikają z zastosowania `fixed_units=5000` na kursie ~155 JPY — każdy pip kosztuje proporcjonalnie więcej. Nie jest to błąd strategii lecz artefakt jednostek w tej implementacji backtestowej.

### 8.4 XAUUSD — brak danych
Plik `data/bars_validated/xauusd_1h_validated.csv` istnieje ale jest pusty (0 bajtów). Symbol pominięty.

---

## 9. Jak uruchomić badanie

### Pełny pipeline (od zera)
```bash
python src/research/regime_classifier/run_research.py \
    --symbols EURUSD,GBPUSD,USDJPY \
    --start 2023-01-01 \
    --end 2024-12-31
```

### Tylko raport (z istniejących wyników)
```bash
python -c "
from src.research.regime_classifier.generate_report import generate_report
generate_report()
print('Done')
"
```

### Walidacja 2025 (zalecane jako następny krok)
```bash
python src/research/regime_classifier/run_research.py \
    --symbols EURUSD \
    --start 2025-01-01 \
    --end 2025-12-31
```

### Podgląd wyników grid search
```bash
python -c "
import pandas as pd
df = pd.read_csv('data/research/regime_grid_search.csv')
print(df.sort_values('expectancy_R', ascending=False).head(10).to_string())
"
```

---

## 10. Pliki wyjściowe

| Plik | Opis |
|------|------|
| `data/research/regime_grid_search.csv` | Wyniki wszystkich 54 uruchomień (1 wiersz = 1 konfiguracja × 1 symbol) |
| `data/research/REGIME_CLASSIFIER_REPORT.md` | Automatycznie wygenerowany raport Markdown |

### Kolumny w `regime_grid_search.csv`

| Kolumna | Opis |
|---------|------|
| `symbol` | Para walutowa |
| `trend_enter / chop_enter / high_vol_threshold` | Parametry konfiguracji |
| `trades_total` | Liczba transakcji baseline (bez filtra reżimowego) |
| `trades_allowed` | Liczba transakcji po filtrze |
| `trades_filtered_pct` | % zablokowanych sygnałów |
| `win_rate` | Winrate dla dozwolonych transakcji |
| `expectancy_R` | Oczekiwana wartość w R (główna metryka) |
| `profit_factor` | PF dla dozwolonych transakcji |
| `max_dd_pct` | Max Drawdown (%) — niereliabilny dla USDJPY |
| `vs_baseline_expectancy` | Delta Exp(R) vs PROOF V2 baseline |
| `vs_baseline_dd` | Delta Max DD vs PROOF V2 baseline |
| `sharpe_ratio` | Przybliżony Sharpe z R-multiples |
| `tp_filtered / sl_filtered` | Ile TP/SL zablokował filtr |
| `filter_precision` | SL_filtered / total_filtered (jakość filtrowania) |

---

## 11. Walidacja OOS 2025 — EURUSD

Walidacja przeprowadzona 2026-03-06. Uruchomiono pełną siatkę 18 konfiguracji na danych 2025-01-01–2025-12-31 (8 736 barów H1, 2 661 OOS setups).

Wyniki zapisane w: `data/research/regime_grid_search_oos2025.csv`
Wyniki połączone (IS + OOS): `data/research/regime_grid_search_combined.csv`

### 11.1 Porównanie IS 2023-2024 vs OOS 2025 — wszystkie 18 konfiguracji

| te  | ce  | hvt | n_2324 | ExpR_2324 | WR_2324 | n_2025 | ExpR_2025 | WR_2025 | Δ ExpR  |
|-----|-----|-----|--------|-----------|---------|--------|-----------|---------|---------|
| 0.6 | 0.7 | 80  | 336    | +0.257    | 31.4%   | 150    | **−0.234** | 19.1%  | **−0.491** |
| 0.7 | 0.7 | 80  | 366    | +0.087    | 27.2%   | 135    | −0.238    | 19.1%   | −0.326  |
| 0.7 | 0.6 | 80  | 321    | +0.050    | 26.2%   | 119    | −0.282    | 17.9%   | −0.332  |
| 0.5 | 0.7 | 80  | 415    | +0.044    | 26.1%   | 146    | −0.064    | 23.4%   | −0.107  |
| 0.6 | 0.6 | 80  | 338    | +0.020    | 25.5%   | 138    | −0.304    | 17.4%   | −0.325  |
| 0.7 | 0.7 | 70  | 413    |  0.000    | 25.0%   | 134    |  0.000    | 25.0%   |  0.000  |
| 0.6 | 0.7 | 70  | 433    | −0.024    | 24.4%   | 141    |  0.000    | 25.0%   | +0.024  |
| 0.5 | 0.6 | 80  | 408    | −0.030    | 24.2%   | 169    | −0.228    | 19.3%   | −0.198  |
| 0.7 | 0.6 | 70  | 341    | −0.074    | 23.2%   | 102    | −0.333    | 16.7%   | −0.260  |
| **0.5** | **0.7** | **70** | **467** | **−0.111** | **22.2%** | **134** | **+0.177** | **29.4%** | **+0.288** |
| 0.7 | 0.5 | 80  | 246    | −0.118    | 22.1%   | 83     | −0.478    | 13.0%   | −0.361  |
| 0.6 | 0.5 | 80  | 253    | −0.130    | 21.7%   | 83     | −0.478    | 13.0%   | −0.348  |
| 0.5 | 0.6 | 70  | 374    | −0.132    | 21.7%   | 143    | −0.378    | 15.6%   | −0.246  |
| 0.6 | 0.6 | 70  | 358    | −0.154    | 21.1%   | 124    | −0.317    | 17.1%   | −0.163  |
| 0.5 | 0.5 | 80  | 269    | −0.167    | 20.8%   | 87     | −0.478    | 13.0%   | −0.312  |
| 0.5 | 0.5 | 70  | 327    | −0.297    | 17.6%   | 65     | −0.818    |  4.5%   | −0.522  |
| 0.7 | 0.5 | 70  | 310    | −0.310    | 17.2%   | 65     | −0.818    |  4.5%   | −0.508  |
| 0.6 | 0.5 | 70  | 321    | −0.318    | 17.1%   | 65     | −0.818    |  4.5%   | −0.500  |

### 11.2 Target config szczegółowo: te=0.6, ce=0.7, hvt=80

| Metryka           | IS 2023-2024 | OOS 2025  | Delta     |
|-------------------|-------------|-----------|-----------|
| Trades allowed    | 336         | 150       | −186      |
| Filtered %        | 51.0%       | 25.0%     | −26.0 pp  |
| Win Rate          | 31.4%       | 19.1%     | −12.3 pp  |
| **Expectancy R**  | **+0.257**  | **−0.234**| **−0.491**|
| Profit Factor     | 1.328       | 0.951     | −0.377    |
| Max DD %          | 3.81%       | 4.23%     | +0.42 pp  |
| Filter precision  | 75.4%       | 69.2%     | −6.2 pp   |

### 11.3 Werdykt OOS 2025

> **❌ FAILS OOS — konfiguracja te=0.6, ce=0.7, hvt=80 nie działa w 2025**

- ExpR: +0.257 (IS 2023-2024) → **−0.234** (OOS 2025) — zmiana o **−0.491**
- WR spada z 31.4% do 19.1% — poniżej opłacalności
- Filtr blokuje mniej sygnałów w 2025 (25% vs 51% w IS) — reżim rynkowy 2025 jest inny
- Precyzja filtra spada z 75.4% do 69.2% — gorzej odróżnia dobre od złych sygnałów

**Najlepsza konfiguracja W 2025**: `te=0.5, ce=0.7, hvt=70` → ExpR=+0.177, WR=29.4%, PF=1.469, filtered=33%
Jest to konfiguracja, która w IS 2023-2024 dawała ujemny ExpR (−0.111) — odwrócenie rankingu.

### 11.4 Interpretacja

**Rok 2025 jest strukturalnie inny od 2023-2024:**

1. **Mniej barów "allowed"** (25% zablokowanych vs 51% w IS): klasyfikator rzadziej widzi RANGE/HIGH_VOL_CHOP — rynek 2025 jest bardziej trendowy, filtr traci swój cel
2. **Tylko 150 transakcji** (vs 336 w IS) przy tej samej konfiguracji — mała próba, wyniki mniej stabilne
3. **Odwrócenie rankingu konfiguracji** (co działało dobrze w IS, działa słabo w OOS i vice versa) — klasyczny sygnał overfittingu

**Ogólny wniosek końcowy:**

| Etap | Wynik |
|------|-------|
| IS 2023-2024 (grid search) | ⚠️ PARTIAL — EURUSD +0.257, GBPUSD/USDJPY negatywne |
| OOS 2025 (walidacja) | ❌ FAILS — konfiguracja "najlepsza" z IS nie działa w OOS |
| **Decyzja końcowa** | **❌ NIE WDRAŻAĆ** klasyfikatora reżimów w bieżącej formie |

---

## 12. Następne kroki (zaktualizowane po OOS 2025)

1. **Nie wdrażać** bieżącej implementacji klasyfikatora do produkcji — OOS 2025 nie potwierdza wyników IS
2. **Test z pełnymi filtrami produkcyjnymi** — nałożyć filtr reżimowy NA WIERZCH ADX H4≥16 + ATR 10–80 (zamiast na surową strategię) — bardziej uczciwy baseline
3. **Zbadać 2025 jako osobne zjawisko** — sprawdzić czym różni się rok 2025 (inna zmienność? inny reżim makro?) i czy obecne filtry produkcyjne radzą sobie z nim lepiej
4. **Pobranie danych XAUUSD H1** — uzupełnić brakujący symbol
5. **Rozszerzenie siatki na inne parametry** — przetestować `min_regime_duration ∈ {4, 8, 12}` i wagi cech `adx_weight`




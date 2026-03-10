# Supply & Demand Backtest System

Kompletny system do backtestingu strategii Supply & Demand na danych tickowych Dukascopy (Bid/Ask), z konwersją tick→M15 bars, wykrywaniem stref DBR/RBD, zaawansowaną egzekucją (worst-case) i raportowaniem.

## 🚀 Funkcje

- ✅ **Pobieranie danych tickowych** z Dukascopy (via dukascopy-node)
- ✅ **Custom resampling** tick→bars z obsługą Bid/Ask OHLC
- ✅ **Wykrywanie stref S&D** (DBR/RBD patterns)
- ✅ **Zaawansowana egzekucja** z worst-case intra-bar policy
- ✅ **Anti-lookahead validation** - prevent same-bar entry
- ✅ **Touch tracking** - segmentacja wyników (1st, 2nd, 3rd touch)
- ✅ **Batch backtest** - wieloletnie testy z podziałem per rok
- ✅ **Sensitivity analysis** - grid test parametrów (±20%)
- ✅ **Zaawansowane metryki** - expectancy R, profit factor, max DD, losing streak

---

## 📋 Wymagania

### Software
- **Python 3.12+**
- **Node.js 18+** (do pobierania tików)

### Instalacja zależności

```powershell
# Python packages
pip install -r requirements.txt

# Node.js package (globalnie lub lokalnie)
npm install -g dukascopy-node
```

---

## 🔧 Konfiguracja

Edytuj `config/config.yaml`:

```yaml
data:
  symbol: "eurusd"
  start_date: "2024-06-01"
  end_date: "2024-12-31"
  timeframe: "15min"
  raw_dir: "data/raw"
  bars_dir: "data/bars"

strategy:
  base_body_atr_mult: 0.6        # Threshold dla bazy (body < X * ATR)
  impulse_atr_mult: 2.0          # Impulse candle threshold
  buffer_atr_mult: 1.0           # SL buffer
  risk_reward: 2.0               # TP ratio
  min_zone_width_pips: 3
  max_zone_width_pips: 20
  max_touches_per_zone: 3        # Deaktywacja strefy po N dotknięciach

execution:
  initial_balance: 10000.0
  max_positions: 1
  commission_per_lot: 7.0
  intra_bar_policy: "worst_case"
  allow_same_bar_entry: false    # Anti-lookahead: zapobiega entry w tej samej świecy co utworzenie strefy
```

---

## 🎯 Podstawowy Pipeline

### 1. Pobierz dane tickowe

```powershell
python scripts/download_ticks.py
```

**Co robi:**
- Pobiera tiki z Dukascopy dla symbolu/zakresu z `config.yaml`
- Zapisuje do `data/raw/`
- **Automatycznie pomija** jeśli plik już istnieje (oszczędza czas!)

**Output:** `data/raw/eurusd-tick-2024-06-01-2024-12-31.csv`

---

### 2. Zbuduj świece M15

```powershell
python scripts/build_bars.py
```

**Co robi:**
- Konwertuje tiki → świece M15
- Oddzielne OHLC dla Bid i Ask
- Forward-fill dla pustych świec
- Zapisuje do `data/bars/`

**Output:** `data/bars/eurusd_m15_bars.csv`

---

### 3. Uruchom backtest

```powershell
python scripts/run_backtest.py
```

**Co robi:**
- Wykrywa strefy S&D (DBR/RBD)
- Symuluje egzekucję (Limit orders, SL, TP)
- Generuje raporty

**Output:**
- `reports/trades.csv` - lista wszystkich transakcji
- `reports/summary.md` - podsumowanie metryk
- `reports/equity_curve.png` - krzywa kapitału
- `reports/histogram_R.png` - rozkład wyników

---

## 📊 Zaawansowane Funkcje

### Batch Backtest (wieloletni test z segmentacją)

Testuj wiele lat/symboli z podziałem na:
- **Okresy** (per rok + overall)
- **Segmenty** (ALL / FIRST_TOUCH / SECOND_TOUCH)

```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --tf M15 `
  --start 2022-01-01 `
  --end 2025-12-31 `
  --config config/config.yaml `
  --yearly_split true
```

**Parametry:**
- `--symbols` - Lista symboli (np. `EURUSD,GBPUSD`)
- `--tf` - Timeframe (domyślnie `M15`)
- `--start` / `--end` - Zakres dat (YYYY-MM-DD)
- `--yearly_split` - Podział per rok (`true`/`false`)

**Output:**
- `data/outputs/batch_summary.csv` - Wszystkie wyniki w CSV
- `reports/batch_summary.md` - Raport markdown z analizą
- `data/outputs/trades_{symbol}_{tf}_{period}.csv` - Szczegółowe transakcje per okres

**Przykładowy raport zawiera:**
- Wyniki per rok i per symbol
- Porównanie FIRST vs SECOND touch
- Top 5 konfiguracji
- Analiza expectancy i drawdown

---

### Sensitivity Test (optymalizacja parametrów)

Test wrażliwości parametrów z siatką ±20%:

```powershell
python scripts/run_sensitivity.py `
  --symbol EURUSD `
  --tf M15 `
  --start 2022-01-01 `
  --end 2025-12-31 `
  --config config/config.yaml
```

**Testuje:**
- `impulse_atr_mult` × {0.8x, 1.0x, 1.2x}
- `buffer_atr_mult` × {0.8x, 1.0x, 1.2x}
- `base_body_atr_mult` × {0.8x, 1.0x, 1.2x}

**= 27 kombinacji**

**Output:**
- `data/outputs/sensitivity_results.csv` - Wszystkie kombinacje
- `reports/sensitivity_summary.md` - Raport z analizą:
  - Top 10 konfiguracji (filtrowane po MaxDD)
  - Worst 5 konfiguracji
  - Analiza stabilności (std dev expectancy)
  - Impact analysis per parametr

---

## 🧪 Testy

Uruchom testy jednostkowe:

```powershell
# Wszystkie testy
pytest tests/

# Konkretny test
pytest tests/test_no_same_bar_entry.py
pytest tests/test_metrics_segments.py
pytest tests/test_tick_to_bars.py
```

**Pokrycie testów:**
- ✅ Anti-lookahead (same-bar entry prevention)
- ✅ Zone tracking (touch_no, zone_created_at)
- ✅ Metrics computation (expectancy R, profit factor, DD, losing streak)
- ✅ Segmentation (TOUCH_1, TOUCH_2, ALL)
- ✅ Tick-to-bars conversion

---

## 📈 Metryki

System oblicza następujące metryki (per segment):

| Metryka | Opis |
|---------|------|
| **trades_count** | Liczba transakcji |
| **win_rate** | Procent wygranych (%) |
| **expectancy_R** | Średni wynik w jednostkach ryzyka (R) |
| **avg_R** | Średnia R |
| **median_R** | Mediana R |
| **profit_factor** | Gross wins / Gross losses |
| **total_pnl** | Łączny zysk/strata ($) |
| **max_dd_percent** | Maksymalny drawdown (%) |
| **max_dd_dollars** | Maksymalny drawdown ($) |
| **max_losing_streak** | Najdłuższa seria strat |

---

## 📁 Struktura Projektu

```
Bojko/
├── config/
│   └── config.yaml              # Konfiguracja główna
├── data/
│   ├── raw/                     # Tiki (pobrane z Dukascopy)
│   ├── bars/                    # Świece M15
│   └── outputs/                 # Wyniki batch/sensitivity
├── reports/                     # Raporty i wykresy
├── scripts/
│   ├── download_ticks.py        # [1] Pobierz tiki
│   ├── build_bars.py            # [2] Zbuduj świece
│   ├── run_backtest.py          # [3] Uruchom backtest
│   ├── run_batch_backtest.py    # [4] Batch test
│   └── run_sensitivity.py       # [5] Sensitivity test
├── src/
│   ├── backtest/
│   │   ├── engine.py            # Główny silnik backtestu
│   │   ├── execution.py         # Egzekucja zleceń
│   │   └── metrics.py           # Obliczanie metryk
│   ├── data_processing/
│   │   └── tick_to_bars.py      # Konwersja tick→bars
│   ├── indicators/
│   │   └── atr.py               # ATR indicator
│   ├── zones/
│   │   └── detect_zones.py      # Wykrywanie stref S&D
│   ├── reporting/
│   │   └── report.py            # Generowanie raportów
│   └── utils/
│       └── config.py            # Ładowanie config
└── tests/
    ├── test_no_same_bar_entry.py
    ├── test_metrics_segments.py
    └── test_tick_to_bars.py
```

---

## 🔍 Anti-Lookahead Validation

System zawiera built-in zabezpieczenia przed look-ahead bias:

### 1. Zone Creation Check
Strefa może być użyta **dopiero w następnej świecy** po utworzeniu:
```python
# W config.yaml:
execution:
  allow_same_bar_entry: false  # (default)
```

### 2. Detection Logic
`detect_zones.py` używa tylko danych historycznych dostępnych do momentu `i`:
- ATR z poprzedniej świecy
- Base candles przed impulsem
- Zone creation time = czas impulsu

### 3. Tracking
Każda transakcja zawiera:
- `zone_created_at` - kiedy strefa powstała
- `entry_time` - kiedy nastąpiło wejście
- `touch_no` - która to próba (1, 2, 3...)

---

## 💡 Przykładowe Użycie

### Quick Start (pojedynczy test)

```powershell
# 1. Pobierz dane (jednorazowo)
python scripts/download_ticks.py

# 2. Zbuduj świece
python scripts/build_bars.py

# 3. Uruchom backtest
python scripts/run_backtest.py

# 4. Zobacz wyniki
cat reports/summary.md
```

### Wieloletnia walidacja

```powershell
# Test 2022-2025 z podziałem per rok
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2022-01-01 `
  --end 2025-12-31 `
  --yearly_split true

# Porównaj wyniki
cat reports/batch_summary.md
```

### Optymalizacja parametrów

```powershell
# Sensitivity test
python scripts/run_sensitivity.py `
  --symbol EURUSD `
  --start 2023-01-01 `
  --end 2024-12-31

# Zobacz najlepsze konfiguracje
cat reports/sensitivity_summary.md
```

---

## 📝 Status Projektu

Zobacz: [PROJECT_STATUS.md](PROJECT_STATUS.md)

---

## 🐛 Troubleshooting

### "No tick files found"
```powershell
# Uruchom download_ticks.py najpierw
python scripts/download_ticks.py
```

### "Bars file not found"
```powershell
# Uruchom build_bars.py
python scripts/build_bars.py
```

### "npx not found"
```powershell
# Zainstaluj Node.js, potem:
npm install -g dukascopy-node
```

### Testy nie przechodzą
```powershell
# Upewnij się że jesteś w venv i zainstalowałeś zależności
pip install -r requirements.txt
pytest tests/
```

---

## 📄 Licencja

Projekt do użytku prywatnego.

---

## 🤝 Współpraca

Pytania? Issues? Otwórz issue lub kontakt przez GitHub.

---

**Happy Backtesting! 📈**


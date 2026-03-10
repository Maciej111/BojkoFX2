# Quick Start Guide - Walidacja Hipotezy

## 🚀 Szybki Start (3 kroki)

### Krok 1: Przygotowanie danych (jednorazowo)

```powershell
# Pobierz tiki (jeśli jeszcze nie masz)
python scripts/download_ticks.py

# Zbuduj świece M15
python scripts/build_bars.py
```

### Krok 2: Wybierz typ testu

#### Opcja A: Prosty backtest

```powershell
python scripts/run_backtest.py
```

**Wyniki:** `reports/trades.csv`, `reports/summary.md`

---

#### Opcja B: Batch backtest (wieloletni + segmentacja)

```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2024-01-01 `
  --end 2024-12-31 `
  --yearly_split true
```

**Wyniki:**
- `data/outputs/batch_summary.csv` - tabela wszystkich wyników
- `reports/batch_summary.md` - raport z analizą
- Porównanie FIRST_TOUCH vs SECOND_TOUCH

---

#### Opcja C: Sensitivity test (optymalizacja parametrów)

```powershell
python scripts/run_sensitivity.py `
  --symbol EURUSD `
  --start 2024-06-01 `
  --end 2024-12-31
```

**Wyniki:**
- `data/outputs/sensitivity_results.csv` - 27 kombinacji parametrów
- `reports/sensitivity_summary.md` - analiza stabilności
- Top 10 najlepszych konfiguracji

---

### Krok 3: Analiza wyników

```powershell
# Zobacz podsumowanie
cat reports/batch_summary.md

# Zobacz sensitivity
cat reports/sensitivity_summary.md

# Otwórz CSV w Excelu
start data/outputs/batch_summary.csv
```

---

## 📊 Co analizować?

### 1. Win Rate by Touch:

Czy drugi touch jest lepszy niż pierwszy?

```
Szukaj w batch_summary.md:
- TOUCH_1 win_rate: X%
- TOUCH_2 win_rate: Y%
- Difference: ...
```

### 2. Expectancy R:

Który touch ma wyższy expectancy?

```
Szukaj:
- TOUCH_1 expectancy_R: X.XX
- TOUCH_2 expectancy_R: Y.YY
```

### 3. Stabilność parametrów:

Czy wyniki są stabilne przy małych zmianach parametrów?

```
Szukaj w sensitivity_summary.md:
- Std Dev Expectancy (R): X.XX
- Jeśli < 0.1 → STABLE
- Jeśli > 0.3 → SENSITIVE
```

---

## 🎯 Typowe Scenariusze

### Scenariusz 1: Sprawdź czy strategia działa w 2024

```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2024-01-01 `
  --end 2024-12-31 `
  --yearly_split false
```

Sprawdź w `reports/batch_summary.md`:
- Total trades
- Win rate
- Expectancy R
- Max DD

---

### Scenariusz 2: Porównaj 2023 vs 2024

```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2023-01-01 `
  --end 2024-12-31 `
  --yearly_split true
```

W `reports/batch_summary.md` zobaczysz:
- Wyniki per rok (2023, 2024, overall)
- Porównanie metryk

---

### Scenariusz 3: Znajdź najlepsze parametry

```powershell
python scripts/run_sensitivity.py `
  --symbol EURUSD `
  --start 2024-01-01 `
  --end 2024-12-31
```

W `reports/sensitivity_summary.md` zobaczysz:
- Top 10 konfiguracji (sorted by expectancy R)
- Impact analysis per parametr
- Stability analysis

---

## ⚙️ Modyfikacja Parametrów

Edytuj `config/config.yaml`:

```yaml
strategy:
  base_body_atr_mult: 0.6    # Zmień na 0.5 lub 0.7
  impulse_atr_mult: 2.0      # Zmień na 1.8 lub 2.2
  buffer_atr_mult: 1.0       # Zmień na 0.8 lub 1.2
  risk_reward: 2.0           # Zmień TP ratio
  max_touches_per_zone: 3    # Ile razy użyć strefy?

execution:
  allow_same_bar_entry: false  # ZAWSZE false (anti-lookahead)
```

Po zmianie uruchom backtest ponownie.

---

## 🐛 Troubleshooting

### "No tick files found"

```powershell
python scripts/download_ticks.py
```

### "Bars file not found"

```powershell
python scripts/build_bars.py
```

### Wyniki wyglądają dziwnie

Sprawdź:
1. Czy `allow_same_bar_entry: false` w config
2. Czy zakres dat jest poprawny
3. Czy dane są kompletne (brak luk)

---

## 📈 Przykładowe Metryki

Po uruchomieniu batch testu możesz zobaczyć:

```
| symbol | period | segment  | trades | win_rate | expectancy_R | max_dd_% |
|--------|--------|----------|--------|----------|--------------|----------|
| EURUSD | 2024   | ALL      | 42     | 45.24%   | 0.28         | 8.5%     |
| EURUSD | 2024   | TOUCH_1  | 28     | 42.86%   | 0.15         | 7.2%     |
| EURUSD | 2024   | TOUCH_2  | 14     | 50.00%   | 0.52         | 6.8%     |
```

**Interpretacja:**
- Second touch ma wyższy win rate (50% vs 42%)
- Second touch ma wyższy expectancy (0.52R vs 0.15R)
- Second touch ma niższy DD
- **Wniosek:** Second touch może być bardziej zyskowny!

---

## 💡 Wskazówki

1. **Zawsze używaj danych out-of-sample** - testuj na innych okresach niż optymalizacja
2. **Sprawdź różne symbole** - czy strategia działa tylko na EURUSD?
3. **Minimum 100 transakcji** - żeby statystyki były wiarygodne
4. **Max DD < 20%** - jako threshold dla akceptowalnych parametrów
5. **Expectancy R > 0.3** - minimum dla zyskownej strategii

---

## 📞 Pomoc

Zobacz:
- `README.md` - pełna dokumentacja
- `IMPLEMENTATION_REPORT.md` - szczegóły techniczne
- `PROJECT_STATUS.md` - status projektu

---

## 📥 Crypto Data Download (Binance OHLCV)

Pobieranie historycznych danych krypto z Binance (publiczny endpoint, bez klucza API).

### Szybki start

```bash
# Pobierz dane dla wszystkich symboli z config/config.yaml
python scripts/download_crypto_data.py

# Podaj symbole i timeframe ręcznie
python scripts/download_crypto_data.py --symbols BTC/USDT,ETH/USDT --timeframes 1h,15m

# Własna data startowa
python scripts/download_crypto_data.py --start 2022-01-01

# Jeden symbol, szybki test (kilka sekund)
python scripts/download_crypto_data.py --symbols BTC/USDT --timeframes 1h
```

### Konfiguracja (`config/config.yaml`)

```yaml
crypto:
  exchange: binance          # źródło danych (CCXT)
  symbols:
    - BTC/USDT
    - ETH/USDT
    - BNB/USDT
    - SOL/USDT
  timeframes:
    - 1h                     # można dodać 15m, 4h itp.
  start_date: "2022-01-01 00:00:00"
  data_dir: data/crypto
```

### Struktura plików wynikowych

```
data/crypto/
  binance/
    1h/
      BTCUSDT.csv    ← timestamp,open,high,low,close,volume
      ETHUSDT.csv
      BNBUSDT.csv
      SOLUSDT.csv
    15m/
      BTCUSDT.csv
      ...
```

### Resume (wznawianie)

Jeśli plik już istnieje, skrypt dociągnie **tylko brakujące świece** od
ostatniego timestamps + 1 interwał. Można uruchamiać codziennie cron-em:

```bash
# cron (Linux/VM) — codzienny update o 01:00 UTC
0 1 * * * cd /path/to/Bojko && .venv/bin/python scripts/download_crypto_data.py
```

### Użycie w backteście

```python
from src.data_sources import load_crypto_bars

# Zwraca DataFrame z kolumnami open_bid/ask, high_bid/ask, ... (jak forex)
df = load_crypto_bars("BTC/USDT", timeframe="1h")
```

### Testy jednostkowe

```bash
pytest tests/test_crypto_loader.py -v
```

---

**Happy Testing! 📊**


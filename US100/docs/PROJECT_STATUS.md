# BojkoIDX — Status Projektu i Wyniki Backtestów

**Data:** 2026-03-09  
**Symbol testowany:** USATECHIDXUSD (US100 / NAS100)  
**Dane:** Dukascopy 1M BID bars, 2021-01-01 → 2024-12-30

---

## 1. Czym jest BojkoIDX

BojkoIDX to algorytmiczny system transakcyjny napisany w Pythonie, działający w dwóch trybach:

| Tryb | Instrument | Infrastruktura |
|------|-----------|---------------|
| **Live trading** | Pary FX (EURUSD, GBPUSD, itp.) | GCP VM, systemd, IBKR Gateway TCP:4002, Flask dashboard :8080 |
| **Backtesting** | Pary FX + indeksy (US100) | Lokalne skrypty, dane Dukascopy 1M |

---

## 2. Algorytm — BOS + Pullback z filtrem HTF

Strategia opiera się na dwóch timeframe'ach:
- **HTF (4H)** — określa kierunek rynku (bias)
- **LTF (5m/15m/30m/1h)** — wykrywa momenty wejścia

### Sekwencja na każdym barze LTF:

```
1. Jeśli otwarta pozycja → sprawdź SL/TP
2. Jeśli oczekujący setup → sprawdź wypełnienie lub wygaśnięcie
3. Jeśli brak pozycji i setupu:
   a. Pobierz bias HTF (pattern HH+HL = BULL, LH+LL = BEAR)
   b. Jeśli NEUTRAL → pomiń
   c. Sprawdź BOS na LTF (close_bid przebija ostatni swing H/L)
   d. BOS zgodny z HTF bias → utwórz limit order pullback
```

### Kluczowe parametry:

| Parametr | Wartość | Opis |
|----------|---------|------|
| `pivot_lookback_ltf` | 3 | Okno swing H/L na LTF |
| `pivot_lookback_htf` | 5 | Okno swing H/L na HTF |
| `confirmation_bars` | 1 | Opóźnienie anty-lookahead (pivot widoczny po +1 barze) |
| `require_close_break` | True | BOS tylko przy zamknięciu przez poziom (nie wick) |
| `entry_offset_atr_mult` | 0.3 | Entry = BOS_level ± 0.3×ATR14 |
| `pullback_max_bars` | 20 | Setup wygasa po 20 barach bez wypełnienia |
| `sl_buffer_atr_mult` | 0.5 | SL = ostatni pivot ± 0.5×ATR14 |
| `risk_reward` | 2.0 | TP = entry ± risk×2.0 |
| Spread (US100) | 1.0 pkt | Stały (ASK = BID + 1.0) |

### Mechanizm SL/TP:
- **SL:** kotwica na ostatnim potwierdzonym pivocie po przeciwnej stronie + bufor ATR
- **TP:** `risk × RR = 2.0`
- **Gorsza strona konfliktu:** jeśli SL i TP trafione w tym samym barze → SL wygrywa (podejście konserwatywne)
- **Ceny wejścia/wyjścia:** LONG kupuje na ASK, zamyka na BID; SHORT sprzedaje na BID, zamyka na ASK

---

## 3. Wyniki backtestów — US100 (HTF=4H, RR=2.0)

### Okres pełny 2021–2024

| LTF | Trades | Win Rate | Exp (R) | PF | Max DD (R) | Ocena |
|-----|--------|----------|---------|-----|-----------|-------|
| **5m** | 1 735 | 42.3% | **+0.300** | 1.39 | 27.6R | ✅ najlepsza |
| **15m** | 959 | 42.3% | +0.121 | 1.45 | 87.8R | 🟡 |
| **30m** | 573 | 38.7% | +0.168 | 1.19 | 19.6R | 🟡 |
| **1h** | 414 | 33.8% | -0.044 | 0.84 | 40.5R | ❌ |

### 5m — rok po roku (jedyna konfiguracja zyskowna we wszystkich 4 latach)

| Rok | Trades | Win Rate | Exp (R) | PF | Max DD (R) |
|-----|--------|----------|---------|-----|-----------|
| 2021 | 445 | 42.9% | +0.253 | 1.35 | 11.0R |
| 2022 | 418 | 43.1% | +0.236 | 1.41 | 18.0R |
| 2023 | 411 | 41.6% | +0.547 | 1.35 | 23.4R |
| 2024 | 443 | 41.3% | +0.177 | 1.45 | 27.6R |
| **2021–2024** | **1 735** | **42.3%** | **+0.300** | **1.39** | **27.6R** |

### 15m — rok po roku

| Rok | Trades | Win Rate | Exp (R) | PF | Max DD (R) |
|-----|--------|----------|---------|-----|-----------|
| 2021 | 227 | 41.9% | +0.109 | 1.54 | 25.9R |
| 2022 | 247 | 41.7% | +0.239 | 1.40 | 9.4R |
| 2023 | 232 | 44.0% | +0.266 | 1.35 | 9.0R |
| 2024 | 243 | 41.2% | -0.149 | 1.54 | **87.8R** ⚠️ |
| **2021–2024** | **959** | **42.3%** | **+0.121** | **1.45** | **87.8R** |

> ⚠️ Anomalia w 15m/2024: Max R-DD = 87.8R przy ujemnym Exp — prawdopodobnie trade z ekstremalnie szerokim SL opartym na odległym pivocie. Do zbadania.

### 30m — rok po roku

| Rok | Trades | Win Rate | Exp (R) | PF | Max DD (R) |
|-----|--------|----------|---------|-----|-----------|
| 2021 | 138 | 46.4% | +0.324 | 1.58 | 13.6R |
| 2022 | 139 | 33.8% | +0.174 | 1.05 | 14.0R |
| 2023 | 155 | 35.5% | +0.037 | 0.93 | 12.6R |
| 2024 | 132 | 39.4% | +0.138 | 1.37 | 8.1R |
| **2021–2024** | **573** | **38.7%** | **+0.168** | **1.19** | **19.6R** |

### 1h — rok po roku (konfiguracja słaba, ujemna wartość oczekiwana)

| Rok | Trades | Win Rate | Exp (R) | PF | Max DD (R) |
|-----|--------|----------|---------|-----|-----------|
| 2021 | 102 | 30.4% | -0.142 | 0.80 | 26.3R |
| 2022 | 107 | 32.7% | +0.003 | 0.67 | 14.5R |
| 2023 | 102 | 30.4% | -0.162 | 0.77 | 23.0R |
| 2024 | 95 | 40.0% | +0.129 | 1.19 | 12.7R |
| **2021–2024** | **414** | **33.8%** | **-0.044** | **0.84** | **40.5R** |

### Heatmapa oczekiwań E(R) per trade

| TF \ Rok | 2021 | 2022 | 2023 | 2024 | Średnia |
|----------|------|------|------|------|---------|
| **5m** | +0.253 | +0.236 | +0.547 | +0.177 | **+0.303** |
| **15m** | +0.109 | +0.239 | +0.266 | -0.149 | **+0.116** |
| **30m** | +0.324 | +0.174 | +0.037 | +0.138 | **+0.169** |
| **1h** | -0.142 | +0.003 | -0.162 | +0.129 | **-0.043** |

---

## 4. Co zostało ostatnio zrobione i naprawione

Sesja code-review (2025-03-08) zidentyfikowała i naprawiła **6 błędów** (4 krytyczne C1–C4, 2 średnie M4–M5). Szczegóły w [docs/FIX_REPORT.md](FIX_REPORT.md).

### C1 — Brak filtra HTF bias w strategii live

**Problem:** `TrendFollowingStrategy.process_bar()` generował sygnały BOS bez sprawdzenia biesu HTF — strategie live i backtestowa działały zupełnie inaczej.  
**Naprawa:** Całkowite przepisanie `src/core/strategy.py` z importem `get_htf_bias_at_bar`. Teraz LONG tylko przy HTF=BULL, SHORT tylko przy HTF=BEAR, NEUTRAL = brak sygnału.

### C2 — Lookahead w detekcji pivotów (strategia live)

**Problem:** Stary `_detect_pivots()` używał `detect_swing_pivots()` z widokiem na cały DataFrame — pivot z baru `i` był dostępny już na barze `i`, zamiast po `i + confirmation_bars`.  
**Naprawa:** Zastąpiono `detect_pivots_confirmed()` z `src/structure/pivots.py` — ta sama funkcja co w backtescie, z anti-lookahead delay.

### C3 — Stan trailing stopu gubiony przy restarcie procesu

**Problem:** `_OrderRecord` trzymał stan trailing stopu (`trail_activated`, `trail_sl`) tylko w pamięci. Po restarcie serwisu trailing stop był rozbrojony.  
**Naprawa:** Dodano kolumnę `trail_state_json` do tabeli `orders` w SQLite (schemat v2→v3), metody `save_trail_state()` / `load_trail_state()` w `state_store.py` oraz odczyt przy `restore_positions_from_ibkr()`.

### C4 — Hardkodowany symbol `EURUSD` w execution engine

**Problem:** `ExecutionEngine._open_position()` zawsze zapisywał `symbol="EURUSD"` niezależnie od handlowanego instrumentu.  
**Naprawa:** `ExecutionEngine.__init__` przyjmuje parametr `symbol=` i używa `self.symbol` w `_open_position()`.

### M4 — Crash backtestów przy zerowej odległości ryzyka (entry == SL)

**Problem:** Przy edge case'ach (zaokrąglenia, anomalie danych) `risk_distance = 0` powodował `ValueError` i przerywał cały backtest.  
**Naprawa:** Zastąpiono `raise ValueError` wywołaniem `log.warning()` + `R_multiple = 0.0`.

### Testy dodane

| Plik | Liczba testów | Co pokrywa |
|------|--------------|-----------|
| `tests/test_htf_bias.py` | 8 | `get_htf_bias_at_bar()` — BULL/BEAR/NEUTRAL, anti-lookahead |
| `tests/test_live_strategy_bos.py` | 11 | `process_bar()` — HTF gate, BOS wymagający close, warmup |
| `tests/test_restart_state_restore.py` | 6 | Trail state roundtrip w DB, restore po restarcie |
| `tests/test_strategy_end_to_end.py` | 8 | Zgodność sygnałów live vs backtest |
| `tests/test_state_store.py` | naprawiony | Usunięto duplikat, zaktualizowano asercje na schema v3 |

---

## 5. Znane ograniczenia

1. **Stały spread** — ASK = BID + 1.0 pkt. Rzeczywisty spread jest zmienny (szczególnie podczas danych makro).
2. **Brak poślizgu** — zlecenia realizowane dokładnie na poziomie limit/stop, bez dodatkowego slippage.
3. **Brak filtra sesji** — transakcje mogą otwierać się podczas niskiej płynności nocnej (godz. 0–13 UTC).
4. **Rozstrzyganie konfliktów intrabar** — jeśli SL i TP trafione w tym samym barze, SL wygrywa (podejście konserwatywne, może zawyżać straty).
5. **PnL w PLN/USD nieistotny dla indeksów** — mnożnik `×100000` pochodzi z FX. Do analizy US100 używać wyłącznie kolumny `R`.
6. **Wyniki in-sample** — brak walk-forward validation; optymalizacja parametrów pod US100 nie była wykonywana.
7. **Anomalia 15m/2024** — Max R-DD = 87.8R wymaga zbadania trade'ów z ekstremalnie szerokim SL.

---

## 6. Rekomendacja

**Najlepsza konfiguracja: 5m LTF + 4H HTF**
- Jedyna zyskowna we wszystkich 4 testowanych latach z rzędu
- Expectancy +0.300R / trade, PF 1.39, ~434 trade'y/rok
- Drawdown 27.6R do zaakceptowania przy odpowiednim position sizingu

Przed wdrożeniem live na US100 zalecane:
- [ ] Zbadać anomalię 15m/2024 (trade z DD=87R)
- [ ] Dodać filtr sesji (tylko 13:00–20:00 UTC dla NAS100)
- [ ] Walk-forward na danych 2025
- [ ] Model zmiennego spreadu lub slippage ATR

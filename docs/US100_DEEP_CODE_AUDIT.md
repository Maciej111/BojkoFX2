# US100 Strategy Deep Code Audit
**Data:** 2026-03-10 · Audytor: Senior Quantitative Developer (AI)  
**Zakres:** Pełna analiza kodu US100 BOS+Pullback / FLAG_CONTRACTION — sygnały, backtest, wykonanie live, persistence, testy  
**Strategia referencyjna:** 5m BOS Pullback — E=+0.46R, WR=46%, PF=1.49 (backtest 2021-2024)  
**Poziomy krytyczności:** 🔴 KRYTYCZNY · 🟠 WYSOKI · 🟡 ŚREDNI · 🟢 NISKI

---

## 1. Mapa ścieżki sygnału (end-to-end)

### Backtest (`src/strategies/trend_following_v1.py`)
```
ltf_df (5m) + htf_df (4h, z resamplingu 5m)
    │
    ├─ calculate_atr(ltf_df, 14)          [⚠ rolling().mean() — NIE Wilder EWM]
    │
    ├─ detect_pivots_confirmed(ltf_df, lookback=3)   [⚠ LOOKAHEAD — pełne dane]
    ├─ detect_pivots_confirmed(htf_df, lookback=5)   [⚠ LOOKAHEAD]
    │
    └─ pętla bar i:
         ├─ aktualizacja pozycji: SL/TP check
         │     LONG exit na BID; SHORT exit na ASK  [✓ poprawna strona]
         │     PnL = (exit − entry) × 100_000       [⚠ hardcoded notional, błędne dla CFD]
         │
         ├─ check_fill(setup, bar)                  [✓ LONG: low_ask ≤ entry ≤ high_ask]
         │
         ├─ PATH A: check_bos(ltf_df, i, ltf_pivot_highs, ...)   [⚠ LOOKAHEAD pivots]
         │     → get_last_confirmed_pivot(df, pivot_highs, ..., current_time)
         │     → wpis do SetupTracker
         │
         ├─ PATH B: detect_flag_contraction(ltf_df, i, atr, flag_params)   [✓ no lookahead]
         │     → 3 okna względem bara i (impulse, contraction, breakout)
         │
         ├─ get_htf_bias_at_bar(htf_df, current_time, htf_pivots)
         │     → determine_htf_bias(pivot_seq) — HH+HL lub LL+LH  [✓ BUG-05 naprawiony]
         │
         └─ metryki:
               equity_curve = [balance + sum(pnl)]   [⚠ pnl = (exit-entry) × 100_000]
               max_dd_pct = dd / peak                 [⚠ odniesiony do złego equity]
```

### Live (`src/runners/run_live_idx.py`)
```
IBKRMarketDataIdx (tick → 5m bars MIDPOINT ±0.5 spread)
    │
    └─ TrendFollowingStrategy.process_bar(ltf, htf, bar_idx=-1)   [SHARED MODULE]
         │   używa shared ATR (Wilder EWM)                         [⚠ MISMATCH vs backtest]
         │   używa precomputed pivots                              [✓ no lookahead]
         │
         └─ IBKRExecutionEngine.execute_intent(intent)   [SHARED MODULE]
               _calculate_units() → risk_first sizing
               _place_limit_bracket()
```

**Kluczowa obserwacja:** Backtest (`trend_following_v1.py`) to ODRĘBNY, lokalny kod US100.  
Live używa **shared** `TrendFollowingStrategy`. Te dwa silniki NIE są tymi samymi — różny ATR, różna obsługa pivotów, różna sesja.

---

## 2. Live vs Backtest — rozbieżności

### 🔴 BUG-US-01 · `check_bos()` używa lookahead pivots w backteście

**Plik:** `US100/src/strategies/trend_following_v1.py` linia ~40 i ~510  
**Klasyfikacja:** Krytyczna — zawyżony winrate / E(R) w backtestach

**Kod (backtest):**
```python
# Przed pętlą — pełne dane:
ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels = detect_pivots_confirmed(
    ltf_df, lookback=ltf_lookback, confirmation_bars=confirmation_bars
)

# W pętli bar i:
bos_detected, bos_direction, bos_level = check_bos(
    ltf_df, i, ltf_pivot_highs, ltf_pivot_lows, ...
)
```

**Problem:** `detect_pivots_confirmed()` jest wywoływane raz na **całym zbiorze** przed pętlą.  
Pivot przy barze `k` jest "potwierdzony" dopiero gdy bar `k+confirmation_bars` jest wyższy/niższy. W pętli przy bar `i < k + confirmation_bars` backtest WIDZI pivot, który w rzeczywistości nie byłby jeszcze potwierdzony. Jest to ten sam błąd co FX BUG-04.

**Wpływ na metryki:**
- Sygnały BOS są generowane o ~1-2 bary wcześniej niż powinny
- SL pivot obliczony z lookahead → SL bliżej entry → lepsze R → sztucznie wysoki win rate
- Szacowany wpływ na E(R): +0.05 do +0.15R na transakcję

**Poprawka (wzorzec z FX):**
```python
# Użyj precompute_pivots z shared:
from bojkofx_shared.structure.pivots import precompute_pivots

ltf_ph_pre, ltf_pl_pre = precompute_pivots(
    ltf_df['high_bid'], ltf_df['low_bid'],
    lookback=ltf_lookback, confirmation_bars=confirmation_bars
)

# check_bos_signal() przyjmuje pre-computed pivots (no lookahead):
from bojkofx_shared.structure.pivots import check_bos_signal
# ... w pętli:
bos_detected = check_bos_signal(close_i, ltf_ph_pre[i], ltf_pl_pre[i])
```

---

### 🔴 BUG-US-02 · Lokalny `calculate_atr()` używa `rolling().mean()` zamiast Wilder EWM

**Plik:** `US100/src/strategies/trend_following_v1.py` linia ~17  
**Klasyfikacja:** Krytyczna live/backtest rozbieżność

**Backtest (lokalny):**
```python
def calculate_atr(df, period=14):
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()   # ← Simple MA, nie EWM
    return atr
```

**Live (shared strategy):**
```python
from bojkofx_shared.indicators.atr import compute_atr_series
atr = compute_atr_series(norm_df, period=14)   # ← Wilder EWM, alpha=1/14
```

**Różnica:** Wilder EWM reaguje wolniej na gwałtowne skoki True Range, ale trzyma pamięć całej historii (wykładnicze wygładzenie). Simple rolling MA "zapomina" o TR sprzed 14 barów. Na NAS100 z lukami sesyjnymi (`useRTH=False` historyczne bary zawierają nocne luki), TR przez luki nocne może być znacznie większy niż H-L danego bara. Rolling mean może zaniżać ATR o 15-30%.

**Konsekwencje:**
- SL buffer (`sl_buffer_atr_mult=0.5`): backtest używa mniejszego ATR → SL bliżej entry → więcej SL hitów
- Entry offset (`entry_offset_atr_mult=0.3`): backtest entry bliżej BOS level
- FLAG contraction: `flag_min_impulse_atr_mult=2.5` ocenia inaczej w backteście vs live
- Testy end-to-end (`test_strategy_end_to_end.py`) failują częściowo z tego powodu

**Poprawka:**
```python
# Usuń lokalny calculate_atr() z trend_following_v1.py
# Zamiast:
ltf_df['atr'] = calculate_atr(ltf_df, period=14)
# Użyj:
from src.indicators.atr import compute_atr_series  # shim → shared
from bojkofx_shared.indicators.signals import normalize_ohlc
ltf_df['atr'] = compute_atr_series(ltf_df, period=14)
```

---

### 🔴 BUG-US-03 · Equity curve i PnL używają hardcoded `× 100_000` — błędne dla CFD NAS100

**Plik:** `US100/src/strategies/trend_following_v1.py` linia ~210, ~335, ~590  
**Klasyfikacja:** Krytyczna — wszystkie metryki equity błędne

**Kod:**
```python
exit_pnl = partial_pnl + remainder_pnl
# gdzie:
partial_pnl = partial_tp_ratio * (exit_price - entry_price) * 100_000   # ← HARDCODED
remainder_pnl = remaining_size * (exit_price - entry_price) * 100_000   # ← HARDCODED
```

**Problem:**
- EUR/USD 1 lot = 100k jednostek → 1 pip = $10. `* 100_000` ma sens dla Forex.
- NAS100 CFD `NAS100USD`: 1 jednostka ≈ $1 na punkt. `* 100_000` = $100,000 na punkt — masowo zawyżone!
- Z `initial_balance=10000` i PnL w setkach tysięcy dolarów na transakcję, `max_dd_pct` wynosi >100%, co jest bez sensu.

**Wpływ:**
- Metryki equity i drawdown w backtestach US100 są w dosłownie złej walucie/skali — nie można ich interpretować
- `max_dd_pct` w backteście nie odzwierciedla rzeczywistego ryzyka
- Raport `E=+0.46R` jest poprawny (oparty na kolumnie R, nie PnL), ale `max_dd_pct` i `profit_factor` są zbliżone do przypadkowych liczb

**Poprawka:**
- Wzorzec z FX: zamiast PnL w dolarach używać R-compounded equity curve:
```python
initial_balance = 10000
risk_fraction = 0.005  # 0.5% per trade
equity = initial_balance
for r_val in trades_df['R']:
    equity *= (1 + r_val * risk_fraction)
    equity_curve.append(equity)
```
- Kolumna `R` jest już poprawnie obliczona; `pnl` powinno być albo usunięte, albo wyrażone w R.

---

## 3. Sesja i filtrowanie

### 🟠 BUG-US-04 · Session filter boundary mismatch: runner `<` vs backtest `<=`

**Plik:**  
- `US100/src/runners/run_live_idx.py` linia ~390  
- `US100/src/strategies/trend_following_v1.py` linia ~61 (`is_allowed_session`)

**Runner (live):**
```python
if not (session_start <= bar_hour < session_end):   # ← exclusive end
    continue
```

**Backtest (`is_allowed_session`):**
```python
return start_hour <= hour <= end_hour   # ← inclusive end
```

**Z parametrami `session_start=13, session_end=20`:**
- Bar 20:xx UTC: backtest **pozwala**, runner **blokuje**
- Oznacza to, że backtest zawiera sygnały z 20:xx UTC, live je odrzuca

**NYSE zamknięcie: 21:00 UTC** (20:00 ET + 1h DST). Godzina 20:xx to ostatnia godzina przed zamknięciem — często ma najwyższy wolumen dnia. Pominięcie jej w live może być istotne dla wyników.

**Poprawka:**
```python
# run_live_idx.py — zmień na inclusive:
if not (session_start <= bar_hour <= session_end):
```

---

## 4. Symbol i state management

### 🟠 BUG-US-05 · `strategy.process_bar()` w live runnerze nie przekazuje `symbol`

**Plik:** `US100/src/runners/run_live_idx.py` linia ~415  
**Klasyfikacja:** Wysoki — state store zapisuje pod "UNKNOWN", nie pod "NAS100USD"

**Kod:**
```python
intents = strategy.process_bar(ltf, htf, len(ltf) - 1)   # ← brak symbol=
# ...
for intent in intents:
    intent.symbol = SYMBOL   # ← naprawia intent, ale strategy_state pozostaje "UNKNOWN"
```

**Problem:** Po BUG-15 fix w shared module, `process_bar()` ma `symbol="UNKNOWN"` jako default.  
State strategii (`StrategyState`) jest zapisywany pod kluczem `"UNKNOWN"` w bazie.  
Przy restarcie bota, `load_strategy_state("NAS100USD")` zwróci `None` — stan jest bezpowrotnie stracony.

**Poprawka:**
```python
intents = strategy.process_bar(ltf, htf, len(ltf) - 1, symbol=SYMBOL)
```

---

### 🟡 BUG-US-11 · `execution_partial_tp.py` hardcoduje `symbol="EURUSD"`

**Plik:** `US100/src/backtest/execution_partial_tp.py` linia ~173  
**Klasyfikacja:** Średni — błędnie identyfikuje instrument w nagranych transakcjach

**Kod:**
```python
def _open_position(self, order, time, fill_price):
    trade = PartialTPTrade(
        ...
        symbol="EURUSD",   # ← HARDCODED, błędne dla US100
        ...
    )
```

**Poprawka:**
```python
trade = PartialTPTrade(
    ...
    symbol=order.get('symbol', 'UNKNOWN'),
    ...
)
# I w place_limit_order dodaj parametr 'symbol' do order dict.
```

---

## 5. Testy — 18 failujących testów (+ 2 broken imports)

### 🟠 BUG-US-06 · `tests_backtests/` — oba pliki mają złamane importy od czasu migracji monorepo

**Pliki:**  
- `US100/tests_backtests/test_engine_fill_logic.py` linia 15
- `US100/tests_backtests/test_indicators_adx_atr.py` linia 15

**Błąd:**
```
ModuleNotFoundError: No module named 'backtests'
from backtests.engine import try_fill, try_exit, calc_units, in_session
from backtests.indicators import atr, adx, ...
```

**Stan:** Te testy są MARTWE od co najmniej kilku tygodni. Nie są zbierane przez pytest, nie dają sygnału CI. `backtests` to stara nazwa modułu sprzed migracji. Poprawna ścieżka to `src.backtest`.

---

### 🟠 BUG-US-07 · `test_htf_bias.py` — 4 testy testują USUNIĘTE zachowanie

**Plik:** `US100/tests/test_htf_bias.py`

**Problem:**  
`test_last_high_broken_returns_bull` i `test_last_low_broken_returns_bear` testują starą logikę `last_high_broken / last_low_broken`, którą celowo usunięto w **FX BUG-05 fix** (usunięcie tautologii: BOS close > pivot high = bias gratis). Shared module `determine_htf_bias()` ma komentarz `# FIX BUG-05: removed last_high_broken...`.

`test_higher_highs_and_higher_lows_returns_bull` i jego BEAR odpowiednik failują bo 15-barowy syntetyczny dataset z `lookback=3` nie produkuje wystarczającej liczby potwierdzonych pivotów (min. 2 HH + 2 HL wymagane). Test wymaga większego syntetycznego datasetu.

**Klasyfikacja testu:** Testy BŁĘDNE — testują usuniętą funkcję albo mają za mało danych.

**Poprawka `test_last_high_broken_*`**: Usuń testy — ta funkcja nie istnieje. Dodaj test sprawdzający, że sama "close > last pivot" NIE wystarczy do BULL bez struktury HH+HL.

**Poprawka `test_higher_highs_*`**: Rozszerz syntetyczny dataset do ≥30 barów z wyraźną strukturą pivot, wystarczającą dla lookback=3 + confirmation_bars=1.

---

### 🟡 BUG-US-08 · `StrategyConfig` duplicate keyword — 4 pliki testowe

**Pliki:**  
- `tests/test_live_strategy_bos.py` linia ~51
- `tests/test_strategy_end_to_end.py` linia ~167

**Błąd:**
```
TypeError: StrategyConfig() got multiple values for keyword argument 'pivot_lookback_ltf'
```

**Przyczyna:** Testy tworzą `StrategyConfig(pivot_lookback_ltf=3, ...)` ORAZ `StrategyConfig` ma te same pola jako `**kwargs`. Po ostatnim refaktorze shared module `StrategyConfig` to `@dataclass` — konstruktor nie przyjmuje `**kwargs`, ale pola są właśnie po prostu podwójnie przekazywane bo dataclass field `pivot_lookback_ltf=3` zderzył się z tym samym parametrem przekazywanym przez test.

Rzeczywista przyczyna jest inna — testy tworzą `StrategyConfig(pivot_lookback_ltf=2, confirmation_bars=1)` ale `StrategyConfig` już MA pola `pivot_lookback_ltf=3, confirmation_bars=1` jako domyślne. Duplikat powstaje gdy np. test DZIEDZICZY konfigurację: `return StrategyConfig(pivot_lookback_ltf=2, **default_kwargs)` gdzie `default_kwargs` też zawiera `pivot_lookback_ltf`.

Trzeba przejrzeć wszystkie instancje `_default_config(**kwargs)` w testach.

---

### 🟡 BUG-US-09 · `DBOrderRecord(intent=...)` — pole nie istnieje w aktualnym schema

**Plik:** `US100/tests/test_restart_state_restore.py` linia ~66, ~282, ~372

**Błąd:**
```
TypeError: DBOrderRecord.__init__() got an unexpected keyword argument 'intent'
```

**Przyczyna:** Testy używają starego API `DBOrderRecord(intent=OrderIntent(...), ibkr_ids=...)`.  
Aktualny `DBOrderRecord` to:
```python
@dataclass
class DBOrderRecord:
    intent_id:     str
    symbol:        str
    intent_json:   Dict[str, Any]   # ← JSON dict, nie OrderIntent object
    status:        str
    parent_id:     int
    ibkr_ids_json: Optional[Dict]
```

Stary schemat miał `intent: OrderIntent` jako object. Aktualny ma `intent_json: Dict` — serializowany JSON.

---

### 🟡 BUG-US-10 · `store.load_trail_state()` bez `store.migrate()` w testach

**Plik:** `US100/tests/test_restart_state_restore.py` linia ~90

**Błąd:**
```
sqlite3.OperationalError: no such table: orders
```

Testy tworzą `SQLiteStateStore(":memory:")` ale nie wywołują `store.migrate()` przed operacją. Ten sam błąd jaki był w FX — `SQLiteStateStore.__init__` otwiera połączenie ale NIE tworzy tabel automatycznie.

---

### 🟡 BUG-US-12 · `test_strategy_end_to_end.py` — live/backtest parity fails (symptom BUG-US-01/02)

**Plik:** `US100/tests/test_strategy_end_to_end.py`

**Błąd:**
```
AssertionError: Live strategy found no signals on bullish data
AssertionError: Backtest found no trades on bearish data
```

**Przyczyna:** Dwa silniki (live shared vs backtest lokalny) używają różnego ATR i różnych pivotów. Na syntetycznych danych (50 barów, stały spread) te różnice wystarczą, by jeden silnik widział sygnał a drugi nie. Test jest poprawny konceptualnie — ujawnia BUG-US-01 i BUG-US-02.

---

## 6. Martwy kod / archiwum

### 🟢 BUG-US-13 · `backtest/engine.py` i `engine_enhanced.py` — stara strategia zone-based

**Pliki:**  
- `US100/src/backtest/engine.py`
- `US100/src/backtest/engine_enhanced.py`

Oba pliki implementują strategię **demand/supply zones** (nie BOS+Pullback). Używają `detect_zones`, `ExecutionEngine` z modelem `lot_size=100_000`. Ta strategia nie jest nigdzie uruchamiana w produkcji — `run_live_idx.py` używa `TrendFollowingStrategy` z shared module. Są to relikty z pierwszej wersji projektu.

Ryzyko: testy mogą przypadkowo przez `import *` wyciągać kod z tych plików.

---

### 🟢 BUG-US-14 · `run_paper_ibkr.py` — `Config.from_env()` nie istnieje

**Plik:** `US100/src/runners/run_paper_ibkr.py` linia ~49

```python
config = Config.from_env(args.config)   # ← metoda nie istnieje
```

Aktualny `Config` z shared module ma `Config.from_yaml()`. Ten runner jest "legacy" — nie jest używany w produkcji ani testach. Ale gdyby ktoś spróbował go uruchomić, wyrzuci `AttributeError`.

---

### 🟢 BUG-US-15 · Dead code w `_rebuild_htf()` — `agg_cols` obliczane podwójnie

**Plik:** `US100/src/data/ibkr_marketdata_idx.py` linia ~345

```python
agg_cols = {c: "first" if "open" in c ...}   # ← DEAD: nigdy nie użyty
agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}  # ← DEAD: filtruje dead var
# Dalej:
agg = {}
for col in df.columns:   # ← POPRAWNA implementacja, używa "agg" nie "agg_cols"
    ...
self.htf_bars = df.resample("4h").agg(agg)  # ← OK
```

`agg_cols` jest obliczany i filtrowany, potem całkowicie ignorowany. Tylko `agg` jest używany.

---

### 🟢 BUG-US-16 · `sys.path.append(os.getcwd())` w 2 plikach — niestabilne

**Pliki:**  
- `US100/src/backtest/engine.py` linia 7
- `US100/src/backtest/engine_enhanced.py` linia 9

```python
sys.path.append(os.getcwd())
```

Działanie zależy od katalogu roboczego w chwili uruchomienia. Jeśli skrypt uruchamiany z innego katalogu, importy sypią się. Poprawka: użyj `Path(__file__).parents[N]` jak w reste plików projektu.

---

## 7. Podsumowanie wg priorytetu

| ID | Plik | Problem | Priorytet | Wpływ |
|----|------|---------|-----------|-------|
| BUG-US-01 | `strategies/trend_following_v1.py` | check_bos() lookahead pivots | 🔴 KRYTYCZNY | Zawyżony E(R) w backteście, wyniki nieporównywalne z live |
| BUG-US-02 | `strategies/trend_following_v1.py` | ATR rolling mean ≠ Wilder EWM | 🔴 KRYTYCZNY | SL/entry/flag incorrectly sized vs live |
| BUG-US-03 | `strategies/trend_following_v1.py` | PnL × 100_000 (Forex notional) błędne dla CFD | 🔴 KRYTYCZNY | Wszystkie metryki equity/DD bez sensu |
| BUG-US-04 | `runners/run_live_idx.py` | Session filter `<` vs `<=` (20 UTC missing) | 🟠 WYSOKI | Brak sygnałów z ostatniej godziny sesji w live |
| BUG-US-05 | `runners/run_live_idx.py` | `process_bar()` bez `symbol=` | 🟠 WYSOKI | State strategii zapisywany pod "UNKNOWN" |
| BUG-US-06 | `tests_backtests/*.py` | Broken imports (`backtests.engine`) | 🟠 WYSOKI | 2 pliki testowe martwe, brak CI coverage |
| BUG-US-07 | `tests/test_htf_bias.py` | 4 testy testują usunięte zachowanie (BUG-05 fix) | 🟠 WYSOKI | Fałszywy sygnał CI o regresji |
| BUG-US-08 | `tests/test_live_strategy_bos.py` | StrategyConfig duplicate keyword | 🟡 ŚREDNI | 4 testy failują |
| BUG-US-09 | `tests/test_restart_state_restore.py` | `DBOrderRecord(intent=...)` stare API | 🟡 ŚREDNI | 5 testów failuje |
| BUG-US-10 | `tests/test_restart_state_restore.py` | `store.migrate()` brak | 🟡 ŚREDNI | 1 test fails |
| BUG-US-11 | `backtest/execution_partial_tp.py` | `symbol="EURUSD"` hardcoded | 🟡 ŚREDNI | Błędny instrument w logach partial TP |
| BUG-US-12 | `tests/test_strategy_end_to_end.py` | Live vs backtest parity fails | 🟡 ŚREDNI | Symptom BUG-US-01/02 |
| BUG-US-13 | `backtest/engine.py`, `engine_enhanced.py` | Martwy kod — zone strategy | 🟢 NISKI | Konfuzja, potencjalne conflict importów |
| BUG-US-14 | `runners/run_paper_ibkr.py` | `Config.from_env()` nie istnieje | 🟢 NISKI | Błąd tylko przy uruchomieniu legacy runnera |
| BUG-US-15 | `data/ibkr_marketdata_idx.py` | `agg_cols` dead code | 🟢 NISKI | Brak efektu, zaśmiecony kod |
| BUG-US-16 | `backtest/engine*.py` | `sys.path.append(os.getcwd())` | 🟢 NISKI | Fragile imports |

**Łącznie: 3 🔴 KRYTYCZNE · 4 🟠 WYSOKIE · 5 🟡 ŚREDNIE · 4 🟢 NISKIE**

---

## 8. Stan testów (baseline 2026-03-10)

```
pytest tests/ -q
18 failed, 104 passed, 3 skipped
```

```
pytest tests_backtests/ -q
2 collection errors (broken imports — nie zbiera ani jednego)
```

### Testy failujące:
| Test class | Przyczyna | Bug ID |
|------------|-----------|--------|
| `test_htf_bias.py::TestBullishBias` (2) | Testuje usuniętą funkcję + za mało danych | BUG-US-07 |
| `test_htf_bias.py::TestBearishBias` (2) | j.w. | BUG-US-07 |
| `test_live_strategy_bos.py::TestBosDetection` (3) | `StrategyConfig` duplicate kwarg | BUG-US-08 |
| `test_live_strategy_bos.py::TestIntentSanity` (1) | `StrategyConfig` duplicate kwarg | BUG-US-08 |
| `test_metrics_segments.py` (1) | Pre-existing (shared module test issue) | — |
| `test_restart_state_restore.py::TestTrailStatePersistence` (4) | `DBOrderRecord` stare API + brak migrate() | BUG-US-09/10 |
| `test_restart_state_restore.py::TestRestorePositionsFromIBKR` (2) | `DBOrderRecord` stare API | BUG-US-09 |
| `test_strategy_end_to_end.py` (3) | Live vs backtest parity | BUG-US-12 |

---

## 9. Analiza porównawcza: US100 vs FX

| Aspekt | FX (po naprawach) | US100 (przed naprawami) |
|--------|-------------------|------------------------|
| Lookahead pivots w backteście | ✅ Naprawione (BUG-04) — precompute_pivots | ❌ Nadal check_bos() + detect_pivots_confirmed |
| ATR — live vs backtest | ✅ Naprawione (BUG-01/02) — oba Wilder EWM | ❌ Backtest rolling mean, live Wilder EWM |
| Equity curve — PnL notional | ✅ Naprawione (BUG-12) — R-compounded | ❌ × 100_000 (Forex), błędne dla CFD |
| check_bos() deprecated | ✅ Naprawione (BUG-06) — DeprecationWarning | ❌ check_bos() to jedyna ścieżka |
| Symbol w state store | ✅ Naprawione (BUG-15) | ❌ BUG-US-05: "UNKNOWN" |
| Session filter boundary | ✅ `<=` inclusive | ❌ Runner `<` exclusive |
| Testy passing | ✅ 108/111 | ❌ 104/125 (18 fail, 2 broken) |
| Parity tests | ✅ 19 parity testów aktywnych | ❌ Brak dedykowanych parity testów |

**Wniosek:** US100 jest o ~1 sprint poprawek za FX. Trzy krytyczne błędy sprawiają, że wyniki backtestu US100 nie są wiarygodne bez ich naprawy. Live trading może działać (shared module nie ma tych błędów), ale brakuje parity testów gwarantujących spójność.

---

## 10. Zalecana kolejność napraw

1. **BUG-US-02** — Zamień lokalny `calculate_atr()` w `trend_following_v1.py` na shared `compute_atr_series()`. Najszybsza zmiana o największym wpływie na parity.

2. **BUG-US-01** — Zastąp `check_bos()` + pełne `detect_pivots_confirmed` przez `precompute_pivots()` + `check_bos_signal()`. Wzorzec identyczny jak FX.

3. **BUG-US-03** — Zamień `equity_curve += pnl × 100_000` na R-compounded equity (`equity *= 1 + r * risk_fraction`). Wzorzec z FX BUG-12 fix.

4. **BUG-US-05** — Dodaj `symbol=SYMBOL` do `strategy.process_bar()` w runnerze.

5. **BUG-US-04** — Ujednolić session filter boundary (runner `<= session_end`).

6. **BUG-US-06/07/08/09/10** — Naprawa testów (zbiorczo): broken imports, stare API, brak migrate(), nowe testy parity, rewrite test_htf_bias.

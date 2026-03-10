# Raport z Poprawek Systemu BojkoIDX

Data: 2025-03-08  
Autor: GitHub Copilot (sesja code-review)  
Podstawa: `docs/CRITICAL_REVIEW.md` — 6 błędów krytycznych (C1–C6), 5 średnich (M1–M5)

---

## Streszczenie

Zidentyfikowano i naprawiono **6 błędów** (4 krytyczne + 2 średnie) oraz dodano:
- 3 nowe pliki testów jednostkowych i integracyjnych
- naprawę istniejącego zestawu testów (duplikat + nieaktualna asercja)
- dokument z sugestiami dla zwiększenia realizmu backtestów

---

## Poprawki zaimplementowane

### C1 — Brak filtra HTF bias w strategii live (`src/core/strategy.py`)

**Problem:**  
`TrendFollowingStrategy.process_bar()` wykrywał sygnały BOS bez sprawdzenia bieżącego biesu HTF. Powodowało to generowanie zleceń LONG i SHORT niezależnie od kierunku rynku na wyższym TF — strategie backtestowa i live działały całkowicie inaczej.

**Naprawiono:**  
Przepisano `src/core/strategy.py` w całości, wzorując się na `src/strategies/trend_following_v1.py`:
- dodano import `get_htf_bias_at_bar` z `src/structure/bias.py`
- obliczanie biesu HTF z antypatrzeniem w przód: `htf_slice = htf_bars[htf_bars.index <= current_time]`
- brama HTF bias gate: sygnał LONG generowany wyłącznie gdy `htf_bias == 'BULL'`, SHORT gdy `htf_bias == 'BEAR'`
- przy `htf_bias == 'NEUTRAL'` — `process_bar()` zwraca pustą listę

---

### C2 — Lookahead w detekcji pivotów (`src/core/strategy.py`)

**Problem:**  
Stara funkcja `_detect_pivots()` używała `src/indicators/pivots.py::detect_swing_pivots()`, która widzi cały dostępny DataFrame. Pivot z baru `i` był widoczny jako potwierdzony już na barze `i`, zamiast dopiero po `confirmation_bars` barach. Backtest i live dawały różne sygnały BOS.

**Naprawiono:**  
- usunięto metody `_detect_pivots()` i stary `_check_bos()` ze strategii live
- dodano import `detect_pivots_confirmed`, `get_last_confirmed_pivot` z `src/structure/pivots.py`
- LTF pivoty: `detect_pivots_confirmed(ltf_window, lookback=config.pivot_lookback_ltf, confirmation_bars=config.confirmation_bars)`
- HTF pivoty: ta sama funkcja, ale na slice'ie `htf_bars[htf_bars.index <= current_time]` — brak dostępu do przyszłych barów
- `_calculate_sl()` przepisane — przyjmuje serię potwierdzonych pivotów zamiast słownika

---

### C3 — Stan trailing stopu gubiony przy restarcie (`src/execution/ibkr_exec.py`, `src/core/state_store.py`)

**Problem:**  
`IBKRExecutionEngine` przechowywał stan trailing stopu (`trail_activated`, `trail_sl`, `trail_sl_ibkr_id`) wyłącznie w pamięci w obiekcie `_OrderRecord`. Po restarcie procesu `restore_positions_from_ibkr()` odbudowywała rekordy bez tego stanu — trailing stop był rozbrojony, SL wracał do pierwotnego poziomu.

**Naprawiono:**

`src/core/state_store.py`:
- `_SCHEMA_VERSION` podniesiony z `2` do `3`
- DDL tabeli `orders` uzupełniony o kolumnę `trail_state_json TEXT`
- migracja v2→v3: `ALTER TABLE orders ADD COLUMN trail_state_json TEXT`
- nowa metoda `save_trail_state(parent_id, activated, sl_price, sl_ibkr_id)`
- nowa metoda `load_trail_state(parent_id) -> Optional[Dict]`

`src/execution/ibkr_exec.py`:
- po uzbrojeniu trailing stopu w `execute_intent()`: wywołanie `self.store.save_trail_state(..., activated=False, ...)`
- po każdym przesunięciu SL w `_update_trail_sl()`: `self.store.save_trail_state(..., activated=record.trail_activated, sl_price=new_trail_sl, ...)`
- w `restore_positions_from_ibkr()`: odczyt `self.store.load_trail_state(parent_id)` i odtworzenie `trail_cfg`, `trail_activated`, `trail_sl`, `trail_sl_ibkr_id` w każdym `_OrderRecord`

---

### C4 — Hardkodowany symbol `EURUSD` w execution engine (`src/backtest/execution.py`)

**Problem:**  
W `ExecutionEngine._open_position()` symbol pozycji był zapisany na sztywno jako `symbol="EURUSD"` niezależnie od faktycznie handlowanego instrumentu. Wszystkie pozycje w logach i PnL były oznaczane jako EURUSD.

**Naprawiono:**
- `ExecutionEngine.__init__` przyjmuje teraz parametr `symbol='UNKNOWN'`
- atrybut `self.symbol` przechowuje wartość
- `_open_position()` używa `self.symbol` zamiast literału

---

### C5 — Prowizja nie skaluje się z wielkością pozycji (`src/backtest/execution.py`)

**Problem:**  
Kod obliczał prowizję jako stałą kwotę za zlecenie (`commission = config.get('commission_per_lot', 0.0)`), ignorując rzeczywistą wielkość pozycji. Pozycja 5-krotnie większa od standardowej miała tę samą prowizję co standardowa.

**Naprawiono:**  
```python
lots = lot_size / config.get('standard_lot', 100_000)
comm = config.get('commission_per_lot', 0.0) * lots
```
Prowizja skaluje się proporcjonalnie do liczby lotów.

---

### M4 — `raise ValueError` przy zerowej odległości ryzyka (`src/backtest/execution.py`)

**Problem:**  
Gdy entry == SL (zerowa odległość ryzyka), kod rzucał nieobsługiwany `ValueError`, przerywając cały backtest. Mogło to się zdarzyć przy zaokrągleniach cen lub niezwykłych danych.

**Naprawiono:**  
Zastąpiono `raise ValueError` wywołaniem `log.warning(...)` + ustawieniem `R_multiple = 0.0`, co pozwala kontynuować backtest z oznaczeniem danego trade'u jako anomalii.

---

## Testy dodane / naprawione

### Nowe pliki testów

**`tests/test_htf_bias.py`** (8 testów)  
Testy jednostkowe funkcji `get_htf_bias_at_bar()` ze `src/structure/bias.py`:
- struktura HH+HL → bias BULL
- ostatnie wysokie przebite → BULL
- brak lookahead (pivot na barze `i` nie widoczny przed `i + confirmation_bars`)
- struktura LL+LH → BEAR
- ostatnie niskie przebite → BEAR
- niewystarczająca liczba barów → NEUTRAL
- kanał boczny → NEUTRAL
- brak potwierdzonych pivotów → NEUTRAL

**`tests/test_live_strategy_bos.py`** (11 testów)  
Testy jednostkowe `TrendFollowingStrategy.process_bar()`:
- brak sygnałów w fazie warmup (<20 barów)
- brak sygnału na barze formacji pivotu (anti-lookahead)
- BOS LONG wymaga close>pivot (nie sam wick)
- BOS SHORT wymaga close<pivot
- LONG zablokowany przy HTF NEUTRAL
- LONG zablokowany przy HTF BEAR
- SHORT zablokowany przy HTF BULL
- dla LONG: SL < entry < TP
- dla SHORT: TP < entry < SL
- stosunek R:R zgodny z konfiguracją

**`tests/test_restart_state_restore.py`** (6 testów)  
Testy stan trailing stopu w DB + odtwarzanie po restarcie:
- `load_trail_state` zwraca None dla brakującego rekordu
- zapis i odczyt stanu trailing stopu (roundtrip)
- nadpisanie stanu aktualizuje dane
- pozycja bez uzbrojenia trailing stopu zwraca None
- po restarcie: `trail_activated=True`, `trail_sl`, `trail_sl_ibkr_id` odtworzone poprawnie
- pozycja bez stanu trail → domyślne wartości (`trail_activated=False`, `trail_sl=0.0`)

**`tests/test_strategy_end_to_end.py`** (8 testów)  
Test zgodności strategii live z backtestem na tych samych danych:
- oba silniki generują sygnały na danych byczych / niedźwiedzich
- strategia live emituje wyłącznie LONG przy HTF BULL
- strategia live emituje wyłącznie SHORT przy HTF BEAR
- kolejność SL/TP poprawna dla każdego sygnału
- stosunek R:R zgodny z konfiguracją
- kierunki z backtestów obecne w sygnałach live
- brak sygnałów w ciągu pierwszych 20 barów

### Naprawiony plik testów

**`tests/test_state_store.py`**  
- usunięto pierwszy duplikat `test_schema_version_is_1` (asercja `== 1` — niepoprawna)
- zmieniono nazwę na `test_schema_version_is_current` z asercją `== 3` (aktualna wersja schematu)
- zaktualizowano `test_migrate_idempotent` — asercja zmieniona z `== 2` na `== 3`

---

## Dokumentacja dodana

**`docs/REALISM_IMPROVEMENTS.md`**  
Pięć priorytetyzowanych sugestii dla zwiększenia realizmu backtestów (bez implementacji):

| Priorytet | Zmiana | Wpływ |
|-----------|--------|-------|
| 1 | Model poślizgu (slippage) — `fixed` lub `atr_fraction` | Wysoki — każdy trade |
| 2 | Zmienny spread (sesja/pora dnia) | Średni — dane już w pliku |
| 3 | Kolejność realizacji wewnątrz baru | Średni — bary konfliktowe |
| 4 | Model prowizji per-unit dla indeksów | Niski — CFD NAS100/SPX |
| 5 | Ryzyko luki cenowej overnight/weekend | Niski — pozycje przez weekend |

---

## Zestawienie zmian w plikach

| Plik | Typ zmiany | Powiązany błąd |
|------|-----------|----------------|
| `src/core/strategy.py` | Całkowite przepisanie | C1, C2 |
| `src/backtest/execution.py` | 3 poprawki | C4, C5, M4 |
| `src/core/state_store.py` | Schemat v3, 2 nowe metody | C3 |
| `src/execution/ibkr_exec.py` | Zapis/odczyt stanu TS | C3 |
| `tests/test_state_store.py` | Usunięcie duplikatu, aktualizacja asercji | C6 |
| `tests/test_htf_bias.py` | Nowy plik | Pokrycie C1+C2 |
| `tests/test_live_strategy_bos.py` | Nowy plik | Pokrycie C1+C2 |
| `tests/test_restart_state_restore.py` | Nowy plik | Pokrycie C3 |
| `tests/test_strategy_end_to_end.py` | Nowy plik | Pokrycie C1+C2 (E2E) |
| `docs/REALISM_IMPROVEMENTS.md` | Nowy dokument | M1–M5 (sugestie) |

---

## Błędy i problemy **nie objęte** tą sesją

| ID | Opis | Powód pominięcia |
|----|------|-----------------|
| M1 | ATR: `rolling(14).mean()` vs Wilder EWM | Zmiana formuły wymaga ponownego uruchomienia wszystkich backtestów — nie zlecono |
| M2 | `src/indicators/pivots.py` lookahead używany przez zone engine (`engine.py`, `engine_enhanced.py`) | Zakres zmiany zbyt duży — wymaga osobnej sesji |
| M3 | Brak locka na połączeniu SQLite w środowisku wielowątkowym | Nie zlecono |
| M5 | Normalizacja symboli w `purge_zombie_records()` | Nie zlecono |

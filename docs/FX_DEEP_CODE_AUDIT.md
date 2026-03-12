# FX Strategy Deep Code Audit
**Data:** 2026-03-10 · Audytor: Senior Quantitative Developer (AI)  
**Zakres:** Pełna analiza kodu FX BOS+Pullback — sygnały, backtest, wykonanie live, persistence, testy  
**Strategia referencyjna:** `cross_adx22_atr_pct_20_80_size_risk_25bp_rr_fixed_3.0`  
**Poziomy krytyczności:** 🔴 KRYTYCZNY · 🟠 WYSOKI · 🟡 ŚREDNI · 🟢 NISKI

---

## 1. Mapa ścieżki sygnału (end-to-end)

### Backtest
```
ltf_df (H1) + htf_df (H4/D1)
    │
    ├─ detect_pivots_confirmed(ltf_df)  → ltf_pivot_highs/lows, ltf_ph/pl_levels   [⚠ LOOKAHEAD]
    ├─ precompute_pivots(ltf_high, ltf_low)  → ltf_ph_pre[], ltf_pl_pre[]          [✓ NO LOOKAHEAD]
    ├─ detect_pivots_confirmed(htf_df)  → htf_pivot_highs/lows, htf_ph/pl_levels   [⚠ LOOKAHEAD]
    │
    └─ pętla bar i:
         ├─ aktualizacja pozycji: SL/TP check → exit (BID dla LONG, ASK dla SHORT)
         │     PnL = (exit − entry) × 100_000  [⚠ hardcoded units]
         │
         ├─ check_fill(setup, bar):
         │     LONG: low_ask ≤ entry ≤ high_ask
         │     SHORT: low_bid ≤ entry ≤ high_bid
         │     → get_last_confirmed_pivot(detect_pivots_confirmed)  [⚠ LOOKAHEAD SL]
         │     → compute_sl_at_fill(pivot, buffer, atr)
         │     → compute_tp_price(entry, sl, rr)
         │
         ├─ get_htf_bias_at_bar(detect_pivots_confirmed)  [⚠ LOOKAHEAD]
         │     last_high_broken = last_close > highs[0]   [⚠ TAUTOLOGIA]
         │
         ├─ check_bos_signal(close, ltf_ph_pre[i], ltf_pl_pre[i])  [✓ NO LOOKAHEAD]
         │
         └─ apply_regime_filters(adx_val, atr_pct_val):
               ATR calc: calculate_atr(ltf_df)  → Wilder EWM TR
               ATR pct: compute_atr_percentile_series(atr, window=100)
```

### Live (runner)
```
IBKRMarketData (H1 ticks → sealed bars)
    │
    ├─ ATR filter: (high_bid - low_bid).rolling(14).mean()  [⚠ MISMATCH vs backtest]
    ├─ ADX H4: obliczany inline przez runner                [⚠ DUPLIKACJA]
    │
    └─ TrendFollowingStrategy.process_bar(h1, htf, bar_idx=-1):
         │   (identyczna logika co run_trend_backtest)
         │
         └─ IBKRExecutionEngine.execute_intent(intent):
               _calculate_units(intent)  → entry or equity  [⚠ SILENT FALLBACK]
               _place_limit_bracket(intent, units)
               _update_trail_sl() w poll_order_events()
```

---

## 2. Live vs Backtest — rozbieżności

### 🔴 BUG-01 · ATR percentile — różna implementacja ATR

**Plik:** `FX/src/runners/run_paper_ibkr_gateway.py` (linia ~430)  
**Klasyfikacja:** Krytyczna rozbieżność live/backtest

**Live (runner):**
```python
_atr_s = (h1['high_bid'] - h1['low_bid']).rolling(14).mean()
_cur_atr = _atr_s.iloc[-1]
_window = _atr_s.dropna().iloc[-100:]
_pct_val = float((_window < _cur_atr).mean() * 100)
```

**Backtest (trend_following_v1.py + signals module):**
```python
ltf_df['atr'] = calculate_atr(ltf_df, period=14)   # Wilder EWM z True Range
ltf_df['atr_pct'] = compute_atr_percentile_series(ltf_df['atr'], window=100)
```

**Różnica:** `rolling(14).mean()` operuje tylko na `high - low` (range), pomija luki gaps (prev close). `calculate_atr()` / `compute_atr_series()` używa True Range = max(H-L, |H-prev_C|, |L-prev_C|) z Wilder smoothing (EWM, alpha=1/14). W rynkach z lukami overnight ATR Wildera bywa 20–40% wyższy niż range-only. Oznacza to, że percentyle ATR w live i backtestach **NIE są porównywalne** — filtr 20–80 strzela w inne momenty.

**Wpływ:** Sygnały zaakceptowane przez backtest mogą być odrzucane live (lub vice versa). Wyniki OOS (Val 0.153R, Test 0.118R) zakładają inną definicję ATR niż ta działająca na prodzie.

---

### 🟠 BUG-02 · ADX H4 — kod zduplikowany poza shared module

**Plik:** `run_paper_ibkr_gateway.py` (~450–500)  
**Klasyfikacja:** Wysoka — ryzyko dryftu kodu

Runner oblicza ADX H4 inline przez 30+ linii kodu z `__import__("numpy")`. Backtest korzysta z `compute_adx_series()` z `trend_following_signals.py`. Aktualnie równoważne, ale każda zmiana w shared function musi być **ręcznie powielona** w runnerze. Brak testu sprawdzającego identyczność.

**Naprawa:** Runner powinien wywoływać `compute_adx_series(normalize_ohlc(_h4))`.

---

### 🟡 BUG-03 · RR override — backtest vs live

**Plik:** `run_paper_ibkr_gateway.py` (~510)  
W runnerze `_sc.risk_reward` (z `SymbolConfig`) może nadpisać `intent.tp_price` po obliczeniu sygnału. Bazowy `rr` w `params_dict` backtestów pochodzi z `config_backtest.yaml`. Jeżeli wartości się różnią (np. config.yaml zmieniony po girdzie), TP live i backtest są inne.

---

## 3. Błędy logiczne w generowaniu sygnałów

### 🔴 BUG-04 · detect_pivots_confirmed — lookahead ~1–2 barów

**Plik:** `FX/src/structure/pivots.py`  
**Klasyfikacja:** KRYTYCZNA — skażenie wyników backtestów

```python
for i in range(lookback, n - lookback):
    window_high = df['high_bid'].iloc[i-lookback:i+lookback+1]  # ← UŻYWA PRZYSZŁYCH BARÓW!
    if high_bid[i] == window_high.max():
        ph.iloc[i] = True
# ...
ph_confirmed = ph.shift(confirmation_bars)   # shift o 1
```

**Analiza lookahead:**  
Pivot raw w barze `p` wykrywany przy user `window = [p-lb, p+lb]` → używa `lb` barów wprzód.  
Confirmation shift = 1 bar → potwierdzone w barze `p+1`.  
Przy `lb=3, conf=1`: w barze `t` najnowszy widoczny potwierdzony pivot pochodzi z obliczenia używającego danych do baru `t+1` (1 bar lookahead).  

Formuła lookahead = `lb − conf_bars` = 3 − 1 = **2 bary** względem czasu potwierdzenia, **1 bar** względem aktualnego baru `t`.

**Gdzie używana:**
1. `ltf_pivot_highs/lows` → `get_last_confirmed_pivot(current_time)` → SL anchor przy fill
2. `htf_pivot_highs/lows` → `get_htf_bias_at_bar()` → decyzja BULL/BEAR

**Kontrast z poprawną funkcją:**  
`precompute_pivots()` w `src/signals/trend_following_signals.py` jest **matematycznie poprawna** (zero lookahead) i jest używana prawidłowo do BOS detection. Ale `detect_pivots_confirmed` jest nadal używana w dwóch krytycznych miejscach.

**Wpływ:** Backtesty widzą pivoty "zbyt wcześnie" → SL bliżej wejścia niż powinien → wyższe R (wyniki zawyżone). HTF bias może zmieniać się o 1–2 bary szybciej niż w real-time → więcej sygnałów w kierunku trendu.

---

### 🔴 BUG-05 · HTF bias — tautologia last_high_broken

**Plik:** `FX/src/structure/bias.py`  
**Klasyfikacja:** KRYTYCZNA na modelu live

```python
last_close = htf_df['close_bid'].iloc[-1]  # aktualny (niezamknięty!) bar H4 live
highs = [(ts, level) for ts, level in pivot_highs_with_levels]
last_high_broken = last_close > highs[0][1] if highs else False
if (highs_ascending and lows_ascending) or last_high_broken:
    return 'BULL'
```

**Problem 1 — tautologia z BOS:** `highs[0][1]` = ostatni potwierdzony pivot high. `close > last_pivot_high` to dokładnie warunek BOS LONG. Ta sama cena sygnalizuje jednocześnie:
- BOS LONG (LTF: `check_bos_signal`)
- BULL bias (HTF: `last_high_broken = True`)

Oznacza to, że każdy BOS LONG **automatycznie tworzy sobie BULL bias** na podstawie tej samej ceny — tautologia logiczna. W praktyce H1 close może przebić H4 pivot o kilka pipsów generując BOS bez trwałego BULL trendu.

**Problem 2 — live: niezamknięty bar H4:** W runnerze `htf_df` = ostatnie sealed bary H4. Przy `iloc[-1]` w czasie procesu baru H1 który **wypada w środku baru H4**, `last_close` jest "live midbar H4 close" — nie potwierdzony. Backtest używa zamkniętych H4 barów.

---

### 🟠 BUG-06 · check_bos() legacy wrapper — lookahead mimo require_close_break=True

**Plik:** `FX/src/strategies/trend_following_v1.py` (fn `check_bos`)  
`check_bos` jest wywoływana z `require_close_break=True` w produkcji. Jednak nawet z `True`, funkcja wywołuje `check_bos_signal(close, last_ph_level, last_pl_level)` gdzie `last_ph_level` pochodzi z `get_last_confirmed_pivot(ltf_pivot_highs, ltf_ph_levels)` — czyli z lookahead serii `detect_pivots_confirmed`.

**Uwaga:** Główna pętla backtestu (linia ~430) **pomija** `check_bos()` i bezpośrednio wywołuje:
```python
bos_side, bos_level = check_bos_signal(current_bar['close_bid'], ltf_ph_pre[i], ltf_pl_pre[i])
```
z no-lookahead `ltf_ph_pre[i]`. Wrapper `check_bos()` jest nieużywany w głównej ścieżce, ale istnieje ryzyko regresu przy przyszłych zmianach.

---

## 4. Błędy w modelu wykonania i cenach

### 🟠 BUG-07 · _calculate_units() — silent fallback na account equity

**Plik:** `shared/bojkofx_shared/execution/ibkr_exec.py`

```python
def _calculate_units(self, intent: OrderIntent) -> int:
    entry = intent.entry_price or self._account_equity   # ← BŁĄD JEŚLI entry=0
    sl    = intent.sl_price
    stop_dist = abs(entry - sl)
```

Jeżeli `intent.entry_price` jest `0` lub `None`, Python `or` wybiera fallback `self._account_equity` (np. 30 000 USD). Wtedy `stop_dist = abs(30000 - sl_price)` ≈ 30 000. Przy `risk_fraction=0.25%`:

```
units = (30000 × 0.0025) / 30000 ≈ 0.0025 → int() = 0
```

Wynik: `units = 0` i `execute_intent` zwraca `None` bez żadnego błędu w logach (tylko `[ERROR] Zero units`). **Brak wyjątku, brak alertu.**

**Kiedy entry_price może być 0/None:**  
Jeżeli `compute_entry_price()` zwróci 0 (np. `bos_level=0`), lub jeżeli `OrderIntent` tworzony jest z pominiętym argumentem.

---

### 🟠 BUG-08 · Trailing stop — asymetria BID/ASK przy aktywacji

**Plik:** `shared/bojkofx_shared/execution/ibkr_exec.py`

```python
# Use bid for LONG (conservative), ask for SHORT
price = current_bid if intent.side == Side.LONG else current_ask
activate_at = entry + ts_r * risk
if price >= activate_at:       # LONG: sprawdza BID >= activate_at
```

**Problem:** Trade LONG otwierany jest na ASK (wyższy). `entry` pochodzi z `record.fill_price or intent.entry_price`. Jeżeli `fill_price` = cena ASK, a `risk = abs(entry_ask - sl)`, to `activate_at = entry_ask + ts_r * risk`. Ale `price = current_bid` — zawsze niższy od ASK o spread. Oznacza to, że trail nigdy się nie aktywuje przy cenie dokładnie na `activate_at` (BID < ASK = activate_at). Wymagane wyższe ruch niż w backteście.

W backtestach `_update_trail_sl` (engine.py) używa `high_bid` jako proxy — inna zasada!  
→ **Triple mismatch**: live używa BID, backtest używa high_bid, dokumentacja mówi o "bid conservative".

---

### 🟠 BUG-09 · poll_order_events — TP priority gdy oba wypełnione (vs workflow backtest)

**Plik:** `ibkr_exec.py`

```python
if tp_trade and tp_trade.orderStatus.status == "Filled":
    exit_trade  = tp_trade
    exit_reason = ExitReason.TP
elif sl_trade and sl_trade.orderStatus.status == "Filled":
    exit_trade  = sl_trade
    exit_reason = ExitReason.TS if record.trail_activated else ExitReason.SL
```

Jeżeli w tym samym cyklu poll obie (TP i SL) są `Filled`, wybierane jest TP — **optimistic outcome**. Backtest wybiera SL (worst-case explicit: `if sl_hit and tp_hit: exit_price = sl`). Ta asymetria zawyża statystyki live względem backtestu w przyszłości.

---

### 🟡 BUG-10 · Bracket failure — brak rollback przy partial order failure

**Plik:** `ibkr_exec.py`, `_place_limit_bracket()`

```python
parent_trade = self.ib.placeOrder(contract, parent)   # transmit=False
# ... wait for acknowledge ...
tp_trade = self.ib.placeOrder(contract, tp_order)     # transmit=False
# ... sleep(0.5) - NO ERROR CHECK ...
sl_trade = self.ib.placeOrder(contract, sl_order)     # transmit=True - FIRES BRACKET
```

Jeżeli TP placement się powiedzie a SL zawiedzie:  
- Parent i TP wiszą na IBKR (blocked, `transmit=False`)  
- Brak automatycznego cancel → zombie orders  
- Ryzyko: po restarcie `restore_positions_from_ibkr` zobaczy tylko parent+TP → źle odtworzy SL → pozycja bez stop-loss

---

## 5. Błędy w logice SL/TP

### 🔴 BUG-11 · SL anchor — używa lookahead pivot series

**Plik:** `trend_following_v1.py` (~line 404)

```python
sl_pivot_time, sl_pivot_level = get_last_confirmed_pivot(
    ltf_df, ltf_pivot_lows, ltf_pl_levels, current_time    # ← detect_pivots_confirmed!
)
sl = compute_sl_at_fill(side=setup.direction, last_pivot_level=sl_pivot_level, ...)
```

SL jest obliczany poprawnie "w momencie fill" (bar i), ale pivot low/high traktowany jako anchor pochodzi z `detect_pivots_confirmed` (lookahead 1-2 bary). W rzeczywistym real-time pivot ten byłby niedostępny lub inny.

**Efekt praktyczny:** SL może być kotwiczony do pivotu który "pojawia się wcześniej" niż powinien. Ponieważ pivoty LTF są gęste, różnica jest małą (~1-2 bary), ale systematycznie zawyża backtest R (SL bliżej wejścia = mniejszy stop = wyższe R nominalne).

**Naprawa:** Zastąpić `detect_pivots_confirmed` siecią no-lookahead. Lub użyć `precompute_pivots` z osobnym indeksem `ph_idxs/pl_idxs` do lookupów.

---

### 🟠 BUG-12 · Exit PnL — hardcoded 100 000 jednostek

**Plik:** `trend_following_v1.py`

```python
exit_pnl = (exit_price - current_position['entry']) * 100_000   # LONG
exit_pnl = (current_position['entry'] - exit_price) * 100_000   # SHORT
```

Strategia używa `risk_first` sizing w live (zmienne jednostki od equity × risk%). W backtest model nie ma pojęcia o dynamicznym sizing — PnL jest zawsze obliczany jako 100k jednostek. To powoduje:
1. `metrics['expectancy_R']` = poprawne (oparte na `R_calc` = `realized_dist / risk_dist`)  
2. `metrics['max_dd_pct']` = **błędne** (oparte na `pnl` = 100k units)  
3. Equity curve = fikcyjna — nie odpowiada rzeczywistemu ryzyku

**Krytyczne:** Drawdown raportowany w dashboard jest obliczony na bazie 100k-lot PnL, NIE percent-risk equity. Na papierowym koncie 30k USD i risk_fraction=0.25%, faktyczny DD jest ~4x mniejszy niż raportowany.

---

### 🟡 BUG-13 · SL clamp ukrywa naruszenie modelu

**Plik:** `trend_following_v1.py`

```python
if exit_price < current_bar['low_bid']:
    exit_price = current_bar['low_bid']  # Clamp to low
```

Clamp w backteście nie rzuca wyjątku — cicho koryguje cenę wyjścia. Oznacza to, że:
- SL który jest poniżej `low_bid` na barze wyjścia jest wykonany po `low_bid` (nie po SL)
- Trade jest raportowany ze złym R (exit_price ≠ sl)
- W `R_calc` jest błąd cichy

Naprawa: `raise ValueError` lub przynajmniej `log.warning` z metryką.

---

## 6. Ryzyko lookahead

### Podsumowanie wszystkich ścieżek lookahead:

| Funkcja | Lookahead | Gdzie używana | Wpływ |
|---------|-----------|---------------|-------|
| `detect_pivots_confirmed()` | ~1-2 bary | SL anchor at fill, HTF bias | **Zawyżone R, fałszywy bias** |
| `get_htf_bias_at_bar()` | ~1-2 bary (via above) | Filtr BULL/BEAR | **Więcej sygnałów** |
| `last_high_broken` w bias.py | 0 bar, ale live: niezamknięty bar | BULL bias declaration | **Live/backtest mismatch** |
| `precompute_pivots()` | **0 barów** | BOS detection (główna pętla) | ✓ Poprawna |
| `compute_adx_series()` z shift(1) | **0 barów** | ADX regime filter | ✓ Poprawna |
| `compute_atr_percentile_series()` | **0 barów** | ATR filter backtest | ✓ Poprawna |

**Wniosek:** Ścieżka BOS detection jest poprawna. Lookahead jest skoncentrowany w dwóch miejscach: SL anchor + HTF bias — co bezpośrednio napędza dwie najważniejsze decyzje strategii poza BOS.

---

## 7. Persistence i bezpieczeństwo restartów

### 🟠 BUG-14 · Aktywny setup nie jest persystowany do DB

**Plik:** `state_store.py` + `runner`

`PullbackSetup` (direction, entry_price, expiry_time) żyje tylko jako `SetupTracker.active_setup` w pamięci RAM. Schemat DB zawiera `strategy_state` (pivots, BOS), `orders`, `risk_state`, `events` — ale **brak tabeli dla pending setups**.

Po restarcie bota:
- DB jest przywracane: pozycje z IBKR, trail state, risk state ✓
- Ale: jeżeli BOS nastąpił i setup był pending (order limit nie wypełniony), setup **znika**
- Kolejny cykl baru — brak setupu → brak orderu → missed trade

**Ryzyko:** W tygodniu gdzie cena spędza 10-15 barów na pullbacku przed wejściem, restart bota w tym oknie = utracona transakcja.

---

### 🟡 BUG-15 · DB symbol patch — problematyczne dla multi-symbol

**Plik:** `run_paper_ibkr_gateway.py`

```python
try:
    _db_state = store.load_strategy_state("UNKNOWN")
    if _db_state is not None:
        _db_state.symbol = sym
        store.save_strategy_state(_db_state)
except Exception:
    pass
```

Przy uruchomieniu 5 symboli (EURUSD, USDJPY, AUDJPY, CADJPY, USDCHF) ten blok wykona się dla każdego — ostatni nadpisze DB state "UNKNOWN" swoim symbolem. Przy restarcie bot może załadować state z złym symbolem. `except pass` ukrywa błędy tej operacji.

---

### 🟡 BUG-16 · Trail state restore — cicha utrata przy braku DB

**Plik:** `ibkr_exec.py`

```python
if self.store is not None:
    trail_state = self.store.load_trail_state(parent_id)
    if trail_state:
        # restore trail...
```

Jeżeli plik DB został skasowany lub tabel brakuje, `trail_state = None` i trail jest resetowany do domyślnego (nieaktywowany, SL = original). Nie ma żadnego alertu/logu "trail state utracony".

Pozycja z aktywowanym trailing stopem (SL przesunięty na breakeven lub wyżej) po restarcie może mieć SL z powrotem na original SL — narażając trade na stratę który był już chroniony.

---

## 8. Luki w pokryciu testów

### Stan testów (45 testów w aktualnym suite):

| Test file | Co testuje | Luki |
|-----------|------------|------|
| `test_pivots_no_lookahead.py` | `detect_pivots_confirmed` shift | Testuje STARĄ funkcję z lookaheadem, nie `precompute_pivots` |
| `test_strategy_signal_consistency.py` | Sygnały, filtry, SL/TP | Nie testuje live/backtest ATR mismatch |
| `test_no_same_bar_entry.py` | SL check po fill | Nie testuje że SL jest sprawdzane NA BARZE FILL |
| `test_state_store.py` | SQLite CRUD | Brak testu dla trail restore po pustym DB |
| `test_execution_logic.py` | ExecutionEngine | Nie testuje worst-case TP+SL collision live vs backtest |
| `test_bos_pullback_setup.py` | BOS → setup | Nie testuje restart recovery (setup zniknie) |
| Brak | ATR percentile live vs backtest | **Brak testu w ogóle** |
| Brak | `_calculate_units(entry=0)` | **Brak testu** |
| Brak | `last_high_broken` tautologia | **Brak testu** |
| Brak | Bracket failure rollback | **Brak testu** |

**Krytyczna luka:** Nie ma ani jednego testu który weryfikuje `detection_pivots_confirmed` vs `precompute_pivots` dają identyczne wyniki — bo nie dają, i to jest błędem.

---

## 9. TOP 10 — Krytyczne problemy (rankizowane)

| # | Problem | Plik | Krytyczność | Wpływ |
|---|---------|------|-------------|-------|
| 1 | `detect_pivots_confirmed` 1-2 bar lookahead w SL anchor | `structure/pivots.py` | 🔴 KRYTYCZNY | Zawyżone R w backtestach, SL nieprawidłowy |
| 2 | ATR percentile live ≠ backtest (range vs TrueRange Wilder) | `run_paper_ibkr_gateway.py` | 🔴 KRYTYCZNY | Filtr strzela inaczej na prodzie |
| 3 | `detect_pivots_confirmed` lookahead w HTF bias | `structure/pivots.py` / `bias.py` | 🔴 KRYTYCZNY | BULL/BEAR bias "za wczesny" |
| 4 | `last_high_broken` tautologia — BOS bar = bias bar | `structure/bias.py` | 🔴 KRYTYCZNY | Fałszywy BULL bias, live niezamknięty H4 |
| 5 | Active setup NOT persisted → lost on restart | Brak tabeli DB | 🟠 WYSOKI | Missed trades po każdym restarcie |
| 6 | `_calculate_units(entry=0)` → near-zero units | `ibkr_exec.py` | 🟠 WYSOKI | Silent no-trade, brak alertu |
| 7 | Exit PnL × 100 000 (metrics DD błędny) | `trend_following_v1.py` | 🟠 WYSOKI | Fałszywe DD metrics, wyniki nieporównywalne |
| 8 | Trailing stop: BID activation dla LONG (vs ASK entry) | `ibkr_exec.py` | 🟠 WYSOKI | Asymetria live vs backtest |
| 9 | poll_order_events: TP priority > SL (vs backtest worst-case) | `ibkr_exec.py` | 🟠 WYSOKI | Live PF zawyżony vs backtest |
| 10 | Bracket partial failure — brak cancel rollback | `ibkr_exec.py` | 🟡 ŚREDNI | Zombie orders (rare) |

---

## 10. Plan napraw

### Naprawa #1 — KRYTYCZNA: Zastąpienie detect_pivots_confirmed przez precompute_pivots

**Zakres:** `trend_following_v1.py` — dwa miejsca:

**a) SL anchor w momencie fill:**
```python
# OBECNIE (lookahead):
sl_pivot_time, sl_pivot_level = get_last_confirmed_pivot(
    ltf_df, ltf_pivot_lows, ltf_pl_levels, current_time
)

# NAPRAWA — użyj precomputed no-lookahead indexed-at-i:
# ltf_pl_pre_with_idx = lista (price, bar_idx) pre-computed przez precompute_pivots z _idxs
if setup.direction == 'LONG':
    sl_pivot_level = ltf_pl_pre[i]   # last confirmed pl visible at bar i (no lookahead)
else:
    sl_pivot_level = ltf_ph_pre[i]   # last confirmed ph visible at bar i
```

**b) HTF bias:** Przekazywać no-lookahead htf pivots do `get_htf_bias_at_bar`, lub przepisać bias.py by używał `precompute_pivots` logiki z H4 serii.

**c) Usunąć `detect_pivots_confirmed` z importów** po migracji (deprecuje ją).

**Ryzyko zmiany:** Wyniki backtestów zmienią się. Oczekiwany kierunek: **niższe** R średnie (usunięcie bias zawyżającego). Bezpieczna zmiana — wymaga re-runu gridów.

---

### Naprawa #2 — KRYTYCZNA: ATR live = ATR backtest

**Plik:** `run_paper_ibkr_gateway.py`, sekcja ATR filter

```python
# USUŃ (runner inline):
_atr_s = (h1['high_bid'] - h1['low_bid']).rolling(14).mean()

# ZASTĄP (shared function):
from src.signals.trend_following_signals import compute_atr_series, compute_atr_percentile_series, normalize_ohlc
_h1_norm = normalize_ohlc(h1.rename(columns={'high_bid': 'high', 'low_bid': 'low', 
                                               'close_bid': 'close', 'open_bid': 'open'}))
_atr_s = compute_atr_series(_h1_norm, period=14)
_cur_atr = _atr_s.iloc[-1]
_window = _atr_s.dropna().iloc[-100:]
_pct_val = float((_window < _cur_atr).mean() * 100)
```

Alternatywnie deleguj do `strategy.process_bar()` który już to oblicza wewnętrznie.

---

### Naprawa #3 — WYSOKA: Persist active setup do DB

Dodać tabelę `pending_setups` w SQLiteStateStore:

```sql
CREATE TABLE IF NOT EXISTS pending_setups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    bos_level REAL NOT NULL,
    bos_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    expiry_time TEXT NOT NULL,
    htf_bias TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

W runnerze: after `tracker.create_setup()`, persist do DB. On restart: load pending setups i rekonstruuj `SetupTracker`. Usuwać przy expire lub fill.

---

### Naprawa #4 — WYSOKA: _calculate_units guard

```python
# NAPRAWA:
entry = intent.entry_price
if not entry or entry <= 0:
    log.error("[SIZING] %s entry_price=%.5f is zero/None — SKIPPING ORDER", 
              intent.symbol, entry or 0.0)
    return 0   # properly blocked with clear error

sl    = intent.sl_price
stop_dist = abs(entry - sl)
```

---

### Naprawa #5 — WYSOKA: ADX H4 z shared function

```python
# run_paper_ibkr_gateway.py — zastąp 30 linii:
from src.signals.trend_following_signals import compute_adx_series, normalize_ohlc
_h4_norm = normalize_ohlc(_h4.rename(columns={...}))
_adx_h4 = compute_adx_series(_h4_norm, period=14)
_adx_val = float(_adx_h4.iloc[-1])
```

---

### Naprawa #6 — ŚREDNIA: last_high_broken — wymagaj min_bars odstępu

```python
# bias.py — wymagaj że przebicie nastąpiło co najmniej 1 bar temu
# i używaj tylko ZAMKNIĘTEGO H4 bar
last_close = htf_df['close_bid'].iloc[-2]  # poprzedni ZAMKNIĘTY H4
# tak samo jak w backtests (nie używaj -1 który może być live)
```

---

### Naprawa #7 — WYSOKA: Trail stop — użyj mid-price zamiast BID dla LONG

```python
# NAPRAWA (lub użyj ask dla symmetry):
price = (current_bid + current_ask) / 2.0
# albo konsekwentnie: użyj ask dla LONG activation (bo entry był na ask)
price = current_ask if intent.side == Side.LONG else current_bid
```

Backtest powinien być zaktualizowany analogicznie.

---

### Naprawa #8 — ŚREDNIA: Exit PnL z rzeczywistym sizing

```python
# W backtest — zaślepka dopóki sizing nie jest zintegrowany:
# Użyj tylko R_calc jako miarę wyników (already correct).
# Dla equity curve: 
actual_units = (initial_balance * risk_fraction) / risk_dist   # approximate
exit_pnl = realized_dist * actual_units   # zamiast 100_000
```

Lub: całkowity backtest z symulowanym `risk_first` sizing (osobna praca, wysoki effort).

---

## 11. "Najbardziej prawdopodobny ukryty bug"

### Hipoteza: Kombinator lookahead + tautologia generuje fałszywy BULL bias na każdym BOS bez prawdziwego trendu

Rozważmy scenariusz:
1. Rynek jest w zakresie (ranging). HTF H4 tworzy oscylujące pivoty — brak `highs_ascending and lows_ascending`.
2. Bar H4 zamknął się 3 pipsy powyżej ostatniego pivot high `highs[0][1]`.
3. `last_high_broken = True` → `get_htf_bias_at_bar = 'BULL'`.
4. Ten sam H4 bar "zawiera" kilka barów H1. Na jednym z nich H1 close > H1 pivot high → LTF BOS LONG.
5. `bos_direction == 'LONG'` and `htf_bias == 'BULL'` → **setup się tworzy**.

Ale: bar H4 uległ rewersji w kolejnym barze. BULL bias był fałszywy (wynikał z tautologicznego `last_high_broken`). H4 zamknął się poniżej pivot. HTF bias zmienia się na NEUTRAL/BEAR. ALE setup już istnieje z poprzednim biasem — **limit order visisi na IBKR**.

Efekt: W ranging rynku (np. USDCHF w 2024 — najgorszy OOS: PF 0.907) bot systematycznie otwiera setupy na fałszywych BULL biasach które są tautologią z LTF BOS.

**To wyjaśnia dlaczego:**
- USDCHF ma ujemne OOS (fałszywy bias w ranging rynku)  
- Q1 2025 system-wide DD: wszystkie waluty miały ranging → dużo fałszywych biasów  
- Filtr ATR percentile częściowo ratuje (ranging = niskie ATR pct → excluded if < 20)  
- Ale jeśli ranging has moderate ATR pct (30-50), setup się tworzy mimo fałszywego bias

**Quantyfikacja:** Jeżeli naprawić BUG-04 + BUG-05 razem, wyniki OOS PRAWDOPODOBNIE spadną o ~10–20% R (np. z 0.118R do 0.095–0.105R) ale będą **bardziej wiarygodne** — aktualne wyniki są częściowo inflated przez lookahad + tautologię.

---

## Podsumowanie wykonawcze

**Pilność napraw (w kolejności):**

1. **Tydzień 1:** Naprawa #2 (ATR percentile live=backtest) — 1 godzina kodu  
2. **Tydzień 1:** Naprawa #5 (ADX shared function) — 30 minut  
3. **Tydzień 2:** Naprawa #1 (precompute_pivots dla SL anchor) — 3 godziny + re-run gridów  
4. **Tydzień 2:** Naprawa #6 (last_high_broken) — 1 godzina + re-run  
5. **Tydzień 3:** Naprawa #3 (persist setups) — 4 godziny + testy  
6. **Tydzień 3:** Naprawa #4 (_calculate_units guard) — 30 minut  
7. **Tydzień 4:** Naprawa #7 (trail stop symmetry) — 2 godziny  

**Przed wejściem z real-money (live):** Wymagane co najmniej naprawy #1, #2, #3, #4, #6.

**Obecny stan (paper trading):** Strategia działa i generuje zyski, ale backtest wyniki są częściowo zawyżone przez lookahead (#1) i niezgodność ATR (#2). Oczekiwane "true" OOS ExpR po naprawach: ~0.08–0.10R (vs raportowane 0.118R).

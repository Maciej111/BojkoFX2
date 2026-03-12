# US100 — Dokumentacja algorytmu generowania sygnałów (tuning guide)

> **Cel dokumentu:** Pełny opis każdego etapu obliczania sygnału wejścia, z wyszczególnieniem wszystkich
> parametrów, ich zakresów i skutków zmiany. Dokument przeznaczony dla AI asystenta lub dewelopera
> przeprowadzającego optymalizację.

---

## Spis treści

1. [Przegląd architektury sygnału](#1-przegląd-architektury-sygnału)
2. [Wejściowe dane — struktury](#2-wejściowe-dane--struktury)
3. [KROK 1 — ATR (Average True Range)](#3-krok-1--atr)
4. [KROK 2 — Precompute pivotów LTF (no-lookahead)](#4-krok-2--precompute-pivotów-ltf)
5. [KROK 3 — Pivoty HTF i wyliczanie bias](#5-krok-3--pivoty-htf-i-wyliczanie-bias)
6. [KROK 4 — Filtr sesji](#6-krok-4--filtr-sesji)
7. [KROK 5 — BOS (Break of Structure)](#7-krok-5--bos-break-of-structure)
8. [KROK 6 — BOS Momentum Filter](#8-krok-6--bos-momentum-filter)
9. [KROK 7 — Tworzenie setupu i entry price](#9-krok-7--tworzenie-setupu-i-entry-price)
10. [KROK 8 — Stop Loss](#10-krok-8--stop-loss)
11. [KROK 9 — Take Profit (RR)](#11-krok-9--take-profit-rr)
12. [KROK 10 — Opcjonalna ścieżka: Flag Contraction](#12-krok-10--opcjonalna-ścieżka-flag-contraction)
13. [Produkcyjne nastawy (run_live_idx.py)](#13-produkcyjne-nastawy)
14. [Mapa wszystkich parametrów z zakresami do tuningu](#14-mapa-wszystkich-parametrów)
15. [Zależności i efekty uboczne zmian](#15-zależności-i-efekty-uboczne)

---

## 1. Przegląd architektury sygnału

```
LTF bars (5m) ──► ATR(14) ──► precompute_pivots(lookback_ltf)
                                        │
HTF bars (4h) ──► detect_pivots_confirmed(lookback_htf, conf_bars)
                              │
                    get_htf_bias_at_bar()  → BULL / BEAR / NEUTRAL
                              │
                  ┌───────────┴────────────┐
                  │                        │
         [HTF bias ≠ NEUTRAL]       [HTF bias = NEUTRAL → SKIP]
                  │
         [Filtr sesji (opcjonalny)]
                  │
           check_bos() ──► BOS detected?
                  │              │
                  │         [tak + aligned + momentum_ok]
                  │              │
                  │      Setup created → wyczekaj pullback do entry_price
                  │              │
                  │         [fill na entry_price]
                  │              │
                  │     Oblicz SL (last_pivot ± sl_buffer*ATR)
                  │     Oblicz TP (entry ± risk * RR)
                  │
             [opcja: FLAG_CONTRACTION gdy BOS=false]
```

Plik źródłowy głównej pętli: `src/strategies/trend_following_v1.py` → `run_trend_backtest()`  
Plik live runnera: `src/runners/run_live_idx.py` → `_build_strategy_config()`

---

## 2. Wejściowe dane — struktury

| Kolumna | Opis |
|---------|------|
| `open_bid` / `open_ask` | Cena otwarcia bid/ask |
| `high_bid` / `high_ask` | Cena max bid/ask |
| `low_bid` / `low_ask` | Cena min bid/ask |
| `close_bid` / `close_ask` | Cena zamknięcia bid/ask |
| `atr` | Obliczane in-loop (KROK 1) |

- **LTF** (5m): używany do wykrywania pivotów, BOS, entry, SL, TP. Index = `DatetimeIndex UTC`.
- **HTF** (4h): używany wyłącznie do wyliczenia bias trendu. Budowany przez resample LTF → 4h.

---

## 3. KROK 1 — ATR

**Plik:** `shared/bojkofx_shared/indicators/atr.py` → `calculate_atr()`

### Wzór

```
TR[i] = max(high[i]-low[i],  |high[i]-close[i-1]|,  |low[i]-close[i-1]|)
ATR[i] = EWM(alpha=1/period, adjust=False).mean(TR)   ← Wilder's smoothing
```

### Parametr

| Parametr | Typ | Produkcja | Opis |
|----------|-----|-----------|------|
| `atr_period` | int | **14** | Okres Wildera. Hardcoded w wywołaniu `calculate_atr(ltf_df, period=14)`. |

### Rola ATR w sygnale

ATR jest **jednostką miary** używaną przez **wszystkie** dalsze progi. Zmiana `atr_period` skaluje:
- Entry offset (`entry_offset_atr_mult * ATR`)
- SL buffer (`sl_buffer_atr_mult * ATR`)
- BOS momentum progi (`bos_min_range_atr_mult * ATR`)
- Flag impulse/contraction progi

> **Uwaga:** ATR 14-barowy na 5m jest bardzo krótki (~70 minut). Rozważane jest użycie
> dłuższego okresu (np. 50 lub 100) dla bardziej stabilnej bazowej jednostki.

---

## 4. KROK 2 — Precompute pivotów LTF

**Plik:** `shared/bojkofx_shared/structure/pivots.py` → `precompute_pivots()`

### Algorytm (O(n), no-lookahead)

```python
# Pivot high "p" potwierdzony gdy bar (p + lookback) jest dostępny:
# high[p] == max(high[p-lookback : p+lookback+1])
```

`ph_prices[i]` / `pl_prices[i]` = cena ostatniego potwierdzonego pivotu widoczna PRZED barem `i`.
Żadnego lookaheadu — gwarancja zgodności backtest/live.

### Parametr

| Parametr | Klucz dict | Typ | Produkcja | Zakres sensowny | Efekt |
|----------|-----------|-----|-----------|-----------------|-------|
| LTF lookback | `pivot_lookback_ltf` | int | **3** | 2–6 | Ile świec z lewej i prawej musi być niższych/wyższych. Im wyższy, tym bardziej "znaczące" pivooty, mniej fałszywych BOS, ale mniej sygnałów. |

### Konsekwencje wartości

| `pivot_lookback_ltf` | Charakter | Efekt |
|--|--|--|
| 2 | Agresywny | Dużo więcej pivotów, więcej sygnałów BOS, wyższe DD (grid 2023-2024: n=60, WR=55%) |
| 3 (prod) | Zrównoważony | Mało sygnałów (n=7–13 / 2y), ale dobre PF |
| 4–5 | Konserwatywny | Pivoty "znaczące", bardzo mało sygnałów |

---

## 5. KROK 3 — Pivoty HTF i wyliczanie bias

**Plik:** `shared/bojkofx_shared/structure/bias.py` → `get_htf_bias_at_bar()` + `determine_htf_bias()`

### Dwustopniowy proces

**A) Wykrycie pivotów HTF** (`detect_pivots_confirmed`):
```
Pivot High at bar p:   high[p] == max(high[p-htf_lookback : p+htf_lookback+1])
Widoczny od baru:      p + confirmation_bars   ← anti-lookahead
```

**B) Ocena bias** (`determine_htf_bias`):

```
BULL = highs[-1] > highs[-2]  AND  lows[-1] > lows[-2]   (HH + HL)
BEAR = lows[-1] < lows[-2]    AND  highs[-1] < highs[-2]  (LL + LH)
else NEUTRAL
```

Funkcja bierze **4 ostatnie pivoty** (`pivot_count=4` — hardcoded w wywołaniu), sprawdza
tylko `min(2, len-1)` par, czyli de facto **2 ostatnie HH/HL lub LL/LH**.

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Zakres | Efekt |
|----------|-----------|-----|-----------|--------|-------|
| HTF lookback | `pivot_lookback_htf` | int | **5** | 3–10 | Jak "duże" muszą być swingowe szczyty/dołki na H4. 5 = pivot obejmuje 5×4h = 20h z każdej strony. |
| HTF confirmation bars | `confirmation_bars` | int | **1** | 1–3 | Ile H4 barów opóźnienia potwierdzenia pivotu. Produkcja = 1 (1×4h = 4h opóźnienie). |
| HTF pivot count | (hardcoded) | int | **4** | — | Ile ostatnich pivotów brać pod uwagę przy ocenie bias. |

### Kiedy NEUTRAL blokuje sygnał

- Rynek w zakresie (brak HH+HL ani LL+LH)
- Mniej niż 2 potwierdzone pivot highs **lub** pivot lows widoczne na HTF

NEUTRAL → cały bar jest skipowany. To główne źródło **małej liczby sygnałów** na 5m (przy lb_htf=5 pivot na H4 wymaga 5×4h=20h z każdej strony → wolno otwiera się).

---

## 6. KROK 4 — Filtr sesji

**Plik:** `src/strategies/trend_following_v1.py` → `is_allowed_session()`

```python
in_session = start_hour <= bar.hour <= end_hour   # INCLUSIVE na obu końcach (BUG-US-04 fix)
```

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Opis |
|----------|-----------|-----|-----------|------|
| Włączenie | `use_session_filter` | bool | **True** | False = 24h trading |
| Start sesji | `session_start_hour_utc` | int | **13** | 13 UTC = otwarcie NY (09:00 ET) |
| Koniec sesji | `session_end_hour_utc` | int | **20** | 20 UTC = 16:00 ET, zamknięcie NY |

### Efekt zmiany (grid 2022–2025, RR=2.0)

| Konfiguracja | n | E(R) | PF | MaxDD |
|---|---|---|---|---|
| sess=ON, bos=ON (prod) | 12 | +0.271 | 1.46 | 2.0R |
| sess=OFF, bos=ON | 27 | +0.269 | 1.48 | 3.0R |

Filtr sesji redukuje liczbę sygnałów o ~55% przy bliskim PF. BOS filter jest ważniejszy.

---

## 7. KROK 5 — BOS (Break of Structure)

**Plik:** `src/strategies/trend_following_v1.py` → `check_bos()`

### Logika

```python
# LONG BOS:
if require_close_break:
    close_bid[i] > last_ph_price[i]   ← pivot high z KROK 2
else:
    high_bid[i]  > last_ph_price[i]

# SHORT BOS:
if require_close_break:
    close_bid[i] < last_pl_price[i]   ← pivot low z KROK 2
else:
    low_bid[i]   < last_pl_price[i]
```

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Opis |
|----------|-----------|-----|-----------|------|
| Close break | `require_close_break` | bool | **True** | True = BOS tylko gdy bar zamknie się za pivotem. False = wystarczy wick (bardziej agresywne, więcej fałszywych). |

### Warunki dodatkowe po wykryciu BOS

1. `bos_direction` musi być **zgodny z HTF bias** (`LONG` + `BULL` lub `SHORT` + `BEAR`)
2. Bar musi być **w oknie sesji** (o ile filtr włączony)
3. BOS momentum filter musi przejść (KROK 6)

---

## 8. KROK 6 — BOS Momentum Filter

**Plik:** `src/strategies/trend_following_v1.py` (inline)

### Logika

```python
impulse_range = high_bid[i] - low_bid[i]
body_size     = abs(close_bid[i] - open_bid[i])
body_ratio    = body_size / impulse_range

mom_ok = (
    impulse_range >= bos_min_range_atr_mult * ATR[i]
    AND
    body_ratio    >= bos_min_body_to_range_ratio
)
```

Bar BOS musi być "silną" świecą: odpowiednio duży zasięg (nie mały range) i odpowiednio duże body (nie doji/spinning top).

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Zakres | Efekt |
|----------|-----------|-----|-----------|--------|-------|
| Włączenie | `use_bos_momentum_filter` | bool | **True** | — | False = każdy BOS przechodzi niezależnie od siły świecy |
| Min range | `bos_min_range_atr_mult` | float | **1.2** | 0.5–2.5 | Min zasięg świecy BOS jako wielokrotność ATR. Wysoki = tylko mocne impulsy. |
| Min body ratio | `bos_min_body_to_range_ratio` | float | **0.6** | 0.3–0.8 | Min stosunek body/zasięg. 0.6 = body zajmuje ≥60% zasięgu (eliminuje doji). |

### Efekt zmiany (grid 2022–2025, RR=2.0)

| Konfiguracja | n | E(R) | PF | MaxDD |
|---|---|---|---|---|
| sess=ON, bos=ON (prod) | 12 | +0.271 | 1.46 | 2.0R |
| sess=ON, bos=OFF | 16 | +0.125 | 1.20 | 2.0R |

Usunięcie BOS filter: +4 trady, E spada o 54%, PF spada 1.46→1.20. **Najważniejszy filtr w pipeline.**

---

## 9. KROK 7 — Tworzenie setupu i entry price

Gdy BOS + alignment + sesja + momentum OK → tworzony jest `Setup`:

```python
entry_price = bos_level + entry_offset_atr * ATR[i]    # LONG
entry_price = bos_level - entry_offset_atr * ATR[i]    # SHORT
expiry_time = current_bar + pullback_max_bars * 5min
```

Setup czeka na **pullback** do `entry_price`. Jeśli cena wróci do `entry_price` przed `expiry_time` → fill.

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Zakres | Efekt |
|----------|-----------|-----|-----------|--------|-------|
| Entry offset | `entry_offset_atr_mult` | float | **0.3** | 0.0–1.0 | Entry ustawione ATR×0.3 za poziomem BOS (nie na samym pivocie, ale lekko deep). 0 = entry dokładnie na poziomie BOS. |
| Max pullback | `pullback_max_bars` | int | **20** | 5–50 | Ile LTF barów czekamy na pullback. 20×5m = 100 minut. Po tym czasie setup wygasa. |

### Mechanizm fill

W każdym kolejnym barze pętla sprawdza `tracker.check_fill()`:
- LONG: `low_bid[i] <= entry_price`
- SHORT: `high_ask[i] >= entry_price`

Fill rejestruje `bars_to_fill` = liczba barów oczekiwania.

---

## 10. KROK 8 — Stop Loss

Obliczany **w momencie fill** (nie w momencie BOS):

```python
# LONG SL:
if sl_anchor == 'last_pivot':
    sl_level = ltf_pl_prices[i]       # ostatni potwierdzony pivot low (no-lookahead)
else:  # 'pre_bos_pivot'
    sl_level = setup.bos_level        # poziom pivotu z momentu BOS
sl = sl_level - sl_buffer_atr * ATR[i]
risk = entry - sl

# SHORT SL:
if sl_anchor == 'last_pivot':
    sl_level = ltf_ph_prices[i]       # ostatni potwierdzony pivot high
else:
    sl_level = setup.bos_level
sl = sl_level + sl_buffer_atr * ATR[i]
risk = sl - entry
```

### Parametry

| Parametr | Klucz dict | Typ | Produkcja | Opis |
|----------|-----------|-----|-----------|------|
| SL anchor | `sl_anchor` | str | `"last_pivot"` | `"last_pivot"` = SL pod/nad ostatnim LTF pivotem w momencie fill. `"pre_bos_pivot"` = SL na poziomie samego pivotu który był wybity przez BOS. |
| SL buffer | `sl_buffer_atr_mult` | float | **0.5** | ATR×0.5 luzu poniżej/powyżej pivotu. Zapobiega wypychaniu przez spread+szum. |

### Degeneracja

Jeśli `risk <= 0` (entry za blisko SL) → setup odrzucany (`tracker.clear_active_setup()`).

---

## 11. KROK 9 — Take Profit (RR)

```python
# LONG TP:
tp = entry + risk * rr      # risk = entry - sl

# SHORT TP:
tp = entry - risk * rr
```

### Parametr

| Parametr | Klucz dict | Typ | Produkcja | Zakres | Efekt (grid 2022-2025) |
|----------|-----------|-----|-----------|--------|------------------------|
| Risk/Reward | `risk_reward` | float | **2.0** | 1.5–3.5 | RR=2.5 daje E=+0.458R vs +0.271R dla RR=2.0 przy tym samym MaxDD=2.0R |

### Partial TP (opcjonalne, domyślnie wyłączone)

| Parametr | Klucz dict | Typ | Domyślnie |
|----------|-----------|-----|-----------|
| Włączenie | `use_partial_take_profit` | bool | **False** |
| Rozmiar cz. TP | `partial_tp_ratio` | float | 0.5 (50% pozycji) |
| RR cz. TP | `partial_tp_rr` | float | 1.0 |
| RR pełny TP | `final_tp_rr` | float | 2.0 |
| SL → BE po cz. TP | `move_sl_to_be_after_partial` | bool | True |

---

## 12. KROK 10 — Opcjonalna ścieżka: Flag Contraction

**Plik:** `src/structure/flags.py` → `detect_flag_contraction()`  
**Domyślnie wyłączona** (`use_flag_contraction_setup=False` w produkcji).

BOS ma PRIORYTET — Flag Contraction odpala tylko gdy BOS nie wykryto na danym barze.

### Algorytm

```
Impulse window  : bary [i - contraction_bars - impulse_lookback ... i - contraction_bars)
Contraction window: bary [i - contraction_bars ... i)
Breakout bar    : bar i (tylko close_bid)

LONG:
  imp_close - imp_open >= min_impulse_atr_mult * ATR    (silny ruch w górę)
  c_max - c_min <= max_contraction_atr_mult * ATR       (wąskie konsolidacja)
  close_bid[i] > contraction_high                       (wybicie górą)
  entry = contraction_high + breakout_buffer * ATR
  sl    = contraction_low  - sl_buffer * ATR
```

### Parametry Flag

| Parametr | Klucz dict | Typ | Domyślnie | Opis |
|----------|-----------|-----|-----------|------|
| Włączenie | `use_flag_contraction_setup` | bool | **False** | Aktywuje PATH B |
| Lookback impulsu | `flag_impulse_lookback_bars` | int | 8 | Ile barów tworzy impulse window |
| Szerokość konsolidacji | `flag_contraction_bars` | int | 5 | Ile barów tworzy contraction window |
| Min siła impulsu | `flag_min_impulse_atr_mult` | float | 2.5 | Minimalny ruch impulsu jako ×ATR |
| Max szerokość konsolidacji | `flag_max_contraction_atr_mult` | float | 1.2 | Flaga odrzucana gdy range > 1.2×ATR |
| Entry buffer | `flag_breakout_buffer_atr_mult` | float | 0.1 | Entry za breakout levelem |
| SL buffer | `flag_sl_buffer_atr_mult` | float | 0.3 | Luż SL poza przeciwnym brzegiem flagi |

---

## 13. Produkcyjne nastawy

Pobierane z `src/runners/run_live_idx.py` → `_build_strategy_config()`.  
**Hardcoded** (nie z YAML) — celowo, żeby uniknąć przypadkowych zmian.

```python
pivot_lookback_ltf         = 3
pivot_lookback_htf         = 5
confirmation_bars          = 1
require_close_break        = True
entry_offset_atr_mult      = 0.3
pullback_max_bars          = 20
sl_anchor                  = "last_pivot"
sl_buffer_atr_mult         = 0.5
risk_reward                = 2.0
use_session_filter         = True
session_start_hour_utc     = 13
session_end_hour_utc       = 20
use_bos_momentum_filter    = True
bos_min_range_atr_mult     = 1.2
bos_min_body_to_range_ratio= 0.6
use_flag_contraction_setup = False
```

Sesja ustawiana przez CLI args lub stałe `SESSION_START_H=13`, `SESSION_END_H=20`.

---

## 14. Mapa wszystkich parametrów

Pełna lista w kolejności pipeline, z bieżącą wartością produkcyjną i zakresem do tuningu:

| # | Parametr (klucz dict) | Typ | Produkcja | Zakres tuning | Efekt główny |
|---|----------------------|-----|-----------|---------------|--------------|
| 1 | `pivot_lookback_ltf` | int | 3 | **2–6** | Granularność LTF pivotów → liczba sygnałów |
| 2 | `pivot_lookback_htf` | int | 5 | **3–10** | Granularność HTF pivotów → czułość bias |
| 3 | `confirmation_bars` | int | 1 | 1–3 | Opóźnienie potwierdzenia HTF pivotu (bary H4) |
| 4 | `require_close_break` | bool | True | True/False | BOS trigger: close vs wick |
| 5 | `use_session_filter` | bool | True | True/False | Ograniczenie do sesji NY |
| 6 | `session_start_hour_utc` | int | 13 | 7–15 | Godzina otwarcia sesji (UTC) |
| 7 | `session_end_hour_utc` | int | 20 | 17–23 | Godzina zamknięcia sesji (UTC) |
| 8 | `use_bos_momentum_filter` | bool | True | True/False | Filtr siły świecy BOS |
| 9 | `bos_min_range_atr_mult` | float | 1.2 | **0.5–2.0** | Min zasięg świecy BOS (×ATR) |
| 10 | `bos_min_body_to_range_ratio` | float | 0.6 | **0.3–0.8** | Min body/range ratio świecy BOS |
| 11 | `entry_offset_atr_mult` | float | 0.3 | **0.0–1.0** | Offset entry za poziomem BOS |
| 12 | `pullback_max_bars` | int | 20 | **5–60** | Czas oczekiwania na pullback (×5m) |
| 13 | `sl_anchor` | str | `"last_pivot"` | `"last_pivot"` / `"pre_bos_pivot"` | Punkt zaczepu SL |
| 14 | `sl_buffer_atr_mult` | float | 0.5 | **0.2–1.5** | Luż SL poza pivotem (×ATR) |
| 15 | `risk_reward` | float | 2.0 | **1.5–3.5** | Stosunek TP/SL |
| 16 | `use_flag_contraction_setup` | bool | False | True/False | Aktywacja PATH B (flag) |

---

## 15. Zależności i efekty uboczne

### Najważniejsze interakcje

```
pivot_lookback_ltf ──► liczba pivotów LTF ──► częstość BOS ──► n tradów
pivot_lookback_htf ──► częstość zmiany bias HTF ──► % czasu bias ≠ NEUTRAL ──► n tradów
bos_min_range_atr_mult ──► zależy od ATR(14) ──► zmiana atr_period = zmiana progu
```

### Bottleneck sygnałów (dlaczego n=13 w 5 latach)

Pipeline ma 5 seryjnych filtrów — każdy redukuje sygnały:

1. `pivot_lookback_htf=5` = pivot H4 obejmuje 5×4h=20h z każdej strony → powolna zmiana bias
2. `confirmation_bars=1` = dodatkowe 4h opóźnienia pivotu HTF
3. `use_session_filter=True` + okno 13–20 UTC = 7h/24h = ~29% czasu
4. `use_bos_momentum_filter=True` = eliminuje słabe BOS bary
5. `pullback_max_bars=20` = setup wygasa po 100 min jeśli cena nie wraca

### Rekomendacje dla grid testów

- **Najszybsze zwiększenie n:** `pivot_lookback_ltf=2` (grid 2023-24: n=60 vs n=7), ale wymaga
  pełnego 5-letniego testu – wyniki z 2-letniego okna mogą być overfitted.
- **Bezpieczna zmiana:** `risk_reward=2.5` zamiast 2.0 → E=+0.458R vs +0.271R, identyczny MaxDD=2.0R.
- **Testuj ostrożnie:** `bos_min_range_atr_mult` i `bos_min_body_to_range_ratio` — silna interakcja
  między sobą i z `pivot_lookback_ltf`. Zmień jedno na raz.
- **Nie zmieniaj jednocześnie** `pivot_lookback_ltf` i `pivot_lookback_htf` — zbyt wiele zmiennych.

### Ścieżka kodu od baru do sygnału (numer linii)

```
trend_following_v1.py:
  L94   → check_bos()                           (BOS detection)
  L54   → is_allowed_session()                  (session filter)
  L68   → run_trend_backtest()                  (main backtest loop)
  L138  → calculate_atr()                       (ATR)
  L144  → precompute_pivots()                   (LTF pivots)
  L150  → detect_pivots_confirmed()             (HTF pivots)
  L465  → get_htf_bias_at_bar()                 (HTF bias)
  L493  → check_bos() call                      (BOS check)
  L501  → bos_aligned check                     (HTF alignment)
  L504  → session check                         (sesja)
  L508  → BOS momentum filter                   (momentum)
  L521  → tracker.create_setup()                (setup creation)
  L406  → tracker.check_fill() + SL/TP calc    (fill + position open)
```

---

## 16. Analiza częstości transakcji — test relaksacji filtrów (2025, 5m)

**Data:** 2026-03-11 | **Instrument:** USATECHIDXUSD | **LTF:** 5m | **HTF:** 4h | **Okres:** 2025-01-01 → 2025-12-31

### Co ogranicza liczbę transakcji najbardziej?

Ranking wpływu poszczególnych filtrów na n (baseline prod = **n=2** w 2025):

| Filtr | Zmiana | n (solo) | Delta n | Ocena jakości |
|-------|--------|----------|---------|---------------|
| `use_session_filter=False` | wyłącz okno sesji | 6 | **+4** | WR=50%, E=+0.542 ✓ |
| `session 08-23` (zamiast 13-20) | poszerz okno | 5 | **+3** | WR=40%, E=+0.251 ✓ |
| `use_bos_momentum_filter=False` | wyłącz momentum | 4 | **+2** | WR=50%, E=+0.500 ✓ |
| `confirmation_bars=0` | brak potwierdzenia HTF | 4 | **+2** | WR=25%, E=-0.665 ✗ |
| `session 09-22` | poszerz okno | 4 | **+2** | WR=25%, E=-0.187 ✗ |
| `pivot_lookback_ltf=2` | wrażliwszy pivot | 3 | +1 | WR=0%, E=-1.000 ✗ |
| `require_close_break=False` | wick BOS | 2 | 0 | bez zmiany |
| `bos_min_range_atr=0.5/0.8` | słabszy BOS | 3 | +1 | WR=67%, E=+1.085 ✓ |
| `pullback_max_bars=50` | dłuższy pullback | 2 | 0 | wysoki PF ale n bez zmiany |

**Wniosek: `use_session_filter` jest największym pojedynczym ogranicznikiem** — okno 13–20 UTC
obejmuje tylko ~29% doby. Jego wyłączenie podwaja+trojkuje liczbę tradów z zachowaniem jakości.
Momentum filter to drugi co do wpływu filtr, ale degraduje nieco WR gdy jest wyłączony samodzielnie.

### Wyniki testów kombinacji (2025, 5m)

#### Podwójne relaksacje

| Konfiguracja | n | WR | E(R) | PF | MaxDD |
|---|---|---|---|---|---|
| `momentum=OFF + ltf=2` | **5** | 60% | **+0.800** | **3.00** | 1.0R |
| `momentum=OFF + no session` | 8 | 38% | +0.125 | 1.20 | 3.0R |
| `momentum=OFF + session 09-22` | 8 | 25% | -0.250 | 0.67 | 4.0R |
| `no session + close_break=False` | 6 | 50% | +0.542 | 2.08 | 1.0R |
| `no session + ltf=2` | 6 | 33% | +0.000 | 1.00 | 4.0R |

#### Potrójne relaksacje

| Konfiguracja | n | WR | E(R) | PF | MaxDD |
|---|---|---|---|---|---|
| `momentum=OFF + ltf=2 + session 09-22` | **11** | 45% | +0.364 | 1.67 | 3.0R |
| `momentum=OFF + no session + ltf=2` | 7 | **57%** | **+0.714** | **2.67** | **2.0R** |
| `momentum=OFF + no session + pullback=100` | 6 | 50% | +0.610 | 2.56 | 2.3R |
| `momentum=OFF + ltf=2 + bos_range=0.5` | 5 | 60% | +0.800 | 3.00 | 1.0R |
| `momentum=OFF + no session + bos_range=0.5` | 8 | 38% | +0.125 | 1.20 | 3.0R |

#### Mocne rozluźnienie (4+ filtrów)

| Konfiguracja | n | WR | E(R) | PF | MaxDD |
|---|---|---|---|---|---|
| `ALL OFF + ltf=1` | **11** | 55% | +0.388 | 1.64 | 3.7R |
| `momentum=OFF + no session + ltf=2 + bos_range=0.5` | 7 | 57% | +0.714 | 2.67 | 2.0R |
| `momentum=OFF + no session + ltf=2 + body_ratio=0.3` | 7 | 57% | +0.714 | 2.67 | 2.0R |
| `momentum=OFF + no session + ltf=2 + close_break=False` | 9 | 33% | +0.000 | 1.00 | 2.0R |

### Kandydaci do testu 2021–2026

Na podstawie bilansu n vs jakość (E > 0, PF > 1.5, MaxDD ≤ 2R):

| Priorytet | Konfiguracja | Uzasadnienie |
|-----------|---|---|
| **A — jakość** | `momentum=OFF + ltf=2` | Najwyższe E(R)=+0.800 i WR=60%, DD=1R. n=5/rok → ~25 na 5 lat |
| **B — balans** | `momentum=OFF + no session + ltf=2` | n=7, E=+0.714, DD=2R. Dobry kompromis |
| **C — częstość** | `momentum=OFF + ltf=2 + session 09-22` | n=11, ale niższe E=+0.364 i DD=3R |

> **Uwaga:** Wyniki z 1 roku (n=5–11) mają wysoką wariancję. Przed podjęciem decyzji
> o zmianie produkcji bezwzględnie wymagany jest test na pełnym okresie 2021–2026.

---

## 17. Analiza bottlenecków — test F1 × F2 × F3 (2025, 5m)

**Data:** 2026-03-11 | **Instrument:** USATECHIDXUSD | **LTF:** 5m | **HTF:** 4h | **Okres:** 2025-01-01 → 2025-12-31 | **Baseline:** n=2

Testowane trzy główne filtry i ich kombinacje:
- **F1** — filtr sesji (`session_start/end_hour_utc`, `use_session_filter`)
- **F2** — BOS momentum filter (`use_bos_momentum_filter`, `bos_min_range_atr_mult`, `bos_min_body_to_range_ratio`)
- **F3** — HTF pivot lookback (`pivot_lookback_htf`, `confirmation_bars`)

---

### Filtr 1: Sesja (F1)

| Konfiguracja | n | WR | E(R) | PF | DD |
|---|---|---|---|---|---|
| `13-20 [prod]` | 2 | 50% | +0.627 | 2.25 | 1.0R |
| `use_session_filter=False` | 6 | 50% | +0.542 | 2.08 | 1.0R |
| `session 00-23` | 6 | 50% | +0.542 | 2.08 | 1.0R |
| `session 08-23` / `07-23` | 5 | 40% | +0.251 | 1.42 | 2.0R |
| `session 09-22` / `09-20` | 4 | 25% | -0.187 | 0.75 | 2.0R |

**Wniosek F1:** Wyłączenie filtra sesji 3× więcej tradów z zachowaniem jakości. `session 09-22` paradoksalnie pogarsza jakość (dodaje złe godziny wieczorne US). Najlepiej: całkowite wyłączenie lub rozszerzenie do `00-23`.

---

### Filtr 2: BOS Momentum (F2)

| Konfiguracja | n | WR | E(R) | PF | DD |
|---|---|---|---|---|---|
| `momentum=ON [prod]` | 2 | 50% | +0.627 | 2.25 | 1.0R |
| `momentum=OFF` | 4 | 50% | +0.500 | 2.00 | 1.0R |
| `bos_range=0.5/0.8/1.0` | 3 | 67% | +1.085 | 4.25 | 1.0R |
| `bos_body=0.3/0.4/0.5` | 2 | 50% | +0.627 | 2.25 | 1.0R |
| `bos_range=0.5 + body=0.3` | 3 | 33% | +0.000 | 1.00 | 1.0R |

**Wniosek F2:** Momentum filter dodaje tylko 2 trady solo. Sama zmiana `bos_range` dodaje 1 trad z wyższą jakością (WR=67%, E=+1.085). `bos_body` nie ma wpływu na n w 2025. Kombinacja range+body nie poprawia n relative do samego range.

---

### Filtr 3: HTF Pivot Lookback (F3) — GŁÓWNY BOTTLENECK

| Konfiguracja | n | WR | E(R) | PF | DD |
|---|---|---|---|---|---|
| `htf_lb=5 [prod]` | 2 | 50% | +0.627 | 2.25 | 1.0R |
| `htf_lb=4` | **10** | 50% | +0.525 | 2.05 | 3.0R |
| **`htf_lb=3`** | **22** | **55%** | **+0.648** | **2.43** | **3.0R** |
| `htf_lb=2` | 35 | 46% | +0.371 | 1.68 | 3.0R |
| `htf_lb=1` | 31 | 45% | +0.355 | 1.65 | 5.0R |
| `htf_lb=3 + conf=0` | 29 | 41% | +0.184 | 1.28 | 4.9R |
| `htf_lb=2 + conf=0` | 42 | 45% | +0.357 | 1.65 | 5.0R |

**Wniosek F3:** `pivot_lookback_htf` jest **bezapelacyjnym głównym bottleneckiem.**
- Zmiana z 5 na 3 daje **11× więcej tradów** (2 → 22) z **lepszą** jakością (E=+0.648 vs +0.627).
- `htf_lb=3` to optimum: więcej tradów niż =4, lepsza jakość niż =2.
- `confirmation_bars=0` samodzielnie obniża jakość (WR spada do 41%).
- `htf_lb=2` i `=1` mają DD=3–5R — zbyt szerokie.

---

### Kombinacje F1 × F2 × F3

| Konfiguracja | n | WR | E(R) | PF | DD | Ocena |
|---|---|---|---|---|---|---|
| `htf_lb=3` (samo) | **22** | 55% | **+0.648** | **2.43** | **3.0R** | **NAJLEPSZE** |
| `session 09-22 + htf_lb=3` | 33 | 45% | +0.373 | 1.68 | 5.0R | DD za wysokie |
| `momentum=OFF + htf_lb=3` | 34 | 44% | +0.305 | 1.53 | 4.0R | pogarsza jakość |
| `no session + htf_lb=3` | 47 | 38% | +0.156 | 1.25 | 8.9R | DD destruktywne |
| `no session + momentum=OFF + htf_lb=3` | 71 | 37% | +0.048 | 1.07 | 8.1R | prawie break-even |
| `no session + htf_lb=2` | 77 | 36% | -0.142 | 0.84 | 28.0R | ujemne |
| `no session + momentum=OFF + htf_lb=2` | 119 | 35% | +0.022 | 1.03 | 16.5R | nierentowne |

**Kluczowy wniosek:** Nakładanie kolejnych relaksacji na siebie **systematycznie degraduje jakość**. Każdy dodatkowy filtr wyłączony ponad `htf_lb=3` dodaje trady ale obniża WR i E(R).

---

### Podsumowanie — ranking filtrów wg wpływu na n

```
pivot_lookback_htf: 5→3  =  +20 tradów/rok  (11×)   ← DOMINUJACY
use_session_filter: OFF  =  +4 trady/rok    (3×)
bos_momentum: OFF        =  +2 trady/rok    (2×)
```

**Rekomendacja do testu 5-letniego:**

| Priorytet | Zmiana | Uzasadnienie |
|-----------|--------|---|
| **ZMIEN** | `pivot_lookback_htf: 5 → 3` | +1000% tradów, lepsza jakość, DD akceptowalne (3R) |
| Opcja | `+ session OFF` | +kolejne ~2×, ale DD rośnie do 9R — ryzykowne |
| Nie ruszaj | F2 (momentum) solo | Mały przyrost n, pogarsza jakość |

> `pivot_lookback_htf=3` to jedyna zmiana, która jednocześnie **zwiększa n** i **utrzymuje lub poprawia jakość**.

---

## 18. Test htf=3 — pełny okres 2021–2026 (5m, US100)

**Data:** 2026-03-11 | **Instrument:** USATECHIDXUSD | **LTF:** 5m | **HTF:** 4h

### Porównanie z produkcją — roczny breakdown

| Rok | Prod n | Prod E(R) | htf=3 n | htf=3 WR | htf=3 E(R) | htf=3 DD |
|-----|--------|-----------|---------|----------|------------|----------|
| 2021 | 1 | +2.000 | 23 | 30% | **-0.087** | 9.0R |
| 2022 | 3 | +0.000 | 20 | 15% | **-0.550** | 11.0R |
| 2023 | 5 | +0.200 | 34 | 41% | +0.211 | 5.8R |
| 2024 | 2 | +0.500 | 27 | 56% | +0.658 | 3.7R |
| 2025 | 2 | +0.627 | 22 | 55% | +0.648 | 3.0R |
| **FULL 2021–2026** | **13** | **+0.404** | **124** | **40%** | **+0.195** | **20.0R** |
| IS 2021–2023H1 | 6 | +0.000 | 58 | 24% | **-0.276** | 20.0R |
| OOS 2023H2–2026 | 7 | +0.751 | 66 | 55% | **+0.609** | 4.0R |

### Kombinacje htf=3 z innymi parametrami (FULL 2021–2026)

| Konfiguracja | n | WR | E(R) | PF | DD | Sharpe |
|---|---|---|---|---|---|---|
| `htf=3 [baza]` | 124 | 40% | +0.195 | 1.33 | 20.0R | 0.94 |
| **`htf=3 + rr=2.5`** | 118 | 38% | **+0.321** | **1.52** | 20.0R | **1.34** |
| `htf=3 + sl_buf=0.3` | 128 | 41% | +0.203 | 1.35 | **14.0R** | 0.99 |
| `htf=3 + sl_buf=0.2` | 130 | 40% | +0.154 | 1.26 | 14.0R | 0.75 |
| `htf=3 + rr=2.5 + sl_buf=0.3` | 122 | 37% | +0.238 | 1.38 | 20.0R | 1.02 |
| `htf=3 + rr=2.5 + sl_buf=0.2` | 125 | 37% | +0.224 | 1.35 | 20.0R | 0.96 |
| `htf=3 + rr=1.5` | 133 | 46% | +0.138 | 1.25 | 16.5R | 0.78 |
| `htf=3 + momentum=OFF` | 181 | 40% | +0.174 | 1.29 | 22.4R | 0.84 |
| `htf=3 + session 09-22` | 180 | 39% | +0.164 | 1.27 | 25.0R | 0.80 |
| `htf=3 + ltf_lb=2` | 134 | 38% | +0.128 | 1.21 | 26.0R | 0.62 |
| `htf=3 + no session` | 275 | 36% | +0.045 | 1.07 | 32.2R | 0.22 |
| `htf=3 + momentum=OFF + session 09-22` | 260 | 39% | +0.135 | 1.22 | 17.0R | 0.66 |
| `htf=3 + momentum=OFF + no session` | 370 | 37% | +0.073 | 1.11 | 27.5R | 0.36 |

### Wnioski z testu 5-letniego

**1. HTF=3 ma podwójną twarz:**
- **2021–2022:** tragiczne — WR=15–30%, E ujemne, DD do 11R/rok. Bias HTF=3 generował fałszywe sygnały w trendach bocznych/silnych tendencjach tamtego okresu.
- **2023–2025:** doskonałe — WR=41–56%, E=+0.21 do +0.65, DD kontrolowane 3–6R.
- **IS (2021–2023H1) E=-0.276** — strategia *traciła* pieniądze w pierwszej połowie danych.
- **OOS (2023H2–2026) E=+0.609** — w drugiej połowie wróciła do znakomitych wyników.

**2. MaxDD=20R na pełnym okresie jest nie do zaakceptowania** — to 2× wyższe niż produkcja przy 9× więcej tradach.

**3. Najlepsza wariacja: `htf=3 + rr=2.5`**
- E(R)=+0.321, Sharpe=1.34, DD=20R — najwyższy E(R) i Sharpe z grupy htf=3.

**4. `sl_buf=0.3` obniża DD do 14R** bez dużej straty na E(R) — interesująca opcja do dalszego tuningu.

**5. Dodatkowe relaksacje (momentum=OFF, no session) nie pomagają** — każda obniża E(R) i podwyższa DD.

### Główne ograniczenie htf=3

`pivot_lookback_htf=3` na 4h = pivot wymaga tylko 12h z każdej strony potwierdzenia.
W lateralnych/choppiness rynkach (US100 2021–2022) bias zmienia się zbyt często →
liczne fałszywe BOS-y → wysoki DD. Strategia działa tylko gdy rynek ma **wyraźny trend 4h**.

### Rekomendacja

| Scenariusz | Decyzja |
|---|---|
| Chcemy więcej tradów z akceptowalnym ryzykiem | `htf_lb=3 + rr=2.5`, ale **wymagany filtr reżimu rynkowego** (np. ADX>20 lub ATR relative) |
| Priorytet jakości nad częstością | **Zostań przy produkcji (`htf=5`)** — n=13 ale E=+0.404, DD=2R |
| Kompromis | `htf=4` — n≈40–50/5 lat (szacunek), DD≈8–10R — **nieprzetestowane, warto zbadać** |

> **Następny krok:** test `pivot_lookback_htf=4` na 2021–2026 jako potencjalny kompromis między htf=5 (zbyt rzadki) a htf=3 (zbyt agresywny w lateralu).

---

## 19. Test htf=4 — pełny okres 2021–2025 (5m, US100)

**Data:** 2026-03-11 | **Instrument:** USATECHIDXUSD | **LTF:** 5m | **HTF:** 4h

### Porównanie z produkcją i htf=3 — roczny breakdown

| Rok | Prod n | Prod E(R) | htf=4 n | htf=4 WR | htf=4 E(R) | htf=4 DD | htf=3 E(R) ref |
|-----|--------|-----------|---------|----------|------------|----------|----------------|
| 2021 | 1 | +2.000 | 6 | 33% | +0.000 | 2.0R | -0.087 |
| 2022 | 3 | +0.000 | 14 | **14%** | **-0.571** | 8.0R | -0.550 |
| 2023 | 5 | +0.200 | 10 | 30% | -0.100 | 6.0R | +0.211 |
| 2024 | 2 | +0.500 | 14 | **71%** | **+1.143** | 2.0R | +0.658 |
| 2025 | 2 | +0.627 | 10 | 50% | +0.525 | 3.0R | +0.648 |
| **FULL 2021–2025** | **13** | **+0.404** | **54** | **41%** | **+0.227** | **16.0R** | +0.195 |
| IS 2021–2023H1 | 6 | +0.000 | 26 | 15% | **-0.538** | 16.0R | -0.276 |
| OOS 2023H2–2025 | 7 | +0.751 | 28 | **64%** | **+0.938** | 3.0R | +0.609 |

### Kombinacje htf=4 z innymi parametrami (FULL 2021–2025)

| Konfiguracja | n | WR | E(R) | PF | DD |
|---|---|---|---|---|---|
| `htf=4 [baza]` | 54 | 41% | +0.227 | 1.38 | 16.0R |
| **`htf=4 + rr=2.5`** | 54 | 39% | **+0.361** | **1.59** | 15.0R |
| `htf=4 + sl_buf=0.3` | 54 | 43% | +0.249 | 1.43 | **13.0R** |
| `htf=4 + sl_buf=0.2` | 55 | 42% | +0.212 | 1.37 | 13.0R |
| `htf=4 + rr=2.5 + sl=0.3` | 54 | 39% | +0.306 | 1.50 | 15.0R |
| `htf=4 + rr=2.5 + sl=0.2` | 54 | 37% | +0.242 | 1.38 | 15.0R |
| `htf=4 + rr=1.5` | 56 | 46% | +0.180 | 1.34 | 12.5R |
| `htf=4 + momentum=OFF` | 78 | 41% | +0.209 | 1.35 | 19.0R |
| `htf=4 + session 09-22` | 74 | 39% | +0.165 | 1.27 | 19.0R |
| `htf=4 + no session` | 121 | 38% | +0.083 | 1.13 | 19.0R |
| `htf=4 + ltf_lb=2` | 57 | 37% | +0.094 | 1.15 | 17.0R |
| `htf=4 + rr=2.5 + no sess` | 120 | 34% | +0.115 | 1.17 | 20.0R |
| `htf=4 + mom=OFF + 09-22` | 106 | 40% | +0.157 | 1.25 | 14.6R |
| `htf=4 + mom=OFF + no sess` | 162 | 36% | +0.058 | 1.09 | 19.0R |

### Roczny breakdown `htf=4 + rr=2.5` (najlepsza wariacja)

| Rok | n | WR | E(R) | PF | DD |
|-----|---|---|---|---|---|
| 2021 | 6 | 33% | +0.167 | 1.25 | 2.0R |
| 2022 | 14 | 14% | -0.500 | 0.42 | 7.5R |
| 2023 | 10 | 30% | +0.050 | 1.07 | 6.0R |
| 2024 | 14 | 71% | +1.500 | 6.25 | 2.0R |
| 2025 | 10 | 40% | +0.400 | 1.67 | 3.0R |

### Wnioski z testu htf=4

**1. HTF=4 to prawdziwy kompromis ilościowy:**
- n=54 vs prod=13 (4× więcej) i htf=3=124 (2× mniej) — pośredni poziom częstości.

**2. Problem roku 2022 jest taki sam jak w htf=3:**
- WR=14%, E=-0.571 w 2022 — US100 był wtedy w silnej bessie z dużą zmiennością.
- Żadna zmiana `pivot_lookback_htf` nie eliminuje tego problemu — to kwestia **reżimu rynkowego**.

**3. IS (2021–2023H1) jest GORSZE niż htf=3 (E=-0.538 vs -0.276):**
- htf=4 łapie więcej tradów w złym 2022, przez co strata IS jest głębsza.

**4. OOS (2023H2–2025) jest LEPSZE niż htf=3 (E=+0.938 vs +0.609):**
- W dobrych warunkach (trend 4h wyraźny) htf=4 generuje lepszą jakość niż htf=3 dzięki mniejszemu szumowi.
- OOS Sharpe wyższy, DD tylko 3.0R — doskonałe wyniki w tym oknie.

**5. MaxDD=16R na pełnym 5-letnim okresie jest wciąż zbyt wysokie** dla strategii produkcyjnej.

**6. Każda dodatkowa relaksacja pogarsza wyniki** — wzorzec identyczny jak w htf=3:
- `no session`, `momentum=OFF`, `ltf_lb=2` — każda obniża E i podwyższa DD.
- `rr=2.5` to jedyna zmiana poprawiająca E (+59%) bez znaczącego wzrostu DD.

### Zestawienie porównawcze htf=3, htf=4, htf=5 (FULL)

| | htf=5 (prod) | htf=4 | htf=3 |
|---|---|---|---|
| n (FULL) | 13 | 54 | 124 |
| WR | 46% | 41% | 40% |
| E(R) | **+0.404** | +0.227 | +0.195 |
| PF | **1.75** | 1.38 | 1.33 |
| MaxDD | **2.0R** | 16.0R | 20.0R |
| IS E(R) | +0.000 | -0.538 | -0.276 |
| OOS E(R) | +0.751 | **+0.938** | +0.609 |
| OOS DD | 1.0R | **3.0R** | 4.0R |

### Konkluzja — jaki jest optymalny `pivot_lookback_htf`?

**Produkcja (htf=5) wygrywa na metrykach pełnego okresu** — najwyższe E(R), najniższe DD, najlepsze PF.
Jej jedyną wadą jest zbyt małe n (13 tradów / 5 lat = ~2-3/rok) — za mało do oceny statystycznej.

Zarówno htf=3 jak i htf=4 karne IS E < 0 — strategia **traciła pieniądze** w pierwszej połowie okresu testów.
Winowajcą jest rok 2022 (bessy US100), który niszczy oba konfiguracje.

**Wniosek systemowy:** Problem nie leży w `pivot_lookback_htf`. Problem leży w braku **filtru reżimu rynkowego** — strategia jest zaprojektowana pod rynki trendujące (2023–2025), ale nie ma mechanizmu samoobrony w rynkach bocznych/bessowych (2022).

### Rekomendacja dalszych kroków

| Priorytet | Działanie | Uzasadnienie |
|-----------|-----------|---|
| **1 — KLUCZOWE** | Dodaj filtr reżimu rynkowego | ADX > 20 lub ATR(50) relative > próg → blokuj sygnały w lateralu |
| **2** | Sprawdź czy htf=4+rr=2.5 z filtrem reżimu daje E>+0.4 na IS | Jeśli tak → htf=4 staje się kandydatem produkcyjnym |
| **3** | Zostań przy htf=5 do czasu implementacji filtru reżimu | Najlepsze metryki full-period, ryzyko kontrolowane |

> **Główne odkrycie badania htf=3/4:** Wszystkie warianty luźniejszego HTF lookback dają znakomite OOS (2023–2025), ale katastrofalne IS (2021–2022). To wskazuje na konieczność filtru reżimu, a nie dalszego tweakowania lookback.

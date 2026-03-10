# Krytyczny Przegląd Inżynieryjny — BojkoIDX

**Zakres:** Pełny audyt kodu obejmujący jakość architektury, poprawność backtestów, błędy lookahead, spójność strategii, realizm modelu egzekucji, bezpieczeństwo potoku danych, jakość testów, ryzyko handlowe, ukryte ryzyka techniczne oraz plan refaktoryzacji.

**Konwencja oznaczeń:**
- 🔴 **Krytyczny** — błędne wyniki lub ryzyko strat finansowych na żywym rachunku
- 🟡 **Średni** — obniżona dokładność lub ryzyko utrzymaniowe
- 🟢 **Niski / informacyjny** — luka best-practice, brak bezpośredniego szkody

---

## 1. Przegląd Jakości Architektury

### Co działa dobrze
- Warstwowa separacja: `data` → `structure` → `strategies` → `backtest` → `execution` → `runners`.
- Typowane dataclassy w `src/core/config.py` (`StrategyConfig`, `SymbolConfig`, `RiskConfig`, `IBKRConfig`) zapewniają widoczne w IDE typy i wartości domyślne.
- `SQLiteStateStore` implementuje idempotentny zapis zleceń (hash SHA-1 `make_intent_id`).
- `IBKRExecutionEngine` posiada trójstopniowy obwód bezpieczeństwa (`readonly` + `allow_live_orders` + `kill_switch_active`).

### Problemy strukturalne

**🔴 Dwie równoległe implementacje strategii nigdy nie zostały połączone**

| Plik | Filtr biasu HTF | Anti-lookahead pivotów | Używany w |
|------|----------------|------------------------|-----------|
| `src/strategies/trend_following_v1.py` | ✅ `get_htf_bias_at_bar()` | ✅ `detect_pivots_confirmed()` | Backtesty |
| `src/core/strategy.py` | ❌ brak | ❌ wewnętrzny `_detect_pivots()` zawiera lookahead | Live trading |

System, który operuje prawdziwymi pieniędzmi, używa innej, słabszej strategii niż ta, której raporty wydajnościowe są pokazywane użytkownikom. Patrz §4, pełna analiza.

**🔴 Dwie równoległe implementacje pivotów**

| Plik | Lookahead-safe? | Używany przez |
|------|----------------|---------------|
| `src/structure/pivots.py` (`detect_pivots_confirmed`) | ✅ | `trend_following_v1.py` |
| `src/indicators/pivots.py` (`detect_swing_pivots`) | ❌ | `engine.py`, `engine_enhanced.py`, `detect_zones.py` |

Backtesty przechodzące przez silnik strefowy raportują zawyżoną przewagę. Patrz §3.

**🟡 Dwa równoległe systemy konfiguracji**
`src/utils/config.py` (stary słownik `BACKTEST_CONFIG`) współistnieje z `src/core/config.py` (typowane dataclassy). Kilka starszych skryptów backtestowych nadal korzysta ze starego słownika. Utrzymywanie obu systemów otwiera drogę do dryftu parametrów niewidocznego dla analizy statycznej.

**🟡 Dwie implementacje ATR z różnym zachowaniem podczas rozgrzewki**

| Lokalizacja | Formuła |
|-------------|---------|
| `trend_following_v1.py` | `rolling(14).mean()` — prosta średnia arytmetyczna |
| `src/indicators/atr.py` | `ewm(alpha=1/14)` — wykładnicza średnia ruchoma Wildera |

Prosta MA wymaga dokładnie 14 świec rozgrzewki i przypisuje równą wagę wszystkim 14 świecom. EWM Wildera nigdy w pełni nie „zapomina" wczesnych danych i jest kanoniczną formułą ATR. Rozbieżności są największe podczas reżimów zmienności, które mają największy wpływ na wielkość pozycji.

---

## 2. Poprawność Silnika Backtestu (`src/backtest/execution.py`)

### Zachowania poprawne
- **Konflikt SL/TP na tym samym słupku → zawsze SL** (najgorszy przypadek). Udokumentowane i uzasadnione.
- **Strona wypełnienia**: LONG na ASK (`low_ask ≤ entry ≤ high_ask`), SHORT na BID — poprawne.
- **Strona wyjścia**: LONG wychodzi na BID, SHORT wychodzi na ASK — poprawne.
- **Asercja wykonalności wypełnienia**: rzuca `ValueError`, jeśli cena wejścia/wyjścia wykracza poza zakres OHLC świecy — wychwytuje błędy danych na wczesnym etapie.

### Błędy

**🔴 Symbol zakodowany na stałe jako `"EURUSD"` w `_open_position()`**
```python
symbol = "EURUSD"   # linia w ExecutionEngine._open_position
```
Każdy obiekt transakcji zapisuje `symbol="EURUSD"` bez względu na instrument faktycznie testowany. Analiza post-transakcyjna — grupowanie wyników według symbolu, filtrowanie wzorców zysk/strata — jest sfałszowana dla wszystkich instrumentów innych niż EURUSD.

**🔴 Prowizja zakłada 1 standardowy lot niezależnie od wielkości pozycji**
```python
commission = self.config['commission_per_lot']   # np. $7, kwota ryczałtowa
```
Prowizja jest potrącana jako stała kwota niezależnie od rzeczywistej liczby lotów. W przypadku indeksów lub dowolnego uruchomienia z parametrycznym rozmiarem lota, netto PnL na transakcję jest błędne. Gdy `lot_size` wynosi 0,01 (mikro lot), prowizja jest zawyżona 100×; gdy wynosi 10 lotów, jest zaniżona 10×.

**🔴 `raise ValueError` przy zerowej odległości ryzyka przerywa cały backtest**
```python
if risk_distance == 0:
    raise ValueError(...)
```
Pojedyncza świeca z zdegenerowanym kształtem (zerowe ATR przy danych niskiej płynności) niszczy cały przebieg. Powinno to być `continue` (pomijające tę świecę) z ostrzeżeniem w logu, nie twarde przerwanie.

**🟡 PnL skalowane przez `lot_size` zakłada konwencję FX pip**
```python
pnl = realized_distance * lot_size * 100_000
```
Mnożnik `× 100_000` koduje na stałe wielkość kontraktu FX. Dla US100 (USATECHIDXUSD) z `lot_size=1` każdy pip ruchu jest wart $100 000 — bez sensu. Skrypty backtestu indeksowego obchodzą to ignorując kolumnę dolarowego PnL i obliczając drawdown oparty na R bezpośrednio, ale pole `Trade.result` nadal zawiera bezsensowne wartości dla indeksów.

---

## 3. Ryzyko Błędu Lookahead

### `src/indicators/pivots.py` — **POTWIERDZONY lookahead** 🔴

```python
for i in range(lookback, len(df) - lookback):
    # Pivot high używa świec i-lookback … i+lookback (przyszłość)
    if all(high[i] >= high[i-lookback:i]) and \
       all(high[i] >= high[i+1:i+lookback+1]):   # ← przyszłe świece
        highs.append((i, high[i]))
```

Podczas iteracji po świecy `i`, świece `i+1` do `i+lookback` jeszcze nie nastąpiły. Funkcja oznacza `i` jako potwierdzony pivot używając informacji z przyszłości — `lookback` świec lookahead jest wbudowanych w każde wywołanie. Każda strategia używająca tej funkcji „wie" o lokalizacjach pivotów, które nie mogły być znane w czasie rzeczywistym.

**Dotknięte moduły:** `src/backtest/engine.py`, `src/backtest/engine_enhanced.py`, `src/backtest/detect_zones.py`. Wszystkie backtesty routowane przez silnik strefowy zawyżają przewagę.

### `src/structure/pivots.py` — **Anti-lookahead, poprawny** ✅

```python
def detect_pivots_confirmed(df, lookback=3, confirmation_bars=1):
    # Oznacza pivot przy świecy i tylko jeśli i+confirmation_bars już się zamknęła
    # Wywołujący iteruje z current_bar_time; przetwarza tylko świece <= current_bar_time
```

Pivot `i` nie jest oznaczany, dopóki świeca `i + confirmation_bars` się nie zamknie. Używany przez `trend_following_v1.py`.

### `src/structure/bias.py` — **Bezpieczny** ✅

```python
htf_slice = htf_df[htf_df.index <= current_bar_time]
```

Bias HTF jest zawsze obliczany na podzbiorze świec dostępnych *w czasie lub przed* przetwarzaną świecą LTF.

### Macierz podsumowania

| Moduł | Lookahead-safe | Strategia używająca |
|-------|---------------|---------------------|
| `src/structure/pivots.py` | ✅ | `trend_following_v1.py` (backtest), live runner |
| `src/indicators/pivots.py` | ❌ | `engine.py`, `engine_enhanced.py`, `detect_zones.py` |
| `src/structure/bias.py` | ✅ | Oba |

---

## 4. Spójność Logiki Strategii

Live runner (`run_paper_ibkr_gateway.py`) tworzy instancję `TrendFollowingStrategy` z `src/core/strategy.py`. Raporty wydajnościowe zostały wygenerowane przez `run_trend_backtest()` z `src/strategies/trend_following_v1.py`. Te dwie ścieżki kodu dzielą nazwę, ale różnią się w trzech krytycznych kwestiach:

### 4.1 Filtr Biasu HTF — brakuje w strategii live 🔴

`trend_following_v1.py`:
```python
htf_bias = get_htf_bias_at_bar(htf_df, bar_time)
if htf_bias == 0:
    continue   # brak trendu na HTF → bez transakcji
```

`core/strategy.py`: Brak wywołania `get_htf_bias_at_bar`. Każdy BOS wyzwala transakcję niezależnie od kierunku trendu na wyższym timeframie. Filtr HTF jest głównym składnikiem przewagi; bez niego system live będzie wchodzić pod trend, co dane backtestowe pokazują jako znaczące pogorszenie oczekiwanej wartości.

### 4.2 Wykrywanie pivotów — lookahead w strategii live 🔴

`core/strategy.py` używa wewnętrznego `_detect_pivots()`:
```python
for i in range(lookback, len(df) - lookback):
    if all(high_col[i] >= high_col[i+1:i+lookback+1]):  # przyszłe świece
```

To to samo okno lookahead co `src/indicators/pivots.py`. Podczas skanowania danych historycznych przy starcie lub na zreprodukowanej świecy, strategia „widzi" potwierdzenia pivotów niedostępne w produkcji.

### 4.3 Opóźnienie potwierdzenia BOS — słabsze w strategii live 🟡

`_check_bos()` w `core/strategy.py`:
```python
if last_high_idx < current_idx - 2:   # minimalne opóźnienie 2 świece
```

`trend_following_v1.py` używa `detect_pivots_confirmed(..., confirmation_bars=1)`, które zapewnia dokładnie 1 potwierdzoną świecę następczą. Próg 2 świec w `core/strategy.py` nieco bardziej opóźnia wejście, ale bazowe wykrywanie pivotów nadal używa przyszłych świec do *lokalizowania* pivotu, przez co opóźnienie jest częściowo kosmetyczne.

---

## 5. Realizm Modelu Egzekucji

### Model spreadu
Stały `ASK = BID + fixed_spread` przez całą dobę. Realne spready poszerzają się przy otwarciu rynku, wydarzeniach newsowych i podczas niskiej płynności. Dla FX jest to nieznaczne zawyżenie kosztu round-trip; dla US100 przed otwarciem lub po zamknięciu spread jest zaniżony 3–10×.

### Model wypełnień
**Optymistyczny dla zmiennych świec.** Jeśli świeca porusza się o 100 pipsów, a zlecenie limit jest w kolejce, wypełnienie zakłada dokładnie cenę limitową. W rzeczywistości szybki rynek mógłby przeskoczyć przez limit. Zawyża to jakość wypełnień na świecach o dużym ATR.

Brak modelowania częściowych wypełnień (poprawne dla płynnych FX/indeksów przy podanych rozmiarach; staje się niepoprawne przy dużych rozmiarach lotów wobec cienkich arkuszy zleceń).

### Latencja
Przy granularności H1 latencja jest nieistotna dla wykrywania wejść. Jednak `IBKRExecutionEngine` przesyła zlecenia bracket synchronicznie w callbacku; każde opóźnienie > 30 s może oznaczać, że cena przesunęła się przed potwierdzeniem bracketu. Brak zaimplementowanego timeoutu dla wieku kolejki.

### Prowizja (live)
`IBKRExecutionEngine._calculate_units()` wielkości pozycji w **jednostkach** (np. 12 453 jednostki EURUSD), nie w lotach. IBKR pobiera prowizję za akcję/kontrakt/jednostkę. Backtest pobiera ryczałt za lot. Są to strukturalnie niekompatybilne modele, które muszą zostać uzgodnione przed porównaniem kosztów transakcyjnych live vs backtest.

---

## 6. Bezpieczeństwo Potoku Danych

### Mocne strony
- Pliki CSV 1M Dukascopy są w UTC — brak potrzeby konwersji stref czasowych dla FX.
- `resample('1h', closed='left', label='left')` jest poprawne: świeca oznaczona przy otwarciu okresu, OHLC agregowane włącznie.
- HTF pochodne przez resample LTF w backtestach eliminuje rozbieżności timestampów między źródłami.

### Ryzyka

**🟡 Luki weekendowe/świąteczne nie są jawnie obsługiwane**
`resample()` generuje wiersze dla każdego zamkniętego okresu. Weekend z luką nie generuje wiersza (resampler pomija puste okresy z `how='ohlc'`), ale logika wykrywania używa `.shift(1)` dla True Range, która cicho przekroczy lukę i wygeneruje anomalnie dużą wartość TR przy otwarciu niedzielnym 17:00. Brak mechanizmu wykrywania luk.

**🟡 Brak asercji integralności danych**
Brak sprawdzeń `open ≤ high`, `low ≤ open`, `close ≥ low`, spread ≥ 0. Uszkodzony wiersz CSV będzie cicho propagowany przez cały backtest.

**🟡 Stały spread ignoruje dynamikę spreadu śróddziennego**
USATECHIDXUSD ma prawie zerowy spread podczas RTH i szeroki spread przed otwarciem rynku. Użycie stałego spreadu zaniża koszt sygnałów poza godzinami. W połączeniu z filtrem sesji ryzyko jest ograniczone, ale nie wyeliminowane.

**🟢 Bootstrap świec live używa danych midpoint z IBKR**
`ibkr_marketdata.py` stosuje `BOOTSTRAP_HALF_SPREAD` do konwersji midpoint na bid/ask — akceptowalne przybliżenie dla płynnych instrumentów, ale wprowadza sparametryzowaną stałą wymagającą utrzymania.

---

## 7. Jakość Testów

### Obszary dobrze pokryte
- `test_state_store.py` — 15+ testów obejmujących tworzenie schematu, idempotentność migracji, save/load, upsert, przejścia statusów (tylko do przodu), idempotentny `intent_id`, zapytania multi-symbol.
- `test_pivots_no_lookahead.py` — dedykowany test zachowania anti-lookahead `structure/pivots.py`.
- `test_bos_pullback_setup.py` — wykrywanie BOS i cykl życia setupu pullback.
- `test_execution_logic.py` — pokrywa logikę `ExecutionEngine.process_bar()`.

### Krytyczne luki

**🔴 `test_schema_version_is_1` zdefiniowany dwukrotnie**
```python
def test_schema_version_is_1(self, store):
    # ... asercja version == 1

def test_schema_version_is_1(self, store):  # ta sama nazwa: cicho nadpisuje pierwszą
    # ... asercja version == 2
```
Przestrzeń nazw klasy Pythona nadpisuje pierwszą definicję. pytest zbiera tylko drugą. Niezmiennik schematu v1 nigdy nie jest weryfikowany. Należy przemianować pierwszą na `test_schema_version_starts_at_1`.

**🔴 Brak testów dla `src/core/strategy.py` (klasa strategii live)**
Zerowe pokrycie testowe dla `TrendFollowingStrategy`: wykrywanie pivotów, wykrywanie BOS, cykl życia setupu, zastosowanie biasu HTF (którego brakuje, ale powinno być), persystencja stanu. To jest ścieżka kodu, która składa prawdziwe zlecenia.

**🟡 Brak testów dla `IBKRExecutionEngine`**
Brak testów jednostkowych dla wielkości pozycji (`_calculate_units`), logiki trailing stop (`_update_trail_sl`) lub bramki ryzyka (`_check_risk`). Są testowalne bez prawdziwego połączenia z IBKR używając mock obiektu `ib`.

**🟡 Brak testu potwierdzającego zastosowanie filtra biasu HTF przez strategię live**
Ponieważ `core/strategy.py` całkowicie nie posiada filtra HTF, test weryfikujący odrzucenie BOS pod prąd trendu wykryłby tę regresję.

**🟡 Brak testu skalowania prowizji**
Brak testu weryfikującego, że `commission_per_lot` skaluje się z rzeczywistą wielkością pozycji, a nie jest stosowana jako ryczałt.

---

## 8. Ocena Ryzyka Tradingowego

### Ryzyko przetrenowania
Konfiguracja w `DEFAULT_SYMBOLS` (`src/core/config.py`) zawiera specyficzne dla symbolu wartości `adx_h4_gate`, `atr_pct_filter_min/max`, `risk_reward`, `trailing_stop`. Każde nadpisanie per-symbol pochodzi z raportów analizy sesji, które używają tych samych danych historycznych co opracowanie strategii. To jest selekcja parametrów in-sample ubrana w optymalizację — przechodzi walk-forward przez przypadek, bo okna OOS są krótkie (1 rok każde).

### Odporność na reżimy rynkowe
Strategia jest trend-following BOS pullback. 4-letnia próbka (2021–2024) obejmuje odbudowę po COVID, zacieśnianie Fed (2022) i normalizację 2023 — rozsądny przekrój. Jednak:
- Wszystkie testy indeksowe są na jednym instrumencie (USATECHIDXUSD). Wnioski z jednego instrumentu mają wysoką wariancję próbki.
- Kombinacja 5M/4H (najlepszy wynik: Exp=+0.300R, PF=1.39) ma ~1000+ transakcji przez 4 lata — statystycznie znaczące, ale PF=1.39 to niska marża, zanim koszty transakcyjne i poślizg ją erodują.

### Ryzyko rozbieżności live-backtest
Biorąc pod uwagę rozbieżność strategii z §4 (brak filtra HTF, lookahead pivoty), można się spodziewać, że wyniki live będą materialnie różne od raportowanych backtestów. Najbardziej prawdopodobny scenariusz to niższa selektywność (więcej transakcji) z niższym średnim R (sygnały pod prąd trendu wymieszane).

### Kontrola obsunięcia kapitału
- Garda maksymalnego obsunięcia: `max_dd_pct` w `RiskConfig` — funkcjonalna.
- Kill switch: persystowany do DB i odtwarzalny po restarcie — dobry projekt.
- Brak circuit breakera dla kolejnych strat: po 5 SL z rzędu system kontynuuje wielkość z pełnym `risk_fraction`. Reguła chłodzenia zmniejszyłaby ryzyko ogonowe.

---

## 9. Ukryte Ryzyka Techniczne

### 🔴 Stan trailing stop nie jest persystowany — tracony przy restarcie

`IBKRExecutionEngine._records` to słownik w pamięci `Dict[int, _OrderRecord]`. `_OrderRecord` przechowuje:
```python
trail_activated: bool = False
trail_sl: float = 0.0
trail_sl_ibkr_id: int = 0
```

Po restarcie procesu `restore_positions_from_ibkr()` odtwarza `_records` z aktywnych bracketów IBKR. Jednak nie ma wiedzy, czy `trail_activated` było `True` ani jaki był ostatni SL trailowany. Restart podczas gdy zwycięska pozycja jest w trybie trail spowoduje:
1. Użycie oryginalnego `sl_price` z `OrderIntent` jako referencji trailing.
2. Potencjalne umieszczenie stopu **szerszego** niż aktualnie aktywny stop IBKR, jeśli pozycja już się przesunęła — luka ryzyka.

**Naprawa:** Persystować `trail_activated`, `trail_sl`, `trail_sl_ibkr_id` do tabeli `orders` i odtwarzać je w `restore_positions_from_ibkr()`.

### 🔴 Threading SQLite: współdzielone połączenie z autocommit + `check_same_thread=False`

```python
conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
```

`isolation_level=None` ustawia tryb autocommit. Context manager `_tx()` wydaje jawne `BEGIN`/`COMMIT`. Jednak `ib_insync` wyzwala callbacki zamknięcia świec z własnego wątku event loop, który może wywołać `store.save_state()` podczas gdy wątek pętli poll jest w środku transakcji. Tryb WAL SQLite serializuje pisarzy, ale jeśli dwa wątki wydają `BEGIN` i jeden jest w środku zapisu, drugi dostaje `database is locked` — połknięty przez `except Exception` w `_tx()`. Ciche błędy zapisu pozostawiają DB w przestarzałym stanie.

**Naprawa:** Użyć `threading.Lock` do serializacji wszystkich zapisów DB lub otworzyć osobne połączenie na wątek.

### 🔴 `purge_zombie_records()` — heurystyka normalizacji symboli może nie trafić

```python
raw = getattr(p.contract, "localSymbol", "") or getattr(p.contract, "symbol", "")
symbols_with_position.add(raw.replace(".", "").replace("/", "").upper())
```

IBKR zwraca różne formaty `localSymbol` zależnie od tego, czy kontrakt to para walutowa (`EUR.USD`) czy indeks (`USATECHIDXUSD` vs `NQ`). Normalizacja usuwa `.` i `/`, ale nie aliasuje kodów kontraktów IBKR do nazw wewnętrznych symboli używanych w `_records`. Rekord zombie dla `USATECHIDXUSD` może nie pasować do `NQ` lub `NQ MAR25` zwracanego przez IBKR, utrzymując zombie przy życiu i blokując nowe wejścia przez bramkę ryzyka.

### 🟡 Kolizja `client_id` IBKR nie jest wykrywana przy starcie

Brak sprawdzenia, czy `client_id` nie jest już używane przez inne połączenie. Zduplikowane uruchomienie z drugiego terminala cicho rozłączy pierwszą instancję bez zwracania błędu. Gateway IBKR loguje rozłączenie; bot tego nie robi.

### 🟡 `equity_override` cicho kontroluje całe wielkości pozycji

```python
override = getattr(self.risk, "equity_override", 0.0)
if override > 0:
    self._account_equity = float(override)
```

Jeśli `equity_override` jest ustawiony w konfiguracji i saldo rachunku znacznie wzrośnie, wszystkie kolejne rozmiary są oparte na przestarzałej nadpisanej wartości. Brak okresowego uzgodnienia. Dla papierowych rachunków z nierealistycznymi saldami jest to celowe — musi być aktywnie utrzymywane dla żywych rachunków.

### 🟢 `_kill_switch_from_env` dołączony jako atrybut spoza dataclass

```python
config._kill_switch_from_env = kill_switch
```

To jest runtime monkeypatch na dataclassie w stylu frozen. `mypy` oznaczy to jako nieznany atrybut. Runner używa `getattr(config, '_kill_switch_from_env', False)` jako zabezpieczenia — pragmatyczne, ale kruche, jeśli `Config` kiedykolwiek zostanie zafreezeowany przez `@dataclass(frozen=True)`.

---

## 10. Plan Refaktoryzacji

### Krytyczne — naprawić przed zaufaniem wynikom live

| # | Zmiana | Plik | Ryzyko bez naprawy |
|---|--------|------|-------------------|
| C1 | Dodać wywołanie `get_htf_bias_at_bar()` w `TrendFollowingStrategy.on_bar()` | `src/core/strategy.py` | System live handluje pod prąd; rozbieżność live/backtest |
| C2 | Zastąpić `_detect_pivots()` przez `detect_pivots_confirmed()` z `src/structure/pivots.py` | `src/core/strategy.py` | Lookahead w wykrywaniu pivotów live podczas replay przy starcie |
| C3 | Persystować `trail_activated`, `trail_sl` do tabeli `orders`; odtwarzać w `restore_positions_from_ibkr()` | `src/core/state_store.py`, `src/execution/ibkr_exec.py` | Trailing stop poszerzony po restarcie; niekontrolowane ryzyko |
| C4 | Naprawić hardcode `symbol = "EURUSD"` — przekazać rzeczywisty symbol ze słownika zlecenia | `src/backtest/execution.py` | Wszystkie rekordy transakcji non-EURUSD błędnie oznaczone; zepsuta analiza |
| C5 | Skalować prowizję przez rzeczywisty rozmiar pozycji (konwertować wewnętrzne jednostki na loty) | `src/backtest/execution.py` | Koszty transakcyjne systematycznie błędne dla rozmiarów ≠ 1 lot |
| C6 | Naprawić zduplikowaną metodę `test_schema_version_is_1` (przemianować pierwszą na `test_schema_version_starts_at_1`) | `tests/test_state_store.py` | Niezmiennik schematu v1 nigdy nie testowany |

### Średnie — naprawić przed dodawaniem nowych funkcji

| # | Zmiana | Plik |
|---|--------|------|
| M1 | Ujednolicić ATR: wybrać Wilder EWM (`ewm(alpha=1/14, adjust=False)`) i usunąć `rolling(14).mean()` | `src/strategies/trend_following_v1.py` |
| M2 | Wycofać lub usunąć `src/indicators/pivots.py`; skontrolować wszystkich wywołujących i przenieść do `src/structure/pivots.py` | `src/backtest/engine.py`, `engine_enhanced.py`, `detect_zones.py` |
| M3 | Dodać `threading.Lock` wokół wszystkich zapisów SQLite w `SQLiteStateStore` | `src/core/state_store.py` |
| M4 | Zmienić `raise ValueError` przy zerowej odległości ryzyka na `log.warning + continue` | `src/backtest/execution.py` |
| M5 | Dodać mapowanie `localSymbol`→nazwa wewnętrzna w `purge_zombie_records()` | `src/execution/ibkr_exec.py` |
| M6 | Usunąć legacy `src/utils/config.py`; przenieść pozostałe skrypty do `src/core/config.py` | Wszystkie skrypty backtestowe |

### Opcjonalne — jakość kodu i przyszłościowość

| # | Zmiana |
|---|--------|
| O1 | Dodać testy jednostkowe dla `TrendFollowingStrategy.on_bar()` włącznie z odrzucaniem BOS pod prąd HTF |
| O2 | Dodać testy jednostkowe dla `IBKRExecutionEngine._calculate_units()` i `_update_trail_sl()` z mock `ib` |
| O3 | Dodać walidację wejściową w `build_h1_idx.py`/`run_backtest_idx.py` (asercje `open ≤ high`, `low ≤ close`, spread ≥ 0) |
| O4 | Dodać wykrywanie konfliktu `client_id` IBKR przy starcie (`ib.managedAccounts()` zwraca puste przy konflikcie) |
| O5 | Dodać circuit breaker dla kolejnych strat w `RiskConfig` (np. zatrzymanie po N stratach w M świecach) |
| O6 | Przenieść `_kill_switch_from_env` do właściwego pola w `Config` lub `IBKRConfig` |

---

## Tabela Podsumowująca Krytyczne Problemy

| ID | Ważność | Lokalizacja | Opis |
|----|---------|-------------|------|
| C1 | 🔴 Krytyczny | `core/strategy.py` | Brak filtra biasu HTF — live handluje pod prąd |
| C2 | 🔴 Krytyczny | `core/strategy.py` | Lookahead w wykrywaniu pivotów używanym przez strategię live |
| C3 | 🔴 Krytyczny | `ibkr_exec.py`, `state_store.py` | Stan trailing stop tylko w pamięci — tracony przy restarcie |
| C4 | 🔴 Krytyczny | `backtest/execution.py` | `symbol="EURUSD"` zakodowany na stałe dla wszystkich instrumentów |
| C5 | 🔴 Krytyczny | `backtest/execution.py` | Prowizja ryczałtowa ignoruje rzeczywisty rozmiar pozycji |
| C6 | 🔴 Krytyczny | `tests/test_state_store.py` | Zduplikowana metoda wycisza test schematu v1 |
| M1 | 🟡 Średni | `trend_following_v1.py` | ATR używa prostej MA zamiast Wilder EWM |
| M2 | 🟡 Średni | `indicators/pivots.py` | Moduł pivotów z lookahead nie wycofany |
| M3 | 🟡 Średni | `state_store.py` | Threading SQLite: brak blokady zapisu |
| M4 | 🟡 Średni | `backtest/execution.py` | `raise ValueError` przy zerowym ryzyku przerywa cały przebieg |
| M5 | 🟡 Średni | `ibkr_exec.py` | Normalizacja symboli nie działa dla kontraktów indeksowych |

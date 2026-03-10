# BojkoFx — Dokumentacja Architektury i Stanu Projektu

**Data powstania:** 2026-03-03
**Ostatnia aktualizacja:** 2026-03-04
**Wersja:** produkcyjna (paper trading, IBKR)
**Środowisko:** GCP VM `bojkofx-vm` (us-central1-a), Ubuntu 22.04 LTS

---

## 1. Cel projektu

BojkoFx to w pełni automatyczny bot do tradingu algorytmicznego na rynku FX (Forex).
Działa 24/7 na maszynie wirtualnej GCP, łączy się z **Interactive Brokers Gateway** (paper trading),
zbiera dane rynkowe w czasie rzeczywistym i składa zlecenia bracket (entry + TP + SL) na podstawie
strategii BOS (Break of Structure) + Pullback.

Projekt jest w fazie **paper trading** — działa na koncie demo IBKR (konto DUP994821, saldo ~$4.2M).
Cel obecnej fazy: weryfikacja działania systemu w warunkach zbliżonych do realnych (latencja, spread,
odrzucenia zleceń, reconnect) przed ewentualnym przejściem na live.

---

## 2. Architektura — przegląd

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GCP VM (bojkofx-vm)                                │
│                                                                             │
│  ┌─────────────────┐     TCP:4002      ┌───────────────────────────────┐   │
│  │  IB Gateway     │◄──────────────────│  bojkofx (systemd service)    │   │
│  │  (Java, IBC)    │                   │                               │   │
│  │  port 4002      │──── market data ──│  IBKRMarketData               │   │
│  │  paper account  │◄─── orders ───────│  TrendFollowingStrategy       │   │
│  └─────────────────┘                   │  IBKRExecutionEngine          │   │
│                                        └───────────────┬───────────────┘   │
│                                                        │ logs              │
│                                        ┌───────────────▼───────────────┐   │
│  ┌──────────────────────────────────┐  │  logs/                        │   │
│  │  bojkofx-dashboard (systemd)    │  │   paper_trading_ibkr.csv      │   │
│  │  Flask API  port 8080           │◄─│   bojkofx.log                 │   │
│  └──────────────────────────────────┘  │  data/live_bars/SYMBOL.csv   │   │
│                                        └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
         ▲
         │ HTTP (X-API-Key)
         │
┌────────┴──────────────┐
│  Lokalny komputer     │
│  dashboard/index.html │   ← plik HTML otwarty lokalnie w przeglądarce
└───────────────────────┘
```

---

## 3. Struktura katalogów

```
BojkoFx/
├── src/
│   ├── core/
│   │   ├── config.py          # dataclassy konfiguracji (StrategyConfig, RiskConfig, IBKRConfig)
│   │   ├── models.py          # modele danych (Bar, Tick, OrderIntent, Side, ExitReason...)
│   │   ├── strategy.py        # logika strategii (BOS + Pullback)
│   │   └── state_store.py     # trwała persystencja stanu (SQLite WAL)
│   ├── data/
│   │   └── ibkr_marketdata.py # pobieranie danych z IBKR (bootstrap + live ticki)
│   ├── execution/
│   │   └── ibkr_exec.py       # składanie zleceń bracket na IBKR, restore po restarcie
│   ├── reporting/
│   │   └── logger.py          # zapis transakcji do CSV
│   └── runners/
│       └── run_paper_ibkr_gateway.py  # główna pętla bota
├── dashboard/
│   ├── app.py                 # Flask API (backend dashboardu)
│   └── index.html             # frontend dashboardu (otwierany lokalnie)
├── scripts/
│   ├── start-bot.sh           # git pull + clear pyc przed startem bota
│   ├── update_bars_from_ibkr.py  # ręczne uzupełnianie historii barów
│   └── patch_today_bars.py    # uzupełnianie dzisiejszych barów
├── config/
│   ├── config.yaml            # główna konfiguracja strategii i symboli
│   └── ibkr.env               # zmienne środowiskowe (IBKR credentials, klucze API)
├── data/
│   ├── bars_validated/        # zwalidowane dane historyczne H1 (seed)
│   ├── live_bars/             # bary zapisywane przez bota w trakcie działania
│   ├── raw_dl_fx/             # pobrane dane historyczne (m30, m60)
│   └── state/                 # SQLite DB (bojkofx_state.db) — nie commitowane do git
└── tests/
    └── test_state_store.py    # testy jednostkowe SQLiteStateStore (pytest)
└── logs/
    ├── bojkofx.log            # stdout bota (DEBUG/INFO/ERROR)
    ├── paper_trading_ibkr.csv # log wszystkich zleceń i wyjść
    └── dashboard.log          # logi Flask API
```

---

## 4. Przepływ danych — krok po kroku

### 4.1 Uruchomienie bota

```
systemd → start-bot.sh
            ├── git pull origin master   (aktualizacja kodu z GitHub)
            └── find src -name "*.pyc" -delete
         → run_paper_ibkr_gateway.py
            ├── Połączenie z IBKR Gateway (TCP 127.0.0.1:4002)
            ├── Dla każdego symbolu: subscribe_symbol()
            │     ├── reqHistoricalData() → 365 dni H1 MIDPOINT bars
            │     ├── Fallback: CSV z data/bars_validated/ (gdy IBKR HMDS offline)
            │     └── reqMktData() → subskrypcja live bid/ask ticków
            ├── restore_positions_from_ibkr()  ← odbudowa stanu po restarcie
            └── Główna pętla (co 30s)
```

### 4.2 Zbieranie danych rynkowych

```
Live ticki (bid/ask) → _tick_buf[symbol]  (bufor RAM, max 2000 ticków)
                         ↓ co 30s
                     update_bars(symbol)
                         ├── Jeśli minęła godzina → seal H1 bar z ticków
                         ├── Jeśli brak ticków   → forward-fill (last close)
                         ├── Dołącz do h1_bars[symbol] (DataFrame w RAM)
                         ├── Przelicz h4_bars/htf_bars (D1 lub H4)
                         ├── Zapisz 500 ostatnich barów → data/live_bars/SYMBOL.csv
                         └── Wywołaj callback on_h1_bar_close(symbol)
```

### 4.3 Generowanie sygnałów

```
on_h1_bar_close(symbol)
    ↓
session_filter → czy godzina baru jest w oknie handlowym?
    ↓
atr_pct_filter → (opcjonalny, per-symbol) czy bieżąca zmienność jest w zakresie?
    │  Oblicz ATR(14) rolling na (high_bid - low_bid)
    │  window = ostatnie 100 barów ATR (bez NaN)
    │  pct_val = ile % historycznych ATR < bieżący ATR
    │  jeśli pct_val < atr_pct_filter_min lub > atr_pct_filter_max → skip
    │  Aktywny tylko gdy atr_pct_filter_min/max ustawione w config.yaml
    ↓
strategy.process_bar(h1_bars, htf_bars, current_idx)
    ├── Oblicz ATR(14) na close_bid
    ├── Wykryj pivoty (swing high/low, lookback=3 bary LTF)
    ├── Sprawdź BOS (Break of Structure):
    │     ├── Bull BOS: close_bid > ostatni pivot high
    │     └── Bear BOS: close_bid < ostatni pivot low
    └── Jeśli BOS wykryty → utwórz OrderIntent:
          ├── entry_price = bos_level ± (entry_offset_atr_mult × ATR)  [0.3 × ATR]
          ├── sl_price    = ostatni pivot low/high ± (sl_buffer_atr_mult × ATR)  [0.1 × ATR]
          ├── tp_price    = entry ± (risk_reward × |entry - sl|)  [RR = 3.0]
          ├── entry_type  = LIMIT
          └── ttl_bars    = 50  (GTD: zlecenie wygasa po 50 barach H1)
```

### 4.4 Składanie zleceń

```
execute_intent(intent)
    ├── _check_risk()  → max 3 pozycje łącznie, max 1 na symbol
    ├── _calculate_units()  → risk_first: equity × 0.5% / stop_distance
    │     (tryb: risk.sizing_mode w config.yaml; domyślnie "risk_first" od 2026-03-04)
    ├── _round_price()  → zaokrąglenie do IBKR tick size
    │     ├── JPY pairs (USDJPY, AUDJPY, CADJPY, EURJPY...): 0.005
    │     └── inne (EURUSD, USDCHF...): 0.00005
    └── _place_limit_bracket(intent, units)
          ├── LimitOrder (parent, transmit=False, GTD)
          │     └── czekaj na status Submitted/PreSubmitted (max 4s)
          ├── LimitOrder TP (child, transmit=False, GTC)
          │     └── sleep(0.5s)
          └── StopOrder  SL (child, transmit=True,  GTC)
                └── sleep(0.5s)
                    → IBKR zatwierdza cały bracket atomowo
```

**Ważne:** Po złożeniu zlecenia TP i SL **żyją na serwerze IBKR** niezależnie od bota.
Jeśli bot padnie — IBKR automatycznie wykona TP lub SL gdy cena dotrze do poziomu.

### 4.5 Odbudowa stanu po restarcie

```
restore_positions_from_ibkr(known_symbols)
    ├── ib.trades()     → wszystkie otwarte zlecenia na IBKR
    ├── ib.positions()  → wypełnione pozycje
    ├── Grupuj po parentId → bracket {parent, tp, sl}
    └── Odbuduj _records[parent_id] = _OrderRecord
          ├── Jeśli pozycja otwarta → status "Filled/Restored"
          └── Jeśli zlecenie pending → status "Pending/Restored"
    → Risk gate wie o istniejących pozycjach
    → poll_order_events() śledzi wyjścia
```

---

## 5. Strategia — BOS + Pullback

### 5.1 Idea

Strategia trend-following bazuje na **Strukturze Rynku** (Market Structure).
Sygnał generowany jest gdy cena **przebija ostatni swing** (Break of Structure),
a wejście realizowane jest **limitowanie przy powrocie** do przełamanego poziomu.

```
           Pivot High ─────────────┐
                                   │  BOS (close > pivot high)
                                   ▼
           ──────────────────────────►  cena
                           ↑
                     entry (limit)
                     = bos_level + 0.3 × ATR
                           │
                    SL = last pivot low - 0.1 × ATR
                           │
                    TP = entry + 3.0 × (entry - SL)   → RR = 3:1
```

### 5.2 Parametry strategii (config.yaml)

| Parametr | Wartość | Opis |
|---|---|---|
| `entry_offset_atr_mult` | 0.3 | Offset wejścia od BOS level (× ATR) |
| `pullback_max_bars` | 50 | TTL zlecenia limit (bary H1) |
| `risk_reward` | 3.0 | Stosunek TP:SL |
| `sl_anchor` | `last_pivot` | SL zakotwiczony w ostatnim pivocie |
| `sl_buffer_atr_mult` | 0.1 | Bufor SL powyżej/poniżej pivota (× ATR) |
| `pivot_lookback_ltf` | 3 | Lookback dla wykrycia pivotów (LTF) |
| `confirmation_bars` | 1 | Liczba barów potwierdzenia BOS |

### 5.3 Timeframe

- **LTF (Lower Time Frame):** H1 — sygnały i wejścia
- **HTF (Higher Time Frame):** D1 — kontekst trendu (używany przez strategię)

### 5.4 Filtr sesji

Każda para walutowa ma skonfigurowane okno handlowe UTC w którym bot może otwierać pozycje.
Pozycje otwarte poza sesją NIE są zamykane — tylko nowe wejścia są blokowane.

| Symbol | Sesja UTC | Uzasadnienie |
|---|---|---|
| EURUSD | 08:00–21:00 | Londyn + NY, Azja marginalna (+0.14R) |
| USDJPY | 00:00–24:00 | Każda sesja pozytywna, brak filtra |
| USDCHF | 08:00–21:00 | Poza sesją bardzo zły wynik (-0.36R) |
| AUDJPY | 00:00–21:00 | Azja aktywna (+0.45R), Off-hours ujemny |
| CADJPY | 00:00–24:00 | Różnica sesji <0.03R, brak filtra |

### 5.5 Filtr ATR percentile (od 2026-03-04)

Opcjonalny filtr zmienności per-symbol. Odrzuca sygnały gdy bieżący ATR(14)
wypada poza zdefiniowanym przedziałem percentylowym 100-barowej historii ATR.

**Aktywny tylko dla CADJPY** (`atr_pct_filter_min: 10`, `atr_pct_filter_max: 80`).
Pozostałe pary: `None` = filtr wyłączony.

```
ATR(14)_current = średnia krocząca (high_bid - low_bid), okno 14
window          = ostatnie 100 wartości ATR (bez NaN)
pct_val         = % wartości w window < ATR_current  (0–100)

jeśli pct_val < 10  → zmienność za niska (konsolidacja) → skip
jeśli pct_val > 80  → zmienność za wysoka (spike)       → skip
10 ≤ pct_val ≤ 80  → normalna zmienność                → kontynuuj
```

Log przy blokowaniu: `[ATR_FILTER] CADJPY skipped — ATR pct=87.3 outside [10, 80]`
Log przy przepuszczaniu: `CADJPY ATR filter: pct=45.2 in [10, 80] — OK` (DEBUG)

**Wyniki backtestów (9-fold walk-forward 2021–2025):**

| Symbol | ExpR baseline | ExpR z filtrem 10–80 | Delta |
|---|---|---|---|
| **CADJPY** | +0.001R | **+0.247R** | **+0.245R** ✅ |
| EURUSD | +0.402R | +0.208R | -0.194R ❌ |
| USDJPY | +0.346R | +0.142R | -0.204R ❌ |

Wniosek: filtr naprawia CADJPY (wiele sygnałów przy złej zmienności), ale szkodzi
parom EURUSD/USDJPY gdzie sygnały są dobre niezależnie od ATR percentyla.

**Konfiguracja w `config.yaml`:**
```yaml
symbols:
  CADJPY:
    atr_pct_filter_min: 10   # percentyl dolny (pomiń niską zmienność)
    atr_pct_filter_max: 80   # percentyl górny (pomiń spike)
  EURUSD:
    # brak pól atr_pct_filter → filtr wyłączony (None)
```

**Dodanie filtra dla nowej pary:**
```yaml
  NOWA_PARA:
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
    # ... pozostałe pola
```

---

### 5.6 Filtr H4 ADX gate (od 2026-03-04, Priorytet 3)

Opcjonalny filtr siły trendu per-symbol. Odrzuca sygnały BOS gdy ADX(14) na H4
jest poniżej progu — wskazując na brak wyraźnego trendu.

**Aktywny dla EURUSD/USDJPY/USDCHF/AUDJPY** (`adx_h4_gate: 16`).
**CADJPY: wyłączony** (`adx_h4_gate: null`) — ATR filtr 10–80 jest wystarczający
i lepszy dla tej pary; dodanie H4 ADX gate niszczyłoby wyniki (−24% ExpR, overfit Δ=−0.114R).

```
H4 bars       = resample H1 → 4h (tylko zamknięte bary <= bar_ts - 4h)
ADX(14)_H4    = Wilder smoothed ADX z 14 barów H4
threshold     = adx_h4_gate z config.yaml (np. 16.0)

jeśli ADX_H4 < threshold → trend zbyt słaby → [ADX_H4] skip
jeśli ADX_H4 >= threshold → trend wystarczający → kontynuuj
```

**No-lookahead:** ostatni H4 bar brany pod uwagę to `floor(bar_ts, 4h) - 4h`
(bar który został już zamknięty przed bieżącym H1 barem).

Log przy blokowaniu: `[ADX_H4] EURUSD skipped — ADX(H4)=13.2 < 16`
Log przy przepuszczaniu: DEBUG `EURUSD H4 ADX gate: ADX=22.1 >= 16 — OK`

**Wyniki backtestów ADX v2 (9-fold walk-forward 2021–2025, 5 symboli):**

| Konfiguracja | Val ExpR | Test ExpR | Δ | Wniosek |
|---|---|---|---|---|
| Baseline (brak ADX) | +0.116R | — | — | punkt odniesienia |
| ADX v1 (D1 thr=25) | +0.092R | — | — | −20% vs baseline ❌ |
| **H4 thr=16 (ctxA)** | **+0.179R** | **+0.187R** | **+0.007R** | **+55% vs baseline ✅** |
| H4 thr=16 + CADJPY | +0.188R→**+0.247R** (CADJPY) | | Δ=−0.114R CADJPY ❌ | CADJPY: nie stosować |

**Konfiguracja w `config.yaml`:**
```yaml
symbols:
  EURUSD:
    adx_h4_gate: 16    # ADX(H4) >= 16 wymagane
  USDJPY:
    adx_h4_gate: 16
  USDCHF:
    adx_h4_gate: 16
  AUDJPY:
    adx_h4_gate: 16
  CADJPY:
    # adx_h4_gate: brak/null — wyłączony, ATR filtr wystarczy
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
```

**Szczegółowy raport:** `backtests/outputs/adx_v2_report.md` (sekcja 6: analiza CADJPY)

---

## 6. Zarządzanie ryzykiem

### 6.1 Limity pozycji

| Parametr | Wartość |
|---|---|
| Max pozycji łącznie | 3 |
| Max pozycji na symbol | 1 |
| Tryb pozycjonowania | `risk_first` (od 2026-03-04) |
| Ryzyko na transakcję | 0.5% equity |
| Kill switch DD | 10% od peak equity |
| Daily loss limit | 2% equity |
| Monthly DD stop | 15% equity |

### 6.2 Rozmiar pozycji

**Tryb aktywny: `risk_first` (od 2026-03-04)**

```python
# risk_first — domyślny, rekomendowany
max_risk = equity × 0.005          # 0.5% equity per trade
units    = int(max_risk / stop_distance)

# Przykład: equity=$4M, stop=20 pipsów (EURUSD, pip=0.0001)
# max_risk = 4_000_000 × 0.005 = $20_000
# units    = 20_000 / 0.0020 = 10_000_000  (10M units EURUSD)
```

Poprzedni tryb (`fixed_units`, do 2026-03-04):
```python
# fixed_units — legacy, zachowany jako fallback
default_units = 5000
implied_risk  = stop_distance × 5000
if implied_risk > max_risk:
    units = int(max_risk / stop_distance)   # scale down
else:
    units = 5000                            # zawsze 5000 gdy ryzyko OK
```

Konfiguracja w `config.yaml`:
```yaml
risk:
  sizing_mode: "risk_first"   # "risk_first" | "fixed_units"
  risk_fraction_start: 0.005  # 0.5% equity per trade
  default_units: 5000         # używane tylko gdy sizing_mode: fixed_units
```

Wyniki backtestów (9-foldowa walk-forward, 2021–2025):

| Tryb | ExpR | DD% equity | Stabilność kw. |
|---|---|---|---|
| fixed_units | 0.1156 R | ~430%* | 33% |
| **risk_first** | **0.1156 R** | **~8.3%** | **61%** |

*\*artefakt — DD przy fixed_units liczony jako % wartości pozycji, nie equity*

### 6.3 Kill Switch

Automatycznie aktywowany gdy drawdown od peak_equity ≥ 10%.
Po aktywacji wszystkie nowe zlecenia są blokowane.
Można ustawić ręcznie przez `KILL_SWITCH=true` w `ibkr.env`.

---

## 7. Infrastruktura GCP

### 7.1 Maszyna wirtualna

| Parametr | Wartość |
|---|---|
| Nazwa | `bojkofx-vm` |
| Strefa | `us-central1-a` |
| Typ | `e2-small` (2 vCPU, 2GB RAM) |
| OS | Ubuntu 22.04 LTS |
| Dysk | 20GB SSD (pd-ssd) |
| IP zewnętrzne | `34.31.64.224` (statyczne) |
| Projekt GCP | `sandbox-439719` |

### 7.2 Usługi systemd

```
ibgateway.service     → IB Gateway (Java/IBC) — auto-start, restart on failure
bojkofx.service       → Bot (Python) — zależy od ibgateway, restart co 60s
bojkofx-dashboard.service → Flask API dashboardu — port 8080
```

### 7.3 Połączenie SSH

```bash
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719

# lub bezpośrednio:
ssh -i ~/.ssh/google_compute_engine macie@34.31.64.224
```

### 7.4 IBC (Interactive Brokers Controller)

IBC automatycznie loguje się do IB Gateway przy starcie, akceptuje dialogi i utrzymuje sesję.
Konfiguracja: `/opt/ibc/config.ini`

```ini
ExistingSessionDetectedAction=primary   # przejęcie sesji od konkurujących klientów
AcceptIncomingConnectionAction=accept   # akceptacja połączeń API
TradingMode=paper
```

**Uwaga:** `primary` nie działa dla IBKR Mobile / WebPortal — w razie Error 10197
(no market data, competing session) należy ręcznie wylogować się z IBKR Mobile.

---

## 8. Bezpieczeństwo zleceń

### 8.1 Bracket order (atomowy)

```
parent (LIMIT, transmit=False, GTD)
  ├── tp_order (LIMIT, transmit=False, GTC, parentId=parent)
  └── sl_order (STOP,  transmit=True,  GTC, parentId=parent)  ← wyzwala cały bracket
```

Przy składaniu bot:
1. Wysyła parent order z `transmit=False`
2. Czeka na status `Submitted/PreSubmitted` na serwerze IBKR (max 4s)
3. Wysyła TP z `transmit=False`
4. Wysyła SL z `transmit=True` → IBKR aktywuje cały bracket

### 8.2 Zaokrąglenie cen (tick size)

Przed wysłaniem zlecenia ceny są zaokrąglane do IBKR minimum price variation:

| Grupo symboli | Tick size |
|---|---|
| JPY pairs (USDJPY, AUDJPY, CADJPY...) | 0.005 |
| Pozostałe (EURUSD, USDCHF...) | 0.00005 |

Brak zaokrąglenia powoduje `Warning 110` → parent order utknięty w `PendingSubmit` → Error 135 na child orders.

### 8.3 Bramy bezpieczeństwa (wszystkie 3 muszą być aktywne)

```
IBKR_READONLY=false       +
ALLOW_LIVE_ORDERS=true    +
kill_switch_active=False
→ dopiero wtedy zlecenie trafia do IBKR
```

W każdym innym stanie bot loguje `[DRY_RUN]` i nie wysyła niczego do IBKR.

---

## 9. Dashboard

### 9.1 Backend (Flask API)

Plik: `/home/macie/bojkofx/app/dashboard/app.py`
Port: `8080`, host: `0.0.0.0`
Auth: nagłówek `X-API-Key` (klucz w `ibkr.env`)

| Endpoint | Opis |
|---|---|
| `GET /api/health` | Liveness check (bez auth) |
| `GET /api/status` | Status bota, portfolio, pozycje per symbol |
| `GET /api/equity_history` | Historia equity z CSV |
| `GET /api/candles/<symbol>` | Świece OHLC (ostatnie 72 bary H1) |
| `GET /api/trades/<symbol>` | Historia zamkniętych transakcji |

### 9.2 Frontend (lokalny)

Plik: `dashboard/index.html` — otwierany lokalnie w przeglądarce (`file://`)
Odpytuje API co 60 sekund.
Wyświetla: equity curve, świece z poziomami SL/TP, tabelę transakcji, status bota.

### 9.3 Uruchomienie dashboardu lokalnie

```bash
# Na lokalnym komputerze (Windows):
python dashboard/serve.py   # serwer lokalny na porcie 8890
# lub otwórz bezpośrednio: dashboard/index.html w przeglądarce
```

---

## 10. Przeprowadzone testy i selekcja par

### 10.1 Proces selekcji

1. **Grid backtest** — siatka parametrów na danych historycznych 2021–2024
2. **Walk-forward validation** — podział na kwartały OOS (Q1–Q4 2024)
3. **OOS 2025** — walidacja na danych 2025 (out-of-sample)

### 10.2 Wyniki — ranking par (OOS 2024/2025)

| Para | Kwartały pozytywne | ExpR | PF | Uwagi |
|---|---|---|---|---|
| **AUDJPY** | 8/8 ✅ | +0.61R | 2.10 | Jedyna para z idealnym wynikiem |
| **USDJPY** | 7/8 | +0.73R | 1.95 | Najwyższy ExpR, DD tylko 4% |
| **USDCHF** | 7/8 | +0.58R | 1.90 | HTF=D1 lepszy niż H4 |
| **EURUSD** | 7/8 | +0.52R | 1.78 | Q4-2024 wyjątkowo silny |
| **CADJPY** | 6/8 | +0.44R | 1.65 | Accelerating w 2024 |

### 10.3 Kluczowe odkrycia z testów

- **HTF D1 > H4** dla USDCHF (OOS 2025: H4=-0.08R vs D1=+0.30R)
- **Filtr sesji** poprawia wyniki o ~0.2–0.4R dla par EUR/CHF
- **Para AUDJPY** najstabilniejsza — 100% kwartałów pozytywnych
- **Pary JPY** dobrze działają w sesji azjatyckiej (AUDJPY, CADJPY)

---

## 11. Znane problemy i rozwiązania

| Problem | Przyczyna | Rozwiązanie |
|---|---|---|
| Error 135 (child orders anulowane) | `Warning 110` — zła precyzja ceny → parent w PendingSubmit | `_round_price()` zaokrągla do IBKR tick size |
| Error 10197 (no market data) | Konkurująca sesja IBKR Mobile/WebPortal | Wyloguj się z IBKR Mobile przed uruchomieniem bota |
| Bot nie wie o pozycji po restarcie | Stan w RAM, nie persystowany | `restore_positions_from_ibkr()` przy każdym starcie |
| `Permission denied` na logach | Plik logów należał do root po restart | `chown macie:macie` w ExecStartPre |
| 0 ticks in buffer | Stale feed / reconnect | Auto-resubskrypcja po 300s bez ticków |
| Forward-fill barów | Bot offline przez całą godzinę | Akceptowalne — bar zapisany jako last close |

---

## 12. Operacje — codzienne

### 12.1 Sprawdzenie statusu

```bash
# Z lokalnego komputera Windows:
status.cmd

# Lub przez SSH:
ssh -i ~/.ssh/google_compute_engine macie@34.31.64.224 \
  "systemctl is-active bojkofx && systemctl is-active ibgateway && \
   tail -5 /home/macie/bojkofx/logs/bojkofx.log"
```

### 12.2 Restart bota

```bash
ssh macie@34.31.64.224 "sudo systemctl restart bojkofx"
```

### 12.3 Restart Gateway (gdy brak danych rynkowych)

```bash
ssh macie@34.31.64.224 "sudo systemctl restart ibgateway"
# Poczekaj ~2 minuty na login przez IBC
```

### 12.4 Logi

```
/home/macie/bojkofx/logs/
  bojkofx.log              # główny log bota (DEBUG/INFO/ERROR)
  paper_trading_ibkr.csv   # wszystkie transakcje
  gateway.log              # log IB Gateway / IBC
  dashboard.log            # log Flask API
```

### 12.5 Diagnostyka DB — ostatnie 20 eventów

```bash
ssh macie@34.31.64.224 "sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  'SELECT ts_utc, event_type, payload_json FROM events ORDER BY id DESC LIMIT 20;'"
```

Przydatne gdy chcesz zobaczyć ostatnie sygnały BOS, fille, exity i starty bota
bez przeglądania całego `bojkofx.log`.

### 12.6 Diagnostyka DB — pending/sent orders

```bash
ssh macie@34.31.64.224 "sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  'SELECT symbol, parent_id, status, updated_at FROM orders
   WHERE status IN (\"PENDING\",\"SENT\",\"CREATED\")
   ORDER BY updated_at DESC;'"
```

Zwraca zlecenia oczekujące na IBKR. Jeśli status `PENDING` jest stary (>2h),
a bota zrestartowałeś — merge przy starcie powinien był oznaczyć je `EXPIRED`.
Jeśli nie — sprawdź logi z ostatniego startu (`STARTUP_MERGE_SUMMARY` event).

---

## 13. Zmienne środowiskowe (`ibkr.env`)

```bash
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=7
IBKR_READONLY=false
ALLOW_LIVE_ORDERS=true
KILL_SWITCH=false
IB_USERNAME=<login>
IB_PASSWORD=<hasło>
DASHBOARD_API_KEY=<klucz hex 32 znaki>
DASHBOARD_PORT=8080
```

---

## 14. Zależności Python

```
ib_insync       # IBKR API wrapper
pandas          # przetwarzanie danych
numpy           # obliczenia numeryczne
flask           # dashboard API
flask-cors      # CORS dla lokalnego frontend
pyyaml          # parsowanie config.yaml
```

---

## 15. Historia kluczowych zmian

| Data | Zmiana |
|---|---|
| 2026-02-22 | Start projektu, migracja z Binance na IBKR |
| 2026-02-23 | Wdrożenie na GCP VM, konfiguracja IB Gateway + IBC |
| 2026-02-27 | Auto-reconnect + startup seal |
| 2026-03-01 | Selekcja par walutowych (grid + walk-forward) |
| 2026-03-01 | Dashboard (Flask API + lokalny HTML) |
| 2026-03-02 | Filtr sesji per para, konfiguracja HTF D1 |
| 2026-03-03 | Fix Error 135 (tick size rounding) |
| 2026-03-03 | Fix Error 10197 (competing session) |
| 2026-03-03 | `restore_positions_from_ibkr()` — odbudowa stanu po restarcie |
| 2026-03-03 | SQLite WAL state persistence — `state_store.py` |
| 2026-03-04 | **Priorytet 1: `risk_first` sizing** — `sizing_mode: risk_first` globalnie (0.5% equity / stop_dist); DD ~8% equity zamiast artefaktowego 430%; backtesty: ExpR bez zmian (0.1156R), stabilność kw. +31pp |
| 2026-03-04 | Fix `restore_positions_from_ibkr` — brakujący `timestamp` w `OrderIntent` powodował błąd przy starcie gdy IBKR miał otwarte zlecenia |
| 2026-03-04 | **Priorytet 2: ATR percentile filter dla CADJPY** — `atr_pct_filter_min: 10`, `atr_pct_filter_max: 80`; nowe pola `SymbolConfig`; logika filtra w runnerze między session filter a strategy; backtesty: CADJPY +0.245R delta |
| 2026-03-04 | **Priorytet 3: H4 ADX gate thr=16** — `adx_h4_gate: 16` dla EURUSD/USDJPY/USDCHF/AUDJPY; CADJPY wyłączony (ATR filtr wystarczy, H4 ADX niszczyłby −24%); `SymbolConfig.adx_h4_gate`; blok filtra w runnerze po ATR filter; backtesty: +0.179R vs +0.116R baseline (+55%), Δ=+0.007R |

---

## 16. Persystencja stanu — SQLite WAL

### 16.1 Cel

Bot przechowywał dotychczas cały stan w RAM. Po restarcie tracił kontekst:
pivoty/BOS, otwarte zlecenia, peak equity. Nowy moduł `src/core/state_store.py`
zapisuje stan do lokalnego SQLite z trybem WAL (crash-safe) na VM.

### 16.2 Lokalizacja pliku i inicjalizacja

```
data/state/bojkofx_state.db    ← domyslnie (nie commitowane do git)
```

Nadpisanie sciezki: `STATE_DB_PATH=/inna/sciezka.db` w srodowisku.

**Kto tworzy DB i kiedy:**
`SQLiteStateStore.__init__()` tworzy katalog `data/state/` i plik DB przy
pierwszym uruchomieniu. Wywolywane jest to w `run_paper_ibkr_gateway.py`
**przed** subskrypcja symboli — migracje sa zawsze aktualne zanim cokolwiek
trafi do bazy.

Sekwencja w runnerze:
```
1. store = SQLiteStateStore(db_path)   <- tworzy plik jesli nie istnieje
2. store.migrate()                     <- tworzy tabele / aktualizuje schemat
3. risk_state = store.load_risk_state()
4. ... polaczenie z IBKR, subscribe ...
5. store.merge_ibkr_state(brackets)   <- reconciliation
```

**Diagnostyka WAL na VM:**
```bash
# Tryb WAL (powinno zwrocic: wal)
sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  "PRAGMA journal_mode;"

# Poziom synchronizacji (powinno zwrocic: 1 = NORMAL)
sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  "PRAGMA synchronous;"

# Wersja schematu (powinno zwrocic: 2)
sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  "SELECT version FROM schema_version;"
```

Obecnosc pliku `bojkofx_state.db-wal` potwierdza aktywny WAL.
Plik znika po zamknieciu polaczenia (checkpoint).

### 16.3 Schemat bazy (v2)

```
schema_version       version: 2

strategy_state       symbol PK | last_processed_bar_ts | last_pivot_high_json
                     last_pivot_low_json | last_bos_json | updated_at

orders               id AUTOINCREMENT PK | parent_id (IBKR) | intent_id UNIQUE
                     symbol | intent_json | status | ibkr_ids_json
                     created_at | updated_at

risk_state           key PK | value_json | updated_at
                     (peak_equity, kill_switch_active, daily_loss_used, ...)

events               id AUTOINCREMENT | ts_utc | event_type | payload_json
                     (append-only audit log)
```

### 16.4 Statusy zlecen i dozwolone przejscia

```
CREATED -> SENT -> PENDING -> FILLED -> EXITED
               \           \
            CANCELLED   CANCELLED / EXPIRED
RESTORED_UNKNOWN    (znalezione na IBKR, brak w DB)
```

**Dozwolone przejscia (rank tylko rosnie):**

| Od        | Do                          | Kiedy                                         |
|-----------|-----------------------------|-----------------------------------------------|
| CREATED   | SENT                        | bracket wyslany do IBKR                       |
| SENT      | PENDING / CANCELLED         | IBKR potwierdzil / odrzucil parent order      |
| PENDING   | FILLED / CANCELLED / EXPIRED| entry wypelniony / anulowany / GTD wygasl     |
| FILLED    | EXITED                      | TP lub SL trafiony                            |

Status przesuwa sie **tylko do przodu** — `upsert_order()` ignoruje probe
zmiany z wyzszego rank na nizszy. Przy konflikcie miedzy DB a IBKR,
**IBKR jest source-of-truth** dla rzeczywistego statusu zlecenia;
DB jest source-of-truth dla intentu, TTL i kontekstu strategii.

### 16.5 Idempotencja — `intent_id`

```python
intent_id = sha1(f"{symbol}|{side}|{bos_level:.8f}|{bos_bar_ts}")
```

Ten sam BOS na tym samym barze — ten sam `intent_id` — `UNIQUE` constraint
w DB blokuje powtorne zlozenie zlecenia po restarcie bota.

**Deterministycznosc `bos_level`:**
`bos_level` jest wartoscia `last_pivot_high/low` z surowych danych bid/ask —
**nie jest zaokraglany do IBKR tick size** przed wyliczeniem hash.
Zaokraglenie do tick size stosowane jest dopiero w `_round_price()` przy
wysylaniu zlecenia. Dzieki temu ten sam BOS zawsze daje ten sam hash,
niezaleznie od pary walutowej czy precyzji tick size.

### 16.6 Startup merge (reconciliation)

Przy kazdym starcie bota:

```
IBKR ib.trades()  <-- source-of-truth dla statusu zlecen
DB orders         <-- source-of-truth dla intentow, TTL, kontekstu strategii

Merge logic:
  DB PENDING/SENT + brak na IBKR  -> DB: EXPIRED  + event ORDER_EXPIRED
  IBKR order  + brak w DB         -> DB: RESTORED_UNKNOWN + event RESTORED_FROM_IBKR
  Oba istnieja                    -> DB: aktualizacja statusu z IBKR
```

**Rozroznienie CANCELLED vs EXPIRED:**
Gdy DB ma zlecenie w statusie PENDING/SENT, a IBKR go nie zwraca, merge
oznacza je jako `EXPIRED` (jeden kod sciezki dla obu przypadkow).
Jesli w przyszlosci potrzebne rozroznienie: porownaj `created_at + ttl_bars * 3600s`
z aktualnym UTC — jesli TTL jeszcze nie minal, to byl to reczny cancel
(`CANCELLED`); jesli minal — `EXPIRED`.

### 16.7 Cykl zapisu per H1 bar

```
update_bars() -> sealed H1 bar
    +-- Sprawdz DB: last_processed_bar_ts
    |     jesli bar_ts <= last_processed -> skip (nie wywoluj strategii ponownie)
    +-- on_h1_bar_close(symbol) -> strategy.process_bar()
    |     +-- BOS wykryty -> DB: save_strategy_state() (pivot/BOS)
    |     +-- intent_id check -> skip jesli juz w DB
    |     +-- append_event("INTENT_CREATED", ...)
    +-- DB: update last_processed_bar_ts
```

### 16.8 Retencja i backup DB

Tabela `events` jest **append-only** — kazdy sygnal, fill, exit i restart
zapisuje nowy wiersz. Przy ciaglym dzialaniu rosnie ~10-50 wierszy/dzien.

**Polityka retencji (zalecana):**
Przechowuj `events` przez minimum **90 dni**. Po tym czasie archiwizuj
lub usun stare wiersze:
```bash
sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  "DELETE FROM events WHERE ts_utc < datetime('now', '-90 days');"
```

**Backup DB:**
```bash
# Backup przy uruchomionym bocie (bezpieczny dzieki WAL)
sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  ".backup '/home/macie/bojkofx/app/data/state/bojkofx_state.db.bak'"

# Backup przez kopiowanie (tylko przy zatrzymanym serwisie)
sudo systemctl stop bojkofx
cp data/state/bojkofx_state.db data/state/bojkofx_state.$(date +%Y%m%d).db
sudo systemctl start bojkofx
```

Zalecany backup automatyczny raz dziennie przez cron:
```bash
# crontab -e
0 2 * * * sqlite3 /home/macie/bojkofx/app/data/state/bojkofx_state.db \
  ".backup '/home/macie/bojkofx/app/data/state/bojkofx_state.db.bak'"
```

### 16.9 Uruchomienie testów

```bash
pytest tests/test_state_store.py -v
# 26 passed -- migracje, strategy state, orders, risk, events, merge

pytest tests_backtests/test_engine_fill_logic.py -v
# 25 passed -- fill logic, calc_units (risk_first/fixed), session filter, portfolio

pytest tests_backtests/test_indicators_adx_atr.py -v
# testy ATR, ADX, rolling percentile
```

---

## 17. Badania — wyniki testów i porównanie z produkcją

### 17.1 Pipeline badawczy

Katalog `backtests/` zawiera kompletny pipeline eksperymentów:

```
backtests/
├── config_backtest.yaml     # konfiguracja eksperymentów
├── run_experiments.py       # CLI: --stage1-only lub pełny Stage1+2
├── engine.py                # symulator portfolio (fill logic, TTL, constraints)
├── signals_bos_pullback.py  # generowanie setupów BOS/pivot
├── indicators.py            # ATR, ADX, rolling percentile
├── experiments.py           # generator siatki Stage1 + Stage2
├── metrics.py               # ExpR, PF, win rate, DD%, stabilność kw.
├── reporting.py             # eksport CSV + Markdown
└── outputs/
    ├── RESEARCH_SUMMARY.md  # dokumentacja zbiorcza wyników
    ├── comparison_report.md # baseline vs atr_10_80 vs Opcja C
    └── report.md            # pełny raport techniczny Stage1+2
```

Uruchomienie:
```bash
python -m backtests.run_experiments --config backtests/config_backtest.yaml
python -m backtests.run_experiments --config backtests/config_backtest.yaml --stage1-only
```

### 17.2 Metodologia

- **Dane:** H1 bid OHLC 2021–2025, 5 symboli (EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY)
- **HTF D1:** resample H1 → D1
- **Foldy:** 1 historyczny (2021–2022 train / 2023 val / 2024–2025 test) + 8 kwartalnych OOS (Q1–Q4 2024/2025)
- **Łącznie:** 9 foldów × 5 symboli = 45 zestawów wyników na konfigurację
- **Fill logic:** conservative (gdy SL i TP w tym samym barze → SL wins)

### 17.3 Wyniki baseline (konfiguracja produkcyjna)

| Metryka | Wartość |
|---|---|
| ExpR per trade (avg 9 foldów) | **0.1156 R** |
| Profit Factor | 1.256 |
| Win Rate | 27.9% |
| Stabilność (% pos. kwartałów) | 33% |
| Max DD% (fixed units, artefakt) | 430%* |
| Trades (9 foldów łącznie) | 13 937 |

*\*DD% przy fixed units = DD jako % wartości pozycji, nie equity. Niemierzalne.*

**Rozkład kwartalny:**

| Kwartał | ExpR | Wynik |
|---|---|---|
| Q1–Q4 2024 | +0.26R … +0.54R | ✅ wszystkie pozytywne |
| Q1 2025 | **-0.247R** | ❌ najgorszy kwartal |
| Q2–Q4 2025 | -0.09R … +0.04R | ⚠️ słabe / breakeven |

Obserwacja: 2024 był bardzo dobry. Od Q1 2025 wyraźne pogorszenie —
sugeruje zmianę reżimu rynkowego.

### 17.4 Przetestowane moduły

#### A) ADX gate — ❌ nie rekomendowany

| Konfiguracja | ExpR | vs Baseline |
|---|---|---|
| adx25 | 0.0920 | -20% |
| adx22 | 0.0396 | -66% |
| adx20 | 0.0458 | -60% |
| adx18 | 0.0626 | -46% |

Każdy próg ADX obniża ExpR — filtr trend-following szkodzi strategii BOS.

#### B) ATR percentile filter — ✅ rekomendowany selektywnie

| Konfiguracja | ExpR val | ExpR test | Delta val→test | Stabilność |
|---|---|---|---|---|
| baseline | 0.1156 | 0.1895 | — | 33% |
| atr_pct_0_90 | **0.1690** | 0.1170 | -0.052 ⚠️ | **86%** |
| atr_pct_20_80 | 0.1533 | 0.1183 | -0.035 ✅ | 64% |
| **atr_pct_10_80** | 0.1292 | 0.1122 | **-0.017 ✅** | 64% |

**Wdrożony:** `atr_pct_10_80` dla CADJPY (najniższy overfitting).

#### C) Risk-based sizing — ✅ wdrożony globalnie

| Tryb | ExpR | DD% equity | Stabilność |
|---|---|---|---|
| fixed_units | 0.1156 | ~430% (artefakt) | 33% |
| **risk_first 0.5%** | **0.1156** | **~8.3%** | **61%** |

ExpR identyczny — sizing nie zmienia kiedy wchodzić. DD spada do mierzalnych 8%.

#### D) Adaptive RR — ❌ nie rekomendowany

Stały RR=3.0 jest optymalny. Adaptacja (ADX-mapped, ATR-mapped) obniża ExpR.

### 17.5 Opcja C — ATR 10-80 + risk_first 0.5%

Połączenie obu zmian (Priorytet 1 + Priorytet 2 dla CADJPY):

| Metryka | Baseline | Opcja C | Zmiana |
|---|---|---|---|
| ExpR portfolio | 0.1156R | **0.1292R** | +12% |
| DD% equity | ~430%* | **~4.4%** | -99% |
| Stabilność kw. | 33% | **64%** | +31pp |
| Trades/rok | ~2787 | ~1470 | -47% |

**Per-symbol:**

| Symbol | Baseline | Opcja C | Delta | Status |
|---|---|---|---|---|
| **CADJPY** | +0.001R | +0.247R | **+0.245R** | ✅ wdrożony filtr ATR |
| EURUSD | +0.402R | +0.208R | -0.194R | brak filtru (baseline lepszy) |
| USDJPY | +0.346R | +0.142R | -0.204R | brak filtru (baseline lepszy) |
| AUDJPY | +0.185R | +0.082R | -0.103R | brak filtru |
| USDCHF | +0.021R | -0.031R | -0.052R | ⚠️ rozważyć wyłączenie |

### 17.6 Rekomendacje do wdrożenia

| Priorytet | Zmiana | Status |
|---|---|---|
| ✅ **P1 — wdrożony** | `sizing_mode: risk_first` globalnie | Wdrożony 2026-03-04 |
| ✅ **P2 — wdrożony** | ATR filtr 10–80 dla CADJPY | Wdrożony 2026-03-04 |
| ✅ **P3 — wdrożony** | H4 ADX gate thr=16 (EURUSD/USDJPY/USDCHF/AUDJPY) | Wdrożony 2026-03-04 |
| ⬜ P4 — do rozważenia | Wyłączyć USDCHF (`enabled: false`) | Ujemny ExpR z filtrem |
| ⬜ P4 — do zbadania | Re-optymalizacja parametrów na 2023–2025 | Q1_2025 wszystkie pary ujemne |

Pełna dokumentacja badań: `backtests/outputs/RESEARCH_SUMMARY.md`


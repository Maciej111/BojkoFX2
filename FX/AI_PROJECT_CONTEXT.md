# AI Project Context — BojkoFx

> **Cel tego dokumentu:** Dać AI kompletny, spójny obraz projektu — czym jest, jak działa,
> jak był testowany i w jakim jest stanie — bez konieczności czytania dziesiątek plików.
>
> **Data ostatniej aktualizacji: 2026-03-04**

---

## 1. Czym jest ten projekt?

**BojkoFx** to prywatny system algo-tradingowy dla rynku Forex.

| Warstwa | Co robi |
|---------|---------|
| **Backtest** | Testuje strategię na danych historycznych H1 (bid OHLC) |
| **Live (Paper)** | Wykonuje strategię na żywo przez Interactive Brokers (IBKR) na koncie demo |

Projekt jest w fazie **aktywnego paper tradingu** — działa na GCP VM 24/7 na koncie paper IBKR
(konto DUP994821, saldo ~$4.2M USD-denominated w PLN, środki demo).

---

## 2. Strategia tradingowa

### Nazwa: BOS + Pullback (Trend-Following)

**Koncepcja:**
Strategia wykrywa **Break of Structure (BOS)** — moment gdy rynek przełamuje ostatni lokalny pivot
(szczyt lub dołek), co sygnalizuje zmianę/kontynuację trendu. Po wybiciu czeka na **pullback**
do poziomu wybicia i wchodzi zleceniem LIMIT.

### Mechanizm wejścia:
1. Na barach **H1** (LTF) wykrywane są pivoty z lookback = 3 bary w każdą stronę.
2. **BOS LONG:** close_bid > ostatni pivot high (musi być ≥ 2 bary wstecz)
3. **BOS SHORT:** close_bid < ostatni pivot low
4. Zlecenie **LIMIT** z offsetem ATR od poziomu BOS:
   - LONG: `entry = bos_level + (0.3 × ATR)`
   - SHORT: `entry = bos_level - (0.3 × ATR)`
5. **Stop Loss** na ostatnim pivocie po przeciwnej stronie + bufor:
   - LONG: `SL = last_pivot_low - (0.1 × ATR)`
   - SHORT: `SL = last_pivot_high + (0.1 × ATR)`
6. **Take Profit:** `entry ± (3.0 × |entry - SL|)` → RR = 3:1
7. Zlecenie wygasa po **50 barach H1** (TTL)

### Parametry (config.yaml — nie zmieniać bez walidacji):

```yaml
strategy:
  entry_offset_atr_mult: 0.3
  pullback_max_bars: 50         # TTL zlecenia
  risk_reward: 3.0
  sl_anchor: "last_pivot"
  sl_buffer_atr_mult: 0.1
  pivot_lookback_ltf: 3
  pivot_lookback_htf: 5
  confirmation_bars: 1
  require_close_break: true
```

### Timeframe'y:
- **LTF:** H1 — wejścia, pivoty, ATR, główna logika
- **HTF:** D1 — kontekst trendu (resample H1→D1)

### Aktywne symbole (od 2026-03-01, na podstawie walk-forward 2021–2025):

| Symbol | Sesja UTC | HTF | ATR filtr | Uzasadnienie selekcji |
|--------|-----------|-----|-----------|-----------------------|
| EURUSD | 08–21 | D1 | brak | 7/8 kw. pos., silny ExpR |
| USDJPY | 00–24 | D1 | brak | 7/8 kw. pos., najniższy DD |
| USDCHF | 08–21 | D1 | brak | 7/8 kw. pos., HTF D1 > H4 |
| AUDJPY | 00–21 | D1 | brak | 8/8 kw. pos. (najstabilniejszy) |
| CADJPY | 00–24 | D1 | **10–80%** | filtr ATR naprawia parę (+0.245R) |

---

## 3. Architektura kodu

```
BojkoFx/
├── src/
│   ├── core/
│   │   ├── models.py          # Dataclassy: Bar, OrderIntent, Side, ExitReason...
│   │   ├── config.py          # StrategyConfig, RiskConfig, IBKRConfig, SymbolConfig
│   │   ├── strategy.py        # TrendFollowingStrategy — generuje OrderIntent
│   │   └── state_store.py     # SQLiteStateStore — trwała persystencja (WAL)
│   ├── data/
│   │   └── ibkr_marketdata.py # Bootstrap H1 + live tick streaming z IBKR
│   ├── execution/
│   │   └── ibkr_exec.py       # Bracket orders do IBKR, restore po restarcie
│   ├── runners/
│   │   └── run_paper_ibkr_gateway.py  # Główna pętla bota (505 linii)
│   └── reporting/
│       └── logger.py          # Zapis do CSV
├── backtests/                 # Research pipeline (Stage1+2, 9-fold walk-forward)
│   ├── config_backtest.yaml
│   ├── run_experiments.py
│   ├── engine.py              # Symulator portfolio
│   ├── signals_bos_pullback.py
│   ├── indicators.py          # ATR, ADX, rolling percentile
│   ├── experiments.py         # Generator siatki eksperymentów
│   ├── metrics.py
│   ├── reporting.py
│   └── outputs/               # *.md raporty (CSV ignorowane przez git)
├── tests_backtests/           # pytest: fill logic, ATR/ADX indicators
├── tests/                     # pytest: state_store
├── dashboard/
│   ├── app.py                 # Flask API (port 8080, X-API-Key auth)
│   └── index.html             # Lokalny frontend (file:// lub localhost:8890)
├── config/
│   ├── config.yaml            # Główna konfiguracja
│   └── ibkr.env               # Credentials (chmod 600, gitignore)
└── data/
    ├── bars_validated/        # Zwalidowane dane historyczne H1
    ├── live_bars/             # Bary zapisywane przez bota
    ├── raw_dl_fx/             # Pobrane dane (m30, m60)
    └── state/                 # SQLite DB — nie commitowane
```

---

## 4. Przepływ danych — Live Trading

```
IB Gateway (port 4002)
        │
IBKRMarketData.connect()
        ├─ reqHistoricalData() → 365 dni H1 (bootstrap)
        │   └─ fallback: data/bars_validated/SYMBOL.csv
        ├─ reqMktData() → live BID/ASK tick streaming
        │
        ▼
update_bars() — co 30s w pętli
        ├─ tick → akumulacja w _tick_buf
        ├─ gdy minęła godzina → "seal" H1 bar
        ├─ forward-fill jeśli brak ticków
        └─ zapisuje 500 ostatnich barów → data/live_bars/SYMBOL.csv
        │
        ▼
on_h1_bar_close(symbol)
        │
        ├─ [GUARD] last_processed_bar_ts z DB → skip jeśli już przetworzony
        ├─ session_filter → czy godzina w oknie handlowym?
        ├─ atr_pct_filter → (tylko CADJPY) czy ATR pct w [10, 80]?
        │     pct = ile % hist. ATR(14) < bieżący ATR (okno 100 barów)
        │     poza zakresem → [ATR_FILTER] skip
        ├─ adx_h4_gate → (EURUSD/USDJPY/USDCHF/AUDJPY) czy ADX(H4,14) >= 16?
        │     H4 = resample H1→4h, tylko zamknięte bary przed bar_ts
        │     ADX < 16 → [ADX_H4] skip (słaby trend)
        │     CADJPY: wyłączony (adx_h4_gate=None)
        │
        ▼
TrendFollowingStrategy.process_bar(h1, htf, idx)
        ├─ oblicza ATR(14) na (high_bid - low_bid)
        ├─ wykrywa pivoty (lookback=3)
        ├─ sprawdza BOS
        ├─ idempotency: intent_id = sha1(symbol|side|bos_level|bos_bar_ts)
        │     jeśli intent_id już w DB → skip (nie składaj drugi raz)
        └─ sygnał → OrderIntent
                        │
                        ▼
IBKRExecutionEngine.execute_intent(intent)
        ├─ _check_risk() → max 3 pozycje, max 1/symbol
        ├─ _calculate_units() → risk_first: equity × 0.5% / stop_dist
        ├─ _round_price() → zaokrąglenie do IBKR tick size
        │     JPY pairs: 0.005 | inne: 0.00005
        ├─ [DRY-RUN] jeśli READONLY lub !ALLOW_LIVE_ORDERS → log [DRY_RUN], return -1
        └─ _place_limit_bracket(intent, units)
              parent LIMIT (transmit=False, GTD)
              TP LimitOrder (transmit=False, GTC)
              SL StopOrder  (transmit=True,  GTC) ← aktywuje bracket
```

---

## 5. Moduł danych — IBKRMarketData

**Plik:** `src/data/ibkr_marketdata.py`

- Bootstrap: `reqHistoricalData` → 365 dni H1 MIDPOINT, fallback z CSV
- Streaming: `reqMktData` generic tick 233 (BID/ASK real-time)
- Bufor ticków: `_tick_buf[symbol]` (max 2000 ticków)
- Zamknięcie baru: `tick_ts.hour != current_bar_open.hour`
- Forward-fill: gdy bufor pusty → duplikuj ostatnią świecę
- Stale feed: brak ticków > 300s → `resubscribe_symbol(sym)`
- Zapis live barów: co ~60 cykli (≈30 min) → `data/live_bars/SYMBOL.csv`

---

## 6. Moduł egzekucji — IBKRExecutionEngine

**Plik:** `src/execution/ibkr_exec.py`

### Triple-gate bezpieczeństwa:
Wszystkie 3 muszą być spełnione:
1. `IBKR_READONLY = false`
2. `ALLOW_LIVE_ORDERS = true`
3. `kill_switch_active = False`

W każdym innym stanie → `[DRY_RUN]`, zwraca `-1`.

### Bracket order:
```
parent (LIMIT @ entry_price, GTD = now + ttl_bars × 1h, transmit=False)
  ├─ TP: LimitOrder  (GTC, transmit=False) — sleep 0.5s między orderami
  └─ SL: StopOrder   (GTC, transmit=True)  ← wyzwala cały bracket
```

### Sizing — `_calculate_units()` (od 2026-03-04):
```python
# risk_first (domyślny):
max_risk = equity × risk_fraction_start   # domyślnie 0.5%
units    = int(max_risk / stop_distance)  # zawsze proporcjonalne do ryzyka

# fixed_units (legacy fallback gdy sizing_mode: "fixed_units"):
units = min(default_units, int(max_risk / stop_distance))
```

### Tick size (zaokrąglenie cen przed wysłaniem):
| Pary JPY (USDJPY, AUDJPY, CADJPY…) | 0.005 |
|-------------------------------------|-------|
| Pozostałe (EURUSD, USDCHF…) | 0.00005 |

Brak zaokrąglenia → Warning 110 → Error 135 (child orders odrzucone).

### Odbudowa po restarcie (`restore_positions_from_ibkr`):
- `ib.trades()` + `ib.positions()` → grupuje po `parentId`
- Odbudowuje `_records` w RAM → risk gate wie o istniejących pozycjach
- TP i SL **żyją na serwerze IBKR** niezależnie od bota

---

## 7. Persystencja stanu — SQLiteStateStore

**Plik:** `src/core/state_store.py`
**DB:** `data/state/bojkofx_state.db` (WAL mode, PRAGMA synchronous=NORMAL)

### Tabele:
| Tabela | Zawartość |
|--------|-----------|
| `strategy_state` | symbol, last_processed_bar_ts, pivoty, BOS (per symbol) |
| `orders` | intent_id UNIQUE, symbol, status, ibkr_ids, created/updated_at |
| `risk_state` | key-value: peak_equity, kill_switch_active, daily_loss |
| `events` | append-only audit: INTENT_CREATED, ORDER_SENT, EXIT_TP/SL, STARTUP… |

### Statusy zleceń (tylko do przodu):
```
CREATED → SENT → PENDING → FILLED → EXITED
                         ↘ CANCELLED / EXPIRED
RESTORED_UNKNOWN  (znalezione na IBKR, brak w DB)
```

### Startup merge (reconciliation przy każdym starcie):
- DB PENDING + brak na IBKR → EXPIRED
- IBKR order + brak w DB → RESTORED_UNKNOWN
- Oba → DB aktualizowana do statusu z IBKR (IBKR = source-of-truth)

### Idempotencja:
```python
intent_id = sha1(f"{symbol}|{side}|{bos_level:.8f}|{bos_bar_ts}")
# UNIQUE constraint → ten sam BOS nie składa zlecenia drugi raz po restarcie
```

---

## 8. Zarządzanie ryzykiem

```yaml
risk:
  sizing_mode: "risk_first"       # ZMIANA 2026-03-04 (poprzednio: fixed_units)
  risk_fraction_start: 0.005      # 0.5% equity per trade
  default_units: 5000             # używane tylko gdy sizing_mode: fixed_units
  max_open_positions_total: 3
  max_open_positions_per_symbol: 1
  daily_loss_limit_pct: 2.0
  monthly_dd_stop_pct: 15.0
  kill_switch_dd_pct: 10.0
```

### Kill Switch:
- Automatyczny gdy drawdown od peak_equity ≥ 10%
- Manualny: `KILL_SWITCH=true` w `ibkr.env`
- Persystowany w SQLite → przywracany po restarcie

### Eventy w logu:
| Event | Znaczenie |
|-------|-----------|
| `INTENT` | Sygnał wygenerowany, zlecenie nie wysłane (DRY) |
| `ORDER_PLACED` | Zlecenie wysłane do IBKR |
| `FILL` | Entry wypełniony |
| `TRADE_CLOSED` | Pozycja zamknięta (SL lub TP) |
| `RISK_BLOCK` | Zablokowane przez risk management |
| `KILL_SWITCH` | Zablokowane przez kill switch |

---

## 9. Runner — run_paper_ibkr_gateway.py

**Plik:** `src/runners/run_paper_ibkr_gateway.py` (505 linii)

### Uruchomienie:
```bash
# DRY-run (bez zleceń):
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD,USDJPY,USDCHF,AUDJPY,CADJPY

# Z prawdziwymi paper orders:
python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD,USDJPY,USDCHF,AUDJPY,CADJPY --allow_live_orders
```

### Pętla główna (co POLL_INTERVAL_S = 30s):
1. Auto-reconnect jeśli `ib.isConnected() == False`
2. Stale feed check (brak ticków > 300s → resubscribe)
3. Kill switch check (`check_kill_switch()`)
4. Dla każdego symbolu:
   - `update_bars(sym)` → tick buffer → sealed H1
   - Sprawdź czy nowy bar (`bar_count > last_bar_count`)
   - Session filter → ATR percentile filter → `strategy.process_bar()`
   - `execute_intent()` → bracket order lub DRY_RUN
5. `poll_order_events()` → śledź fille i wyjścia
6. Co ~60 cykli: eksport live barów → `data/live_bars/SYMBOL.csv`

### Sekwencja startu:
```
1. Config.from_env(config.yaml)
2. IBKRMarketData.connect()
3. SQLiteStateStore.migrate()
4. load_risk_state() z DB
5. TrendFollowingStrategy + IBKRExecutionEngine (z inject store)
6. subscribe_symbol() dla każdego aktywnego symbolu
7. restore_positions_from_ibkr()       ← odbudowa stanu
8. merge_ibkr_state()                  ← reconciliation DB
9. Startup seal (update_bars dla wszystkich)
10. Główna pętla
```

### Tryb non-interactive (systemd):
- `sys.stdin.isatty()` → jeśli False → pomija potwierdzenie `YES`
- Wszystkie błędy w pętli → auto-reconnect (30s czekania + `return main()`)

---

## 10. Infrastruktura — GCP VM

| Parametr | Wartość |
|----------|---------|
| Projekt | `sandbox-439719` |
| VM | `bojkofx-vm`, `us-central1-a` |
| IP | `34.31.64.224` (statyczne) |
| User | `macie` |
| OS | Ubuntu 22.04 LTS, e2-small, 20GB SSD |

### Systemd services:
```
ibgateway.service         → IB Gateway (Java/IBC), port 4002, paper
bojkofx.service           → trading bot (Python), After=ibgateway, Restart=on-failure 60s
bojkofx-dashboard.service → Flask API, port 8080
```

### Ważne ścieżki na VM:
```
/home/macie/bojkofx/app/           ← klon repo GitHub
/home/macie/bojkofx/venv/          ← Python 3.12 venv
/home/macie/bojkofx/config/ibkr.env
/home/macie/bojkofx/logs/bojkofx.log
/home/macie/bojkofx/app/data/state/bojkofx_state.db
```

### IBC (auto-login):
```ini
ExistingSessionDetectedAction=primary   # przejęcie sesji — IBKR Mobile rozłącza bota
AcceptIncomingConnectionAction=accept
TradingMode=paper
```

### SSH:
```bash
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719
```

---

## 11. Dashboard

**Backend:** `dashboard/app.py` — Flask API, port 8080, auth: `X-API-Key`

| Endpoint | Opis |
|----------|------|
| `GET /api/health` | Liveness (bez auth) |
| `GET /api/status` | Status bota, portfolio, pozycje per symbol |
| `GET /api/equity_history` | Historia equity |
| `GET /api/candles/<symbol>` | Świece OHLC, ostatnie 72 bary H1 |
| `GET /api/trades/<symbol>` | Historia zamkniętych transakcji |

**Frontend:** `dashboard/index.html` — otwierany lokalnie lub przez `python dashboard/serve.py` (port 8890).
Auto-refresh co 60s. Świece rysowane przez Canvas 2D (nie Chart.js).
Weekendy (bez barów) = pionowa przerywana kreska na wykresie.

---

## 12. Badania — research pipeline

**Katalog:** `backtests/`

```bash
python -m backtests.run_experiments --config backtests/config_backtest.yaml
python -m backtests.run_experiments --config backtests/config_backtest.yaml --stage1-only
```

### Metodologia:
- Dane: H1 bid OHLC 2021–2025, 5 symboli
- 9-foldowa walk-forward (1 historyczny + 8 kwartalnych OOS Q1–Q4 2024/2025)
- Fill logic: conservative (gdy SL+TP w tym samym barze → SL wins)
- Metryki: ExpR, PF, win rate, DD%, stabilność kw.

### Wyniki kluczowych modułów:

| Moduł | Wynik | Rekomendacja |
|-------|-------|--------------|
| Baseline (produkcja) | ExpR=0.1156R, DD=430%*, stabilność 33% | punkt odniesienia |
| ADX gate | ExpR −20–66% | ❌ nie wdrażać |
| **ATR filtr 10–80** | ExpR +12%, stabilność 64%, delta -0.017 | ✅ wdrożony dla CADJPY |
| **risk_first sizing** | ExpR bez zmian, DD: 430%* → 8.3% | ✅ wdrożony globalnie |
| Adaptive RR | ExpR gorszy | ❌ nie wdrażać |

*\*DD% przy fixed units = artefakt (% pozycji, nie equity)*

### Wnioski per-symbol:

| Symbol | ExpR base | ExpR z filtrem ATR | Wniosek |
|--------|-----------|-------------------|---------|
| CADJPY | +0.001R | **+0.247R** | filtr ATR naprawia (wdrożony) |
| EURUSD | +0.402R | +0.208R | filtr szkodzi — bez filtru |
| USDJPY | +0.346R | +0.142R | filtr szkodzi — bez filtru |
| AUDJPY | +0.185R | +0.082R | bez filtru |
| USDCHF | +0.021R | -0.031R | ⚠️ ATR szkodzi; z H4 ADX16 → +0.060R (status quo, patrz P4) |

Pełna dokumentacja: `backtests/outputs/RESEARCH_SUMMARY.md`

---

## 13. Testy

```bash
pytest tests/test_state_store.py -v          # 26 passed — SQLite WAL, merge, idempotency
pytest tests_backtests/test_engine_fill_logic.py -v  # 25 passed — fill, sizing, session
pytest tests_backtests/test_indicators_adx_atr.py -v # ATR, ADX, rolling percentile
```

---

## 14. Konfiguracja — zmienne środowiskowe (ibkr.env)

```ini
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=7
IBKR_ACCOUNT=DUP994821
IBKR_READONLY=false
ALLOW_LIVE_ORDERS=true
KILL_SWITCH=false
IB_USERNAME=<username>
IB_PASSWORD=<password>
DASHBOARD_API_KEY=<hex 32 znaki>
DASHBOARD_PORT=8080
```

---

## 15. Log tradingowy

**Plik:** `logs/paper_trading_ibkr.csv`
Kolumny: `timestamp`, `symbol`, `signal_id`, `event_type`, `side`, `entry_type`,
`entry_price_intent`, `sl_price`, `tp_price`, `ttl_bars`, `parentOrderId`,
`tpOrderId`, `slOrderId`, `fill_time`, `fill_price`, `exit_time`, `exit_price`,
`exit_reason`, `latency_ms`, `slippage_entry_pips`, `realized_R`, `pnl`, `notes`

---

## 16. Stan projektu (2026-03-04)

| Komponent | Status |
|-----------|--------|
| Strategia BOS+Pullback | ✅ Aktywna, parametry zamrożone |
| Silnik backtestu (backtests/) | ✅ 9-fold walk-forward, Stage1+2 pipeline |
| IBKR adapter (ib_insync) | ✅ Działa, auto-reconnect, stale feed check |
| Paper trading runner | ✅ Aktywny 24/7 na GCP VM |
| Systemd (ibgateway + bojkofx + dashboard) | ✅ Auto-restart, na żywo |
| Triple-gate bezpieczeństwa | ✅ READONLY=false, ALLOW_LIVE=true |
| Live streaming ticków + H1 bars | ✅ Forward-fill dla godzin bez ticków |
| Generowanie sygnałów BOS | ✅ Sygnały pojawiają się w logach |
| Bracket orders (paper) | ✅ Odblokowane, błąd 135 naprawiony |
| **risk_first sizing** | ✅ **Wdrożony 2026-03-04** (0.5% equity/trade) |
| **ATR percentile filter CADJPY** | ✅ **Wdrożony 2026-03-04** (10–80%) |
| **H4 ADX gate (thr=16)** | ✅ **Wdrożony 2026-03-04** (EURUSD/USDJPY/USDCHF/AUDJPY) |
| **USDCHF P4 analiza** | ✅ **Zbadano 2026-03-04** — status quo (brak ATR filtra, enabled=true) |
| Session filter (per-symbol) | ✅ Wszystkie 5 par skonfigurowane |
| SQLite WAL state persistence | ✅ DB na VM, startup merge, idempotency |
| Restore po restarcie | ✅ `restore_positions_from_ibkr()` działa |
| Dashboard (Flask + HTML) | ✅ Dostępny na port 8080 |
| Monitoring z Windows | ✅ `status.cmd` — zbiera logi z VM |

### Znane ograniczenia:
- **Q1 2025 ujemny** dla wszystkich par — możliwa zmiana reżimu rynkowego
- **USDCHF** — słaby baseline (+0.021R), ale z H4 ADX16 +0.060R (61% kw. pos.); ATR filtr szkodzi — status quo (patrz P4)
- Weekendy: brak barów (forward-fill), dashboard pokazuje przerywane linie
- Znak `Γö` w logach — artefakt UTF-8 Box Drawing w terminalu Windows

### Rekomendacje do wdrożenia (kolejka):
| Priorytet | Zmiana | Status |
|-----------|--------|--------|
| ✅ P1 | `sizing_mode: risk_first` | Wdrożony 2026-03-04 |
| ✅ P2 | ATR filtr 10–80 dla CADJPY | Wdrożony 2026-03-04 |
| ✅ P3 | H4 ADX gate thr=16 (EURUSD/USDJPY/USDCHF/AUDJPY) | Wdrożony 2026-03-04 |
| ✅ P4 | USDCHF: zbadano `enabled: false` i `atr_pct_filter` | **Status quo** (2026-03-04) |
| ⬜ P5 | Re-optymalizacja na 2023–2025 | Q1_2025 wszystkie ujemne |

### P4 — USDCHF: szczegółowy wniosek (2026-03-04)

Zbadano dwie opcje dla USDCHF (para ledwie pozytywna w baseline +0.021R):

| Opcja | Wynik | Decyzja |
|-------|-------|---------|
| Dodać `atr_pct_filter: 10–80` | -0.031R (gorzej niż baseline) | ❌ Nie wdrażać — ATR szkodzi USDCHF |
| `enabled: false` | +0.060R z H4 ADX16 (+186% vs baseline) | ❌ Nie wyłączać — para pozytywna |
| Status quo (H4 ADX16, bez ATR) | +0.060R val, 61% kw. pos. | ✅ Utrzymać |

**Mechanizm:** ATR filtr 10–80 niszczy USDCHF analogicznie jak H4 ADX niszczyłby CADJPY
— podwójne filtrowanie eliminuje zbyt wiele sygnałów bez poprawy jakości.

**Trigger rewizji:** jeśli USDCHF da ≥ 2 kolejne ujemne kwartały na produkcji w 2026
→ rozważyć `adx_h4_gate: 18` (test +0.172R) lub `enabled: false`.

Pełny raport: `backtests/outputs/USDCHF_P4_ANALYSIS.md`

---

## 17. Zależności (requirements.txt)

```
ib_insync      # IBKR Gateway API
pandas         # przetwarzanie danych, resample
numpy          # obliczenia numeryczne
flask          # dashboard API
flask-cors     # CORS dla lokalnego frontend
pyyaml         # config.yaml
python-dotenv  # ibkr.env
pytest         # testy
```

---

## 18. Słownik pojęć

| Termin | Znaczenie |
|--------|-----------|
| **BOS** | Break of Structure — przełamanie ostatniego pivotu |
| **Pullback** | Powrót ceny do poziomu wybięcia przed kontynuacją |
| **LTF / HTF** | Low/High Timeframe — H1 (wejścia) / D1 (kontekst) |
| **ATR** | Average True Range — miara zmienności (okno 14 barów) |
| **ATR pct** | Percentyl bieżącego ATR w 100-barowej historii (0–100%) |
| **ExpR / Exp(R)** | Expectancy w jednostkach ryzyka — średni wynik na trade |
| **PF** | Profit Factor — suma zysków / suma strat |
| **risk_first** | Tryb pozycjonowania: units = equity × 0.5% / stop_dist |
| **fixed_units** | Tryb legacy: stałe 5000 units (z cap-down do max_risk) |
| **bracket order** | Parent LIMIT + SL STOP + TP LIMIT złożone razem |
| **TTL** | Time-to-live zlecenia — liczba barów H1, po których wygasa |
| **intent_id** | sha1(symbol|side|bos_level|bos_bar_ts) — klucz idempotency |
| **DRY mode** | Tryb bez zleceń — loguje [DRY_RUN], zwraca -1 |
| **triple-gate** | 3 bramki: READONLY=false + ALLOW_LIVE=true + !kill_switch |
| **forward-fill** | Duplikowanie ostatniej świecy gdy brak ticków |
| **startup merge** | Reconciliation DB ↔ IBKR przy każdym starcie bota |
| **WAL** | Write-Ahead Log — tryb SQLite odporny na crash |
| **IBC** | Interactive Brokers Controller — auto-login do Gateway |
| **OOS** | Out-of-Sample — dane nie widziane podczas optymalizacji |
| **walk-forward** | Walidacja na kolejnych kwartalach OOS (9 foldów) |

---

*Dokument zaktualizowany: 2026-03-04.
Aktualizować po każdej istotnej zmianie architektury, konfiguracji lub wynikach walidacji.*

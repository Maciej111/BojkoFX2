# BojkoFx — GCP VM Setup: Pełna dokumentacja dla AI

> Ostatnia aktualizacja: 2026-02-23  
> Dokument opisuje **co zostało zrobione**, **jak działa infrastruktura**, **znane problemy** i **co pozostało do zrobienia**.

---

## 1. Architektura systemu

```
GCP VM (bojkofx-vm)
│
├── Xvfb :99          ← wirtualny ekran dla GUI IB Gateway
├── IB Gateway        ← połączenie z IBKR, port 4002
│   └── IBC (auto-login + konfiguracja)
│
└── BojkoFx Bot       ← Python, łączy się do Gateway przez ib_insync
    ├── IBKRMarketData   (H1/H4 bary, live ticks)
    ├── TrendFollowingStrategy
    ├── IBKRExecutionEngine
    └── TradingLogger
```

---

## 2. GCP VM — parametry

| Parametr | Wartość |
|----------|---------|
| Projekt | `sandbox-439719` |
| Nazwa VM | `bojkofx-vm` |
| Zona | `us-central1-a` |
| Machine type | `e2-small` |
| OS | Ubuntu 22.04 LTS |
| Boot disk | 20 GB SSD (pd-ssd) |
| Zewnętrzny IP | `34.31.64.224` (statyczny, nazwa: `bojkofx-ip`) |
| Tag | `bojkofx` |
| Firewall | SSH (port 22) tylko z IP autora |

### SSH

```bash
ssh macie@34.31.64.224
# lub
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719
```

---

## 3. Software zainstalowany na VM

| Software | Wersja | Lokalizacja |
|----------|--------|-------------|
| Python | 3.12 | `/usr/bin/python3.12` |
| Java JRE | 11 | `openjdk-11-jre` |
| IB Gateway | stable (headless) | `/home/macie/ibgateway/` |
| IBC (auto-login) | 3.23.0 | `/opt/ibc/` |
| Xvfb | system | port `:99` |
| venv | Python 3.12 | `/home/macie/bojkofx/venv/` |
| Bot repo | git | `/home/macie/bojkofx/app/` |

### Python dependencies (venv)
Zainstalowane z `/home/macie/bojkofx/app/requirements.txt`, kluczowe:
- `ib_insync`
- `pandas`, `numpy`
- `pyyaml`

---

## 4. Struktura katalogów na VM

```
/home/macie/
├── ibgateway/              ← IB Gateway binaries
├── Jts/                    ← konfiguracja IB Gateway (jts.ini, credentials)
│   └── jts.ini             ← ReadOnlyApi=false, AllowApiWriteAccess=yes
├── bojkofx/
│   ├── app/                ← kod bota (git repo)
│   ├── venv/               ← Python virtual environment
│   ├── logs/
│   │   ├── gateway.log     ← logi IB Gateway + IBC
│   │   └── bojkofx.log     ← logi bota
│   ├── config/
│   │   └── ibkr.env        ← zmienne środowiskowe (credentials, flagi)
│   └── start-gateway-ibc.sh ← skrypt startowy Xvfb + IBC
└── .ibc/
    └── ib-credentials.txt  ← login + hasło IB (chmod 600)

/opt/ibc/                   ← IBC (Interactive Brokers Controller)
└── config.ini              ← konfiguracja IBC
```

---

## 5. Konfiguracja IBC (`/opt/ibc/config.ini`)

Kluczowe ustawienia:

```ini
IbLoginId=ehzjkm491
IbPassword=4UiM5-KM}.8
TradingMode=paper
ReadOnlyApi=no          ← WAŻNE: IBC automatycznie odznacza checkbox przy logowaniu
ReadonlyLogin=no
AllowApiWriteAccess=yes
CommandServerPort=7462
AcceptIncomingConnectionAction=accept
```

> **Kluczowe odkrycie:** `ReadOnlyApi=no` w `config.ini` IBC powoduje że IBC
> automatycznie otwiera Config Dialog Gateway i odznacza checkbox "Read-Only API"
> przy każdym logowaniu. Eliminuje to dialog "API client needs write access".

---

## 6. Konfiguracja serwisów systemd

### `/etc/systemd/system/ibgateway.service`

```ini
[Unit]
Description=IB Gateway (IBC auto-login)
After=network.target

[Service]
Type=simple
User=macie
Environment=HOME=/home/macie
Environment=DISPLAY=:99
ExecStart=/home/macie/bojkofx/start-gateway-ibc.sh
TimeoutStartSec=180
Restart=always
RestartSec=30s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log
```

### `/etc/systemd/system/bojkofx.service`

```ini
[Unit]
Description=BojkoFx Trading Bot
After=ibgateway.service network.target
Requires=ibgateway.service

[Service]
Type=simple
User=macie
WorkingDirectory=/home/macie/bojkofx/app
EnvironmentFile=/home/macie/bojkofx/config/ibkr.env
ExecStartPre=/bin/sleep 90        ← czeka 90s na zalogowanie Gateway
ExecStart=/home/macie/bojkofx/venv/bin/python -m src.runners.run_paper_ibkr_gateway \
    --symbol EURUSD,GBPUSD,USDJPY \
    --allow_live_orders
Restart=always
RestartSec=60s
```

### Zarządzanie serwisami

```bash
sudo systemctl start ibgateway
sudo systemctl start bojkofx
sudo systemctl stop bojkofx
sudo systemctl restart ibgateway
sudo systemctl status ibgateway bojkofx
```

---

## 7. Zmienne środowiskowe (`/home/macie/bojkofx/config/ibkr.env`)

```bash
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=7
IBKR_ACCOUNT=DUP994821
IBKR_READONLY=false
ALLOW_LIVE_ORDERS=true
KILL_SWITCH=false
IB_USERNAME=ehzjkm491
IB_PASSWORD=4UiM5-KM}.8
```

> **Uwaga:** `IBKR_READONLY=false` + `ALLOW_LIVE_ORDERS=true` — zlecenia są aktywne.
> `KILL_SWITCH=true` natychmiast blokuje wszystkie zlecenia bez restartu.

---

## 8. Konto IBKR Paper

| Parametr | Wartość |
|----------|---------|
| Konto | `DUP994821` |
| Typ | Paper Trading (Simulated) |
| Waluta bazowa | **PLN** |
| Cash EUR | ~1,000,000 EUR |
| Cash PLN | 0 |
| Cash USD | 0 |

### ⚠ Znane ograniczenie konta

Konto ma walutę bazową **PLN** i posiada EUR. Powoduje to:

- `SELL EURUSD` — **działa** (sprzedajemy EUR, dostajemy USD) ✅
- `BUY EURUSD` — **odrzucane** błędem `201: FX trade would expose account to currency leverage` ❌
  - Konto PLN nie może trzymać długiej pozycji USD (traktowane jako leverage)

**Rozwiązanie:** Zaloguj się do [IBKR Client Portal](https://www.interactivebrokers.co.uk/portal)
→ Paper Trading Account → **Reset** → konto dostanie $1,000,000 USD jako walutę bazową.

### Aktualna otwarta pozycja (do zamknięcia!)

Na koncie jest otwarta pozycja z testów:
```
EUR  -25,000  @ 1.18210
```
Należy zamknąć ją ręcznie przez Client Portal → Positions → Close.

---

## 9. Auto-reconnect (daily restart IBKR ~23:45 EST)

IBKR codziennie ~23:45 EST restartuje serwery. Mechanizm obsługi:

### Co się dzieje:

```
23:45 EST  Gateway traci połączenie z IBKR
           → ibgateway.service: Restart=always, RestartSec=30s
           → IBC loguje się automatycznie (~60-90s)
           → port 4002 wraca

Bot:
           → ib.disconnectedEvent → _on_disconnected() → connected=False
           → main loop: is_connected() == False
           → reconnect() — próby co 60s, bez limitu
           → po powrocie: connect() + re-subscribe wszystkich symboli
           → bojkofx.service: Restart=always jako backup
```

### Implementacja (`src/data/ibkr_marketdata.py`)

Dodane metody:
- `reconnect()` — pętla prób co `RECONNECT_DELAY_S=60s`, bez limitu (`MAX_RECONNECT_ATTEMPTS=0`)
- `is_connected()` — zwraca `ib.isConnected()`
- `_on_disconnected()` — callback rejestrowany na `ib.disconnectedEvent`
- `_subscribed_symbols` — lista symboli do ponownej subskrypcji po reconnect

### Implementacja (`src/runners/run_paper_ibkr_gateway.py`)

W main loop dodano:
```python
if not marketdata.is_connected():
    if not marketdata.reconnect():
        sys.exit(1)
    execution.ib = marketdata.ib  # rebind
    last_bar_count = {s: marketdata.bar_count(s) for s in subscribed}
    continue
```

---

## 10. Logi — gdzie patrzeć

```bash
# Gateway (IBC auto-login, połączenie z IBKR)
tail -f /home/macie/bojkofx/logs/gateway.log

# Bot (strategia, zlecenia, błędy)
tail -f /home/macie/bojkofx/logs/bojkofx.log

# Paper trading CSV (każde zlecenie)
cat /home/macie/bojkofx/logs/paper_trading_ibkr.csv

# Systemd status
journalctl -u ibgateway -n 50
journalctl -u bojkofx -n 50
```

### Przykładowe logi IBC przy poprawnym starcie

```
IBC: Setting ReadOnlyApi
IBC: Read-Only API checkbox is now set to: false
IBC: Configuration tasks completed
IBC: Login has completed
IBC: Click button: OK
```

---

## 11. Test API — wyniki

### Test zlecenia SELL EURUSD (2026-02-22)

```
orderId=20  SELL 25000 EURUSD
status=Submitted → Filled
price=1.18210
latencja=1002ms
komisja=7.17 PLN
✅ SUKCES
```

### Potwierdzone działanie

- ✅ Połączenie API (port 4002)
- ✅ Write access (ReadOnlyApi=false przez IBC)
- ✅ Zlecenie rynkowe SELL EURUSD — wypełnione
- ✅ Komisja naliczona
- ✅ Pozycja widoczna (`-25000 EUR @ 1.18210`)
- ❌ BUY EURUSD — odrzucane (ograniczenie konta PLN, patrz sekcja 8)

---

## 12. Skrypty pomocnicze (lokalne: `scripts/`)

| Skrypt | Opis |
|--------|------|
| `check-account.sh` | Sprawdza saldo i pozycje konta przez API |
| `start-vnc.sh` | Uruchamia x11vnc na Xvfb:99 (port 5901) |
| `patch-services.sh` | Aktualizuje serwisy systemd |
| `deploy-readonlyno-test.sh` | Deploy config + restart + test |
| `run-rt-test.sh` | Uruchamia test round-trip |

### Uruchomienie testu ręcznie na VM

```bash
ssh macie@34.31.64.224
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
  /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py
```

---

## 13. Git repo bota

```bash
# Na VM
cd /home/macie/bojkofx/app
git log --oneline -5
# ba6ba65 feat: add auto-reconnect to IBKRMarketData and main loop
# 40f0796 chore: add GCP scripts, AI context, remove OANDA refs
# 5b797d1 clean from oanda
```

Remote: GitHub (private repo, token w `/home/macie/.git-credentials`)

---

## 14. Znane problemy i TODO

| Problem | Status | Rozwiązanie |
|---------|--------|-------------|
| Konto PLN — BUY EURUSD odrzucane | ⚠ Otwarte | Reset konta paper na USD w Client Portal |
| Pozycja -25k EUR otwarta | ⚠ Otwarte | Zamknąć ręcznie w Client Portal |
| Bot nie uruchomiony (bojkofx.service inactive) | ⚠ Otwarte | `sudo systemctl start bojkofx` po resecie konta |
| Dialog "write access" przy nowym clientId | ✅ Rozwiązane | `ReadOnlyApi=no` w IBC config.ini |
| Daily reconnect | ✅ Rozwiązane | Auto-reconnect w IBKRMarketData |

---

## 15. Szybki start po przerwie / dla nowego AI

```bash
# 1. Sprawdź czy gateway działa
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719 \
  --command "systemctl is-active ibgateway; ss -tlnp | grep 4002"

# 2. Sprawdź logi
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719 \
  --command "tail -20 /home/macie/bojkofx/logs/gateway.log"

# 3. Sprawdź konto
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719 \
  --command "bash /tmp/check-account.sh"

# 4. Uruchom bota
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719 \
  --command "sudo systemctl start bojkofx && journalctl -u bojkofx -f"
```


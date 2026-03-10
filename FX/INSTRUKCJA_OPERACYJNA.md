# BojkoFx — Instrukcja Operacyjna VM

## 1. Logowanie na VM

```bash
ssh -i ~/.ssh/google_compute_engine macie@34.31.64.224
```

Lub przez gcloud:
```bash
gcloud compute ssh macie@bojkofx-vm --zone us-central1-a --project sandbox-439719
```

---

## 2. Status serwisów

```bash
# IB Gateway (port 4002)
sudo systemctl status ibgateway --no-pager

# Trading Bot
sudo systemctl status bojkofx --no-pager

# Oba naraz
sudo systemctl status ibgateway bojkofx --no-pager
```

---

## 3. Logi — na żywo

```bash
# Log IB Gateway (połączenie, auto-login IBC)
tail -f /home/macie/bojkofx/logs/gateway.log

# Log bota (sygnały, zlecenia, błędy)
tail -f /home/macie/bojkofx/logs/bojkofx.log

# CSV z historią transakcji
cat /home/macie/bojkofx/logs/paper_trading_ibkr.csv
```

Oba logi jednocześnie:
```bash
tail -f /home/macie/bojkofx/logs/gateway.log /home/macie/bojkofx/logs/bojkofx.log
```

---

## 4. Start / Stop / Restart

```bash
# Start wszystkiego
sudo systemctl start ibgateway
sudo systemctl start bojkofx

# Stop
sudo systemctl stop bojkofx
sudo systemctl stop ibgateway

# Restart (np. po zmianie konfiguracji)
sudo systemctl restart ibgateway
sudo systemctl restart bojkofx
```

---

## 5. Uruchomienie bota ręcznie (bez systemd)

Przydatne do testów — output widoczny bezpośrednio w terminalu:

```bash
cd /home/macie/bojkofx/app
source /home/macie/bojkofx/config/ibkr.env

# Dry-run (bez zleceń) — 30 minut
/home/macie/bojkofx/venv/bin/python -m src.runners.run_paper_ibkr_gateway \
    --symbol EURUSD,GBPUSD,USDJPY \
    --minutes 30

# Paper trading z zleceniami
/home/macie/bojkofx/venv/bin/python -m src.runners.run_paper_ibkr_gateway \
    --symbol EURUSD,GBPUSD,USDJPY \
    --allow_live_orders
```

---

## 6. Zmiana konfiguracji

```bash
# Edycja credentials / trybu
nano /home/macie/bojkofx/config/ibkr.env

# Kluczowe zmienne:
# IBKR_READONLY=false       ← false = zlecenia aktywne
# ALLOW_LIVE_ORDERS=true    ← true = zlecenia do IB
# KILL_SWITCH=false         ← true = natychmiastowe zatrzymanie
```

Po każdej zmianie ibkr.env — restart serwisu:
```bash
sudo systemctl restart bojkofx
```

---

## 7. Kill switch — awaryjne zatrzymanie zleceń

Bez restartu serwisu:
```bash
sudo sed -i 's/KILL_SWITCH=false/KILL_SWITCH=true/' /home/macie/bojkofx/config/ibkr.env
sudo systemctl restart bojkofx
```

Powrót do normalnej pracy:
```bash
sudo sed -i 's/KILL_SWITCH=true/KILL_SWITCH=false/' /home/macie/bojkofx/config/ibkr.env
sudo systemctl restart bojkofx
```

---

## 8. Sprawdzenie portu 4002 (czy Gateway odpowiada)

```bash
ss -tlnp | grep 4002
```

Oczekiwany output:
```
LISTEN 0   50   *:4002   *:*   users:(("java",...))
```

---

## 9. Szybki test połączenia z Gateway

```bash
/home/macie/bojkofx/venv/bin/python /tmp/test_gateway.py
```

Oczekiwany output:
```
✓ Connected — account: ['DUP994821']
✓ EURUSD  BID=1.08xxx  ASK=1.08xxx
```

---

## 10. Healthcheck VM

```bash
bash /home/macie/bojkofx/healthcheck.sh
```

---

## 11. Procesy — podgląd zasobów

```bash
# CPU / RAM live
htop

# Tylko procesy bota
ps aux | grep -E "(ibgateway|Xvfb|python|ibc)" | grep -v grep
```

---

## 12. Autostart po restarcie VM

Serwisy są włączone (`enabled`) — startują automatycznie po rebootcie:

```bash
# Weryfikacja
systemctl is-enabled ibgateway bojkofx

# Ręczny reboot
sudo reboot
```

---

## Podsumowanie ścieżek

| Co | Ścieżka |
|----|---------|
| Config / credentials | `/home/macie/bojkofx/config/ibkr.env` |
| Log gateway (IBC) | `/home/macie/bojkofx/logs/gateway.log` |
| Log bota | `/home/macie/bojkofx/logs/bojkofx.log` |
| Historia transakcji CSV | `/home/macie/bojkofx/logs/paper_trading_ibkr.csv` |
| Katalog aplikacji | `/home/macie/bojkofx/app/` |
| Virtual env Python | `/home/macie/bojkofx/venv/` |
| IB Gateway binary | `/home/macie/ibgateway/ibgateway` |
| IBC (auto-login) | `/opt/ibc/` |


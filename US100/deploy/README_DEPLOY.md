# BojkoIDX — VM Deployment Guide

## Target VM

| Field | Value |
|---|---|
| VM name | `bojkofx-vm` |
| IP | `34.31.64.224` |
| SSH | `ssh macie@34.31.64.224` |
| OS | Ubuntu 22.04 |
| Zone | GCP `us-central1-a` |

## Layout on VM

```
/home/macie/
├── bojkofx/              ← existing FX bot (unchanged)
│   ├── app/
│   ├── venv/
│   └── config/ibkr.env   (client_id=7)
│
└── bojkoidx/             ← NEW IDX bot
    ├── app/              ← git clone of BojkoIDX
    ├── venv/             ← separate Python venv
    ├── logs/             ← log files
    ├── data/
    │   └── bars_idx/     ← 5m CSV bars (fallback)
    └── config/
        └── ibkr.env      ← client_id=8 (must differ from FX=7)
```

## Shared IBKR Gateway

Both bots use the SAME IB Gateway (port 4002), but with **different client IDs**:

| Bot | Client ID | Service |
|---|---|---|
| BojkoFX | `7` | `bojkofx.service` |
| BojkoIDX | `8` | `bojkoidx.service` |

The `ibgateway.service` is already running and shared.

## Quick Deploy (first time)

```bash
# From your local machine (project root):
bash deploy/deploy_idx.sh
```

This will:
1. Push local code to git
2. Clone repo on VM at `/home/macie/bojkoidx/app`
3. Upload 5m bars CSV if it exists locally
4. Create Python venv + install `requirements.txt`
5. Copy `bojkoidx.env` → `/home/macie/bojkoidx/config/ibkr.env`
6. Install and enable `bojkoidx.service`

## Update after code changes

```bash
# On VM:
cd /home/macie/bojkoidx/app
git pull origin main

# Restart service:
sudo systemctl restart bojkoidx
```

Or re-run `deploy_idx.sh` locally.

## First Run (dry test — no orders)

```bash
ssh macie@34.31.64.224
cd /home/macie/bojkoidx/app
/home/macie/bojkoidx/venv/bin/python -m src.runners.run_live_idx --minutes 10
```

Expected output:
- `[IBKR-IDX] Connected to 127.0.0.1:4002 | server time: ...`
- `[IBKR-IDX] Bootstrapping 30d 5m history for NAS100USD...`
- `[IBKR-IDX] Loaded N 5m bars for NAS100USD`
- `[READY] Subscribed to NAS100USD — N 5m bars loaded`
- Every 5 min (during 13–20 UTC): `[BAR] NAS100USD 5m closed: ...`
- `DRY-RUN MODE — no orders will be sent` (since not using --allow_live_orders)

## Enable Live Orders

Edit `/home/macie/bojkoidx/config/ibkr.env`:
```bash
IBKR_READONLY=false
ALLOW_LIVE_ORDERS=true
```

Then restart:
```bash
sudo systemctl restart bojkoidx
```

The service will start in live-order mode. The first time systemd starts it,
confirmation prompt is skipped (non-interactive mode).

## Monitoring

```bash
# Live logs:
tail -f /home/macie/bojkoidx/logs/bojkoidx.log

# Service status:
sudo systemctl status bojkoidx

# Both services running:
sudo systemctl status ibgateway bojkofx bojkoidx
```

## Stop / Emergency Kill

```bash
sudo systemctl stop bojkoidx
```

Or set `KILL_SWITCH=true` in the env file and restart:
```bash
# Edit env:
sudo nano /home/macie/bojkoidx/config/ibkr.env
# Set: KILL_SWITCH=true
sudo systemctl restart bojkoidx
```

This blocks all new orders while keeping the service running for monitoring.

## Manual Deployment (alternative to deploy_idx.sh)

```bash
# On VM:
mkdir -p /home/macie/bojkoidx/{app,venv,logs,data/bars_idx,config}

# Clone repo:
git clone <YOUR_REPO_URL> /home/macie/bojkoidx/app

# Create venv:
python3 -m venv /home/macie/bojkoidx/venv
/home/macie/bojkoidx/venv/bin/pip install -r /home/macie/bojkoidx/app/requirements.txt

# Deploy env file:
cp /home/macie/bojkoidx/app/deploy/bojkoidx.env /home/macie/bojkoidx/config/ibkr.env
chmod 600 /home/macie/bojkoidx/config/ibkr.env

# Install service:
sudo cp /home/macie/bojkoidx/app/deploy/bojkoidx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bojkoidx
sudo systemctl start bojkoidx
```

## Upload 5m Bars CSV (from local machine)

```bash
# Build bars locally first if needed:
python -m scripts.build_h1_idx --ltf 5min

# Upload:
scp data/bars_idx/usatechidxusd_5m_bars.csv \
    macie@34.31.64.224:/home/macie/bojkoidx/data/bars_idx/
```

The CSV fallback is used only when IBKR historical data is unavailable at startup.
Normally the bot bootstraps 30 days of 5m history directly from IBKR.

## Key Files

| File | Purpose |
|---|---|
| `src/runners/run_live_idx.py` | Main live runner |
| `src/data/ibkr_marketdata_idx.py` | NAS100USD CFD market data (5m bars) |
| `src/core/strategy.py` | Live BOS+Pullback strategy |
| `src/execution/ibkr_exec.py` | IBKR order execution (supports CFD) |
| `deploy/bojkoidx.env` | Environment template |
| `deploy/bojkoidx.service` | systemd unit file |

## Strategy Configuration (production — do not change)

| Parameter | Value | Note |
|---|---|---|
| LTF | 5m | IBKR `5 mins` bars |
| HTF | 4h | aggregated from 5m |
| Session | 13–20 UTC | NYSE session |
| Risk/trade | 0.5% | configurable via RISK_FRACTION env |
| RR | 2.0 | fixed in runner |
| pullback_max_bars | 20 | ≈ 100 min TTL |
| pivot_lookback_ltf | 3 | |
| pivot_lookback_htf | 5 | |
| Backtest result | E=+0.46R, WR=46%, PF=1.49, DD=34.5R, n=694 (2021–2024) | |

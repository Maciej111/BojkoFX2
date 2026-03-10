#!/usr/bin/env bash
# patch-services.sh — poprawia serwisy systemd pod kątem daily restart IBKR

# ibgateway.service — bez zmian zasadniczych, tylko upewniamy sie ze Restart=always
sudo tee /etc/systemd/system/ibgateway.service > /dev/null << 'EOF'
[Unit]
Description=IB Gateway (IBC auto-login)
After=network.target

[Service]
Type=simple
User=macie
Group=macie
WorkingDirectory=/home/macie/ibgateway
Environment=HOME=/home/macie
Environment=DISPLAY=:99
ExecStart=/home/macie/bojkofx/start-gateway-ibc.sh
PIDFile=/tmp/ibgateway.pid
TimeoutStartSec=180
Restart=always
RestartSec=30s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log

[Install]
WantedBy=multi-user.target
EOF

# bojkofx.service — Restart=always, dłuższy ExecStartPre, usuwamy --confirm
sudo tee /etc/systemd/system/bojkofx.service > /dev/null << 'EOF'
[Unit]
Description=BojkoFx Trading Bot
After=ibgateway.service network.target
Requires=ibgateway.service

[Service]
Type=simple
User=macie
Group=macie
WorkingDirectory=/home/macie/bojkofx/app
EnvironmentFile=/home/macie/bojkofx/config/ibkr.env
ExecStartPre=/bin/sleep 90
ExecStart=/home/macie/bojkofx/venv/bin/python -m src.runners.run_paper_ibkr_gateway \
    --symbol EURUSD,GBPUSD,USDJPY \
    --allow_live_orders
Restart=always
RestartSec=60s
StandardOutput=append:/home/macie/bojkofx/logs/bojkofx.log
StandardError=append:/home/macie/bojkofx/logs/bojkofx.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo "[OK] Services reloaded"
sudo systemctl status ibgateway --no-pager | head -5
sudo systemctl status bojkofx --no-pager | head -5


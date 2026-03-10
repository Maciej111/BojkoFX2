#!/bin/bash
set -e

echo "=== Installing Flask ==="
/home/macie/bojkofx/venv/bin/pip install flask flask-cors

echo "=== Generating API key ==="
API_KEY=$(openssl rand -hex 16)
echo "GENERATED_KEY=${API_KEY}"

echo "=== Updating ibkr.env ==="
# Remove old entries if exist
sed -i '/^DASHBOARD_API_KEY=/d' /home/macie/bojkofx/config/ibkr.env
sed -i '/^DASHBOARD_PORT=/d'    /home/macie/bojkofx/config/ibkr.env
echo "DASHBOARD_API_KEY=${API_KEY}" >> /home/macie/bojkofx/config/ibkr.env
echo "DASHBOARD_PORT=8080"          >> /home/macie/bojkofx/config/ibkr.env
echo "Env updated."

echo "=== Creating systemd service ==="
cat > /tmp/bojkofx-dashboard.service << 'EOF'
[Unit]
Description=BojkoFx Trading Dashboard API
After=network.target

[Service]
Type=simple
User=macie
WorkingDirectory=/home/macie/bojkofx/app
EnvironmentFile=/home/macie/bojkofx/config/ibkr.env
ExecStart=/home/macie/bojkofx/venv/bin/python dashboard/app.py
Restart=always
RestartSec=10s
StandardOutput=append:/home/macie/bojkofx/logs/dashboard.log
StandardError=append:/home/macie/bojkofx/logs/dashboard.log

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/bojkofx-dashboard.service /etc/systemd/system/bojkofx-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable bojkofx-dashboard
sudo systemctl start bojkofx-dashboard
sleep 3
echo "=== Service status ==="
sudo systemctl is-active bojkofx-dashboard
echo "=== Last 5 log lines ==="
tail -5 /home/macie/bojkofx/logs/dashboard.log 2>/dev/null || echo "(no log yet)"
echo "=== Health check ==="
curl -s http://localhost:8080/api/health
echo ""
echo "=== DONE. API_KEY=${API_KEY} ==="


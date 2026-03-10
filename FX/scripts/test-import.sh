#!/usr/bin/env bash
cd /home/macie/bojkofx/app
/home/macie/bojkofx/venv/bin/python - << 'EOF'
from src.data.ibkr_marketdata import IBKRMarketData
m = IBKRMarketData()
print("reconnect:", hasattr(m, "reconnect"))
print("is_connected:", hasattr(m, "is_connected"))
print("_subscribed_symbols:", hasattr(m, "_subscribed_symbols"))
print("OK")
EOF


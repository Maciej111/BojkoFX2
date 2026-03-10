#!/usr/bin/env bash
cd /home/macie/bojkofx/app
git config user.email "bot@bojkofx.vm"
git config user.name "BojkoFx Bot"
git add src/data/ibkr_marketdata.py src/runners/run_paper_ibkr_gateway.py
git status
git commit -m "feat: add auto-reconnect to IBKRMarketData and main loop"
git log --oneline -3


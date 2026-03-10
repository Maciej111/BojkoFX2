# IBKR Paper Trading Integration
Interactive Brokers Paper Trading for the algorithmic trading system.
## Quick Start
### 1. Requirements
- Interactive Brokers Paper Account (free)
- TWS or IB Gateway installed
- API enabled in TWS/Gateway settings
### 2. Setup
```bash
pip install -r requirements.txt
```
### 3. Start TWS/Gateway
- Login with paper credentials
- Enable API (File -> Global Configuration -> API -> Settings)
- Port: 7497 (TWS Paper) or 4002 (Gateway Paper)
### 4. Run Dry Run Test
```bash
python -m src.runners.run_paper_ibkr --symbol EURUSD --dry_run 1
```
### 5. Enable Live Orders (Paper Account)
```bash
python -m src.runners.run_paper_ibkr --symbol EURUSD --dry_run 0 --allow_live_orders
```
## Key Features
- Real-time market data from IBKR
- H1 bar aggregation
- Bracket orders (entry + SL + TP)
- Risk management (0.5% per trade)
- Kill switch at 10% DD
- Complete logging to CSV
## Supported Symbols
- EURUSD, GBPUSD, USDJPY (FX pairs)
## Logs
All activity logged to: `logs/paper_trading.csv`
## Troubleshooting
**Connection failed?**
- Check TWS/Gateway is running
- Verify API is enabled
- Correct port (7497 or 4002)
**No signals?**
- Normal - strategy waits for setup
- May take hours/days
## Documentation
See full docs: `docs/integration/README_IBKR_PAPER.md` (to be created)
**Status:** Ready for testing
**Date:** 2026-02-20

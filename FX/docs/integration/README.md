# 🔌 Integration Documentation

IBKR paper trading integration guides and setup instructions.

---

## 🚀 Quick Start

**[README_IBKR_GATEWAY.md](../../README_IBKR_GATEWAY.md)** ⭐ **START HERE**

Complete setup guide for IBKR paper trading:
- Environment setup (config.yaml)
- Dependencies installation
- Dry run testing
- Live demo execution
- Monitoring & safety features

---

## 📋 Integration Status

**[INTEGRATION_COMPLETE.md](INTEGRATION_COMPLETE.md)**

Complete integration summary:
- ✅ Clean architecture (Core/Data/Execution/Runners)
- ✅ IBKR TWS/Gateway API implementation
- ✅ Order placement (LIMIT + SL/TP)
- ✅ Risk management & kill switch
- ✅ CSV logging

---

## 📊 Data Management

### EURUSD 2024 Rebuild:

**[EURUSD_2024_REBUILD_SUCCESS.md](EURUSD_2024_REBUILD_SUCCESS.md)**
- Full year 2024 data (12/12 months)
- 34,970 H1 bars (2021-2024)
- Complete OOS validation ready

**[EURUSD_2024_COMPLETION_STATUS.md](EURUSD_2024_COMPLETION_STATUS.md)**
- Data completion process
- Validation steps
- Quality checks

**[EURUSD_2024_DATA_STATUS.md](EURUSD_2024_DATA_STATUS.md)**
- Current data status
- Coverage analysis

**[EURUSD_2024_DOWNLOAD_FINAL_STATUS.md](EURUSD_2024_DOWNLOAD_FINAL_STATUS.md)**
- Download completion
- Source validation

### Data Organization:

**[DATA_SPLIT_REPORT.md](DATA_SPLIT_REPORT.md)**
- Tick data organization
- Year-by-year split
- Quality metrics per period

---

## 🏗️ Architecture

### New Structure:
```
src/
├── core/           # Pure strategy logic (no I/O)
├── data/           # Data sources (historical)
├── execution/      # Order execution (backtest + IBKR)
├── runners/        # Entry points
├── reporting/      # Logging & metrics
└── utils/          # Helpers
```

### Key Features:
- ✅ **Clean separation** of concerns
- ✅ **Testable** (core has zero dependencies)
- ✅ **Flexible** (easy to add new brokers)
- ✅ **Safe** (execution layer isolated)

---

## 🔐 Security

### Environment Variables:
```bash
KILL_SWITCH=false
```

**Never commit credentials to git!**

Template: `config/ibkr.env.example`

---

## 🛡️ Safety Features

### Risk Management:
- Position sizing: 0.5% per trade (default)
- Max positions: 2 total, 1 per symbol
- Daily loss limit: 2%
- Monthly DD stop: 15%

### Kill Switch:
- Auto-stop at 10% DD
- Manual override via ENV
- Logs all activity

### Dry Run Mode:
- Test without real orders
- Validates signals
- Logs intents only

---

## 📈 Expected Performance

### Conservative (0.5% risk, mild slippage):
- Expected return: ~27% annualized
- MaxDD: ~12%
- Symbols: EURUSD, GBPUSD, USDJPY, XAUUSD

---

## ✅ Setup Checklist

- [ ] IBKR paper account configured
- [ ] `config/config.yaml` updated with IBKR settings
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Dry run tested (1 week minimum)
- [ ] Logs verified (`logs/paper_trading_ibkr.csv`)
- [ ] Kill switch tested
- [ ] Ready for live demo orders

---

## 📝 Logging

### Event Types:
- `INTENT` - Signal generated
- `ORDER_PLACED` - Order submitted
- `FILL` - Order filled
- `TRADE_CLOSED` - Position closed
- `RISK_BLOCK` - Trade blocked by risk limits

### Metrics Tracked:
- Slippage (pips)
- Latency (ms)
- R-multiple realized
- PnL
- Spread at entry/exit

---

## 🎯 Next Steps

1. **Week 1:** Dry run validation
2. **Week 2:** Live demo orders
3. **Week 3-4:** Collect 20+ trades
4. **Week 5:** Performance analysis → GO/NO-GO

---

## 🆘 Support

**Setup issues?** → Check [README_IBKR_GATEWAY.md](../../README_IBKR_GATEWAY.md)

**Performance questions?** → See [../validation/](../validation/)

**Strategy details?** → See [../guides/](../guides/)

---

**Status:** ✅ Ready for dry run testing  
**Last Updated:** 2026-02-19


"""
IBKR Paper Trading Runner (legacy entry point)
-----------------------------------------------
Thin wrapper kept for backward compatibility.
For new deployments prefer run_paper_ibkr_gateway.py which uses Gateway
defaults (port 4002) and the full log format.
"""

import sys
import time
import os
from pathlib import Path
from ib_insync import IB

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config import Config
from src.core.strategy import TrendFollowingStrategy
from src.data.ibkr_marketdata import IBKRMarketData
from src.execution.ibkr_exec import IBKRExecutionEngine
from src.reporting.logger import TradingLogger


def main():
    import argparse

    parser = argparse.ArgumentParser(description='IBKR Paper Trading (legacy runner)')
    parser.add_argument('--symbol', type=str, default='EURUSD')
    parser.add_argument('--dry_run', type=int, default=1, help='1=dry run (no orders), 0=execute')
    parser.add_argument('--allow_live_orders', action='store_true',
                        help='Required for real execution (with dry_run=0)')
    parser.add_argument('--config', type=str, default='config/config.yaml')
    parser.add_argument('--host', type=str, default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--client_id', type=int, default=None)

    args = parser.parse_args()

    print("=" * 80)
    print("IBKR PAPER TRADING (legacy runner — prefer run_paper_ibkr_gateway.py)")
    print("=" * 80)

    config = Config.from_env(args.config)

    host = args.host or os.getenv('IBKR_HOST', config.ibkr.host)
    port = args.port or int(os.getenv('IBKR_PORT', str(config.ibkr.port)))
    client_id = args.client_id or int(os.getenv('IBKR_CLIENT_ID', str(config.ibkr.client_id)))

    dry_run = bool(args.dry_run)
    allow_live_orders = args.allow_live_orders or config.ibkr.allow_live_orders
    readonly = True if dry_run else config.ibkr.readonly
    kill_switch_env = getattr(config, '_kill_switch_from_env', False)

    print(f"Symbol           : {args.symbol}")
    print(f"Dry run          : {dry_run}")
    print(f"Allow live orders: {allow_live_orders}")
    print(f"IBKR             : {host}:{port}  clientId={client_id}")

    ib = IB()
    print(f"\n[IBKR] Connecting to {host}:{port}...")
    try:
        ib.connect(host, port, clientId=client_id, timeout=20)
        print("[IBKR] Connected")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        print("Tip: Gateway paper=4002, TWS paper=7497")
        sys.exit(1)

    strategy = TrendFollowingStrategy(config.strategy)

    marketdata = IBKRMarketData(
        host=host,
        port=port,
        client_id=client_id,
        historical_days=config.ibkr.historical_days,
    )
    marketdata.ib = ib
    marketdata.connected = True

    execution = IBKRExecutionEngine(
        ib=ib,
        risk_config=config.risk,
        readonly=readonly,
        allow_live_orders=allow_live_orders,
    )
    logger = TradingLogger(log_dir='logs')

    if kill_switch_env:
        execution.kill_switch_active = True
        print("[KILL_SWITCH] Activated from ENV")

    print(f"\n[IBKR] Subscribing to {args.symbol}...")
    if not marketdata.subscribe_symbol(args.symbol):
        print(f"[ERROR] Failed to subscribe to {args.symbol}")
        ib.disconnect()
        sys.exit(1)

    if not dry_run and allow_live_orders:
        confirm = input("\n[LIVE] REAL ORDERS will be placed. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted")
            ib.disconnect()
            sys.exit(0)

    print("\n[READY] Waiting for H1 bar close...\nPress Ctrl+C to stop\n")

    last_bar_count = 0
    try:
        while True:
            marketdata.update_bars(args.symbol)

            ltf_bars = marketdata.get_h1_bars(args.symbol)
            htf_bars = marketdata.get_h4_bars(args.symbol)

            if ltf_bars is None or len(ltf_bars) < 200:
                n = len(ltf_bars) if ltf_bars is not None else 0
                print(f"[INFO] Waiting for bars {n}/200")
                time.sleep(60)
                continue

            cur_count = marketdata.bar_count(args.symbol)
            if cur_count > last_bar_count:
                last_bar_count = cur_count
                print(f"\n[BAR] H1 closed: {ltf_bars.index[-1]}")

                intents = strategy.process_bar(ltf_bars, htf_bars, len(ltf_bars) - 1)

                for intent in intents:
                    intent.symbol = args.symbol
                    logger.log_intent(intent, notes="run_paper_ibkr legacy")
                    order_id = execution.execute_intent(intent)
                    if order_id is None:
                        logger.log_risk_block(intent, "RISK_BLOCK or SIZING_ERROR")
                    elif order_id > 0:
                        logger.log_order_placed(intent, str(order_id))

            # Poll exits (no-op in dry run)
            exit_rows = execution.poll_order_events()
            for row in exit_rows:
                logger.log_exit_row(row)
                print(f"[EXIT] {row.get('symbol')} {row.get('exit_reason')} R={row.get('realized_R','?')}")

            execution.check_kill_switch()
            if execution.kill_switch_active:
                logger.log_kill_switch("Drawdown threshold exceeded")
                print("\n[KILL_SWITCH] Trading stopped")
                break

            time.sleep(30)

    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc()
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("[IBKR] Disconnected")

    print(f"\nSession ended. Logs: logs/paper_trading_ibkr.csv")


if __name__ == "__main__":
    main()


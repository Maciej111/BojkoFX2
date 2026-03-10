#!/usr/bin/env python3
"""
test_order_roundtrip.py — EURUSD round-trip
Konto DUP994821: waluta bazowa PLN, cash EUR 1M
=> SELL EURUSD (sprzedajemy EUR, dostajemy USD) -> BUY EURUSD (zamknięcie)
"""
import logging, os, sys, time
from datetime import datetime, timezone
from ib_insync import IB, Forex, MarketOrder, Trade

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s — %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("rt_test")

HOST      = os.getenv("IBKR_HOST", "127.0.0.1")
PORT      = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID = 88
SYMBOL    = "EURUSD"
UNITS     = 25000   # min IDEALPRO = 20k EUR
HOLD_S    = 5
WAIT_S    = 30

READONLY   = os.getenv("IBKR_READONLY", "true").lower()
ALLOW_LIVE = os.getenv("ALLOW_LIVE_ORDERS", "false").lower()
if READONLY == "true" or ALLOW_LIVE != "true":
    print("SAFETY BLOCK — ustaw IBKR_READONLY=false i ALLOW_LIVE_ORDERS=true")
    sys.exit(1)


def wait_fill(ib, trade, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        ib.sleep(1)
        s = trade.orderStatus.status
        f = trade.orderStatus.filled
        log.info("  status=%-14s filled=%.0f", s, f)
        if s == "Filled":
            return True
        if s in ("Cancelled", "Inactive"):
            log.error("  Odrzucone/Inactive: %s", s)
            return False
    return False


def main():
    ib = IB()
    print(f"\n{'='*56}")
    print(f"  ROUND-TRIP TEST  {SYMBOL}  {UNITS} units")
    print(f"  SELL EUR->USD (open),  BUY EUR<-USD (close)")
    print(f"{'='*56}")

    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=15)
    print(f"\n[1] Połączono — konto: {ib.managedAccounts()}")
    for av in ib.accountValues():
        if av.tag == "CashBalance":
            print(f"    Cash {av.currency}: {float(av.value):,.2f}")

    contract = Forex(SYMBOL)
    ib.qualifyContracts(contract)
    print(f"    Kontrakt: {contract.localSymbol} @ {contract.exchange}")

    # ── OPEN: SELL EURUSD ─────────────────────────────────────────────────────
    print(f"\n[2] SELL MARKET {UNITS} {SYMBOL} (sprzedajemy EUR za USD)...")
    sell_order = MarketOrder("SELL", UNITS)
    sell_order.orderRef = f"rt_sell_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    t0 = datetime.now(timezone.utc)

    trade_open: Trade = ib.placeOrder(contract, sell_order)
    print(f"    Wysłano orderId={trade_open.order.orderId}")

    if not wait_fill(ib, trade_open, WAIT_S):
        log.error("SELL nie wypełniony — abort.")
        ib.disconnect(); sys.exit(1)

    open_price = trade_open.orderStatus.avgFillPrice
    lat_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
    print(f"\n    ✅ SELL wypełniony @ {open_price:.5f}  (latencja {lat_ms:.0f} ms)")

    # ── HOLD ─────────────────────────────────────────────────────────────────
    print(f"\n[3] Trzymam {HOLD_S}s...")
    ib.sleep(HOLD_S)
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(2)
    bid = ticker.bid or open_price
    ask = ticker.ask or open_price
    print(f"    Bid/Ask: {bid:.5f} / {ask:.5f}")

    # ── CLOSE: BUY EURUSD ────────────────────────────────────────────────────
    print(f"\n[4] BUY MARKET {UNITS} {SYMBOL} (zamknięcie)...")
    buy_order = MarketOrder("BUY", UNITS)
    buy_order.orderRef = f"rt_buy_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    trade_close: Trade = ib.placeOrder(contract, buy_order)
    print(f"    Wysłano orderId={trade_close.order.orderId}")

    if not wait_fill(ib, trade_close, WAIT_S):
        log.error("BUY zamknięcie nie wypełnione!")
        ib.disconnect(); sys.exit(1)

    close_price = trade_close.orderStatus.avgFillPrice
    pnl = (open_price - close_price) * UNITS  # SELL open - BUY close

    print(f"\n    ✅ BUY zamknięcie @ {close_price:.5f}")

    # ── Podsumowanie ─────────────────────────────────────────────────────────
    dur = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n{'='*56}")
    print(f"  PODSUMOWANIE ROUND-TRIP")
    print(f"  Symbol       : {SYMBOL}  ({UNITS} units)")
    print(f"  SELL (open)  : {open_price:.5f}")
    print(f"  BUY  (close) : {close_price:.5f}")
    print(f"  P&L          : ${pnl:+.2f}")
    print(f"  Czas         : {dur:.1f}s")
    print(f"  Status       : ✅ SUKCES")
    print(f"{'='*56}\n")

    ib.disconnect()


if __name__ == "__main__":
    main()


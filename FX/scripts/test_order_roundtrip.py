#!/usr/bin/env python3
"""
test_order_roundtrip.py
=======================
Manualny test: złóż zlecenie BUY MARKET na EURUSD, odczekaj wypełnienie,
następnie zamknij pozycję zleceniem SELL MARKET.

Wymaga:
  - IB Gateway działającego na 127.0.0.1:4002
  - IBKR_READONLY=false, ALLOW_LIVE_ORDERS=true w środowisku

Uruchomienie:
  cd /home/macie/bojkofx/app
  source /home/macie/bojkofx/config/ibkr.env
  /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

from ib_insync import IB, Forex, MarketOrder, Trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("order_test")

# ── Config ─────────────────────────────────────────────────────────────────────
HOST        = os.getenv("IBKR_HOST", "127.0.0.1")
PORT        = int(os.getenv("IBKR_PORT", "4002"))
CLIENT_ID   = 88          # osobny client_id żeby nie kolidować z botem (7)
SYMBOL      = "EURUSD"
UNITS       = 2000        # minimalna sensowna wielkość dla Forex w IB (1000+)
WAIT_FILL_S = 30          # max sekund czekania na wypełnienie
HOLD_S      = 15          # ile sekund trzymamy pozycję przed zamknięciem

# ── Safety guard ───────────────────────────────────────────────────────────────
READONLY         = os.getenv("IBKR_READONLY", "true").lower()
ALLOW_LIVE       = os.getenv("ALLOW_LIVE_ORDERS", "false").lower()

if READONLY == "true" or ALLOW_LIVE != "true":
    print("\n⚠  SAFETY BLOCK — zmienne środowiskowe blokują zlecenia:")
    print(f"   IBKR_READONLY     = {READONLY}   (musi być: false)")
    print(f"   ALLOW_LIVE_ORDERS = {ALLOW_LIVE}  (musi być: true)")
    print("\n   Uruchom po załadowaniu ibkr.env:")
    print("   source /home/macie/bojkofx/config/ibkr.env")
    sys.exit(1)


def wait_for_fill(ib: IB, trade: Trade, timeout: int) -> bool:
    """Polling wait until trade is Filled or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ib.sleep(1)
        status = trade.orderStatus.status
        filled = trade.orderStatus.filled
        log.info("  status=%-12s  filled=%.0f", status, filled)
        if status == "Filled":
            return True
        if status in ("Cancelled", "Inactive"):
            log.error("  Zlecenie anulowane/nieaktywne: %s", status)
            return False
    return False


def main():
    ib = IB()

    # ── 1. Połączenie ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  TEST ROUND-TRIP ORDER — {SYMBOL}  {UNITS} units")
    print(f"{'='*60}")
    print(f"\n[1] Łączenie z IB Gateway {HOST}:{PORT} (clientId={CLIENT_ID})...")

    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10)
    except Exception as e:
        log.error("Nie można połączyć się z Gateway: %s", e)
        sys.exit(1)

    account = ib.managedAccounts()
    print(f"    ✓ Połączono — konto: {account}")

    # Equity
    equity = None
    for av in ib.accountValues():
        if av.tag == "NetLiquidation" and av.currency == "USD":
            equity = float(av.value)
            break
    print(f"    ✓ Equity konta: ${equity:,.2f}" if equity else "    ~ Equity: N/A")

    contract = Forex(SYMBOL)
    ib.qualifyContracts(contract)
    print(f"    ✓ Kontrakt: {contract.symbol}/{contract.currency} @ {contract.exchange}")

    # ── 2. BUY MARKET ─────────────────────────────────────────────────────────
    print(f"\n[2] Składanie zlecenia BUY MARKET {UNITS} {SYMBOL}...")
    buy_order = MarketOrder("BUY", UNITS)
    buy_order.orderRef = f"test_buy_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    buy_trade: Trade = ib.placeOrder(contract, buy_order)
    t_buy_sent = datetime.now(timezone.utc)
    print(f"    ✓ Zlecenie wysłane — orderId={buy_trade.order.orderId}")
    print(f"    ⏳ Czekam na wypełnienie (max {WAIT_FILL_S}s)...")

    filled = wait_for_fill(ib, buy_trade, WAIT_FILL_S)

    if not filled:
        log.error("BUY nie wypełniony w czasie %ds — anulowanie.", WAIT_FILL_S)
        ib.cancelOrder(buy_order)
        ib.disconnect()
        sys.exit(1)

    buy_fill_price = buy_trade.orderStatus.avgFillPrice
    t_buy_filled = datetime.now(timezone.utc)
    latency_ms = (t_buy_filled - t_buy_sent).total_seconds() * 1000

    print(f"\n    ✅ BUY wypełniony!")
    print(f"       Cena wejścia : {buy_fill_price:.5f}")
    print(f"       Czas         : {t_buy_filled.strftime('%H:%M:%S')}")
    print(f"       Latencja     : {latency_ms:.0f} ms")

    # ── 3. Trzymamy pozycję ───────────────────────────────────────────────────
    print(f"\n[3] Trzymam pozycję przez {HOLD_S} sekund...")
    ib.sleep(HOLD_S)

    # Bieżąca cena
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(2)
    current_bid = ticker.bid or buy_fill_price
    current_ask = ticker.ask or buy_fill_price
    unrealized = (current_bid - buy_fill_price) * UNITS
    print(f"    Bid/Ask teraz: {current_bid:.5f} / {current_ask:.5f}")
    print(f"    Niezrealizowany P&L: ${unrealized:.2f}")

    # ── 4. SELL MARKET (zamknięcie) ───────────────────────────────────────────
    print(f"\n[4] Zamykanie pozycji — SELL MARKET {UNITS} {SYMBOL}...")
    sell_order = MarketOrder("SELL", UNITS)
    sell_order.orderRef = f"test_sell_{datetime.now(timezone.utc).strftime('%H%M%S')}"

    sell_trade: Trade = ib.placeOrder(contract, sell_order)
    t_sell_sent = datetime.now(timezone.utc)
    print(f"    ✓ Zlecenie wysłane — orderId={sell_trade.order.orderId}")
    print(f"    ⏳ Czekam na wypełnienie (max {WAIT_FILL_S}s)...")

    filled = wait_for_fill(ib, sell_trade, WAIT_FILL_S)

    if not filled:
        log.error("SELL nie wypełniony w czasie %ds!", WAIT_FILL_S)
        ib.disconnect()
        sys.exit(1)

    sell_fill_price = sell_trade.orderStatus.avgFillPrice
    t_sell_filled = datetime.now(timezone.utc)

    # ── 5. Podsumowanie ───────────────────────────────────────────────────────
    pnl = (sell_fill_price - buy_fill_price) * UNITS
    duration_s = (t_sell_filled - t_buy_sent).total_seconds()

    print(f"\n    ✅ SELL wypełniony!")
    print(f"       Cena wyjścia : {sell_fill_price:.5f}")

    print(f"\n{'='*60}")
    print(f"  PODSUMOWANIE ROUND-TRIP")
    print(f"{'='*60}")
    print(f"  Symbol          : {SYMBOL}")
    print(f"  Jednostki       : {UNITS:,}")
    print(f"  Cena wejścia    : {buy_fill_price:.5f}")
    print(f"  Cena wyjścia    : {sell_fill_price:.5f}")
    print(f"  Spread wejścia  : {(buy_fill_price - current_bid):.5f}  (~{abs(buy_fill_price - current_bid)/0.0001:.1f} pips)")
    print(f"  P&L             : ${pnl:+.2f}")
    print(f"  Czas trwania    : {duration_s:.1f}s")
    print(f"  Status          : {'✅ SUKCES' if filled else '❌ BŁĄD'}")
    print(f"{'='*60}\n")

    ib.disconnect()
    print("  Rozłączono z Gateway.")


if __name__ == "__main__":
    main()


"""
Restart safety tests — verifies that IBKRExecutionEngine correctly
persists and restores trailing stop state across a simulated restart.

Approach
--------
1.  Build a SQLiteStateStore in :memory:.
2.  Directly insert an `orders` row that represents an open position
    with a trailing stop (trail_state_json populated by save_trail_state).
3.  Construct a *new* IBKRExecutionEngine (simulating a process restart)
    backed by a mock IB object + the same store.
4.  Call restore_positions_from_ibkr() with a hand-crafted mock of IBKR's
    open order / position data.
5.  Assert that the rebuilt _OrderRecord faithfully reflects the saved
    trailing stop state.

Run: pytest tests/test_restart_state_restore.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone
from typing import List, Optional

from src.core.state_store import (
    SQLiteStateStore,
    DBOrderRecord,
    OrderStatus,
)
from src.core.models import Side


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _minimal_order_row(
    store: SQLiteStateStore,
    parent_id: int,
    symbol: str,
    side: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    status: str = "OPEN",
) -> None:
    """Insert an order row directly via upsert_order so the DB schema is satisfied."""
    from src.core.models import OrderIntent, OrderType
    from src.core.state_store import DBOrderRecord

    intent = OrderIntent(
        signal_id=f"test_signal_{parent_id}",
        timestamp=_utc_now(),
        symbol=symbol,
        side=Side.LONG if side == "LONG" else Side.SHORT,
        entry_type=OrderType.LIMIT,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        ttl_bars=40,
        risk_R=1.0,
    )
    rec = DBOrderRecord(
        parent_id=parent_id,
        intent=intent,
        status=status,
        ibkr_ids={
            "parent_id": parent_id,
            "tp_id":     parent_id + 1,
            "sl_id":     parent_id + 2,
        },
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    store.upsert_order(rec)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  trail state persistence in SQLiteStateStore                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class TestTrailStatePersistence:
    """Unit tests for save_trail_state / load_trail_state in the store."""

    def test_load_missing_returns_none(self):
        store = SQLiteStateStore(":memory:")
        result = store.load_trail_state(parent_id=99999)
        assert result is None

    def test_save_and_load_roundtrip(self):
        store = SQLiteStateStore(":memory:")
        _minimal_order_row(store, parent_id=1001, symbol="EURUSD",
                           side="LONG", entry_price=1.0800,
                           sl_price=1.0750, tp_price=1.0900)

        store.save_trail_state(
            parent_id=1001,
            activated=True,
            sl_price=1.0800,
            sl_ibkr_id=555,
        )

        loaded = store.load_trail_state(1001)
        assert loaded is not None
        assert loaded["activated"] is True
        assert loaded["sl_price"] == pytest.approx(1.0800)
        assert loaded["sl_ibkr_id"] == 555

    def test_overwrite_updates_state(self):
        store = SQLiteStateStore(":memory:")
        _minimal_order_row(store, parent_id=1002, symbol="USDJPY",
                           side="LONG", entry_price=150.0,
                           sl_price=148.0, tp_price=154.0)

        store.save_trail_state(1002, activated=False, sl_price=148.0, sl_ibkr_id=100)
        store.save_trail_state(1002, activated=True,  sl_price=151.0, sl_ibkr_id=101)

        loaded = store.load_trail_state(1002)
        assert loaded["activated"] is True
        assert loaded["sl_price"] == pytest.approx(151.0)
        assert loaded["sl_ibkr_id"] == 101

    def test_unarmed_position_returns_none(self):
        """A position with no trail state set should return None."""
        store = SQLiteStateStore(":memory:")
        _minimal_order_row(store, parent_id=1003, symbol="GBPUSD",
                           side="SHORT", entry_price=1.2700,
                           sl_price=1.2750, tp_price=1.2600)

        result = store.load_trail_state(1003)
        assert result is None, "Expected None when trail state was never saved"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  IBKRExecutionEngine trail state restore (integration test via mocked IB)  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _make_mock_ib_open_order(
    parent_id: int,
    tp_id: int,
    sl_id: int,
    symbol: str,
    order_type: str = "LMT",
    action: str = "BUY",
    lmt_price: float = 1.0800,
    aux_price: float = 1.0750,
    status: str = "Filled",
):
    """Build a minimal mock ib_insync Trade object that restore_positions_from_ibkr expects."""
    # ib_insync Trade composition: .order, .contract, .orderStatus
    order = MagicMock()
    order.orderId       = parent_id
    order.parentId      = 0
    order.orderType     = order_type
    order.action        = action
    order.lmtPrice      = lmt_price
    order.auxPrice      = aux_price
    order.totalQuantity = 1000

    contract = MagicMock()
    contract.symbol     = symbol
    contract.secType    = "CASH"  # FX
    contract.currency   = "USD"

    order_status = MagicMock()
    order_status.status = status

    trade = MagicMock()
    trade.order       = order
    trade.contract    = contract
    trade.orderStatus = order_status
    return trade


def _make_tp_order(parent_id: int, tp_id: int, symbol: str,
                   action: str = "SELL", tp_price: float = 1.0900):
    order = MagicMock()
    order.orderId       = tp_id
    order.parentId      = parent_id
    order.orderType     = "LMT"
    order.action        = action
    order.lmtPrice      = tp_price
    order.auxPrice      = 0.0
    order.totalQuantity = 1000
    contract = MagicMock()
    contract.symbol     = symbol
    contract.secType    = "CASH"
    contract.currency   = "USD"
    status = MagicMock()
    status.status = "Submitted"
    trade = MagicMock()
    trade.order = order
    trade.contract = contract
    trade.orderStatus = status
    return trade


def _make_sl_order(parent_id: int, sl_id: int, symbol: str,
                   action: str = "SELL", sl_price: float = 1.0750):
    order = MagicMock()
    order.orderId       = sl_id
    order.parentId      = parent_id
    order.orderType     = "STP"
    order.action        = action
    order.auxPrice      = sl_price
    order.lmtPrice      = 0.0
    order.totalQuantity = 1000
    contract = MagicMock()
    contract.symbol     = symbol
    contract.secType    = "CASH"
    contract.currency   = "USD"
    status = MagicMock()
    status.status = "Submitted"
    trade = MagicMock()
    trade.order = order
    trade.contract = contract
    trade.orderStatus = status
    return trade


class TestRestorePositionsFromIBKR:
    """
    Simulates how IBKRExecutionEngine.restore_positions_from_ibkr() rebuilds
    _OrderRecord from the DB + IBKR order feed, and verify trail state
    is correctly restored.
    """

    def _make_engine(self, store: SQLiteStateStore):
        """Construct engine with a mocked (non-connecting) IB instance."""
        try:
            from src.execution.ibkr_exec import IBKRExecutionEngine
            from src.core.config import RiskConfig
        except ImportError as err:
            pytest.skip(f"IBKRExecutionEngine not importable: {err}")

        ib = MagicMock()
        ib.isConnected.return_value = False   # skip _refresh_equity
        risk = RiskConfig(
            risk_per_trade_pct=1.0,
            max_open_trades=5,
            max_daily_drawdown_pct=5.0,
        )
        trail_cfg = {
            "EURUSD": {"enabled": True, "ts_r": 2.0, "lock_r": 0.5},
        }
        return IBKRExecutionEngine(
            ib=ib,
            risk_config=risk,
            readonly=True,
            allow_live_orders=False,
            store=store,
            trail_config_by_symbol=trail_cfg,
        )

    def _seed_db(
        self,
        store: SQLiteStateStore,
        parent_id: int = 2001,
        tp_id: int = 2002,
        sl_id: int = 2003,
        symbol: str = "EURUSD",
    ) -> None:
        """Insert a Filled order + persist a trail state."""
        from src.core.models import OrderIntent, OrderType
        from src.core.state_store import DBOrderRecord

        intent = OrderIntent(
            signal_id="restart_test_signal",
            timestamp=_utc_now(),
            symbol=symbol,
            side=Side.LONG,
            entry_type=OrderType.LIMIT,
            entry_price=1.0800,
            sl_price=1.0750,
            tp_price=1.0900,
            ttl_bars=40,
            risk_R=1.0,
        )
        rec = DBOrderRecord(
            parent_id=parent_id,
            intent=intent,
            status="OPEN",
            ibkr_ids={
                "parent_id": parent_id,
                "tp_id":     tp_id,
                "sl_id":     sl_id,
            },
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        store.upsert_order(rec)

        # Persist trail state as if it was activated mid-trade
        store.save_trail_state(
            parent_id=parent_id,
            activated=True,
            sl_price=1.0820,
            sl_ibkr_id=sl_id,
        )

    def test_trail_state_restored_after_restart(self):
        """
        After restart, restore_positions_from_ibkr must reload trail state
        (activated=True, sl_price, sl_ibkr_id) into the rebuilt _OrderRecord.
        """
        store = SQLiteStateStore(":memory:")
        parent_id, tp_id, sl_id = 2001, 2002, 2003
        symbol = "EURUSD"

        self._seed_db(store, parent_id=parent_id, tp_id=tp_id, sl_id=sl_id, symbol=symbol)

        engine = self._make_engine(store)

        # Mock IB's open trades: parent (Filled), TP (Submitted), SL (Submitted)
        mock_trades = [
            _make_mock_ib_open_order(
                parent_id=parent_id, tp_id=tp_id, sl_id=sl_id,
                symbol=symbol, order_type="LMT",
                action="BUY", lmt_price=1.0800, status="Filled",
            ),
            _make_tp_order(parent_id=parent_id, tp_id=tp_id,
                           symbol=symbol, action="SELL", tp_price=1.0900),
            _make_sl_order(parent_id=parent_id, sl_id=sl_id,
                           symbol=symbol, action="SELL", sl_price=1.0750),
        ]
        engine.ib.openTrades.return_value = mock_trades

        # Simulate restart: call restore
        restored, _ = engine.restore_positions_from_ibkr(known_symbols=[symbol])

        assert restored >= 1, "Expected at least one position to be restored"

        # Check _records
        assert parent_id in engine._records, "parent_id not in _records after restore"
        record = engine._records[parent_id]

        assert record.trail_activated is True, \
            f"trail_activated should be True, got {record.trail_activated}"
        assert record.trail_sl == pytest.approx(1.0820), \
            f"trail_sl should be 1.0820, got {record.trail_sl}"
        assert record.trail_sl_ibkr_id == sl_id, \
            f"trail_sl_ibkr_id should be {sl_id}, got {record.trail_sl_ibkr_id}"

    def test_no_trail_state_leaves_defaults(self):
        """
        A position with no trail state saved should restore with default values
        (trail_activated=False, trail_sl=0.0).
        """
        store = SQLiteStateStore(":memory:")
        parent_id, tp_id, sl_id = 3001, 3002, 3003
        symbol = "EURUSD"

        # Insert order WITHOUT saving trail state
        from src.core.models import OrderIntent, OrderType
        from src.core.state_store import DBOrderRecord

        intent = OrderIntent(
            signal_id="no_trail_test",
            timestamp=_utc_now(),
            symbol=symbol,
            side=Side.LONG,
            entry_type=OrderType.LIMIT,
            entry_price=1.0800,
            sl_price=1.0750,
            tp_price=1.0900,
            ttl_bars=40,
            risk_R=1.0,
        )
        rec = DBOrderRecord(
            parent_id=parent_id,
            intent=intent,
            status="OPEN",
            ibkr_ids={
                "parent_id": parent_id,
                "tp_id":     tp_id,
                "sl_id":     sl_id,
            },
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        store.upsert_order(rec)
        # No save_trail_state call — trail state is absent

        engine = self._make_engine(store)

        mock_trades = [
            _make_mock_ib_open_order(
                parent_id=parent_id, tp_id=tp_id, sl_id=sl_id,
                symbol=symbol, order_type="LMT",
                action="BUY", lmt_price=1.0800, status="Filled",
            ),
            _make_tp_order(parent_id=parent_id, tp_id=tp_id,
                           symbol=symbol, action="SELL", tp_price=1.0900),
            _make_sl_order(parent_id=parent_id, sl_id=sl_id,
                           symbol=symbol, action="SELL", sl_price=1.0750),
        ]
        engine.ib.openTrades.return_value = mock_trades

        engine.restore_positions_from_ibkr(known_symbols=[symbol])

        if parent_id in engine._records:
            record = engine._records[parent_id]
            assert record.trail_activated is False, \
                "No trail state saved — trail_activated should remain False"
            assert record.trail_sl == pytest.approx(0.0), \
                "No trail state saved — trail_sl should remain 0.0"

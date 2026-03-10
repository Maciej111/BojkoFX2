"""
Unit tests for src/core/state_store.py

Run: pytest tests/test_state_store.py -v
"""

import json
import pytest
from pathlib import Path

from src.core.state_store import (
    BosInfo,
    DBOrderRecord,
    OrderStatus,
    PivotInfo,
    SQLiteStateStore,
    StrategyState,
    make_intent_id,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    s = SQLiteStateStore(tmp_path / "test_state.db")
    s.migrate()
    return s


# ── Migration / schema ────────────────────────────────────────────────────────

class TestMigration:
    def test_tables_created(self, store: SQLiteStateStore):
        cur = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {r["name"] for r in cur.fetchall()}
        assert "strategy_state" in tables
        assert "orders" in tables
        assert "risk_state" in tables
        assert "events" in tables
        assert "schema_version" in tables

    def test_schema_version_is_current(self, store: SQLiteStateStore):
        cur = store._conn.execute("SELECT version FROM schema_version")
        assert cur.fetchone()["version"] == 3

    def test_migrate_idempotent(self, store: SQLiteStateStore):
        store.migrate()   # second call must not raise
        cur = store._conn.execute("SELECT version FROM schema_version")
        assert cur.fetchone()["version"] == 3


# ── Strategy state ────────────────────────────────────────────────────────────

class TestStrategyState:
    def test_load_missing_returns_none(self, store: SQLiteStateStore):
        assert store.load_strategy_state("EURUSD") is None

    def test_save_and_load(self, store: SQLiteStateStore):
        state = StrategyState(
            symbol="EURUSD",
            last_processed_bar_ts="2026-03-03T21:00:00Z",
            last_pivot_high=PivotInfo(price=1.1620, bar_ts="2026-03-03T18:00:00Z", idx=42),
            last_pivot_low=PivotInfo(price=1.1500, bar_ts="2026-03-03T10:00:00Z", idx=10),
            last_bos=BosInfo(direction="LONG", level=1.1610, bar_ts="2026-03-03T20:00:00Z"),
        )
        store.save_strategy_state(state)
        loaded = store.load_strategy_state("EURUSD")
        assert loaded is not None
        assert loaded.symbol == "EURUSD"
        assert loaded.last_processed_bar_ts == "2026-03-03T21:00:00Z"
        assert loaded.last_pivot_high.price == pytest.approx(1.1620)
        assert loaded.last_pivot_low.idx == 10
        assert loaded.last_bos.direction == "LONG"
        assert loaded.last_bos.level == pytest.approx(1.1610)

    def test_upsert_overwrites(self, store: SQLiteStateStore):
        state = StrategyState(symbol="USDJPY",
                              last_processed_bar_ts="2026-03-03T20:00:00Z")
        store.save_strategy_state(state)
        state.last_processed_bar_ts = "2026-03-03T21:00:00Z"
        store.save_strategy_state(state)
        loaded = store.load_strategy_state("USDJPY")
        assert loaded.last_processed_bar_ts == "2026-03-03T21:00:00Z"

    def test_load_all(self, store: SQLiteStateStore):
        for sym in ("EURUSD", "USDJPY", "USDCHF"):
            store.save_strategy_state(StrategyState(symbol=sym))
        all_states = store.load_all_strategy_states()
        assert set(all_states.keys()) == {"EURUSD", "USDJPY", "USDCHF"}

    def test_null_pivots_round_trip(self, store: SQLiteStateStore):
        state = StrategyState(symbol="AUDJPY", last_processed_bar_ts="2026-03-03T21:00:00Z")
        store.save_strategy_state(state)
        loaded = store.load_strategy_state("AUDJPY")
        assert loaded.last_pivot_high is None
        assert loaded.last_pivot_low is None
        assert loaded.last_bos is None


# ── Order records ─────────────────────────────────────────────────────────────

class TestOrders:
    def _make_rec(self, symbol="EURUSD", status=OrderStatus.CREATED,
                  parent_id=0, suffix="") -> DBOrderRecord:
        intent_id = make_intent_id(symbol, "LONG", 1.1610, f"2026-03-03T20:00:00Z{suffix}")
        return DBOrderRecord(
            intent_id=intent_id,
            symbol=symbol,
            intent_json={"symbol": symbol, "side": "LONG", "entry_price": 1.1615},
            status=status,
            parent_id=parent_id,
        )

    def test_insert_new(self, store: SQLiteStateStore):
        rec = self._make_rec()
        result = store.upsert_order(rec)
        assert result is True
        loaded = store.get_order_by_intent_id(rec.intent_id)
        assert loaded is not None
        assert loaded.symbol == "EURUSD"
        assert loaded.status == OrderStatus.CREATED

    def test_intent_id_unique_blocks_duplicate(self, store: SQLiteStateStore):
        rec = self._make_rec()
        store.upsert_order(rec)
        # Second upsert with same intent_id but CREATED status — should NOT
        # downgrade existing status (idempotent).
        rec2 = self._make_rec()
        rec2.status = OrderStatus.CREATED
        store.upsert_order(rec2)
        loaded = store.get_order_by_intent_id(rec.intent_id)
        # Status should remain CREATED (no downgrade)
        assert loaded.status == OrderStatus.CREATED

    def test_status_upgrades_forward(self, store: SQLiteStateStore):
        rec = self._make_rec(parent_id=100)
        store.upsert_order(rec)
        # Upgrade CREATED → PENDING
        rec.status = OrderStatus.PENDING
        store.upsert_order(rec)
        loaded = store.get_order_by_intent_id(rec.intent_id)
        assert loaded.status == OrderStatus.PENDING

    def test_status_does_not_downgrade(self, store: SQLiteStateStore):
        rec = self._make_rec(parent_id=101, status=OrderStatus.FILLED)
        store.upsert_order(rec)
        rec.status = OrderStatus.SENT   # older state
        store.upsert_order(rec)
        loaded = store.get_order_by_intent_id(rec.intent_id)
        assert loaded.status == OrderStatus.FILLED

    def test_update_order_status(self, store: SQLiteStateStore):
        rec = self._make_rec(parent_id=200, status=OrderStatus.PENDING)
        store.upsert_order(rec)
        store.update_order_status(200, OrderStatus.FILLED,
                                  ibkr_ids={"parent": 200, "tp": 201, "sl": 202})
        loaded = store.get_order_by_parent_id(200)
        assert loaded.status == OrderStatus.FILLED
        assert loaded.ibkr_ids_json["tp"] == 201

    def test_get_orders_by_status(self, store: SQLiteStateStore):
        store.upsert_order(self._make_rec(status=OrderStatus.PENDING,
                                          parent_id=300, suffix="a"))
        store.upsert_order(self._make_rec(status=OrderStatus.FILLED,
                                          parent_id=301, suffix="b"))
        store.upsert_order(self._make_rec(status=OrderStatus.PENDING,
                                          parent_id=302, suffix="c"))
        pending = store.get_orders_by_status([OrderStatus.PENDING])
        assert len(pending) == 2

    def test_multiple_symbols(self, store: SQLiteStateStore):
        for sym in ("EURUSD", "USDJPY"):
            rec = self._make_rec(symbol=sym, suffix=sym)
            store.upsert_order(rec)
        all_orders = store.get_orders_by_status([OrderStatus.CREATED])
        symbols = {o.symbol for o in all_orders}
        assert "EURUSD" in symbols
        assert "USDJPY" in symbols


# ── Risk state ────────────────────────────────────────────────────────────────

class TestRiskState:
    def test_save_and_load(self, store: SQLiteStateStore):
        store.save_risk_state("peak_equity", 42191.53)
        store.save_risk_state("kill_switch_active", False)
        state = store.load_risk_state()
        assert state["peak_equity"] == pytest.approx(42191.53)
        assert state["kill_switch_active"] is False

    def test_overwrite(self, store: SQLiteStateStore):
        store.save_risk_state("peak_equity", 100.0)
        store.save_risk_state("peak_equity", 200.0)
        state = store.load_risk_state()
        assert state["peak_equity"] == pytest.approx(200.0)


# ── Events ────────────────────────────────────────────────────────────────────

class TestEvents:
    def test_append_and_read(self, store: SQLiteStateStore):
        store.append_event("ORDER_SENT", {"parent_id": 123, "symbol": "EURUSD"})
        store.append_event("EXIT_TP", {"parent_id": 123, "R": 2.97})
        events = store.get_recent_events(10)
        assert len(events) == 2
        types = [e["event_type"] for e in events]
        assert "ORDER_SENT" in types
        assert "EXIT_TP" in types

    def test_events_ordered_desc(self, store: SQLiteStateStore):
        for i in range(5):
            store.append_event("TEST", {"i": i})
        events = store.get_recent_events(5)
        ids = [e["id"] for e in events]
        assert ids == sorted(ids, reverse=True)


# ── Intent ID ─────────────────────────────────────────────────────────────────

class TestMakeIntentId:
    def test_deterministic(self):
        a = make_intent_id("EURUSD", "LONG", 1.1610, "2026-03-03T20:00:00Z")
        b = make_intent_id("EURUSD", "LONG", 1.1610, "2026-03-03T20:00:00Z")
        assert a == b

    def test_different_side(self):
        a = make_intent_id("EURUSD", "LONG",  1.1610, "2026-03-03T20:00:00Z")
        b = make_intent_id("EURUSD", "SHORT", 1.1610, "2026-03-03T20:00:00Z")
        assert a != b

    def test_different_bar_ts(self):
        a = make_intent_id("EURUSD", "LONG", 1.1610, "2026-03-03T20:00:00Z")
        b = make_intent_id("EURUSD", "LONG", 1.1610, "2026-03-03T21:00:00Z")
        assert a != b

    def test_sha1_length(self):
        h = make_intent_id("USDJPY", "SHORT", 157.500, "2026-03-03T10:00:00Z")
        assert len(h) == 40


# ── Startup merge ─────────────────────────────────────────────────────────────

class TestMergeIbkrState:
    def test_inserts_unknown(self, store: SQLiteStateStore):
        brackets = [{"parent_id": 999, "symbol": "AUDJPY",
                     "status": "PENDING", "tp_id": 1000, "sl_id": 1001}]
        counts = store.merge_ibkr_state(brackets)
        assert counts["inserted"] == 1
        rec = store.get_order_by_parent_id(999)
        assert rec is not None
        assert rec.status == OrderStatus.RESTORED_UNKNOWN

    def test_expires_db_pending_not_on_ibkr(self, store: SQLiteStateStore):
        rec = DBOrderRecord(
            intent_id="test_expire",
            symbol="USDJPY",
            intent_json={},
            status=OrderStatus.PENDING,
            parent_id=888,
        )
        store.upsert_order(rec)
        # IBKR returns empty list
        counts = store.merge_ibkr_state([])
        assert counts["expired"] == 1
        loaded = store.get_order_by_parent_id(888)
        assert loaded.status == OrderStatus.EXPIRED

    def test_updates_existing(self, store: SQLiteStateStore):
        rec = DBOrderRecord(
            intent_id="test_update",
            symbol="CADJPY",
            intent_json={},
            status=OrderStatus.PENDING,
            parent_id=777,
        )
        store.upsert_order(rec)
        brackets = [{"parent_id": 777, "symbol": "CADJPY",
                     "status": OrderStatus.FILLED, "tp_id": 778, "sl_id": 779}]
        counts = store.merge_ibkr_state(brackets)
        assert counts["updated"] == 1
        loaded = store.get_order_by_parent_id(777)
        assert loaded.status == OrderStatus.FILLED



"""
SQLite-backed persistent state store for BojkoFx.

Tables
------
schema_version  – single-row version tracker for migrations
strategy_state  – per-symbol BOS/pivot/bar context
orders          – bracket order records (intent → IBKR lifecycle)
risk_state      – key/value risk metrics (peak equity, kill switch, …)
events          – append-only audit log

Design
------
* SQLite with WAL journal mode – crash-safe without a full RDBMS
* Lightweight: every public method opens/closes cursor in a single
  transaction; the connection stays open for the process lifetime.
* JSON columns store flexible payloads (intents, pivot details, …)
* intent_id UNIQUE prevents duplicate order submissions after restart
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

log = logging.getLogger(__name__)

# ── Current schema version ────────────────────────────────────────────────────
_SCHEMA_VERSION = 3

# ── SQL DDL ───────────────────────────────────────────────────────────────────
_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_state (
    symbol                TEXT    PRIMARY KEY,
    last_processed_bar_ts TEXT,           -- ISO-8601 UTC
    last_pivot_high_json  TEXT,           -- {price, bar_ts, idx}
    last_pivot_low_json   TEXT,           -- {price, bar_ts, idx}
    last_bos_json         TEXT,           -- {direction, level, bar_ts}
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id        INTEGER,              -- IBKR parentOrderId (NULL/0 = not yet sent)
    intent_id        TEXT    UNIQUE,        -- sha1 idempotency key
    symbol           TEXT    NOT NULL,
    intent_json      TEXT    NOT NULL,      -- full OrderIntent as JSON
    status           TEXT    NOT NULL,      -- see OrderStatus enum
    ibkr_ids_json    TEXT,                 -- {parent, tp, sl}
    trail_state_json TEXT,                 -- {activated, sl_price, sl_ibkr_id} or NULL
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_state (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc       TEXT    NOT NULL,
    event_type   TEXT    NOT NULL,
    payload_json TEXT    NOT NULL
);
"""


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PivotInfo:
    price:  float
    bar_ts: str   # ISO-8601
    idx:    int = 0


@dataclass
class BosInfo:
    direction: str   # "LONG" or "SHORT"
    level:     float
    bar_ts:    str   # ISO-8601


@dataclass
class StrategyState:
    symbol:                str
    last_processed_bar_ts: Optional[str]      = None
    last_pivot_high:       Optional[PivotInfo] = None
    last_pivot_low:        Optional[PivotInfo] = None
    last_bos:              Optional[BosInfo]   = None
    updated_at:            str                 = field(
        default_factory=lambda: _utc_now()
    )


class OrderStatus:
    CREATED          = "CREATED"
    SENT             = "SENT"
    PENDING          = "PENDING"          # submitted, waiting fill
    FILLED           = "FILLED"           # entry filled, TP/SL active
    EXITED           = "EXITED"           # TP or SL hit
    CANCELLED        = "CANCELLED"
    EXPIRED          = "EXPIRED"
    RESTORED_UNKNOWN = "RESTORED_UNKNOWN" # found on IBKR but not in DB


@dataclass
class DBOrderRecord:
    intent_id:     str
    symbol:        str
    intent_json:   Dict[str, Any]
    status:        str                    = OrderStatus.CREATED
    parent_id:     int                    = 0
    ibkr_ids_json: Optional[Dict]         = None
    created_at:    str                    = field(
        default_factory=lambda: _utc_now()
    )
    updated_at:    str                    = field(
        default_factory=lambda: _utc_now()
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dumps(obj: Any) -> str:
    """JSON-safe serialiser that handles numpy floats and datetimes."""
    def _default(o: Any) -> Any:
        if hasattr(o, "item"):          # numpy scalar
            return o.item()
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Not serialisable: {type(o)}")
    return json.dumps(obj, default=_default)


def make_intent_id(symbol: str, side: str, bos_level: float, bos_bar_ts: str) -> str:
    """
    Deterministic idempotency key for an OrderIntent.

    Same symbol + side + BOS level + BOS bar timestamp → same id.
    Prevents duplicate order submissions after restart.
    """
    raw = f"{symbol}|{side}|{bos_level:.8f}|{bos_bar_ts}"
    return hashlib.sha1(raw.encode()).hexdigest()


# ── Main store class ──────────────────────────────────────────────────────────

class SQLiteStateStore:
    """
    Persistent state store backed by SQLite (WAL mode).

    Usage
    -----
    store = SQLiteStateStore("data/state/bojkofx_state.db")
    store.migrate()
    """

    def __init__(self, db_path: str | Path = "data/state/bojkofx_state.db"):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            isolation_level=None,   # autocommit – we manage transactions manually
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        log.info("StateStore: opened %s", self._path)

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Cursor, None, None]:
        """Yield a cursor inside a BEGIN/COMMIT block."""
        cur = self._conn.cursor()
        cur.execute("BEGIN")
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Migrations ────────────────────────────────────────────────────────────

    def migrate(self) -> None:
        """Create tables and seed schema_version if not present."""
        # executescript runs outside autocommit – use it for DDL
        self._conn.executescript(_DDL)
        cur = self._conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        if row is None:
            with self._tx() as c:
                c.execute("INSERT INTO schema_version(version) VALUES(?)",
                          (_SCHEMA_VERSION,))
            log.info("StateStore: schema v%d created", _SCHEMA_VERSION)
        else:
            db_ver = row["version"]
            if db_ver < _SCHEMA_VERSION:
                if db_ver < 2:
                    # v1→v2: orders.parent_id was PK, now id is autoincrement PK
                    self._conn.executescript("""
                        ALTER TABLE orders RENAME TO orders_v1;
                        CREATE TABLE IF NOT EXISTS orders (
                            id               INTEGER PRIMARY KEY AUTOINCREMENT,
                            parent_id        INTEGER,
                            intent_id        TEXT    UNIQUE,
                            symbol           TEXT    NOT NULL,
                            intent_json      TEXT    NOT NULL,
                            status           TEXT    NOT NULL,
                            ibkr_ids_json    TEXT,
                            trail_state_json TEXT,
                            created_at       TEXT    NOT NULL,
                            updated_at       TEXT    NOT NULL
                        );
                        INSERT INTO orders
                            (parent_id, intent_id, symbol, intent_json,
                             status, ibkr_ids_json, created_at, updated_at)
                        SELECT parent_id, intent_id, symbol, intent_json,
                               status, ibkr_ids_json, created_at, updated_at
                        FROM orders_v1;
                        DROP TABLE orders_v1;
                    """)
                if db_ver < 3:
                    # v2→v3: add trail_state_json column (nullable — pre-existing rows get NULL)
                    try:
                        self._conn.execute(
                            "ALTER TABLE orders ADD COLUMN trail_state_json TEXT"
                        )
                        log.info("StateStore: added trail_state_json column")
                    except Exception:
                        pass  # column may already exist (idempotent)
                with self._tx() as c:
                    c.execute("UPDATE schema_version SET version=?",
                              (_SCHEMA_VERSION,))
                log.info("StateStore: migrated v%d → v%d", db_ver, _SCHEMA_VERSION)

    # ── Strategy state ────────────────────────────────────────────────────────

    def load_strategy_state(self, symbol: str) -> Optional[StrategyState]:
        cur = self._conn.execute(
            "SELECT * FROM strategy_state WHERE symbol=?", (symbol,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_strategy_state(row)

    def load_all_strategy_states(self) -> Dict[str, StrategyState]:
        cur = self._conn.execute("SELECT * FROM strategy_state")
        return {row["symbol"]: self._row_to_strategy_state(row)
                for row in cur.fetchall()}

    def save_strategy_state(self, state: StrategyState) -> None:
        state.updated_at = _utc_now()
        with self._tx() as c:
            c.execute("""
                INSERT INTO strategy_state
                    (symbol, last_processed_bar_ts,
                     last_pivot_high_json, last_pivot_low_json,
                     last_bos_json, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET
                    last_processed_bar_ts = excluded.last_processed_bar_ts,
                    last_pivot_high_json  = excluded.last_pivot_high_json,
                    last_pivot_low_json   = excluded.last_pivot_low_json,
                    last_bos_json         = excluded.last_bos_json,
                    updated_at            = excluded.updated_at
            """, (
                state.symbol,
                state.last_processed_bar_ts,
                _dumps(asdict(state.last_pivot_high)) if state.last_pivot_high else None,
                _dumps(asdict(state.last_pivot_low))  if state.last_pivot_low  else None,
                _dumps(asdict(state.last_bos))        if state.last_bos        else None,
                state.updated_at,
            ))

    @staticmethod
    def _row_to_strategy_state(row: sqlite3.Row) -> StrategyState:
        def _pivot(js: Optional[str]) -> Optional[PivotInfo]:
            if not js:
                return None
            d = json.loads(js)
            return PivotInfo(**d)

        def _bos(js: Optional[str]) -> Optional[BosInfo]:
            if not js:
                return None
            d = json.loads(js)
            return BosInfo(**d)

        return StrategyState(
            symbol=row["symbol"],
            last_processed_bar_ts=row["last_processed_bar_ts"],
            last_pivot_high=_pivot(row["last_pivot_high_json"]),
            last_pivot_low=_pivot(row["last_pivot_low_json"]),
            last_bos=_bos(row["last_bos_json"]),
            updated_at=row["updated_at"],
        )

    # ── Order records ─────────────────────────────────────────────────────────

    def upsert_order(self, rec: DBOrderRecord) -> bool:
        """
        Insert or update an order record.

        Returns True if inserted (new), False if updated (existing intent_id).
        On conflict by intent_id, updates status/ibkr_ids/updated_at only when
        the incoming status is "newer" (CREATED < SENT < PENDING < FILLED …).
        """
        _STATUS_RANK = {
            OrderStatus.CREATED: 0,
            OrderStatus.SENT: 1,
            OrderStatus.PENDING: 2,
            OrderStatus.RESTORED_UNKNOWN: 2,
            OrderStatus.FILLED: 3,
            OrderStatus.EXITED: 4,
            OrderStatus.CANCELLED: 4,
            OrderStatus.EXPIRED: 4,
        }
        rec.updated_at = _utc_now()
        try:
            with self._tx() as c:
                c.execute("""
                    INSERT INTO orders
                        (parent_id, intent_id, symbol, intent_json,
                         status, ibkr_ids_json, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(intent_id) DO UPDATE SET
                        parent_id     = CASE WHEN excluded.parent_id > 0
                                             THEN excluded.parent_id
                                             ELSE orders.parent_id END,
                        status        = CASE WHEN ? > COALESCE(
                                               (SELECT val FROM (
                                                 SELECT CASE status
                                                   WHEN 'CREATED'          THEN 0
                                                   WHEN 'SENT'             THEN 1
                                                   WHEN 'PENDING'          THEN 2
                                                   WHEN 'RESTORED_UNKNOWN' THEN 2
                                                   WHEN 'FILLED'           THEN 3
                                                   WHEN 'EXITED'           THEN 4
                                                   WHEN 'CANCELLED'        THEN 4
                                                   WHEN 'EXPIRED'          THEN 4
                                                   ELSE 0 END AS val
                                                 FROM orders WHERE intent_id=excluded.intent_id
                                               )), 0)
                                             THEN excluded.status
                                             ELSE orders.status END,
                        ibkr_ids_json = COALESCE(excluded.ibkr_ids_json, orders.ibkr_ids_json),
                        updated_at    = excluded.updated_at
                """, (
                    rec.parent_id,
                    rec.intent_id,
                    rec.symbol,
                    _dumps(rec.intent_json),
                    rec.status,
                    _dumps(rec.ibkr_ids_json) if rec.ibkr_ids_json else None,
                    rec.created_at,
                    rec.updated_at,
                    # rank for CASE comparison
                    _STATUS_RANK.get(rec.status, 0),
                ))
            return True
        except sqlite3.IntegrityError:
            return False

    def get_order_by_intent_id(self, intent_id: str) -> Optional[DBOrderRecord]:
        cur = self._conn.execute(
            "SELECT * FROM orders WHERE intent_id=?", (intent_id,)
        )
        row = cur.fetchone()
        return self._row_to_order(row) if row else None

    def get_order_by_parent_id(self, parent_id: int) -> Optional[DBOrderRecord]:
        cur = self._conn.execute(
            "SELECT * FROM orders WHERE parent_id=?", (parent_id,)
        )
        row = cur.fetchone()
        return self._row_to_order(row) if row else None

    def save_trail_state(
        self,
        parent_id: int,
        activated: bool,
        sl_price: float,
        sl_ibkr_id: int,
    ) -> None:
        """
        Persist trailing stop state for an open position.

        Called by IBKRExecutionEngine whenever trail state changes so that
        a process restart can restore the correct trailing SL level.
        """
        payload = _dumps({"activated": activated, "sl_price": sl_price,
                          "sl_ibkr_id": sl_ibkr_id})
        now = _utc_now()
        with self._tx() as c:
            c.execute(
                "UPDATE orders SET trail_state_json=?, updated_at=? WHERE parent_id=?",
                (payload, now, parent_id),
            )

    def load_trail_state(self, parent_id: int) -> Optional[Dict]:
        """
        Return the persisted trailing stop state dict for a given parent_id,
        or None if no trail state was saved (e.g. trailing stop not enabled).

        Dict keys: activated (bool), sl_price (float), sl_ibkr_id (int).
        """
        cur = self._conn.execute(
            "SELECT trail_state_json FROM orders WHERE parent_id=?", (parent_id,)
        )
        row = cur.fetchone()
        if row is None or not row["trail_state_json"]:
            return None
        return json.loads(row["trail_state_json"])

    def get_orders_by_status(self, statuses: List[str]) -> List[DBOrderRecord]:
        placeholders = ",".join("?" * len(statuses))
        cur = self._conn.execute(
            f"SELECT * FROM orders WHERE status IN ({placeholders})", statuses
        )
        return [self._row_to_order(r) for r in cur.fetchall()]

    def update_order_status(
        self,
        parent_id: int,
        status: str,
        ibkr_ids: Optional[Dict] = None,
    ) -> None:
        now = _utc_now()
        with self._tx() as c:
            if ibkr_ids is not None:
                c.execute("""
                    UPDATE orders SET status=?, ibkr_ids_json=?, updated_at=?
                    WHERE parent_id=?
                """, (status, _dumps(ibkr_ids), now, parent_id))
            else:
                c.execute("""
                    UPDATE orders SET status=?, updated_at=?
                    WHERE parent_id=?
                """, (status, now, parent_id))

    def update_order_parent_id(self, intent_id: str, parent_id: int,
                               ibkr_ids: Optional[Dict] = None) -> None:
        """Assign IBKR orderId after bracket is placed."""
        now = _utc_now()
        with self._tx() as c:
            c.execute("""
                UPDATE orders SET parent_id=?, ibkr_ids_json=COALESCE(?,ibkr_ids_json),
                                  updated_at=?
                WHERE intent_id=?
            """, (parent_id,
                  _dumps(ibkr_ids) if ibkr_ids else None,
                  now, intent_id))

    @staticmethod
    def _row_to_order(row: sqlite3.Row) -> DBOrderRecord:
        return DBOrderRecord(
            parent_id=row["parent_id"],
            intent_id=row["intent_id"],
            symbol=row["symbol"],
            intent_json=json.loads(row["intent_json"]),
            status=row["status"],
            ibkr_ids_json=json.loads(row["ibkr_ids_json"]) if row["ibkr_ids_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Risk state ────────────────────────────────────────────────────────────

    def save_risk_state(self, key: str, value: Any) -> None:
        now = _utc_now()
        with self._tx() as c:
            c.execute("""
                INSERT INTO risk_state(key, value_json, updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                                               updated_at=excluded.updated_at
            """, (key, _dumps(value), now))

    def load_risk_state(self) -> Dict[str, Any]:
        cur = self._conn.execute("SELECT key, value_json FROM risk_state")
        return {row["key"]: json.loads(row["value_json"]) for row in cur.fetchall()}

    # ── Events ────────────────────────────────────────────────────────────────

    def append_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        now = _utc_now()
        with self._tx() as c:
            c.execute(
                "INSERT INTO events(ts_utc, event_type, payload_json) VALUES(?,?,?)",
                (now, event_type, _dumps(payload))
            )

    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        cur = self._conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = cur.fetchall()
        return [{"id": r["id"], "ts_utc": r["ts_utc"],
                 "event_type": r["event_type"],
                 "payload": json.loads(r["payload_json"])} for r in rows]

    # ── Startup merge (IBKR source-of-truth reconciliation) ──────────────────

    def merge_ibkr_state(
        self,
        ibkr_brackets: List[Dict],   # [{parent_id, symbol, status, tp_id, sl_id}, …]
    ) -> Dict[str, int]:
        """
        Reconcile IBKR open orders against DB:

        - IBKR has order, DB has it → update DB status from IBKR
        - IBKR has order, DB missing → insert RESTORED_UNKNOWN
        - DB has PENDING/SENT, IBKR missing → mark CANCELLED/EXPIRED

        Returns counts: {inserted, updated, expired}
        """
        ibkr_parent_ids = {b["parent_id"] for b in ibkr_brackets}
        counts = {"inserted": 0, "updated": 0, "expired": 0}

        # ── DB PENDING/SENT not seen on IBKR → expired/cancelled ─────────────
        db_pending = self.get_orders_by_status(
            [OrderStatus.PENDING, OrderStatus.SENT, OrderStatus.CREATED]
        )
        for rec in db_pending:
            if rec.parent_id == 0:
                # FIX BUG-14: pre-saved intent never reached IBKR (crashed before placement).
                # parent_id=0 means _place_limit_bracket never ran — expire by intent_id.
                with self._tx() as c:
                    c.execute(
                        "UPDATE orders SET status=?, updated_at=? WHERE intent_id=?",
                        (OrderStatus.EXPIRED, _utc_now(), rec.intent_id),
                    )
                self.append_event("ORDER_EXPIRED", {
                    "source": "startup_merge",
                    "parent_id": 0,
                    "symbol": rec.symbol,
                    "intent_id": rec.intent_id,
                    "reason": "never_placed",
                })
                counts["expired"] += 1
                log.info("merge_ibkr: intent_id=%s %s → EXPIRED (never placed on IBKR)",
                         rec.intent_id, rec.symbol)
            elif rec.parent_id > 0 and rec.parent_id not in ibkr_parent_ids:
                self.update_order_status(rec.parent_id, OrderStatus.EXPIRED)
                self.append_event("ORDER_EXPIRED", {
                    "source": "startup_merge",
                    "parent_id": rec.parent_id,
                    "symbol": rec.symbol,
                    "intent_id": rec.intent_id,
                })
                counts["expired"] += 1
                log.info("merge_ibkr: parent_id=%d %s → EXPIRED (not on IBKR)",
                         rec.parent_id, rec.symbol)

        # ── IBKR brackets → upsert into DB ───────────────────────────────────
        for bracket in ibkr_brackets:
            pid = bracket["parent_id"]
            sym = bracket["symbol"]
            existing = self.get_order_by_parent_id(pid)
            ibkr_ids = {
                "parent": pid,
                "tp": bracket.get("tp_id", 0),
                "sl": bracket.get("sl_id", 0),
            }
            if existing is None:
                # Not in DB — create a stub record
                rec = DBOrderRecord(
                    intent_id=f"ibkr_{pid}",   # stub intent_id
                    symbol=sym,
                    intent_json=bracket,
                    status=OrderStatus.RESTORED_UNKNOWN,
                    parent_id=pid,
                    ibkr_ids_json=ibkr_ids,
                )
                self.upsert_order(rec)
                self.append_event("RESTORED_FROM_IBKR", {
                    "parent_id": pid, "symbol": sym
                })
                counts["inserted"] += 1
                log.info("merge_ibkr: parent_id=%d %s → RESTORED_UNKNOWN (not in DB)", pid, sym)
            else:
                # Update to IBKR status
                new_status = bracket.get("status", OrderStatus.PENDING)
                self.update_order_status(pid, new_status, ibkr_ids=ibkr_ids)
                counts["updated"] += 1

        self.append_event("STARTUP_MERGE_SUMMARY", {**counts,
                                                     "ibkr_count": len(ibkr_brackets)})
        log.info("merge_ibkr: %s", counts)
        return counts


# ── Module-level singleton helper ─────────────────────────────────────────────

def get_default_db_path() -> Path:
    """
    Resolve DB path from environment STATE_DB_PATH or use default.
    Works on Linux (VM) and Windows (local dev).
    """
    env_path = os.environ.get("STATE_DB_PATH", "")
    if env_path:
        return Path(env_path)
    # Relative to project root (two levels up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "data" / "state" / "bojkofx_state.db"





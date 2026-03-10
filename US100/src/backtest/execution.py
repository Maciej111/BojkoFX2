from dataclasses import dataclass
from datetime import datetime

@dataclass
class Trade:
    id: int
    symbol: str
    direction: str # 'LONG' or 'SHORT'
    entry_time: datetime
    entry_price: float
    sl: float
    tp: float
    exit_time: datetime = None
    exit_price: float = None
    result: float = 0.0 # PnL
    status: str = 'OPEN' # OPEN, SL, TP, CLOSED, PARTIAL_TP, SL_intrabar_conflict
    touch_no: int = 1  # Touch number (1, 2, 3...)
    zone_created_at: datetime = None  # When zone was created
    # Extended columns for audit
    risk_distance: float = None  # abs(entry_price - sl)
    realized_distance: float = None  # exit_price - entry_price (signed)
    planned_tp: float = None  # same as tp (for clarity)
    planned_sl: float = None  # same as sl (for clarity)
    exit_reason: str = None  # 'SL', 'TP', 'SL_intrabar_conflict'
    R_multiple: float = None  # realized_distance / risk_distance
    # Partial TP fields
    partial_tp_enabled: bool = False
    first_tp_hit: bool = False
    first_tp_price: float = None
    be_moved: bool = False
    original_size: float = 1.0  # Position size (1.0 = full, 0.5 = half after partial)

class ExecutionEngine:
    def __init__(self, initial_balance, config, symbol='UNKNOWN'):
        self.balance = initial_balance
        self.equity = initial_balance
        self.symbol = symbol  # instrument being tested — avoids "EURUSD" hardcode
        self.positions = [] # Active trades
        self.closed_trades = []
        self.pending_orders = [] # List of dicts
        self.config = config
        self.trade_id_counter = 0

    def place_limit_order(self, direction, price, sl, tp, time, comment="", touch_no=1, zone_created_at=None):
        # Check max positions
        if len(self.positions) + len(self.pending_orders) >= self.config['max_positions']:
            return

        order = {
            'id': self.trade_id_counter,
            'direction': direction,
            'price': price,
            'sl': sl,
            'tp': tp,
            'time': time,
            'comment': comment,
            'touch_no': touch_no,
            'zone_created_at': zone_created_at
        }
        self.trade_id_counter += 1
        self.pending_orders.append(order)

    def process_bar(self, bar):
        # 1. Check Pending Orders
        # Remove executed orders from pending
        remaining_orders = []
        for order in self.pending_orders:
            executed = False

            if order['direction'] == 'LONG':
                # Buy Limit: Ask price must touch or go below order price
                if bar['low_ask'] <= order['price']:
                    # FEASIBILITY CHECK: entry must be within ASK range
                    if not (bar['low_ask'] <= order['price'] <= bar['high_ask']):
                        raise ValueError(f"LONG entry price {order['price']:.5f} outside ASK range [{bar['low_ask']:.5f}, {bar['high_ask']:.5f}] at {bar['timestamp']}")

                    # Execute
                    self._open_position(order, bar['timestamp'], fill_price=order['price'])
                    executed = True

            elif order['direction'] == 'SHORT':
                # Sell Limit: Bid price must touch or go above order price
                if bar['high_bid'] >= order['price']:
                    # FEASIBILITY CHECK: entry must be within BID range
                    if not (bar['low_bid'] <= order['price'] <= bar['high_bid']):
                        raise ValueError(f"SHORT entry price {order['price']:.5f} outside BID range [{bar['low_bid']:.5f}, {bar['high_bid']:.5f}] at {bar['timestamp']}")

                    self._open_position(order, bar['timestamp'], fill_price=order['price'])
                    executed = True

            if not executed:
                remaining_orders.append(order)

        self.pending_orders = remaining_orders

        # 2. Check Open Positions (SL/TP)
        # Iterate over copy to allow removal
        for trade in list(self.positions):
            if trade.status != 'OPEN':
                continue

            sl_hit = False
            tp_hit = False

            if trade.direction == 'LONG':
                # LONG exits on BID side
                if bar['low_bid'] <= trade.sl:
                    sl_hit = True
                if bar['high_bid'] >= trade.tp:
                    tp_hit = True

            elif trade.direction == 'SHORT':
                # SHORT exits on ASK side
                if bar['high_ask'] >= trade.sl:
                    sl_hit = True
                if bar['low_ask'] <= trade.tp:
                    tp_hit = True

            # Conflict Resolution - ENFORCED WORST-CASE
            # If both SL and TP are hit in same bar, ALWAYS choose SL (worst case)
            if sl_hit and tp_hit:
                # WORST-CASE: Always SL, never TP
                # Use correct side for exit: BID for LONG, ASK for SHORT
                if trade.direction == 'LONG':
                    exit_price = trade.sl  # SL exit on BID side (already checked vs low_bid)
                    # FEASIBILITY CHECK
                    if not (bar['low_bid'] <= exit_price <= bar['high_bid']):
                        raise ValueError(f"LONG SL exit {exit_price:.5f} outside BID range [{bar['low_bid']:.5f}, {bar['high_bid']:.5f}] at {bar['timestamp']}")
                else:
                    exit_price = trade.sl  # SL exit on ASK side (already checked vs high_ask)
                    # FEASIBILITY CHECK
                    if not (bar['low_ask'] <= exit_price <= bar['high_ask']):
                        raise ValueError(f"SHORT SL exit {exit_price:.5f} outside ASK range [{bar['low_ask']:.5f}, {bar['high_ask']:.5f}] at {bar['timestamp']}")

                self._close_position(trade, exit_price, bar['timestamp'], 'SL_intrabar_conflict')

            elif sl_hit:
                # Use correct side for SL exit
                if trade.direction == 'LONG':
                    exit_price = trade.sl  # BID side
                    # FEASIBILITY CHECK
                    if not (bar['low_bid'] <= exit_price <= bar['high_bid']):
                        raise ValueError(f"LONG SL exit {exit_price:.5f} outside BID range [{bar['low_bid']:.5f}, {bar['high_bid']:.5f}] at {bar['timestamp']}")
                else:
                    exit_price = trade.sl  # ASK side
                    # FEASIBILITY CHECK
                    if not (bar['low_ask'] <= exit_price <= bar['high_ask']):
                        raise ValueError(f"SHORT SL exit {exit_price:.5f} outside ASK range [{bar['low_ask']:.5f}, {bar['high_ask']:.5f}] at {bar['timestamp']}")
                self._close_position(trade, exit_price, bar['timestamp'], 'SL')

            elif tp_hit:
                # Use correct side for TP exit
                if trade.direction == 'LONG':
                    exit_price = trade.tp  # BID side
                    # FEASIBILITY CHECK
                    if not (bar['low_bid'] <= exit_price <= bar['high_bid']):
                        raise ValueError(f"LONG TP exit {exit_price:.5f} outside BID range [{bar['low_bid']:.5f}, {bar['high_bid']:.5f}] at {bar['timestamp']}")
                else:
                    exit_price = trade.tp  # ASK side
                    # FEASIBILITY CHECK
                    if not (bar['low_ask'] <= exit_price <= bar['high_ask']):
                        raise ValueError(f"SHORT TP exit {exit_price:.5f} outside ASK range [{bar['low_ask']:.5f}, {bar['high_ask']:.5f}] at {bar['timestamp']}")
                self._close_position(trade, exit_price, bar['timestamp'], 'TP')

    def _open_position(self, order, time, fill_price):
        # Calculate risk_distance
        risk_dist = abs(fill_price - order['sl'])

        # Apply commission?
        # TODO: Calculate commission here or on close? On close is easier.
        trade = Trade(
            id=order['id'],
            symbol=self.symbol,
            direction=order['direction'],
            entry_time=time,
            entry_price=fill_price,
            sl=order['sl'],
            tp=order['tp'],
            touch_no=order.get('touch_no', 1),
            zone_created_at=order.get('zone_created_at'),
            # Extended fields
            risk_distance=risk_dist,
            planned_sl=order['sl'],
            planned_tp=order['tp']
        )
        self.positions.append(trade)

    def _close_position(self, trade, price, time, reason):
        trade.exit_time = time
        trade.exit_price = price
        trade.status = reason # SL, TP, or SL_intrabar_conflict
        trade.exit_reason = reason

        # Calculate realized_distance (signed)
        if trade.direction == 'LONG':
            realized_dist = trade.exit_price - trade.entry_price
        else:  # SHORT
            realized_dist = trade.entry_price - trade.exit_price

        trade.realized_distance = realized_dist

        # Calculate R_multiple
        if trade.risk_distance and trade.risk_distance > 0:
            trade.R_multiple = realized_dist / trade.risk_distance
        else:
            # Degenerate bar (zero ATR) — skip R calculation, record as 0
            import logging as _log
            _log.getLogger(__name__).warning(
                "Trade %s: risk_distance=%s — skipping R calculation",
                trade.id, trade.risk_distance,
            )
            trade.R_multiple = 0.0

        # Calculate PnL
        # (Exit - Entry) * LotSize [Long]
        # (Entry - Exit) * LotSize [Short]

        lot_size = self.config['lot_size']

        if trade.direction == 'LONG':
            gross_pnl = (price - trade.entry_price) * lot_size
        else:
            gross_pnl = (trade.entry_price - price) * lot_size

        # Commission scales with position size.
        # lot_size is the contract size (e.g. 100_000 for 1 standard FX lot).
        # commission_per_lot is the fee per 1 standard lot (100_000 units).
        standard_lot = self.config.get('standard_lot', 100_000)
        lots = lot_size / standard_lot
        comm = self.config.get('commission_per_lot', 0.0) * lots

        net_pnl = gross_pnl - comm
        trade.result = net_pnl

        self.balance += net_pnl
        self.closed_trades.append(trade)
        self.positions.remove(trade)
        # print(f"Closed {trade.direction} at {price} ({reason}). PnL: {net_pnl:.2f}")


    def get_results_df(self):
        import pandas as pd
        data = []
        for t in self.closed_trades:
            data.append({
                'id': t.id,
                'direction': t.direction,
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'sl': t.sl,
                'tp': t.tp,
                'pnl': t.result,
                'status': t.status,
                'exit_reason': t.exit_reason,
                'touch_no': t.touch_no,
                'zone_created_at': t.zone_created_at,
                # Extended columns
                'risk_distance': t.risk_distance,
                'realized_distance': t.realized_distance,
                'planned_sl': t.planned_sl,
                'planned_tp': t.planned_tp,
                'R': t.R_multiple
            })
        return pd.DataFrame(data)





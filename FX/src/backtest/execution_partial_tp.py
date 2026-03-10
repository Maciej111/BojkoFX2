"""
Partial Take Profit execution logic.
Extends base execution with 50% @ +1R, 50% @ final target with BE move.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PartialTPTrade:
    id: int
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    sl: float
    first_tp: float  # +1R target
    final_tp: float  # Final target (e.g., +1.5R)
    exit_time: datetime = None
    exit_price: float = None
    result: float = 0.0
    status: str = 'OPEN'  # OPEN, PARTIAL_TP, SL, FINAL_TP, BE_HIT
    touch_no: int = 1
    zone_created_at: datetime = None
    # Partial TP state
    first_tp_hit: bool = False
    first_tp_time: datetime = None
    first_tp_pnl: float = 0.0
    be_moved: bool = False
    remaining_size: float = 1.0  # 1.0 full, 0.5 after first TP


class PartialTPEngine:
    """
    Execution engine with partial take profit logic.

    Logic:
    - Entry: full position
    - First TP (+1R): Close 50%, move SL to BE
    - Final TP: Close remaining 50%
    - If BE hit after first TP: 0R on second half
    """

    def __init__(self, initial_balance, config):
        self.balance = initial_balance
        self.equity = initial_balance
        self.positions = []
        self.closed_trades = []
        self.pending_orders = []
        self.config = config
        self.trade_id_counter = 0

    def place_limit_order(self, direction, price, sl, tp, time, comment="",
                         touch_no=1, zone_created_at=None,
                         first_tp_target=1.0, final_tp_target=1.5):
        """
        Place limit order with partial TP parameters.

        Args:
            first_tp_target: R multiple for first TP (default 1.0)
            final_tp_target: R multiple for final TP (default 1.5)
        """
        if len(self.positions) + len(self.pending_orders) >= self.config['max_positions']:
            return

        # Calculate first and final TP prices
        if direction == 'LONG':
            risk = price - sl
            first_tp = price + (risk * first_tp_target)
            final_tp = price + (risk * final_tp_target)
        else:  # SHORT
            risk = sl - price
            first_tp = price - (risk * first_tp_target)
            final_tp = price - (risk * final_tp_target)

        order = {
            'id': self.trade_id_counter,
            'direction': direction,
            'price': price,
            'sl': sl,
            'first_tp': first_tp,
            'final_tp': final_tp,
            'time': time,
            'comment': comment,
            'touch_no': touch_no,
            'zone_created_at': zone_created_at
        }
        self.trade_id_counter += 1
        self.pending_orders.append(order)

    def process_bar(self, bar):
        """Process bar for fills, partial TPs, and exits."""
        # 1. Check pending orders
        remaining_orders = []
        for order in self.pending_orders:
            executed = False

            if order['direction'] == 'LONG':
                if bar['low_ask'] <= order['price']:
                    self._open_position(order, bar['timestamp'], fill_price=order['price'])
                    executed = True
            elif order['direction'] == 'SHORT':
                if bar['high_bid'] >= order['price']:
                    self._open_position(order, bar['timestamp'], fill_price=order['price'])
                    executed = True

            if not executed:
                remaining_orders.append(order)

        self.pending_orders = remaining_orders

        # 2. Check open positions
        for trade in list(self.positions):
            if trade.status not in ['OPEN', 'PARTIAL_TP']:
                continue

            # Check what got hit this bar
            sl_hit = False
            first_tp_hit = False
            final_tp_hit = False

            if trade.direction == 'LONG':
                if bar['low_bid'] <= trade.sl:
                    sl_hit = True
                if not trade.first_tp_hit and bar['high_bid'] >= trade.first_tp:
                    first_tp_hit = True
                if trade.first_tp_hit and bar['high_bid'] >= trade.final_tp:
                    final_tp_hit = True

            elif trade.direction == 'SHORT':
                if bar['high_ask'] >= trade.sl:
                    sl_hit = True
                if not trade.first_tp_hit and bar['low_ask'] <= trade.first_tp:
                    first_tp_hit = True
                if trade.first_tp_hit and bar['low_ask'] <= trade.final_tp:
                    final_tp_hit = True

            # Process hits
            if not trade.first_tp_hit:
                # Full position still active
                if first_tp_hit and sl_hit:
                    # Both hit - worst case: SL first
                    if self.config.get('intra_bar_policy', 'worst_case') == 'worst_case':
                        self._close_full_position(trade, trade.sl, bar['timestamp'], 'SL')
                    else:
                        self._hit_first_tp(trade, trade.first_tp, bar['timestamp'])

                elif first_tp_hit:
                    # First TP hit - close 50%, move SL to BE
                    self._hit_first_tp(trade, trade.first_tp, bar['timestamp'])

                elif sl_hit:
                    # SL hit before first TP
                    self._close_full_position(trade, trade.sl, bar['timestamp'], 'SL')

            else:
                # First TP already hit, 50% remaining
                if final_tp_hit and sl_hit:
                    # Both hit - worst case: SL (BE) first
                    if self.config.get('intra_bar_policy', 'worst_case') == 'worst_case':
                        self._hit_be(trade, trade.entry_price, bar['timestamp'])
                    else:
                        self._hit_final_tp(trade, trade.final_tp, bar['timestamp'])

                elif final_tp_hit:
                    # Final TP hit
                    self._hit_final_tp(trade, trade.final_tp, bar['timestamp'])

                elif sl_hit:
                    # BE hit (SL moved to BE after first TP)
                    self._hit_be(trade, trade.entry_price, bar['timestamp'])

    def _open_position(self, order, time, fill_price):
        """Open new position."""
        trade = PartialTPTrade(
            id=order['id'],
            symbol="EURUSD",
            direction=order['direction'],
            entry_time=time,
            entry_price=fill_price,
            sl=order['sl'],
            first_tp=order['first_tp'],
            final_tp=order['final_tp'],
            touch_no=order.get('touch_no', 1),
            zone_created_at=order.get('zone_created_at')
        )
        self.positions.append(trade)

    def _hit_first_tp(self, trade, price, time):
        """Hit first TP - close 50%, move SL to BE."""
        lot_size = self.config['lot_size']

        # Calculate PnL for first 50%
        if trade.direction == 'LONG':
            gross_pnl = (price - trade.entry_price) * lot_size * 0.5
        else:
            gross_pnl = (trade.entry_price - price) * lot_size * 0.5

        comm = self.config['commission_per_lot'] * 0.5
        net_pnl = gross_pnl - comm

        trade.first_tp_hit = True
        trade.first_tp_time = time
        trade.first_tp_pnl = net_pnl
        trade.remaining_size = 0.5
        trade.status = 'PARTIAL_TP'

        # Move SL to BE
        trade.sl = trade.entry_price
        trade.be_moved = True

        # Add to balance
        self.balance += net_pnl

    def _hit_final_tp(self, trade, price, time):
        """Hit final TP - close remaining 50%."""
        lot_size = self.config['lot_size']

        # Calculate PnL for second 50%
        if trade.direction == 'LONG':
            gross_pnl = (price - trade.entry_price) * lot_size * 0.5
        else:
            gross_pnl = (trade.entry_price - price) * lot_size * 0.5

        comm = self.config['commission_per_lot'] * 0.5
        net_pnl = gross_pnl - comm

        # Total PnL
        total_pnl = trade.first_tp_pnl + net_pnl

        trade.exit_time = time
        trade.exit_price = price
        trade.result = total_pnl
        trade.status = 'FINAL_TP'

        self.balance += net_pnl
        self.closed_trades.append(trade)
        self.positions.remove(trade)

    def _hit_be(self, trade, price, time):
        """Hit BE after first TP - second half closes at 0R."""
        # Second 50% closes at BE (entry price)
        # PnL = 0 for this part (minus commission)
        comm = self.config['commission_per_lot'] * 0.5
        net_pnl = -comm  # Just commission loss

        # Total PnL
        total_pnl = trade.first_tp_pnl + net_pnl

        trade.exit_time = time
        trade.exit_price = price
        trade.result = total_pnl
        trade.status = 'BE_HIT'

        self.balance += net_pnl
        self.closed_trades.append(trade)
        self.positions.remove(trade)

    def _close_full_position(self, trade, price, time, reason):
        """Close full position (before first TP hit)."""
        lot_size = self.config['lot_size']

        if trade.direction == 'LONG':
            gross_pnl = (price - trade.entry_price) * lot_size
        else:
            gross_pnl = (trade.entry_price - price) * lot_size

        comm = self.config['commission_per_lot']
        net_pnl = gross_pnl - comm

        trade.exit_time = time
        trade.exit_price = price
        trade.result = net_pnl
        trade.status = reason

        self.balance += net_pnl
        self.closed_trades.append(trade)
        self.positions.remove(trade)

    def get_results_df(self):
        """Export results to DataFrame."""
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
                'sl': t.entry_price if t.be_moved else t.sl,  # Show final SL
                'tp': t.final_tp,
                'pnl': t.result,
                'status': t.status,
                'touch_no': t.touch_no,
                'zone_created_at': t.zone_created_at,
                'first_tp_hit': t.first_tp_hit,
                'first_tp_pnl': t.first_tp_pnl if t.first_tp_hit else 0.0
            })
        return pd.DataFrame(data)


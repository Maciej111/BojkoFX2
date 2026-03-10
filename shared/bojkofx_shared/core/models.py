"""
Core data models - pure dataclasses without external dependencies
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
from enum import Enum


class Side(Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ExitReason(Enum):
    TP = "TP"
    SL = "SL"
    TS = "TS"       # Trailing Stop hit
    CANCEL = "CANCEL"
    EXPIRE = "EXPIRE"
    MANUAL = "MANUAL"


@dataclass
class Tick:
    """Raw tick data"""
    timestamp: datetime
    bid: float
    ask: float
    symbol: str = ""


@dataclass
class Bar:
    """OHLC bar (any timeframe)"""
    timestamp: datetime
    open_bid: float
    high_bid: float
    low_bid: float
    close_bid: float
    open_ask: float
    high_ask: float
    low_ask: float
    close_ask: float
    symbol: str = ""
    timeframe: str = "H1"
    
    @property
    def mid_close(self) -> float:
        return (self.close_bid + self.close_ask) / 2


@dataclass
class Signal:
    """Trading signal from strategy"""
    timestamp: datetime
    symbol: str
    side: Side
    reason: str  # e.g., "BOS_PULLBACK"
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class OrderIntent:
    """Order intent from strategy (execution-agnostic)"""
    signal_id: str
    timestamp: datetime
    symbol: str
    side: Side
    entry_type: OrderType
    entry_price: Optional[float] = None  # None = MARKET
    sl_price: float = 0.0
    tp_price: float = 0.0
    ttl_bars: int = 40  # time-to-live in bars
    risk_R: float = 1.0  # risk in R units
    metadata: dict = field(default_factory=dict)


@dataclass
class Fill:
    """Order fill event"""
    order_id: str
    signal_id: str
    timestamp: datetime
    symbol: str
    side: Side
    fill_price: float
    units: float
    spread_at_fill: float = 0.0
    latency_ms: float = 0.0
    slippage_pips: float = 0.0


@dataclass
class Trade:
    """Complete trade (entry + exit)"""
    trade_id: str
    signal_id: str
    symbol: str
    side: Side
    
    # Entry
    entry_time: datetime
    entry_price: float
    entry_units: float
    
    # Exit
    exit_time: datetime
    exit_price: float
    exit_reason: ExitReason
    
    # Risk/Reward
    sl_price: float
    tp_price: float
    risk_distance: float
    reward_distance: float
    
    # Performance
    pnl: float
    R_multiple: float
    
    # Execution quality
    entry_slippage_pips: float = 0.0
    exit_slippage_pips: float = 0.0
    entry_latency_ms: float = 0.0
    exit_latency_ms: float = 0.0
    spread_at_entry: float = 0.0
    spread_at_exit: float = 0.0
    
    # Metadata
    metadata: dict = field(default_factory=dict)


@dataclass
class Position:
    """Current open position"""
    position_id: str
    signal_id: str
    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    units: float
    sl_price: float
    tp_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


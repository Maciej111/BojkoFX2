"""
Configuration loader with typed config
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List


@dataclass
class SymbolConfig:
    """Per-symbol trading configuration"""
    ltf: str = "H1"              # LTF timeframe: "H1" or "30m"
    htf: str = "D1"              # HTF timeframe: "D1" or "H4"
    session_filter: bool = True  # True = restrict entries to session window below
    session_start_h: int = 8     # UTC hour inclusive (default: London open)
    session_end_h: int = 21      # UTC hour exclusive (default: NY close)
    enabled: bool = True         # False = skip this symbol entirely
    # ATR percentile filter (Priorytet 2 — 2026-03-04)
    atr_pct_filter_min: Optional[float] = None
    atr_pct_filter_max: Optional[float] = None
    # H4 ADX gate (Priorytet 3 — 2026-03-04)
    adx_h4_gate: Optional[float] = None
    # Per-symbol risk/reward override (None = use global strategy.risk_reward)
    # USDJPY: 2.5 (TS backtests), CADJPY: 3.0 (unchanged), others: None → global
    risk_reward: Optional[float] = None
    # Trailing stop config (2026-03-08 — validated USDJPY + CADJPY)
    # None = disabled. Dict keys: enabled (bool), ts_r (float), lock_r (float)
    # ts_r: activation threshold in R units from entry
    # lock_r: SL locked to entry + lock_r * risk at activation (0 = breakeven)
    trailing_stop: Optional[dict] = None

    @property
    def ltf_resample(self) -> str:
        """Pandas resample string for LTF"""
        return {"H1": "1h", "30m": "30min", "30M": "30min"}.get(self.ltf, "1h")

    @property
    def htf_resample(self) -> str:
        """Pandas resample string for HTF"""
        return {"D1": "1D", "H4": "4h", "H8": "8h"}.get(self.htf, "1D")

    def in_session(self, hour: int) -> bool:
        """Return True if UTC hour is within this symbol's trading window."""
        if not self.session_filter:
            return True
        return self.session_start_h <= hour < self.session_end_h


# Default symbol configs (used when not present in YAML)
# Session windows derived from SESSION_ANALYSIS.md (OOS 2023-2024 backtests)
DEFAULT_SYMBOLS: Dict[str, SymbolConfig] = {
    # EURUSD: best = Overlap 13-17, safe window = London+NY 08-21
    "EURUSD": SymbolConfig(ltf="H1",  htf="D1", session_filter=True,  session_start_h=8,  session_end_h=21,  adx_h4_gate=16.0),
    # USDJPY: 24h optimal — trailing stop RR=2.5, ts_r=2.0, lock_r=0.5 (validated 2 OOS periods)
    "USDJPY": SymbolConfig(ltf="H1",  htf="D1", session_filter=False, session_start_h=0,  session_end_h=24,  adx_h4_gate=16.0,
                           risk_reward=2.5,
                           trailing_stop={"enabled": True, "ts_r": 2.0, "lock_r": 0.5}),
    # USDCHF: Off-hours 21-00 very bad (-0.36R) → cut at 21 UTC. HTF=D1 (OOS2025: H4=-0.08R, D1=+0.30R)
    "USDCHF": SymbolConfig(ltf="H1",  htf="D1", session_filter=True,  session_start_h=8,  session_end_h=21,  adx_h4_gate=16.0),
    # AUDJPY: London+NY ≈ 24h, Off-hours 21-00 negative (-0.17R) → add filter
    "AUDJPY": SymbolConfig(ltf="H1",  htf="D1", session_filter=True,  session_start_h=0,  session_end_h=21,  adx_h4_gate=16.0),
    # CADJPY: ATR filtr 10-80, trailing stop RR=3.0, ts_r=2.0, lock_r=0.5 (validated 2 OOS periods)
    "CADJPY": SymbolConfig(ltf="H1",  htf="D1", session_filter=False, session_start_h=0,  session_end_h=24,  adx_h4_gate=None,
                           atr_pct_filter_min=10.0, atr_pct_filter_max=80.0,
                           risk_reward=3.0,
                           trailing_stop={"enabled": True, "ts_r": 2.0, "lock_r": 0.5}),
    # Legacy pairs (kept for backtest compatibility)
    "EURJPY": SymbolConfig(ltf="H1",  htf="D1", session_filter=False, session_start_h=0,  session_end_h=24),
    "GBPJPY": SymbolConfig(ltf="30m", htf="D1", session_filter=False, session_start_h=0,  session_end_h=24),
    "GBPUSD": SymbolConfig(ltf="30m", htf="D1", session_filter=True,  session_start_h=8,  session_end_h=21),
}


@dataclass
class StrategyConfig:
    """Strategy parameters (frozen from PROOF V2)"""
    entry_offset_atr_mult: float = 0.3
    pullback_max_bars: int = 40
    risk_reward: float = 1.5
    sl_anchor: str = "last_pivot"
    sl_buffer_atr_mult: float = 0.5
    pivot_lookback_ltf: int = 3
    pivot_lookback_htf: int = 5
    confirmation_bars: int = 1
    require_close_break: bool = True


@dataclass
class RiskConfig:
    """Risk management parameters"""
    risk_fraction_start: float = 0.005  # 0.5% per trade (used by both modes)
    sizing_mode: str = "risk_first"     # "risk_first" | "fixed_units"
    default_units: int = 5000           # used only when sizing_mode == "fixed_units"
    max_units_per_trade: int = 200_000  # hard cap — prevents giant orders on large paper accounts
    equity_override: float = 0.0        # >0 → use this fixed value instead of IBKR NetLiquidation
    max_open_positions_total: int = 5       # 1 per symbol × 5 aktywnych symboli
    max_open_positions_per_symbol: int = 1
    daily_loss_limit_pct: float = 2.0
    monthly_dd_stop_pct: float = 15.0
    kill_switch_dd_pct: float = 10.0


@dataclass
class IBKRConfig:
    """IBKR Gateway / TWS connection configuration"""
    host: str = "127.0.0.1"
    port: int = 4002            # 4002 = Gateway paper, 7497 = TWS paper
    client_id: int = 7
    account: str = ""           # Optional: IBKR account string
    readonly: bool = True       # Safety: do not send orders unless False
    allow_live_orders: bool = False  # Extra gate: must be explicitly True
    historical_days: int = 60   # Days of H1 history to bootstrap on start
    default_units_fx: int = 5000  # Conservative default position size (FX)


@dataclass
class Config:
    """Complete system configuration"""
    strategy: StrategyConfig
    risk: RiskConfig
    ibkr: Optional[IBKRConfig] = None
    symbols: Dict[str, SymbolConfig] = field(default_factory=lambda: dict(DEFAULT_SYMBOLS))

    def get_symbol_config(self, symbol: str) -> SymbolConfig:
        """Return per-symbol config, falling back to defaults."""
        return self.symbols.get(symbol.upper(),
               DEFAULT_SYMBOLS.get(symbol.upper(), SymbolConfig()))

    def enabled_symbols(self) -> List[str]:
        """Return list of enabled symbol names."""
        return [s for s, cfg in self.symbols.items() if cfg.enabled]

    @classmethod
    def from_yaml(cls, path: str = "config/config.yaml") -> "Config":
        """Load config from YAML file"""
        config_path = Path(path)

        if not config_path.exists():
            return cls(
                strategy=StrategyConfig(),
                risk=RiskConfig(),
                ibkr=IBKRConfig(),
            )

        with open(config_path, 'r', encoding='utf-8-sig') as f:
            data = yaml.safe_load(f)

        strategy_data = data.get('strategy', {})
        risk_data = data.get('risk', {})
        ibkr_data = data.get('ibkr', {})
        symbols_data = data.get('symbols', {})

        # Filter only known keys to avoid TypeError on unexpected YAML fields
        strategy_fields = {f.name for f in StrategyConfig.__dataclass_fields__.values()}
        risk_fields = {f.name for f in RiskConfig.__dataclass_fields__.values()}
        ibkr_fields = {f.name for f in IBKRConfig.__dataclass_fields__.values()}
        symbol_fields = {f.name for f in SymbolConfig.__dataclass_fields__.values()}

        strategy_data = {k: v for k, v in strategy_data.items() if k in strategy_fields}
        risk_data = {k: v for k, v in risk_data.items() if k in risk_fields}
        ibkr_data = {k: v for k, v in ibkr_data.items() if k in ibkr_fields}

        # Parse per-symbol configs
        symbols: Dict[str, SymbolConfig] = dict(DEFAULT_SYMBOLS)
        for sym, sym_data in symbols_data.items():
            if isinstance(sym_data, dict):
                filtered = {k: v for k, v in sym_data.items() if k in symbol_fields}
                symbols[sym.upper()] = SymbolConfig(**filtered)

        return cls(
            strategy=StrategyConfig(**strategy_data),
            risk=RiskConfig(**risk_data),
            ibkr=IBKRConfig(**ibkr_data) if ibkr_data else IBKRConfig(),
            symbols=symbols,
        )

    @classmethod
    def from_env(cls, base_config_path: str = "config/config.yaml") -> "Config":
        """Load config, then override IBKR settings from ENV variables."""
        import os

        config = cls.from_yaml(base_config_path)

        ibkr = config.ibkr or IBKRConfig()

        ibkr.host = os.getenv('IBKR_HOST', ibkr.host)
        ibkr.port = int(os.getenv('IBKR_PORT', str(ibkr.port)))
        ibkr.client_id = int(os.getenv('IBKR_CLIENT_ID', str(ibkr.client_id)))
        ibkr.account = os.getenv('IBKR_ACCOUNT', ibkr.account)
        ibkr.readonly = os.getenv('IBKR_READONLY', 'true').lower() != 'false'
        ibkr.allow_live_orders = os.getenv('ALLOW_LIVE_ORDERS', 'false').lower() == 'true'

        # Global kill switch from ENV
        kill_switch = os.getenv('KILL_SWITCH', 'false').lower() == 'true'

        config.ibkr = ibkr
        config.symbols = config.symbols  # already loaded from YAML, keep as-is
        config._kill_switch_from_env = kill_switch  # attach as runtime attr

        return config


"""
Walk-Forward Validation — M60 (H1) Strategy
============================================
Approach:
  - TRAIN window: 2021-01-01 to 2022-12-31  (fixed, 2 years)
  - OOS split into 8 quarters: Q1-2023 ... Q4-2024
  - For each symbol: take the best config from grid results CSV
    (highest OOS ExpR), then re-run it on each quarter independently.
  - Also runs the reference config (D1, RR=3.0, off=0.3, buf=0.1, pmb=50)
    on every symbol/quarter for cross-symbol comparability.

Outputs:
    data/outputs/m60_walkforward_results.csv
    reports/M60_WALKFORWARD_REPORT.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parent.parent
DATA_DIR_M60 = ROOT / "data" / "raw_dl_fx" / "download" / "m60"
GRID_CSV     = ROOT / "data" / "outputs" / "m60_grid_results.csv"
OUT_DIR      = ROOT / "data" / "outputs"
REPORT_DIR   = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Walk-forward quarters (OOS window 2023-2024) ──────────────────────────────
QUARTERS = [
    ("Q1-2023", "2023-01-01", "2023-03-31"),
    ("Q2-2023", "2023-04-01", "2023-06-30"),
    ("Q3-2023", "2023-07-01", "2023-09-30"),
    ("Q4-2023", "2023-10-01", "2023-12-31"),
    ("Q1-2024", "2024-01-01", "2024-03-31"),
    ("Q2-2024", "2024-04-01", "2024-06-30"),
    ("Q3-2024", "2024-07-01", "2024-09-30"),
    ("Q4-2024", "2024-10-01", "2024-12-31"),
]

# Reference config applied to ALL symbols for cross-symbol comparison
REF_CFG = dict(htf="1D", risk_reward=3.0, entry_offset_atr_mult=0.3,
               sl_buffer_atr_mult=0.1, pullback_max_bars=50)

SYMBOL_PARAMS = {
    "eurusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "gbpusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "audusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "nzdusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdcad": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.5, session_filter=False),
    "gbpjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "eurjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "audjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "cadjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "gbpchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
    "eurgbp": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
    "eurchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
}
ALL_SYMBOLS = list(SYMBOL_PARAMS.keys())


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open", "high", "low", "close"]].dropna()


def load_m60_bars(symbol: str) -> pd.DataFrame:
    bid_file = DATA_DIR_M60 / f"{symbol}_m60_bid_2021_2024.csv"
    ask_file = DATA_DIR_M60 / f"{symbol}_m60_ask_2021_2024.csv"
    if not bid_file.exists() or not ask_file.exists():
        raise FileNotFoundError(f"Missing M60 data for {symbol}")
    bid = _read_csv(bid_file)
    ask = _read_csv(ask_file)
    idx = bid.index.intersection(ask.index)
    df = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        df[f"{c}_bid"] = bid.loc[idx, c].values
        df[f"{c}_ask"] = ask.loc[idx, c].values
    df = df.dropna()
    df = df[(df["high_bid"] - df["low_bid"]) > 0].copy()
    return df


def build_htf(ltf: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open_bid": "first", "high_bid": "max", "low_bid": "min", "close_bid": "last",
        "open_ask": "first", "high_ask": "max", "low_ask": "min", "close_ask": "last",
    }
    return ltf.resample(rule).agg(agg).dropna()


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h = df["high_bid"].values
    l = df["low_bid"].values
    c = df["close_bid"].values
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    return pd.Series(tr, index=df.index).rolling(period).mean()


def build_pivot_arrays(df: pd.DataFrame, lookback: int, confirmation: int = 1):
    n = len(df)
    h = df["high_bid"].values.astype(np.float64)
    l = df["low_bid"].values.astype(np.float64)
    w = 2 * lookback + 1
    h_pad = np.pad(h, (lookback, lookback), mode='edge')
    l_pad = np.pad(l, (lookback, lookback), mode='edge')
    shape   = (n, w)
    strides = (h_pad.strides[0], h_pad.strides[0])
    h_win = np.lib.stride_tricks.as_strided(h_pad, shape=shape, strides=strides)
    l_win = np.lib.stride_tricks.as_strided(l_pad, shape=shape, strides=strides)
    raw_ph = h == h_win.max(axis=1)
    raw_pl = l == l_win.min(axis=1)
    raw_ph[:lookback] = False;  raw_ph[n-lookback:] = False
    raw_pl[:lookback] = False;  raw_pl[n-lookback:] = False
    conf_ph = np.zeros(n, bool)
    conf_pl = np.zeros(n, bool)
    if confirmation > 0:
        conf_ph[confirmation:] = raw_ph[:-confirmation]
        conf_pl[confirmation:] = raw_pl[:-confirmation]
    else:
        conf_ph[:] = raw_ph
        conf_pl[:] = raw_pl
    ph_lv = np.full(n, np.nan)
    pl_lv = np.full(n, np.nan)
    src = np.clip(np.arange(n) - (confirmation if confirmation > 0 else 0), 0, n-1)
    ph_lv[conf_ph] = h[src[conf_ph]]
    pl_lv[conf_pl] = l[src[conf_pl]]
    return ph_lv, pl_lv, conf_ph, conf_pl


def get_htf_bias_at(ltf_time, htf_df, htf_ph_lv, htf_pl_lv,
                    htf_ph_mask, htf_pl_mask, pivot_count=4) -> str:
    pos = htf_df.index.searchsorted(ltf_time, side="right") - 1
    if pos < 1:
        return "NEUTRAL"
    last_close = htf_df["close_bid"].iloc[pos]
    ph_p, pl_p = [], []
    for j in range(pos, -1, -1):
        if htf_ph_mask[j] and not np.isnan(htf_ph_lv[j]):
            ph_p.append(htf_ph_lv[j])
        if htf_pl_mask[j] and not np.isnan(htf_pl_lv[j]):
            pl_p.append(htf_pl_lv[j])
        if len(ph_p) >= pivot_count and len(pl_p) >= pivot_count:
            break
    if len(ph_p) < 2 or len(pl_p) < 2:
        return "NEUTRAL"
    if last_close > ph_p[0]:
        return "BULL"
    if last_close < pl_p[0]:
        return "BEAR"
    hh = ph_p[0] > ph_p[1]; hl = pl_p[0] > pl_p[1]
    ll = pl_p[0] < pl_p[1]; lh = ph_p[0] < ph_p[1]
    if hh and hl:
        return "BULL"
    if ll and lh:
        return "BEAR"
    return "NEUTRAL"


def _last_pv(bar_i, pv_lv, pv_mask, max_lb=100):
    stop = max(0, bar_i - max_lb)
    for j in range(bar_i - 1, stop - 1, -1):
        if pv_mask[j] and not np.isnan(pv_lv[j]):
            return pv_lv[j]
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG & OBJECTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    htf: str = "1D"
    pivot_lookback_ltf: int = 3
    pivot_lookback_htf: int = 5
    confirmation_bars: int = 1
    entry_offset_atr_mult: float = 0.3
    pullback_max_bars: int = 50
    sl_buffer_atr_mult: float = 0.1
    risk_reward: float = 3.0
    atr_period: int = 14
    htf_pivot_count: int = 4
    session_filter: bool = True
    session_start_h: int = 7
    session_end_h: int = 21
    commission: float = 0.00005
    min_risk: float = 0.0003
    risk_pct: float = 0.01
    initial_balance: float = 10_000.0


@dataclass
class Trade:
    direction: str
    entry_price: float
    sl: float
    tp: float
    risk_dist: float
    entry_idx: int
    exit_idx: int = -1
    exit_price: float = 0.0
    exit_reason: str = ""
    R: float = 0.0


@dataclass
class _Setup:
    direction: str
    entry_price: float
    expiry_idx: int
    bos_level: float


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE  (identical logic to m60_grid_backtest.py)
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(ltf_full: pd.DataFrame, cfg: Config,
                 period_start: str, period_end: str) -> Tuple[List[Trade], pd.Series]:
    """Run backtest on ltf_full but ONLY score trades within [period_start, period_end].
    Indicators and pivot arrays are built on the FULL dataset so look-back is warm."""

    mask = (ltf_full.index >= period_start) & (ltf_full.index <= period_end)
    if mask.sum() < 10:
        return [], pd.Series(dtype=float)

    htf_full = build_htf(ltf_full, cfg.htf)
    atr_vals = calc_atr(ltf_full, cfg.atr_period).values

    ltf_ph_lv, ltf_pl_lv, ltf_ph_mask, ltf_pl_mask = build_pivot_arrays(
        ltf_full, cfg.pivot_lookback_ltf, cfg.confirmation_bars)
    htf_ph_lv, htf_pl_lv, htf_ph_mask, htf_pl_mask = build_pivot_arrays(
        htf_full, cfg.pivot_lookback_htf, cfg.confirmation_bars)

    idx       = ltf_full.index
    close_bid = ltf_full["close_bid"].values
    high_bid  = ltf_full["high_bid"].values
    low_bid   = ltf_full["low_bid"].values
    high_ask  = ltf_full["high_ask"].values
    low_ask   = ltf_full["low_ask"].values

    # Start at least 200 bars in for warm-up, but never before period_start
    warmup_i  = 200
    start_i   = max(idx.searchsorted(period_start, side="left"), warmup_i)
    end_i     = idx.searchsorted(period_end, side="right")

    trades: List[Trade] = []
    equity = cfg.initial_balance
    eq_dict = {}
    active_setup: Optional[_Setup] = None
    open_trade:   Optional[Trade]  = None

    for i in range(start_i, end_i):
        t   = idx[i]
        atr = atr_vals[i]
        if np.isnan(atr) or atr <= 0:
            eq_dict[t] = equity
            continue

        # Exit
        if open_trade is not None:
            tr = open_trade
            sl_hit = (low_bid[i] <= tr.sl  if tr.direction == "LONG" else high_ask[i] >= tr.sl)
            tp_hit = (high_bid[i] >= tr.tp if tr.direction == "LONG" else low_ask[i]  <= tr.tp)
            if sl_hit and tp_hit:
                sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep = tr.sl if sl_hit else tr.tp
                if tr.direction == "LONG":
                    ep = max(min(ep, high_bid[i]), low_bid[i]) - cfg.commission
                else:
                    ep = max(min(ep, high_ask[i]), low_ask[i]) + cfg.commission
                reason = "SL" if sl_hit else "TP"
                tr.R = ((ep - tr.entry_price) / tr.risk_dist if tr.direction == "LONG"
                        else (tr.entry_price - ep) / tr.risk_dist)
                tr.exit_price = ep; tr.exit_reason = reason; tr.exit_idx = i
                equity *= (1.0 + tr.R * cfg.risk_pct)
                trades.append(tr)
                open_trade = None

        eq_dict[t] = equity
        if open_trade is not None:
            continue

        # Fill
        if active_setup is not None:
            s = active_setup
            if i > s.expiry_idx:
                active_setup = None
            else:
                filled = (low_ask[i] <= s.entry_price <= high_ask[i] if s.direction == "LONG"
                          else low_bid[i] <= s.entry_price <= high_bid[i])
                if filled:
                    fill_p = (s.entry_price + cfg.commission if s.direction == "LONG"
                              else s.entry_price - cfg.commission)
                    buf = cfg.sl_buffer_atr_mult * atr
                    if s.direction == "LONG":
                        lv = _last_pv(i, ltf_pl_lv, ltf_pl_mask)
                        sl = (lv - buf) if lv else (close_bid[i] - 2*atr)
                        sl = max(sl, close_bid[i] - 5*atr)
                    else:
                        lv = _last_pv(i, ltf_ph_lv, ltf_ph_mask)
                        sl = (lv + buf) if lv else (close_bid[i] + 2*atr)
                        sl = min(sl, close_bid[i] + 5*atr)
                    risk_dist = abs(fill_p - sl)
                    if risk_dist < cfg.min_risk:
                        active_setup = None
                        continue
                    tp = (fill_p + risk_dist * cfg.risk_reward if s.direction == "LONG"
                          else fill_p - risk_dist * cfg.risk_reward)
                    open_trade = Trade(s.direction, fill_p, sl, tp, risk_dist, i)
                    active_setup = None
                    continue

        if active_setup is not None or open_trade is not None:
            continue

        # Session filter
        if cfg.session_filter and not (cfg.session_start_h <= t.hour < cfg.session_end_h):
            continue

        # HTF bias
        bias = get_htf_bias_at(t, htf_full, htf_ph_lv, htf_pl_lv,
                               htf_ph_mask, htf_pl_mask, cfg.htf_pivot_count)
        if bias == "NEUTRAL":
            continue

        # BOS
        last_ph = _last_pv(i, ltf_ph_lv, ltf_ph_mask)
        last_pl = _last_pv(i, ltf_pl_lv, ltf_pl_mask)
        bos_dir = bos_level = None
        if bias == "BULL" and last_ph and close_bid[i] > last_ph:
            bos_dir, bos_level = "LONG", last_ph
        elif bias == "BEAR" and last_pl and close_bid[i] < last_pl:
            bos_dir, bos_level = "SHORT", last_pl
        if bos_dir is None:
            continue

        offset = cfg.entry_offset_atr_mult * atr
        entry  = bos_level + offset if bos_dir == "LONG" else bos_level - offset
        active_setup = _Setup(bos_dir, entry, i + cfg.pullback_max_bars, bos_level)

    return trades, pd.Series(eq_dict)


def calc_metrics(trades: List[Trade], eq: pd.Series, bal: float = 10_000.0) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "expR": 0.0, "pf": 0.0, "dd": 0.0, "ret": 0.0,
                "long_n": 0, "short_n": 0}
    Rs    = [t.R for t in trades]
    wins  = [r for r in Rs if r > 0]
    loss  = [r for r in Rs if r <= 0]
    pf    = sum(wins) / abs(sum(loss)) if loss else float("inf")
    longs  = sum(1 for t in trades if t.direction == "LONG")
    shorts = sum(1 for t in trades if t.direction == "SHORT")
    if not eq.empty:
        peak  = np.maximum.accumulate(eq.values)
        dd    = np.where(peak > 0, (peak - eq.values) / peak * 100, 0)
        maxdd = float(dd.max())
        ret   = float((eq.iloc[-1] / bal - 1) * 100)
    else:
        maxdd = ret = 0.0
    return {"n": len(Rs), "wr": round(len(wins)/len(Rs)*100, 1),
            "expR": round(float(np.mean(Rs)), 4), "pf": round(pf, 3),
            "dd": round(maxdd, 1), "ret": round(ret, 1),
            "long_n": longs, "short_n": shorts}


# ══════════════════════════════════════════════════════════════════════════════
# LOAD BEST CONFIGS FROM GRID CSV
# ══════════════════════════════════════════════════════════════════════════════

def load_best_configs(grid_csv: Path) -> dict:
    """Return {symbol_lower: dict_of_best_params} from grid results."""
    df = pd.read_csv(grid_csv)
    best = {}
    for sym, grp in df.groupby("symbol"):
        row = grp.sort_values("oos_expR", ascending=False).iloc[0]
        best[sym.lower()] = {
            "htf":                   row["htf"],
            "risk_reward":           float(row["risk_reward"]),
            "entry_offset_atr_mult": float(row["entry_offset_atr_mult"]),
            "sl_buffer_atr_mult":    float(row["sl_buffer_atr_mult"]),
            "pullback_max_bars":     int(row["pullback_max_bars"]),
        }
    return best


# ══════════════════════════════════════════════════════════════════════════════
# WALK-FORWARD RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def make_cfg(params: dict, sp: dict) -> Config:
    pip = sp["pip"]
    return Config(
        htf=params["htf"],
        risk_reward=params["risk_reward"],
        entry_offset_atr_mult=params["entry_offset_atr_mult"],
        sl_buffer_atr_mult=params["sl_buffer_atr_mult"],
        pullback_max_bars=params["pullback_max_bars"],
        commission=sp["commission_pips"] * pip,
        min_risk=sp["min_risk_pips"] * pip,
        session_filter=sp["session_filter"],
    )


def run_walkforward(symbol: str, bars: pd.DataFrame,
                    best_params: dict, ref_params: dict,
                    sp: dict) -> List[dict]:
    rows = []
    cfg_best = make_cfg(best_params, sp)
    cfg_ref  = make_cfg(ref_params,  sp)

    for qname, qstart, qend in QUARTERS:
        for cfg_type, cfg in [("best", cfg_best), ("ref", cfg_ref)]:
            trades, eq = run_backtest(bars, cfg, qstart, qend)
            m = calc_metrics(trades, eq, cfg.initial_balance)
            rows.append({
                "symbol":  symbol.upper(),
                "quarter": qname,
                "config":  cfg_type,
                "htf":     cfg.htf,
                "rr":      cfg.risk_reward,
                "off":     cfg.entry_offset_atr_mult,
                "buf":     cfg.sl_buffer_atr_mult,
                "pmb":     cfg.pullback_max_bars,
                **{f"{k}": v for k, v in m.items()},
            })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def stability_score(quarterly_expRs: list) -> str:
    """Rate consistency of quarterly results."""
    if not quarterly_expRs:
        return "N/A"
    pos = sum(1 for r in quarterly_expRs if r > 0)
    frac = pos / len(quarterly_expRs)
    avg  = np.mean(quarterly_expRs)
    std  = np.std(quarterly_expRs)
    if frac >= 0.75 and avg > 0.15 and std < 0.5:
        return "STABLE"
    elif frac >= 0.5 and avg > 0.05:
        return "MODERATE"
    else:
        return "UNSTABLE"


def generate_report(df: pd.DataFrame) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []

    L.append("# Walk-Forward Validation Report — M60/H1 Strategy")
    L.append("")
    L.append(f"> Generated: {now}")
    L.append(f"> LTF: H1 (native M60) | OOS split: 8 quarters (Q1-2023 to Q4-2024)")
    L.append(f"> Two configs tested per symbol per quarter:")
    L.append(f">   - **best**: top config from grid search (per-symbol)")
    L.append(f">   - **ref**:  reference config D1/RR=3.0/off=0.3/buf=0.1/pmb=50")
    L.append(f"> Risk: 1% equity/trade")
    L.append("")
    L.append("---")
    L.append("")

    symbols = sorted(df["symbol"].unique())
    quarters = [q[0] for q in QUARTERS]

    # ── 1. Heatmap: ExpR per symbol per quarter (best config) ─────────────────
    L.append("## Heatmap — OOS ExpR per Quarter (Best Config)")
    L.append("")
    L.append("*Positive = profitable quarter. Stability = % profitable quarters.*")
    L.append("")

    hdr = "| Symbol | " + " | ".join(quarters) + " | +Q | Stab | Avg ExpR |"
    sep = "|--------|" + "|".join(["------"]*len(quarters)) + "|----|----|---------|"
    L.append(hdr)
    L.append(sep)

    sym_stability = {}
    for sym in symbols:
        sub = df[(df["symbol"] == sym) & (df["config"] == "best")]
        vals = []
        cells = []
        for q in quarters:
            row = sub[sub["quarter"] == q]
            if not row.empty:
                v = row.iloc[0]["expR"]
                vals.append(v)
                sign = "+" if v >= 0 else ""
                cells.append(f"{sign}{v:.3f}R")
            else:
                cells.append("—")
        pos_q = sum(1 for v in vals if v > 0)
        stab  = stability_score(vals)
        avg   = np.mean(vals) if vals else 0.0
        sym_stability[sym] = (stab, pos_q, avg)
        L.append(f"| {sym} | " + " | ".join(cells) +
                 f" | {pos_q}/8 | {stab} | {avg:+.3f}R |")

    L.append("")
    L.append("---")
    L.append("")

    # ── 2. Heatmap: Reference config ─────────────────────────────────────────
    L.append("## Heatmap — OOS ExpR per Quarter (Reference Config D1/RR=3.0/off=0.3/buf=0.1/pmb=50)")
    L.append("")
    hdr2 = "| Symbol | " + " | ".join(quarters) + " | +Q | Avg ExpR |"
    sep2 = "|--------|" + "|".join(["------"]*len(quarters)) + "|----|---------|"
    L.append(hdr2)
    L.append(sep2)

    for sym in symbols:
        sub = df[(df["symbol"] == sym) & (df["config"] == "ref")]
        vals = []
        cells = []
        for q in quarters:
            row = sub[sub["quarter"] == q]
            if not row.empty:
                v = row.iloc[0]["expR"]
                vals.append(v)
                sign = "+" if v >= 0 else ""
                cells.append(f"{sign}{v:.3f}R")
            else:
                cells.append("—")
        pos_q = sum(1 for v in vals if v > 0)
        avg   = np.mean(vals) if vals else 0.0
        L.append(f"| {sym} | " + " | ".join(cells) +
                 f" | {pos_q}/8 | {avg:+.3f}R |")

    L.append("")
    L.append("---")
    L.append("")

    # ── 3. Stability ranking ──────────────────────────────────────────────────
    L.append("## Stability Ranking (Best Config)")
    L.append("")
    L.append("| Rank | Symbol | Stability | +Q/8 | Avg ExpR | Verdict |")
    L.append("|------|--------|-----------|------|----------|---------|")

    ranked = sorted(sym_stability.items(), key=lambda x: (x[1][1], x[1][2]), reverse=True)
    for rank, (sym, (stab, pos_q, avg)) in enumerate(ranked, 1):
        if stab == "STABLE" and avg > 0.20:
            verdict = "✅ DEPLOY"
        elif stab == "STABLE" or (stab == "MODERATE" and avg > 0.15):
            verdict = "✅ MONITOR"
        elif stab == "MODERATE":
            verdict = "⚠️ CAUTION"
        else:
            verdict = "❌ SKIP"
        L.append(f"| {rank} | {sym} | {stab} | {pos_q}/8 | {avg:+.3f}R | {verdict} |")

    L.append("")
    L.append("---")
    L.append("")

    # ── 4. Per-symbol quarterly detail ───────────────────────────────────────
    L.append("## Per-Symbol Quarterly Detail")
    L.append("")

    for sym in symbols:
        sub_best = df[(df["symbol"] == sym) & (df["config"] == "best")]
        sub_ref  = df[(df["symbol"] == sym) & (df["config"] == "ref")]
        stab, pos_q, avg = sym_stability.get(sym, ("?", 0, 0.0))

        L.append(f"### {sym}  —  {stab} ({pos_q}/8 positive quarters, avg {avg:+.3f}R)")
        L.append("")
        L.append("| Quarter | Config | n | WR | ExpR | PF | DD | Ret | Long | Short |")
        L.append("|---------|--------|---|----|----|----|----|-----|------|-------|")

        for q in quarters:
            for cfg_type, sub in [("best", sub_best), ("ref", sub_ref)]:
                row = sub[sub["quarter"] == q]
                if not row.empty:
                    r = row.iloc[0]
                    sign = "+" if r["expR"] >= 0 else ""
                    L.append(f"| {q} | {cfg_type} | {int(r['n'])} | {r['wr']}% | "
                             f"{sign}{r['expR']:.3f}R | {r['pf']:.3f} | "
                             f"{r['dd']:.1f}% | {r['ret']:+.1f}% | "
                             f"{int(r['long_n'])} | {int(r['short_n'])} |")

        # Trend analysis
        best_vals = []
        for q in quarters:
            row = sub_best[sub_best["quarter"] == q]
            if not row.empty:
                best_vals.append(float(row.iloc[0]["expR"]))

        if len(best_vals) >= 4:
            h1 = np.mean(best_vals[:4])  # 2023
            h2 = np.mean(best_vals[4:])  # 2024
            trend = "improving" if h2 > h1 else "deteriorating"
            L.append(f"")
            L.append(f"> 2023 avg ExpR: {h1:+.3f}R | 2024 avg ExpR: {h2:+.3f}R "
                     f"| Trend: **{trend}**")

        L.append("")

    # ── 5. Quarter-by-quarter cross-symbol summary ────────────────────────────
    L.append("---")
    L.append("")
    L.append("## Quarter-by-Quarter Cross-Symbol Summary (Reference Config)")
    L.append("")
    L.append("*How many symbols were profitable each quarter at reference config.*")
    L.append("")
    L.append("| Quarter | +Symbols | -Symbols | Avg ExpR | Best | Worst |")
    L.append("|---------|----------|----------|----------|------|-------|")

    for q in quarters:
        sub = df[(df["config"] == "ref") & (df["quarter"] == q)]
        expRs = sub["expR"].tolist()
        pos   = sum(1 for v in expRs if v > 0)
        neg   = len(expRs) - pos
        avg   = np.mean(expRs) if expRs else 0.0
        if sub.empty:
            continue
        best_sym  = sub.loc[sub["expR"].idxmax(), "symbol"]
        worst_sym = sub.loc[sub["expR"].idxmin(), "symbol"]
        best_v    = sub["expR"].max()
        worst_v   = sub["expR"].min()
        L.append(f"| {q} | {pos} | {neg} | {avg:+.3f}R | "
                 f"{best_sym} ({best_v:+.3f}R) | {worst_sym} ({worst_v:+.3f}R) |")

    L.append("")
    L.append("---")
    L.append("")

    # ── 6. Final recommendations ──────────────────────────────────────────────
    L.append("## Final Deployment Recommendations")
    L.append("")
    deploy   = [(sym, avg) for sym, (stab, pq, avg) in sym_stability.items()
                if stab == "STABLE" and avg > 0.20]
    monitor  = [(sym, avg) for sym, (stab, pq, avg) in sym_stability.items()
                if (stab == "STABLE" and avg <= 0.20) or (stab == "MODERATE" and avg > 0.15)]
    caution  = [(sym, avg) for sym, (stab, pq, avg) in sym_stability.items()
                if stab == "MODERATE" and avg <= 0.15]
    skip     = [(sym, avg) for sym, (stab, pq, avg) in sym_stability.items()
                if stab == "UNSTABLE"]

    if deploy:
        L.append("### ✅ DEPLOY — Stable & consistently profitable")
        for sym, avg in sorted(deploy, key=lambda x: -x[1]):
            L.append(f"- **{sym}** (avg {avg:+.3f}R/quarter)")
        L.append("")
    if monitor:
        L.append("### ✅ MONITOR — Stable or good average but needs watching")
        for sym, avg in sorted(monitor, key=lambda x: -x[1]):
            L.append(f"- **{sym}** (avg {avg:+.3f}R/quarter)")
        L.append("")
    if caution:
        L.append("### ⚠️ CAUTION — Moderate edge, inconsistent")
        for sym, avg in sorted(caution, key=lambda x: -x[1]):
            L.append(f"- **{sym}** (avg {avg:+.3f}R/quarter)")
        L.append("")
    if skip:
        L.append("### ❌ SKIP — Unstable, no consistent edge on H1")
        for sym, avg in sorted(skip, key=lambda x: -x[1]):
            L.append(f"- **{sym}** (avg {avg:+.3f}R/quarter)")
        L.append("")

    L.append("---")
    L.append("")
    L.append("## Methodology Notes")
    L.append("")
    L.append("- **No re-fitting between quarters** — configs fixed from 2021-2022 train")
    L.append("- **Indicator warm-up**: full dataset used for pivot/ATR calc, only entries "
             "within the quarter are counted (no look-ahead)")
    L.append("- **'best' config**: highest OOS ExpR from grid search across 144 combos")
    L.append("- **'ref' config**: D1/RR=3.0/off=0.3/buf=0.1/pmb=50 — same for all symbols")
    L.append("- Quarterly n may be low (<10 trades) — interpret with caution")
    L.append("")
    L.append(f"*Report generated: {now}*")
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("Walk-Forward Validation — M60/H1 | 8 Quarters OOS")
    print("=" * 65)

    if not GRID_CSV.exists():
        print(f"ERROR: grid results CSV not found: {GRID_CSV}")
        print("Run m60_grid_backtest.py first.")
        return

    print("Loading best configs from grid results...")
    best_configs = load_best_configs(GRID_CSV)
    print(f"  Loaded configs for: {sorted(best_configs.keys())}")
    print()

    all_rows = []

    for sym in ALL_SYMBOLS:
        print(f"[{sym.upper()}] Loading M60 bars...", flush=True)
        try:
            bars = load_m60_bars(sym)
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue

        best_p = best_configs.get(sym, REF_CFG)
        sp     = SYMBOL_PARAMS[sym]

        print(f"  Best config: HTF={best_p['htf']} RR={best_p['risk_reward']} "
              f"off={best_p['entry_offset_atr_mult']} buf={best_p['sl_buffer_atr_mult']} "
              f"pmb={best_p['pullback_max_bars']}")
        print(f"  Running 8 quarters x 2 configs...", flush=True)

        rows = run_walkforward(sym, bars, best_p, REF_CFG, sp)
        all_rows.extend(rows)

        # Quick summary per symbol
        best_rows = [r for r in rows if r["config"] == "best"]
        expRs = [r["expR"] for r in best_rows]
        pos   = sum(1 for v in expRs if v > 0)
        avg   = np.mean(expRs) if expRs else 0.0
        stab  = stability_score(expRs)
        print(f"  Result: {pos}/8 positive quarters | avg ExpR={avg:+.4f}R | {stab}")
        print()

    if not all_rows:
        print("No results produced.")
        return

    result_df = pd.DataFrame(all_rows)
    out_csv = OUT_DIR / "m60_walkforward_results.csv"
    result_df.to_csv(out_csv, index=False)
    print(f"CSV saved: {out_csv}")

    print("Generating report...", flush=True)
    md = generate_report(result_df)
    rp = REPORT_DIR / "M60_WALKFORWARD_REPORT.md"
    rp.write_text(md, encoding="utf-8")
    print(f"Report: {rp}")

    # Console summary
    print()
    print("=" * 65)
    print("WALK-FORWARD SUMMARY (best config per symbol)")
    print("=" * 65)
    print(f"{'Symbol':<8} {'+Q/8':<6} {'Avg ExpR':>9} {'Stability':<12} {'Verdict'}")
    print("-" * 55)
    for sym in sorted(set(r["symbol"] for r in all_rows)):
        rows_sym = [r for r in all_rows if r["symbol"] == sym and r["config"] == "best"]
        expRs = [r["expR"] for r in rows_sym]
        pos   = sum(1 for v in expRs if v > 0)
        avg   = np.mean(expRs) if expRs else 0.0
        stab  = stability_score(expRs)
        flag  = "*" if stab == "STABLE" and avg > 0.15 else " "
        print(f"{sym:<8} {pos}/8   {avg:>+9.4f}R  {stab:<12} {flag}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()


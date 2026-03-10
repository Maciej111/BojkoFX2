"""
USDCHF HTF Comparison: H4 vs D1
================================
Testuje USDCHF z dwoma konfiguracjami HTF na wszystkich 3 okresach.
Odpowiada: czy zmiana H4 → D1 naprawia wyniki 2025?
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pandas as pd
import datetime

DATA_DIR = ROOT / "data" / "raw_dl_fx" / "download" / "m60"
REPORT   = ROOT / "reports" / "USDCHF_HTF_COMPARE.md"

SYMBOL   = "usdchf"
COMM     = 0.00006
MIN_RISK = 0.0003

SESSION  = (8, 21)  # 08–21 UTC

HTF_VARIANTS = [
    ("H4 (obecny)", "4h"),
    ("D1 (nowy)",   "1D"),
]

PERIODS = [
    ("TRAIN    2021-22", "2021-01-01", "2022-12-31"),
    ("OOS-A   2023-24", "2023-01-01", "2024-12-31"),
    ("OOS-B   2025",    "2025-01-01", "2025-12-31"),
]

BASE_CFG = dict(
    pivot_lb_ltf=3, pivot_lb_htf=5, confirm=1,
    entry_off=0.3,  sl_buf=0.1,     pmb=50,
    rr=3.0,         atr_period=14,  pivot_count=4,
    risk_pct=0.01,  initial_bal=10_000.0,
)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars() -> pd.DataFrame:
    for suffix in ["2021_2025", "2021_2024"]:
        bid_f = DATA_DIR / f"{SYMBOL}_m60_bid_{suffix}.csv"
        ask_f = DATA_DIR / f"{SYMBOL}_m60_ask_{suffix}.csv"
        if bid_f.exists() and ask_f.exists():
            break
    else:
        raise FileNotFoundError(f"No data file for {SYMBOL}")

    bid = pd.read_csv(bid_f); ask = pd.read_csv(ask_f)
    for df in (bid, ask):
        df.columns = [c.strip().lower() for c in df.columns]
        ts_col = [c for c in df.columns if "time" in c or "stamp" in c][0]
        if ts_col != "timestamp":
            df.rename(columns={ts_col: "timestamp"}, inplace=True)
        sample = df["timestamp"].iloc[0]
        unit = "ms" if sample > 1e11 else "s"
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit)
        df.set_index("timestamp", inplace=True)
    idx = bid.index.intersection(ask.index)
    out = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        out[f"{c}_bid"] = bid.loc[idx, c].values
        out[f"{c}_ask"] = ask.loc[idx, c].values
    return out.dropna().sort_index()


# ── Indicators ────────────────────────────────────────────────────────────────

def calc_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    h, l, c = df["high_bid"].values, df["low_bid"].values, df["close_bid"].values
    n = len(h); tr = np.empty(n); tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    atr = np.full(n, np.nan); atr[period-1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
    return atr


def build_pivots(df: pd.DataFrame, lb: int, confirm: int = 1):
    n = len(df); h, l = df["high_bid"].values, df["low_bid"].values
    hp = np.pad(h, (lb,lb), mode="edge"); lp = np.pad(l, (lb,lb), mode="edge")
    w = 2*lb+1
    hw = np.lib.stride_tricks.as_strided(hp, shape=(n,w), strides=(hp.strides[0],hp.strides[0]))
    lw = np.lib.stride_tricks.as_strided(lp, shape=(n,w), strides=(lp.strides[0],lp.strides[0]))
    raw_ph = (h == hw.max(axis=1)); raw_ph[:lb]=False; raw_ph[n-lb:]=False
    raw_pl = (l == lw.min(axis=1)); raw_pl[:lb]=False; raw_pl[n-lb:]=False
    ph_mask = np.zeros(n, bool); pl_mask = np.zeros(n, bool)
    if confirm > 0:
        ph_mask[confirm:] = raw_ph[:-confirm]; pl_mask[confirm:] = raw_pl[:-confirm]
    else:
        ph_mask[:] = raw_ph; pl_mask[:] = raw_pl
    src = np.clip(np.arange(n)-confirm, 0, n-1)
    ph_lv = np.full(n, np.nan); pl_lv = np.full(n, np.nan)
    ph_lv[ph_mask] = h[src[ph_mask]]; pl_lv[pl_mask] = l[src[pl_mask]]
    return ph_lv, pl_lv, ph_mask, pl_mask


def htf_bias(ltf_time, htf_df, ph_lv, pl_lv, ph_mask, pl_mask, pcount=4):
    pos = htf_df.index.searchsorted(ltf_time, side="right") - 1
    if pos < 1: return "NEUTRAL"
    close = htf_df["close_bid"].iloc[pos]; phs, pls = [], []
    for j in range(pos, -1, -1):
        if ph_mask[j] and not np.isnan(ph_lv[j]): phs.append(ph_lv[j])
        if pl_mask[j] and not np.isnan(pl_lv[j]): pls.append(pl_lv[j])
        if len(phs) >= pcount and len(pls) >= pcount: break
    if len(phs) < 2 or len(pls) < 2: return "NEUTRAL"
    if close > phs[0]: return "BULL"
    if close < pls[0]: return "BEAR"
    if phs[0] > phs[1] and pls[0] > pls[1]: return "BULL"
    if pls[0] < pls[1] and phs[0] < phs[1]: return "BEAR"
    return "NEUTRAL"


def last_pv(i, lv, mask, max_lb=100):
    for j in range(i-1, max(0, i-max_lb)-1, -1):
        if mask[j] and not np.isnan(lv[j]): return lv[j]
    return None


# ── Backtest ──────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    direction: str; entry: float; sl: float; tp: float; risk: float
    R: float = 0.0; exit_reason: str = ""

@dataclass
class Setup:
    direction: str; entry: float; expiry: int


def run(bars: pd.DataFrame, htf_rule: str,
        period_start: str, period_end: str) -> List[Trade]:

    htf_df = bars.resample(htf_rule).agg({
        c: ("first" if "open" in c else ("max" if "high" in c
            else ("min" if "low" in c else "last")))
        for c in bars.columns}).dropna()

    atr    = calc_atr(bars, BASE_CFG["atr_period"])
    ph_lv_l, pl_lv_l, ph_m_l, pl_m_l = build_pivots(bars, BASE_CFG["pivot_lb_ltf"], BASE_CFG["confirm"])
    ph_lv_h, pl_lv_h, ph_m_h, pl_m_h = build_pivots(htf_df, BASE_CFG["pivot_lb_htf"], BASE_CFG["confirm"])

    idx    = bars.index
    cb, hb, lb_arr = bars["close_bid"].values, bars["high_bid"].values, bars["low_bid"].values
    ha, la = bars["high_ask"].values, bars["low_ask"].values

    mask_oos = (idx >= period_start) & (idx <= period_end)
    if mask_oos.sum() == 0: return []
    start_i = max(int(np.where(mask_oos)[0][0]), 200)
    end_i   = int(np.where(mask_oos)[0][-1])

    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    active_setup: Optional[Setup] = None

    for i in range(start_i, end_i):
        t = idx[i]; a = atr[i]
        if np.isnan(a) or a <= 0: continue

        # Exit
        if open_trade is not None:
            tr = open_trade
            sl_hit = (lb_arr[i] <= tr.sl) if tr.direction=="LONG" else (ha[i] >= tr.sl)
            tp_hit = (hb[i] >= tr.tp)     if tr.direction=="LONG" else (la[i] <= tr.tp)
            if sl_hit and tp_hit: sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep = tr.sl if sl_hit else tr.tp
                tr.R = ((ep-tr.entry)/tr.risk if tr.direction=="LONG" else (tr.entry-ep)/tr.risk)
                trades.append(tr); open_trade = None
            continue

        # Fill
        if active_setup is not None:
            s = active_setup
            if i > s.expiry: active_setup = None
            else:
                filled = (la[i] <= s.entry <= ha[i]) if s.direction=="LONG" \
                         else (lb_arr[i] <= s.entry <= hb[i])
                if filled:
                    fp  = s.entry + COMM if s.direction=="LONG" else s.entry - COMM
                    buf = BASE_CFG["sl_buf"] * a
                    if s.direction == "LONG":
                        lv = last_pv(i, pl_lv_l, pl_m_l)
                        sl = (lv-buf) if lv else (cb[i]-2*a); sl = max(sl, cb[i]-5*a)
                    else:
                        lv = last_pv(i, ph_lv_l, ph_m_l)
                        sl = (lv+buf) if lv else (cb[i]+2*a); sl = min(sl, cb[i]+5*a)
                    risk = abs(fp-sl)
                    if risk < MIN_RISK: active_setup = None; continue
                    tp = (fp+risk*BASE_CFG["rr"]) if s.direction=="LONG" else (fp-risk*BASE_CFG["rr"])
                    open_trade = Trade(s.direction, fp, sl, tp, risk)
                    active_setup = None; continue

        if active_setup is not None or open_trade is not None: continue

        # Session filter 08–21 UTC
        if not (SESSION[0] <= t.hour < SESSION[1]): continue

        # HTF bias
        bias = htf_bias(t, htf_df, ph_lv_h, pl_lv_h, ph_m_h, pl_m_h, BASE_CFG["pivot_count"])
        if bias == "NEUTRAL": continue

        # BOS
        lph = last_pv(i, ph_lv_l, ph_m_l); lpl = last_pv(i, pl_lv_l, pl_m_l)
        bos_dir = bos_lv = None
        if bias=="BULL" and lph and cb[i] > lph: bos_dir, bos_lv = "LONG",  lph
        elif bias=="BEAR" and lpl and cb[i] < lpl: bos_dir, bos_lv = "SHORT", lpl
        if bos_dir is None: continue

        off   = BASE_CFG["entry_off"] * a
        entry = bos_lv+off if bos_dir=="LONG" else bos_lv-off
        active_setup = Setup(bos_dir, entry, i+BASE_CFG["pmb"])

    return trades


def metrics(trades: List[Trade]) -> dict:
    if not trades: return dict(n=0, wr=0.0, expR=0.0, pf=0.0, dd=0.0, ret=0.0)
    Rs   = [t.R for t in trades]
    wins = [r for r in Rs if r > 0]; loss = [r for r in Rs if r <= 0]
    pf   = sum(wins)/abs(sum(loss)) if loss else float("inf")
    eq   = 10_000.0; peak = eq; max_dd = 0.0
    for r in Rs:
        eq *= (1+r*BASE_CFG["risk_pct"]); peak = max(peak, eq)
        max_dd = max(max_dd, (peak-eq)/peak*100)
    return dict(n=len(Rs), wr=round(len(wins)/len(Rs)*100,1),
                expR=round(float(np.mean(Rs)),4),
                pf=round(pf,3), dd=round(max_dd,1),
                ret=round((eq-10_000)/10_000*100,1))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    bars = load_bars()
    has_2025 = (bars.index.year == 2025).any()

    print(f"USDCHF HTF Comparison: H4 vs D1")
    print(f"Session: 08–21 UTC | RR=3.0 | pmb=50 | off=0.3 | buf=0.1")
    print(f"Data range: {bars.index.min().date()} -> {bars.index.max().date()}")
    print()

    all_results = {}

    for htf_name, htf_rule in HTF_VARIANTS:
        print(f"-- {htf_name} --")
        results = []
        for period_name, p_start, p_end in PERIODS:
            if "2025" in period_name and not has_2025:
                results.append((period_name, dict(n=0,wr=0,expR=0,pf=0,dd=0,ret=0)))
                print(f"  {period_name:<18s}  [no 2025 data]")
                continue
            trades = run(bars, htf_rule, p_start, p_end)
            m = metrics(trades)
            results.append((period_name, m))
            sign = "+" if m["expR"] >= 0 else ""
            print(f"  {period_name:<18s}  n={m['n']:>4}  WR={m['wr']:>5.1f}%  "
                  f"ExpR={sign}{m['expR']:.4f}R  PF={m['pf']:.3f}  "
                  f"DD={m['dd']:.1f}%  Ret={m['ret']:+.1f}%")
        all_results[htf_name] = results
        print()

    # ── Report ────────────────────────────────────────────────────────────────
    L = [
        "# USDCHF — Porównanie HTF: H4 vs D1",
        "",
        f"> Wygenerowano: {now}",
        "> Session: 08–21 UTC | RR=3.0 | pmb=50 | off=0.3 | buf=0.1",
        "> Pytanie: czy zmiana HTF H4 → D1 naprawia USDCHF w 2025?",
        "",
        "---", "",
        "## Wyniki",
        "",
        "| Okres | H4 n | H4 ExpR | H4 PF | H4 DD | D1 n | D1 ExpR | D1 PF | D1 DD | Lepszy |",
        "|-------|------|---------|-------|-------|------|---------|-------|-------|--------|",
    ]

    h4_res = {n: m for n, m in all_results.get("H4 (obecny)", [])}
    d1_res = {n: m for n, m in all_results.get("D1 (nowy)",   [])}

    oos_b_winner = None
    for period_name, _, _ in PERIODS:
        h4 = h4_res.get(period_name, {}); d1 = d1_res.get(period_name, {})
        if not h4 or not d1: continue
        better = "D1 ✅" if d1["expR"] > h4["expR"] else ("H4 ✅" if h4["expR"] > d1["expR"] else "=")
        if "2025" in period_name:
            oos_b_winner = "D1" if d1["expR"] > h4["expR"] else "H4"
        h4s = "+" if h4["expR"] >= 0 else ""
        d1s = "+" if d1["expR"] >= 0 else ""
        L.append(
            f"| **{period_name.strip()}** "
            f"| {h4['n']} | {h4s}{h4['expR']:.4f}R | {h4['pf']:.3f} | {h4['dd']:.1f}% "
            f"| {d1['n']} | {d1s}{d1['expR']:.4f}R | {d1['pf']:.3f} | {d1['dd']:.1f}% "
            f"| {better} |"
        )

    h4_oos_b = h4_res.get("OOS-B   2025", {})
    d1_oos_b = d1_res.get("OOS-B   2025", {})
    h4_oos_a = h4_res.get("OOS-A   2023-24", {})
    d1_oos_a = d1_res.get("OOS-A   2023-24", {})

    d1_pass = d1_oos_b.get("n", 0) > 0 and d1_oos_b.get("expR", -99) >= 0.2 and d1_oos_b.get("pf", 0) >= 1.3
    h4_pass = h4_oos_b.get("n", 0) > 0 and h4_oos_b.get("expR", -99) >= 0.2 and h4_oos_b.get("pf", 0) >= 1.3

    L += [
        "",
        "---", "",
        "## Wnioski",
        "",
    ]

    if d1_pass and not h4_pass:
        L += [
            f"✅ **Zmiana H4 → D1 naprawia USDCHF w 2025.**",
            f"",
            f"- H4 OOS-B 2025: **{h4_oos_b.get('expR',0):+.4f}R** ❌ FAIL",
            f"- D1 OOS-B 2025: **{d1_oos_b.get('expR',0):+.4f}R** ✅ PASS",
            f"",
            f"**Rekomendacja: zmienić USDCHF `htf: H4` → `htf: D1` w config.yaml.**",
        ]
    elif d1_pass and h4_pass:
        L += [
            f"⚠️ Obie konfiguracje przechodzą OOS 2025.",
            f"- H4 OOS-B: {h4_oos_b.get('expR',0):+.4f}R | D1 OOS-B: {d1_oos_b.get('expR',0):+.4f}R",
            f"- D1 daje {'lepszy' if d1_oos_b.get('expR',0) > h4_oos_b.get('expR',0) else 'gorszy'} wynik w 2025.",
            f"",
            f"**Rekomendacja: {'preferuj D1' if d1_oos_b.get('expR',0) > h4_oos_b.get('expR',0) else 'zostań przy H4'}.**",
        ]
    elif not d1_pass and not h4_pass:
        L += [
            f"❌ **Ani H4 ani D1 nie przechodzi OOS 2025.**",
            f"- H4 OOS-B: {h4_oos_b.get('expR',0):+.4f}R | D1 OOS-B: {d1_oos_b.get('expR',0):+.4f}R",
            f"",
            f"**Rekomendacja: rozważ wyłączenie USDCHF (`enabled: false`) do dalszych badań.**",
        ]
    else:
        L += [
            f"❌ D1 nie naprawia problemu. H4 daje lepszy wynik w 2025.",
            f"**Rekomendacja: zostań przy H4, rozważ wyłączenie USDCHF.**",
        ]

    # Consistency across all periods
    L += ["", "### Spójność wyników (D1):", ""]
    for period_name, _, _ in PERIODS:
        m = d1_res.get(period_name, {})
        if m.get("n", 0) == 0: continue
        icon = "✅" if m["expR"] > 0.1 else ("⚠️" if m["expR"] > 0 else "❌")
        L.append(f"- {period_name.strip()}: {icon} ExpR={m['expR']:+.4f}R, WR={m['wr']}%, PF={m['pf']:.3f}")

    L += ["", f"*Wygenerowano: {now}*"]

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"Raport: {REPORT}")


if __name__ == "__main__":
    main()




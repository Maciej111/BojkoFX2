"""
HTF Comparison — D1 vs H4 for all 5 production pairs
=====================================================
Sprawdza czy zmiana HTF na D1 poprawia wyniki dla par które mają H4 lub inny HTF.
Testuje 3 okresy: TRAIN 2021-22, OOS-A 2023-24, OOS-B 2025
Zapisuje raport do reports/HTF_COMPARISON_ALL.md
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
REPORT   = ROOT / "reports" / "HTF_COMPARISON_ALL.md"

SYMBOL_SETTINGS = {
    "eurusd": dict(current_htf="1D", comm=0.00005, min_risk=0.0003, session=(8, 21)),
    "usdjpy": dict(current_htf="1D", comm=0.005,   min_risk=0.03,   session=(0, 24)),
    "usdchf": dict(current_htf="1D", comm=0.00006, min_risk=0.0003, session=(8, 21)),
    "audjpy": dict(current_htf="1D", comm=0.007,   min_risk=0.03,   session=(0, 21)),
    "cadjpy": dict(current_htf="1D", comm=0.0075,  min_risk=0.03,   session=(0, 24)),
}

HTF_OPTIONS = [("H4", "4h"), ("D1", "1D")]

PERIODS = [
    ("TRAIN 2021-22", "2021-01-01", "2022-12-31"),
    ("OOS-A 2023-24", "2023-01-01", "2024-12-31"),
    ("OOS-B 2025",    "2025-01-01", "2025-12-31"),
]

BASE_CFG = dict(
    pivot_lb_ltf=3, pivot_lb_htf=5, confirm=1,
    entry_off=0.3, sl_buf=0.1, pmb=50,
    rr=3.0, atr_period=14, pivot_count=4,
    risk_pct=0.01,
)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars(symbol: str) -> pd.DataFrame:
    for suffix in ["2021_2025", "2021_2024"]:
        bid_f = DATA_DIR / f"{symbol}_m60_bid_{suffix}.csv"
        ask_f = DATA_DIR / f"{symbol}_m60_ask_{suffix}.csv"
        if bid_f.exists() and ask_f.exists():
            break
    else:
        raise FileNotFoundError(f"No data for {symbol}")
    bid = pd.read_csv(bid_f); ask = pd.read_csv(ask_f)
    for df in (bid, ask):
        df.columns = [c.strip().lower() for c in df.columns]
        ts_col = [c for c in df.columns if "time" in c or "stamp" in c][0]
        if ts_col != "timestamp":
            df.rename(columns={ts_col: "timestamp"}, inplace=True)
        unit = "ms" if df["timestamp"].iloc[0] > 1e11 else "s"
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
        atr[i] = (atr[i-1]*(period-1)+tr[i])/period
    return atr


def build_pivots(df, lb, confirm=1):
    n = len(df); h, l = df["high_bid"].values, df["low_bid"].values
    hp = np.pad(h, (lb,lb), mode="edge"); lp = np.pad(l, (lb,lb), mode="edge")
    w = 2*lb+1
    hw = np.lib.stride_tricks.as_strided(hp, shape=(n,w), strides=(hp.strides[0],hp.strides[0]))
    lw = np.lib.stride_tricks.as_strided(lp, shape=(n,w), strides=(lp.strides[0],lp.strides[0]))
    raw_ph = (h == hw.max(axis=1)); raw_ph[:lb]=False; raw_ph[n-lb:]=False
    raw_pl = (l == lw.min(axis=1)); raw_pl[:lb]=False; raw_pl[n-lb:]=False
    ph_m = np.zeros(n,bool); pl_m = np.zeros(n,bool)
    if confirm > 0:
        ph_m[confirm:] = raw_ph[:-confirm]; pl_m[confirm:] = raw_pl[:-confirm]
    else:
        ph_m[:] = raw_ph; pl_m[:] = raw_pl
    src = np.clip(np.arange(n)-confirm, 0, n-1)
    ph_lv = np.full(n,np.nan); pl_lv = np.full(n,np.nan)
    ph_lv[ph_m] = h[src[ph_m]]; pl_lv[pl_m] = l[src[pl_m]]
    return ph_lv, pl_lv, ph_m, pl_m


def htf_bias(t, htf_df, ph_lv, pl_lv, ph_m, pl_m, pc=4):
    pos = htf_df.index.searchsorted(t, side="right") - 1
    if pos < 1: return "NEUTRAL"
    close = htf_df["close_bid"].iloc[pos]; phs, pls = [], []
    for j in range(pos, -1, -1):
        if ph_m[j] and not np.isnan(ph_lv[j]): phs.append(ph_lv[j])
        if pl_m[j] and not np.isnan(pl_lv[j]): pls.append(pl_lv[j])
        if len(phs) >= pc and len(pls) >= pc: break
    if len(phs) < 2 or len(pls) < 2: return "NEUTRAL"
    if close > phs[0]: return "BULL"
    if close < pls[0]: return "BEAR"
    if phs[0]>phs[1] and pls[0]>pls[1]: return "BULL"
    if pls[0]<pls[1] and phs[0]<phs[1]: return "BEAR"
    return "NEUTRAL"


def last_pv(i, lv, mask, max_lb=100):
    for j in range(i-1, max(0,i-max_lb)-1, -1):
        if mask[j] and not np.isnan(lv[j]): return lv[j]
    return None


# ── Backtest ──────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    direction: str; entry: float; sl: float; tp: float; risk: float
    R: float = 0.0

@dataclass
class Setup:
    direction: str; entry: float; expiry: int


def run(bars, htf_rule, comm, min_risk, session, p_start, p_end):
    htf_df = bars.resample(htf_rule).agg({
        c: ("first" if "open" in c else ("max" if "high" in c
            else ("min" if "low" in c else "last")))
        for c in bars.columns}).dropna()

    atr = calc_atr(bars, BASE_CFG["atr_period"])
    ph_l, pl_l, phm_l, plm_l = build_pivots(bars, BASE_CFG["pivot_lb_ltf"], BASE_CFG["confirm"])
    ph_h, pl_h, phm_h, plm_h = build_pivots(htf_df, BASE_CFG["pivot_lb_htf"], BASE_CFG["confirm"])

    idx = bars.index
    cb = bars["close_bid"].values; hb = bars["high_bid"].values
    lb_arr = bars["low_bid"].values; ha = bars["high_ask"].values; la = bars["low_ask"].values

    mask = (idx >= p_start) & (idx <= p_end)
    if mask.sum() == 0: return []
    si = max(int(np.where(mask)[0][0]), 200)
    ei = int(np.where(mask)[0][-1])

    sess_on = not (session[0] == 0 and session[1] == 24)
    trades: List[Trade] = []; ot: Optional[Trade] = None; ast: Optional[Setup] = None

    for i in range(si, ei):
        t = idx[i]; a = atr[i]
        if np.isnan(a) or a <= 0: continue

        if ot is not None:
            sl_hit = (lb_arr[i] <= ot.sl) if ot.direction=="LONG" else (ha[i] >= ot.sl)
            tp_hit = (hb[i] >= ot.tp)     if ot.direction=="LONG" else (la[i] <= ot.tp)
            if sl_hit and tp_hit: sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep = ot.sl if sl_hit else ot.tp
                ot.R = (ep-ot.entry)/ot.risk if ot.direction=="LONG" else (ot.entry-ep)/ot.risk
                trades.append(ot); ot = None
            continue

        if ast is not None:
            if i > ast.expiry: ast = None
            else:
                filled = (la[i] <= ast.entry <= ha[i]) if ast.direction=="LONG" \
                         else (lb_arr[i] <= ast.entry <= hb[i])
                if filled:
                    fp = ast.entry + comm if ast.direction=="LONG" else ast.entry - comm
                    buf = BASE_CFG["sl_buf"] * a
                    if ast.direction == "LONG":
                        lv = last_pv(i, pl_l, plm_l)
                        sl = (lv-buf) if lv else (cb[i]-2*a); sl = max(sl, cb[i]-5*a)
                    else:
                        lv = last_pv(i, ph_l, phm_l)
                        sl = (lv+buf) if lv else (cb[i]+2*a); sl = min(sl, cb[i]+5*a)
                    risk = abs(fp-sl)
                    if risk < min_risk: ast = None; continue
                    tp = (fp+risk*BASE_CFG["rr"]) if ast.direction=="LONG" else (fp-risk*BASE_CFG["rr"])
                    ot = Trade(ast.direction, fp, sl, tp, risk); ast = None; continue

        if ast is not None or ot is not None: continue
        if sess_on and not (session[0] <= t.hour < session[1]): continue

        bias = htf_bias(t, htf_df, ph_h, pl_h, phm_h, plm_h, BASE_CFG["pivot_count"])
        if bias == "NEUTRAL": continue

        lph = last_pv(i, ph_l, phm_l); lpl = last_pv(i, pl_l, plm_l)
        bd = bl = None
        if bias=="BULL" and lph and cb[i]>lph: bd, bl = "LONG",  lph
        elif bias=="BEAR" and lpl and cb[i]<lpl: bd, bl = "SHORT", lpl
        if bd is None: continue

        off = BASE_CFG["entry_off"] * a
        entry = bl+off if bd=="LONG" else bl-off
        ast = Setup(bd, entry, i+BASE_CFG["pmb"])

    return trades


def metrics(trades):
    if not trades: return dict(n=0,wr=0.0,expR=0.0,pf=0.0,dd=0.0,ret=0.0)
    Rs = [t.R for t in trades]
    wins = [r for r in Rs if r>0]; loss = [r for r in Rs if r<=0]
    pf = sum(wins)/abs(sum(loss)) if loss else float("inf")
    eq = 10_000.0; peak = eq; dd = 0.0
    for r in Rs:
        eq *= (1+r*BASE_CFG["risk_pct"]); peak = max(peak,eq)
        dd = max(dd,(peak-eq)/peak*100)
    return dict(n=len(Rs), wr=round(len(wins)/len(Rs)*100,1),
                expR=round(float(np.mean(Rs)),4),
                pf=round(pf,3), dd=round(dd,1),
                ret=round((eq-10_000)/10_000*100,1))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print("HTF Comparison: H4 vs D1 — all 5 production pairs")
    print("="*65)

    # results[symbol][htf_label] = [(period_name, metrics_dict), ...]
    results = {}

    for symbol, cfg in SYMBOL_SETTINGS.items():
        bars = load_bars(symbol)
        has_2025 = (bars.index.year == 2025).any()
        print(f"\n[{symbol.upper()}]  current_HTF={cfg['current_htf']}")
        results[symbol] = {}

        for htf_label, htf_rule in HTF_OPTIONS:
            sym_res = []
            for pname, ps, pe in PERIODS:
                if "2025" in pname and not has_2025:
                    sym_res.append((pname, dict(n=0,wr=0,expR=0,pf=0,dd=0,ret=0)))
                    continue
                tr = run(bars, htf_rule, cfg["comm"], cfg["min_risk"], cfg["session"], ps, pe)
                m = metrics(tr)
                sym_res.append((pname, m))
            results[symbol][htf_label] = sym_res

            # print row
            for pname, m in sym_res:
                sign = "+" if m["expR"] >= 0 else ""
                print(f"  {htf_label} {pname:<16s}  n={m['n']:>4}  WR={m['wr']:>5.1f}%  "
                      f"ExpR={sign}{m['expR']:.4f}R  PF={m['pf']:.3f}  DD={m['dd']:.1f}%")

    # ── Generate report ───────────────────────────────────────────────────────
    L = [
        "# HTF Porownanie: H4 vs D1 — wszystkie 5 par produkcyjnych",
        "",
        f"> Wygenerowano: {now}",
        "> RR=3.0 | pmb=50 | off=0.3 | buf=0.1 | per-pair session windows",
        "> Pytanie: czy D1 jest lepszy niz H4 dla kazdej pary we wszystkich okresach?",
        "",
        "---", "",
    ]

    # Per-symbol comparison table
    for symbol, sym_results in results.items():
        cfg = SYMBOL_SETTINGS[symbol]
        sess = cfg["session"]
        sess_str = f"{sess[0]:02d}-{sess[1]:02d} UTC" if not (sess[0]==0 and sess[1]==24) else "24h"

        h4_res = {pn: m for pn, m in sym_results.get("H4", [])}
        d1_res = {pn: m for pn, m in sym_results.get("D1", [])}

        L += [
            f"## {symbol.upper()}  (session: {sess_str} | current HTF: {cfg['current_htf']})",
            "",
            "| Okres | H4 ExpR | H4 PF | H4 DD | D1 ExpR | D1 PF | D1 DD | Lepszy |",
            "|-------|---------|-------|-------|---------|-------|-------|--------|",
        ]

        d1_wins = 0; total_periods = 0
        for pname, _, _ in PERIODS:
            h4 = h4_res.get(pname, {}); d1 = d1_res.get(pname, {})
            if not h4 or h4.get("n",0) == 0: continue
            total_periods += 1
            h4s = "+" if h4["expR"] >= 0 else ""
            d1s = "+" if d1["expR"] >= 0 else ""
            if d1["expR"] > h4["expR"]:
                better = "D1 ✅"; d1_wins += 1
            elif h4["expR"] > d1["expR"]:
                better = "H4 ✅"
            else:
                better = "="
            # highlight OOS-B 2025
            bold = "**" if "2025" in pname else ""
            L.append(
                f"| {bold}{pname}{bold} "
                f"| {h4s}{h4['expR']:.4f}R | {h4['pf']:.3f} | {h4['dd']:.1f}% "
                f"| {d1s}{d1['expR']:.4f}R | {d1['pf']:.3f} | {d1['dd']:.1f}% "
                f"| {better} |"
            )

        # Verdict
        oos_b_h4 = h4_res.get("OOS-B 2025", {})
        oos_b_d1 = d1_res.get("OOS-B 2025", {})
        d1_pass_2025 = oos_b_d1.get("expR", -99) >= 0.2 and oos_b_d1.get("pf", 0) >= 1.3
        h4_pass_2025 = oos_b_h4.get("expR", -99) >= 0.2 and oos_b_h4.get("pf", 0) >= 1.3

        delta_oos_b = oos_b_d1.get("expR", 0) - oos_b_h4.get("expR", 0)

        if d1_wins == total_periods:
            verdict = f"D1 lepszy we wszystkich {total_periods} okresach"
            rec = "D1" if cfg["current_htf"] != "1D" else "D1 (bez zmian)"
        elif d1_wins > total_periods / 2:
            verdict = f"D1 lepszy w {d1_wins}/{total_periods} okresach"
            rec = "D1" if delta_oos_b > 0.05 else "pozostan przy obecnym"
        else:
            verdict = f"H4 lepszy lub rowny w wiekszosci"
            rec = "H4" if cfg["current_htf"] != "1D" else "D1 (bez zmian)"

        change_needed = cfg["current_htf"] != ("1D" if "D1" in rec else "4h")
        status = "**ZMIANA WYMAGANA**" if change_needed and "D1" in rec else "bez zmian"

        L += [
            "",
            f"**Wynik:** {verdict} | Delta OOS-B 2025: {delta_oos_b:+.4f}R",
            f"**Rekomendacja:** {rec} | {status}",
            "",
        ]

    # ── Summary table ─────────────────────────────────────────────────────────
    L += [
        "---", "",
        "## Tabela zbiorcza",
        "",
        "| Para | Obecny HTF | OOS-B H4 | OOS-B D1 | Lepszy | Rekomendacja |",
        "|------|-----------|---------|---------|--------|--------------|",
    ]

    for symbol, sym_results in results.items():
        cfg = SYMBOL_SETTINGS[symbol]
        h4_res = {pn: m for pn, m in sym_results.get("H4", [])}
        d1_res = {pn: m for pn, m in sym_results.get("D1", [])}
        h4_b = h4_res.get("OOS-B 2025", {})
        d1_b = d1_res.get("OOS-B 2025", {})

        if h4_b.get("n", 0) == 0:
            L.append(f"| **{symbol.upper()}** | {cfg['current_htf']} | N/A | N/A | - | brak danych 2025 |")
            continue

        h4s = "+" if h4_b["expR"] >= 0 else ""
        d1s = "+" if d1_b["expR"] >= 0 else ""
        better = "D1" if d1_b["expR"] > h4_b["expR"] else "H4"
        delta = d1_b["expR"] - h4_b["expR"]

        d1_pass = d1_b["expR"] >= 0.2 and d1_b["pf"] >= 1.3
        h4_pass = h4_b["expR"] >= 0.2 and h4_b["pf"] >= 1.3

        if better == "D1" and delta > 0.05:
            rec = f"Zmien na D1 (+{delta:.3f}R)" if cfg["current_htf"] != "1D" else "D1 OK"
            icon = "✅"
        elif better == "H4" and abs(delta) > 0.05:
            rec = f"Zostaw H4 ({delta:+.3f}R)"
            icon = "⚠️"
        else:
            rec = "Roznica < 0.05R, bez zmian"
            icon = "➡️"

        L.append(
            f"| **{symbol.upper()}** | {cfg['current_htf']} "
            f"| {h4s}{h4_b['expR']:.4f}R ({'PASS' if h4_pass else 'FAIL'}) "
            f"| {d1s}{d1_b['expR']:.4f}R ({'PASS' if d1_pass else 'FAIL'}) "
            f"| {better} {icon} | {rec} |"
        )

    L += ["", f"*Wygenerowano: {now} | OOS-B = rok 2025 (nigdy nie widziany przez strategie)*"]

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"\nRaport: {REPORT}")


if __name__ == "__main__":
    main()


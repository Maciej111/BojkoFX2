"""
OOS 2025 Backtest — walidacja 5 par produkcyjnych na roku 2025
==============================================================
TRAIN: 2021-2022  |  OOS-A: 2023-2024 (znany)  |  OOS-B: 2025 (nowy)

Odpowiada: czy strategia działa na danych których nigdy nie widziała?
Zapisuje raport do reports/OOS_2025_VALIDATION.md
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
REPORT   = ROOT / "reports" / "OOS_2025_VALIDATION.md"

SYMBOL_CFG = {
    "eurusd": dict(htf_rule="1D", pip=0.0001, min_risk=0.0003, comm=0.00005),
    "usdjpy": dict(htf_rule="1D", pip=0.01,   min_risk=0.03,   comm=0.005),
    "usdchf": dict(htf_rule="1D", pip=0.0001, min_risk=0.0003, comm=0.00006),  # changed H4->D1
    "audjpy": dict(htf_rule="1D", pip=0.01,   min_risk=0.03,   comm=0.007),
    "cadjpy": dict(htf_rule="1D", pip=0.01,   min_risk=0.03,   comm=0.0075),
}

# Session windows from SESSION_ANALYSIS.md
SESSION_CFG = {
    "eurusd": (8,  21),
    "usdjpy": (0,  24),   # no filter
    "usdchf": (8,  21),
    "audjpy": (0,  21),
    "cadjpy": (0,  24),   # no filter
}

PERIODS = [
    ("TRAIN",   "2021-01-01", "2022-12-31"),
    ("OOS-A",   "2023-01-01", "2024-12-31"),
    ("OOS-B 2025", "2025-01-01", "2025-12-31"),
]

BASE_CFG = dict(
    pivot_lb_ltf=3, pivot_lb_htf=5, confirm=1,
    entry_off=0.3,  sl_buf=0.1,     pmb=50,
    rr=3.0,         atr_period=14,  pivot_count=4,
    risk_pct=0.01,  initial_bal=10_000.0,
)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars(symbol: str) -> pd.DataFrame:
    # prefer 2021-2025 file, fall back to 2021-2024
    for suffix in ["2021_2025", "2021_2024"]:
        bid_f = DATA_DIR / f"{symbol}_m60_bid_{suffix}.csv"
        ask_f = DATA_DIR / f"{symbol}_m60_ask_{suffix}.csv"
        if bid_f.exists() and ask_f.exists():
            break
    else:
        raise FileNotFoundError(f"No data file for {symbol}")

    bid = pd.read_csv(bid_f); ask = pd.read_csv(ask_f)
    for df in (bid, ask):
        df.columns = [c.strip().lower() for c in df.columns]
        ts_col = [c for c in df.columns if "time" in c or "stamp" in c][0]
        if ts_col != "timestamp":
            df.rename(columns={ts_col: "timestamp"}, inplace=True)
        # auto-detect unit: ms values are ~1.6e12, seconds are ~1.6e9
        sample = df["timestamp"].iloc[0]
        unit = "ms" if sample > 1e11 else "s"
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit=unit)
        df.set_index("timestamp", inplace=True)
    idx = bid.index.intersection(ask.index)
    out = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        out[f"{c}_bid"] = bid.loc[idx, c].values
        out[f"{c}_ask"] = ask.loc[idx, c].values
    out = out.dropna()
    out = out[(out["high_bid"] - out["low_bid"]) > 0]
    return out.sort_index()


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
    direction: str; entry: float; expiry: int; bos_level: float


def run(bars: pd.DataFrame, sym_cfg: dict, sess: tuple,
        period_start: str, period_end: str) -> List[Trade]:

    htf_df = bars.resample(sym_cfg["htf_rule"]).agg({
        c: ("first" if "open" in c else ("max" if "high" in c
            else ("min" if "low" in c else "last")))
        for c in bars.columns}).dropna()

    atr = calc_atr(bars, BASE_CFG["atr_period"])
    ph_lv_l, pl_lv_l, ph_m_l, pl_m_l = build_pivots(bars, BASE_CFG["pivot_lb_ltf"], BASE_CFG["confirm"])
    ph_lv_h, pl_lv_h, ph_m_h, pl_m_h = build_pivots(htf_df, BASE_CFG["pivot_lb_htf"], BASE_CFG["confirm"])

    idx = bars.index
    cb, hb, lb_arr = bars["close_bid"].values, bars["high_bid"].values, bars["low_bid"].values
    ha, la = bars["high_ask"].values, bars["low_ask"].values
    comm = sym_cfg["comm"]; min_r = sym_cfg["min_risk"]
    sess_start, sess_end = sess
    has_filter = not (sess_start == 0 and sess_end == 24)

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

        if open_trade is not None:
            tr = open_trade
            sl_hit = (lb_arr[i] <= tr.sl) if tr.direction=="LONG" else (ha[i] >= tr.sl)
            tp_hit = (hb[i] >= tr.tp)     if tr.direction=="LONG" else (la[i] <= tr.tp)
            if sl_hit and tp_hit: sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep = tr.sl if sl_hit else tr.tp
                tr.R = ((ep-tr.entry)/tr.risk if tr.direction=="LONG" else (tr.entry-ep)/tr.risk)
                tr.exit_reason = "SL" if sl_hit else "TP"
                trades.append(tr); open_trade = None
            continue

        if active_setup is not None:
            s = active_setup
            if i > s.expiry: active_setup = None
            else:
                filled = (la[i] <= s.entry <= ha[i]) if s.direction=="LONG" \
                         else (lb_arr[i] <= s.entry <= hb[i])
                if filled:
                    fp = s.entry + comm if s.direction=="LONG" else s.entry - comm
                    buf = BASE_CFG["sl_buf"] * a
                    if s.direction == "LONG":
                        lv = last_pv(i, pl_lv_l, pl_m_l)
                        sl = (lv-buf) if lv else (cb[i]-2*a); sl = max(sl, cb[i]-5*a)
                    else:
                        lv = last_pv(i, ph_lv_l, ph_m_l)
                        sl = (lv+buf) if lv else (cb[i]+2*a); sl = min(sl, cb[i]+5*a)
                    risk = abs(fp-sl)
                    if risk < min_r: active_setup = None; continue
                    tp = (fp+risk*BASE_CFG["rr"]) if s.direction=="LONG" else (fp-risk*BASE_CFG["rr"])
                    open_trade = Trade(s.direction, fp, sl, tp, risk)
                    active_setup = None; continue

        if active_setup is not None or open_trade is not None: continue

        if has_filter and not (sess_start <= t.hour < sess_end): continue

        bias = htf_bias(t, htf_df, ph_lv_h, pl_lv_h, ph_m_h, pl_m_h, BASE_CFG["pivot_count"])
        if bias == "NEUTRAL": continue

        lph = last_pv(i, ph_lv_l, ph_m_l); lpl = last_pv(i, pl_lv_l, pl_m_l)
        bos_dir = bos_lv = None
        if bias=="BULL" and lph and cb[i] > lph: bos_dir, bos_lv = "LONG",  lph
        elif bias=="BEAR" and lpl and cb[i] < lpl: bos_dir, bos_lv = "SHORT", lpl
        if bos_dir is None: continue

        off = BASE_CFG["entry_off"] * a
        entry = bos_lv+off if bos_dir=="LONG" else bos_lv-off
        active_setup = Setup(bos_dir, entry, i+BASE_CFG["pmb"], bos_lv)

    return trades


def metrics(trades: List[Trade]) -> dict:
    if not trades: return dict(n=0, wr=0.0, expR=0.0, pf=0.0, dd=0.0, ret=0.0)
    Rs = [t.R for t in trades]
    wins = [r for r in Rs if r > 0]; loss = [r for r in Rs if r <= 0]
    pf = sum(wins)/abs(sum(loss)) if loss else float("inf")
    eq = 10_000.0; peak = eq; max_dd = 0.0
    for r in Rs:
        eq *= (1+r*BASE_CFG["risk_pct"]); peak = max(peak, eq)
        max_dd = max(max_dd, (peak-eq)/peak*100)
    ret = (eq-10_000.0)/10_000.0*100
    return dict(n=len(Rs), wr=round(len(wins)/len(Rs)*100,1),
                expR=round(float(np.mean(Rs)),4),
                pf=round(pf,3), dd=round(max_dd,1), ret=round(ret,1))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print("OOS 2025 Validation — 5 production pairs")
    print(f"Config: H1/D1(H4), RR=3.0, pmb=50, off=0.3, buf=0.1")
    print()

    all_results = {}

    for symbol, sym_cfg in SYMBOL_CFG.items():
        sess = SESSION_CFG[symbol]
        sess_str = f"{sess[0]:02d}-{sess[1]:02d} UTC" if not (sess[0]==0 and sess[1]==24) else "24h"
        print(f"[{symbol.upper()}]  HTF={sym_cfg['htf_rule']}  session={sess_str}", flush=True)

        try:
            bars = load_bars(symbol)
        except FileNotFoundError as e:
            print(f"  [ERROR] {e}"); continue

        has_2025 = (bars.index.year == 2025).any()
        if not has_2025:
            print(f"  [WARN] No 2025 data available — skipping OOS-B")

        sym_results = []
        for period_name, p_start, p_end in PERIODS:
            if "2025" in period_name and not has_2025:
                sym_results.append((period_name, dict(n=0, wr=0.0, expR=0.0, pf=0.0, dd=0.0, ret=0.0)))
                continue
            trades = run(bars, sym_cfg, sess, p_start, p_end)
            m = metrics(trades)
            sym_results.append((period_name, m))
            sign = "+" if m["expR"] >= 0 else ""
            print(f"  {period_name:<16s}  n={m['n']:>4}  WR={m['wr']:>5.1f}%  "
                  f"ExpR={sign}{m['expR']:.4f}R  PF={m['pf']:.3f}  "
                  f"DD={m['dd']:.1f}%  Ret={m['ret']:+.1f}%")
        print()
        all_results[symbol] = sym_results

    # ── Generate report ───────────────────────────────────────────────────────
    L = []
    L += [
        "# OOS 2025 Validation — Walidacja na roku 2025",
        "",
        f"> Wygenerowano: {now}",
        "> Config: LTF=H1 | HTF=D1/H4 | RR=3.0 | pmb=50 | off=0.3 | buf=0.1",
        "> Session windows: EURUSD/USDCHF 08-21, AUDJPY 00-21, USDJPY/CADJPY 24h",
        "> **Kluczowe pytanie: czy strategia działa na danych z 2025 (nigdy nie widzianych)?**",
        "",
        "---", "",
        "## Wyniki per para",
        "",
    ]

    for symbol, sym_results in all_results.items():
        sym_cfg = SYMBOL_CFG[symbol]
        sess = SESSION_CFG[symbol]
        sess_str = f"{sess[0]:02d}:00–{sess[1]:02d}:00 UTC" if not (sess[0]==0 and sess[1]==24) else "24h"

        L += [
            f"### {symbol.upper()}  _(HTF: {sym_cfg['htf_rule']} | session: {sess_str})_",
            "",
            "| Okres | n | WR | ExpR | PF | MaxDD | Ret | Ocena |",
            "|-------|---|----|----|----|----|-----|-------|",
        ]

        res = {name: m for name, m in sym_results}
        oos_a = res.get("OOS-A", {})
        oos_b = res.get("OOS-B 2025", {})

        for period_name, m in sym_results:
            sign = "+" if m["expR"] >= 0 else ""
            if m["n"] == 0:
                tag = "⚠️ brak danych"
            elif "TRAIN" in period_name:
                tag = "📚 trening"
            elif "OOS-A" in period_name:
                tag = "✅ znany OOS" if m["expR"] > 0 else "❌ znany OOS"
            else:
                # OOS-B 2025 verdict
                if m["expR"] >= 0.2 and m["pf"] >= 1.3:
                    tag = "✅ PASS"
                elif m["expR"] > 0:
                    tag = "⚠️ marginalny"
                else:
                    tag = "❌ FAIL"
            L.append(f"| **{period_name}** | {m['n']} | {m['wr']}% | "
                     f"{sign}{m['expR']:.4f}R | {m['pf']:.3f} | "
                     f"{m['dd']:.1f}% | {m['ret']:+.1f}% | {tag} |")

        # Consistency check
        if oos_a.get("n", 0) > 0 and oos_b.get("n", 0) > 0:
            delta = oos_b["expR"] - oos_a["expR"]
            if oos_b["expR"] > 0 and oos_a["expR"] > 0:
                consistency = f"✅ Spójna — OOS-B pozytywny ({oos_b['expR']:+.4f}R)"
            elif oos_b["expR"] > 0:
                consistency = f"⚠️ OOS-B pozytywny ale OOS-A słabszy"
            else:
                consistency = f"❌ UWAGA — OOS-B ujemny ({oos_b['expR']:+.4f}R)"
            L += ["", f"**Spójność:** {consistency}  (delta vs OOS-A: {delta:+.4f}R)", ""]
        else:
            L += ["", "**Spójność:** ⚠️ brak danych 2025", ""]

    # ── Summary table ─────────────────────────────────────────────────────────
    L += [
        "---", "",
        "## Tabela zbiorcza",
        "",
        "| Para | TRAIN ExpR | OOS-A (2023-24) | **OOS-B (2025)** | Verdict |",
        "|------|-----------|----------------|-----------------|---------|",
    ]

    pass_count = 0
    for symbol, sym_results in all_results.items():
        res = {name: m for name, m in sym_results}
        tr  = res.get("TRAIN", {}); oa = res.get("OOS-A", {}); ob = res.get("OOS-B 2025", {})
        if ob.get("n", 0) == 0:
            verdict = "⚠️ brak danych"
        elif ob["expR"] >= 0.2 and ob["pf"] >= 1.3:
            verdict = "✅ PASS"
            pass_count += 1
        elif ob["expR"] > 0:
            verdict = "⚠️ marginalny"
        else:
            verdict = "❌ FAIL"
        L.append(f"| **{symbol.upper()}** | {tr.get('expR',0):+.4f}R | "
                 f"{oa.get('expR',0):+.4f}R | **{ob.get('expR',0):+.4f}R** | {verdict} |")

    n_total = len(all_results)
    L += [
        "",
        f"**Wynik: {pass_count}/{n_total} par przeszło OOS 2025** "
        f"(kryterium: ExpR≥0.20R i PF≥1.30)",
        "",
        "---", "",
        "## Wnioski",
        "",
    ]

    if pass_count == n_total:
        L.append("✅ **Strategia jest stabilna** — wszystkie pary pozytywne w 2025. "
                 "Obecna konfiguracja jest gotowa do live tradingu.")
    elif pass_count >= n_total * 0.6:
        L.append(f"⚠️ **Wyniki mieszane** — {pass_count}/{n_total} par przeszło. "
                 "Rozważ wyłączenie par które nie przeszły.")
    else:
        L.append(f"❌ **Strategia może być overfitted** — tylko {pass_count}/{n_total} par "
                 "pozytywnych w 2025. Wymagana rewizja parametrów.")

    L += [
        "",
        "### Dlaczego wcześniej brakowało tej walidacji?",
        "- Dane były pobrane tylko za lata 2021–2024",
        "- Backtesty (TRAIN 2021-2022, OOS 2023-2024) nie obejmowały roku 2025",
        "- Rok 2025 to **prawdziwy forward test** — strategia go nigdy nie widziała",
        "- Jest to ważne bo OOS 2023-2024 jest 'zainfekowany' doborem parametrów",
        "  (grid search był robiony wiedząc że 2023-2024 istnieje)",
        "",
        f"*Wygenerowano: {now}*",
    ]

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"Raport: {REPORT}")


if __name__ == "__main__":
    main()


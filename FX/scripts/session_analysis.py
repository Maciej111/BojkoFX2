"""
Session Hours Analysis — wszystkie 5 par produkcyjnych
=======================================================
EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY
Odpowiada: kiedy warto handlować każdą parą?
Zapisuje raport do reports/SESSION_ANALYSIS.md
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

DATA_DIR = ROOT / "data" / "raw_dl_fx" / "download" / "m60"
REPORT   = ROOT / "reports" / "SESSION_ANALYSIS.md"

# Per-symbol settings (from grid backtest results)
SYMBOL_CFG = {
    "eurusd": dict(htf_rule="1D",  pip=0.0001, min_risk=0.0003, comm=0.00005),
    "usdjpy": dict(htf_rule="1D",  pip=0.01,   min_risk=0.03,   comm=0.005),
    "usdchf": dict(htf_rule="4h",  pip=0.0001, min_risk=0.0003, comm=0.00006),
    "audjpy": dict(htf_rule="1D",  pip=0.01,   min_risk=0.03,   comm=0.007),
    "cadjpy": dict(htf_rule="1D",  pip=0.01,   min_risk=0.03,   comm=0.0075),
}

SESSION_VARIANTS = [
    ("24h (bez filtra)",       None, None),
    ("Azja/Tokio  00-08 UTC",  0,    8),
    ("Londyn      08-13 UTC",  8,    13),
    ("Overlap     13-17 UTC",  13,   17),
    ("Nowy Jork   13-22 UTC",  13,   22),
    ("London+NY   07-21 UTC",  7,    21),
    ("Off-hours   21-00 UTC",  21,   24),
]

OOS_START = "2023-01-01"
OOS_END   = "2024-12-31"

BASE_CFG = dict(
    pivot_lb_ltf=3, pivot_lb_htf=5, confirm=1,
    entry_off=0.3,  sl_buf=0.1,     pmb=50,
    rr=3.0,         atr_period=14,  pivot_count=4,
    risk_pct=0.01,  initial_bal=10_000.0,
)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars(symbol: str) -> pd.DataFrame:
    bid = pd.read_csv(DATA_DIR / f"{symbol}_m60_bid_2021_2024.csv")
    ask = pd.read_csv(DATA_DIR / f"{symbol}_m60_ask_2021_2024.csv")
    for df in (bid, ask):
        df.columns = [c.strip().lower() for c in df.columns]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
    idx = bid.index.intersection(ask.index)
    out = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        out[f"{c}_bid"] = bid.loc[idx, c].values
        out[f"{c}_ask"] = ask.loc[idx, c].values
    out = out.dropna()
    out = out[(out["high_bid"] - out["low_bid"]) > 0]
    return out


# ── Indicators ────────────────────────────────────────────────────────────────

def calc_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    h, l, c = df["high_bid"].values, df["low_bid"].values, df["close_bid"].values
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    atr = np.full(n, np.nan)
    atr[period-1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
    return atr


def build_pivots(df: pd.DataFrame, lb: int, confirm: int = 1):
    n = len(df)
    h, l = df["high_bid"].values, df["low_bid"].values
    hp = np.pad(h, (lb, lb), mode="edge")
    lp = np.pad(l, (lb, lb), mode="edge")
    w = 2*lb+1
    hw = np.lib.stride_tricks.as_strided(hp, shape=(n,w), strides=(hp.strides[0],hp.strides[0]))
    lw = np.lib.stride_tricks.as_strided(lp, shape=(n,w), strides=(lp.strides[0],lp.strides[0]))
    raw_ph = (h == hw.max(axis=1)); raw_ph[:lb]=False; raw_ph[n-lb:]=False
    raw_pl = (l == lw.min(axis=1)); raw_pl[:lb]=False; raw_pl[n-lb:]=False
    ph_mask = np.zeros(n, bool); pl_mask = np.zeros(n, bool)
    if confirm > 0:
        ph_mask[confirm:] = raw_ph[:-confirm]
        pl_mask[confirm:] = raw_pl[:-confirm]
    else:
        ph_mask[:] = raw_ph; pl_mask[:] = raw_pl
    src = np.clip(np.arange(n)-confirm, 0, n-1)
    ph_lv = np.full(n, np.nan); pl_lv = np.full(n, np.nan)
    ph_lv[ph_mask] = h[src[ph_mask]]; pl_lv[pl_mask] = l[src[pl_mask]]
    return ph_lv, pl_lv, ph_mask, pl_mask


def htf_bias(ltf_time, htf_df, ph_lv, pl_lv, ph_mask, pl_mask, pcount=4):
    pos = htf_df.index.searchsorted(ltf_time, side="right") - 1
    if pos < 1: return "NEUTRAL"
    close = htf_df["close_bid"].iloc[pos]
    phs, pls = [], []
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


def run(bars: pd.DataFrame, sym_cfg: dict,
        session_start: Optional[int], session_end: Optional[int]) -> List[Trade]:

    htf_df = bars.resample(sym_cfg["htf_rule"]).agg({
        c: ("first" if "open" in c else ("max" if "high" in c else
            ("min" if "low" in c else "last")))
        for c in bars.columns
    }).dropna()

    atr = calc_atr(bars, BASE_CFG["atr_period"])
    ph_lv_l, pl_lv_l, ph_m_l, pl_m_l = build_pivots(bars, BASE_CFG["pivot_lb_ltf"], BASE_CFG["confirm"])
    ph_lv_h, pl_lv_h, ph_m_h, pl_m_h = build_pivots(htf_df, BASE_CFG["pivot_lb_htf"], BASE_CFG["confirm"])

    idx = bars.index
    cb, hb, lb_arr = bars["close_bid"].values, bars["high_bid"].values, bars["low_bid"].values
    ha, la = bars["high_ask"].values, bars["low_ask"].values
    comm    = sym_cfg["comm"]
    min_r   = sym_cfg["min_risk"]

    mask_oos = (idx >= OOS_START) & (idx <= OOS_END)
    if mask_oos.sum() == 0:
        return []
    start_i = max(int(np.where(mask_oos)[0][0]), 200)
    end_i   = int(np.where(mask_oos)[0][-1])

    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    active_setup: Optional[Setup] = None

    for i in range(start_i, end_i):
        t = idx[i]
        a = atr[i]
        if np.isnan(a) or a <= 0: continue

        # ── Exit open trade ───────────────────────────────────────────────────
        if open_trade is not None:
            tr = open_trade
            sl_hit = (lb_arr[i] <= tr.sl) if tr.direction == "LONG" else (ha[i] >= tr.sl)
            tp_hit = (hb[i] >= tr.tp)     if tr.direction == "LONG" else (la[i] <= tr.tp)
            if sl_hit and tp_hit: sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep   = tr.sl if sl_hit else tr.tp
                tr.R = ((ep - tr.entry) / tr.risk if tr.direction == "LONG"
                        else (tr.entry - ep) / tr.risk)
                tr.exit_reason = "SL" if sl_hit else "TP"
                trades.append(tr)
                open_trade = None
            continue

        # ── Try to fill pending setup ─────────────────────────────────────────
        if active_setup is not None:
            s = active_setup
            if i > s.expiry:
                active_setup = None
            else:
                filled = (la[i] <= s.entry <= ha[i]) if s.direction == "LONG" \
                         else (lb_arr[i] <= s.entry <= hb[i])
                if filled:
                    fp  = s.entry + comm if s.direction == "LONG" else s.entry - comm
                    buf = BASE_CFG["sl_buf"] * a
                    if s.direction == "LONG":
                        lv = last_pv(i, pl_lv_l, ph_m_l)
                        sl = (lv - buf) if lv else (cb[i] - 2*a)
                        sl = max(sl, cb[i] - 5*a)
                    else:
                        lv = last_pv(i, ph_lv_l, ph_m_l)
                        sl = (lv + buf) if lv else (cb[i] + 2*a)
                        sl = min(sl, cb[i] + 5*a)
                    risk = abs(fp - sl)
                    if risk < min_r:
                        active_setup = None
                        continue
                    tp = (fp + risk * BASE_CFG["rr"]) if s.direction == "LONG" \
                         else (fp - risk * BASE_CFG["rr"])
                    open_trade   = Trade(s.direction, fp, sl, tp, risk)
                    active_setup = None
                    continue

        if active_setup is not None or open_trade is not None:
            continue

        # ── Session filter ────────────────────────────────────────────────────
        if session_start is not None and session_end is not None:
            h = t.hour
            if session_end <= 24:
                if not (session_start <= h < session_end):
                    continue
            else:
                if not (h >= session_start or h < session_end % 24):
                    continue

        # ── HTF bias ──────────────────────────────────────────────────────────
        bias = htf_bias(t, htf_df, ph_lv_h, pl_lv_h, ph_m_h, pl_m_h, BASE_CFG["pivot_count"])
        if bias == "NEUTRAL":
            continue

        # ── BOS detection ─────────────────────────────────────────────────────
        lph = last_pv(i, ph_lv_l, ph_m_l)
        lpl = last_pv(i, pl_lv_l, pl_m_l)
        bos_dir = bos_lv = None
        if bias == "BULL" and lph and cb[i] > lph:
            bos_dir, bos_lv = "LONG",  lph
        elif bias == "BEAR" and lpl and cb[i] < lpl:
            bos_dir, bos_lv = "SHORT", lpl
        if bos_dir is None:
            continue

        off   = BASE_CFG["entry_off"] * a
        entry = bos_lv + off if bos_dir == "LONG" else bos_lv - off
        active_setup = Setup(bos_dir, entry, i + BASE_CFG["pmb"], bos_lv)

    return trades


def metrics(trades: List[Trade]) -> dict:
    if not trades:
        return dict(n=0, wr=0.0, expR=0.0, pf=0.0, dd=0.0)
    Rs   = [t.R for t in trades]
    wins = [r for r in Rs if r > 0]
    loss = [r for r in Rs if r <= 0]
    pf   = sum(wins) / abs(sum(loss)) if loss else float("inf")
    eq   = 10_000.0; peak = eq; max_dd = 0.0
    for r in Rs:
        eq   *= (1 + r * BASE_CFG["risk_pct"])
        peak  = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    return dict(n=len(Rs), wr=round(len(wins)/len(Rs)*100, 1),
                expR=round(float(np.mean(Rs)), 4),
                pf=round(pf, 3), dd=round(max_dd, 1))


# ── Verdict helpers ───────────────────────────────────────────────────────────

def verdict(m: dict, baseline_expR: float) -> str:
    if m["n"] == 0:              return "❌ brak danych"
    if m["expR"] < 0:            return "❌ ujemny"
    if m["expR"] < 0.05:         return "⚠️  marginalny"
    if m["expR"] >= baseline_expR * 0.95: return "✅ warto"
    if m["expR"] >= baseline_expR * 0.7:  return "⚠️  słabszy niż 24h"
    return "⚠️  znacznie słabszy"


def best_session(sym_results: list) -> str:
    """Return name of session variant with highest ExpR (excluding 24h baseline)."""
    filtered = [(name, m) for name, m in sym_results if "24h" not in name and m["n"] > 0]
    if not filtered:
        return "brak danych"
    return max(filtered, key=lambda x: x[1]["expR"])[0].strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import datetime
    print("Session Hours Analysis — 5 par produkcyjnych")
    print("OOS: 2023–2024 | H1/D1(H4) | RR=3.0, pmb=50, off=0.3, buf=0.1")
    print()

    all_results = {}

    for symbol, sym_cfg in SYMBOL_CFG.items():
        print(f"[{symbol.upper()}]  HTF={sym_cfg['htf_rule']}", flush=True)
        bars = load_bars(symbol)
        sym_results = []
        for name, s_start, s_end in SESSION_VARIANTS:
            trades = run(bars, sym_cfg, s_start, s_end)
            m = metrics(trades)
            sym_results.append((name, m))
            sign = "+" if m["expR"] >= 0 else ""
            print(f"  {name:<28}  n={m['n']:>4}  WR={m['wr']:>5.1f}%  "
                  f"ExpR={sign}{m['expR']:.4f}R  PF={m['pf']:.3f}  DD={m['dd']:.1f}%")
        print()
        all_results[symbol] = sym_results

    # ── Generate markdown report ──────────────────────────────────────────────
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L += [
        "# Analiza Godzin Sesji — Wszystkie Pary Produkcyjne",
        "",
        f"> Wygenerowano: {now}",
        "> OOS: 2023–2024 | LTF: H1 | HTF: D1 lub H4 (per para) | RR=3.0, pmb=50, off=0.3, buf=0.1",
        "> Pytanie: **kiedy warto handlować każdą parą walutową?**",
        "",
        "---",
        "",
    ]

    # Per-symbol tables
    for symbol, sym_results in all_results.items():
        sym_cfg = SYMBOL_CFG[symbol]
        base_expR = next(m["expR"] for name, m in sym_results if "24h" in name)
        best = best_session(sym_results)

        L += [
            f"## {symbol.upper()}  _(HTF: {sym_cfg['htf_rule']})_",
            "",
            f"| Sesja | n | WR | ExpR | PF | MaxDD | Ocena |",
            f"|-------|---|----|----|----|----|-------|",
        ]
        for name, m in sym_results:
            tag = "📊 baseline" if "24h" in name else verdict(m, base_expR)
            sign = "+" if m["expR"] >= 0 else ""
            bold = "**" if "24h" in name or name.strip() == best else ""
            L.append(f"| {bold}{name.strip()}{bold} | {m['n']} | {m['wr']}% | "
                     f"{sign}{m['expR']:.4f}R | {m['pf']:.3f} | {m['dd']:.1f}% | {tag} |")
        L += [
            "",
            f"🏆 **Najlepsza sesja:** `{best}`",
            "",
        ]

        # Key insights per symbol
        res = {name.strip(): m for name, m in sym_results}
        asia  = res.get("Azja/Tokio  00-08 UTC", res.get("Azja/noc   00-07 UTC", {}))
        ny    = res.get("Nowy Jork   13-22 UTC", {})
        lond  = res.get("Londyn      08-13 UTC", {})
        ovlp  = res.get("Overlap     13-17 UTC", {})
        off   = res.get("Off-hours   21-00 UTC", {})

        L.append("**Kluczowe obserwacje:**")
        if asia.get("n", 0) > 0:
            if asia["expR"] > 0.1:
                L.append(f"- 🌏 Azja (00–08): **jest edge** ExpR={asia['expR']:+.4f}R — rozważ włączenie")
            elif asia["expR"] > 0:
                L.append(f"- 🌏 Azja (00–08): marginalny edge ExpR={asia['expR']:+.4f}R — nie warto")
            else:
                L.append(f"- 🌏 Azja (00–08): **ujemny** ExpR={asia['expR']:+.4f}R — słusznie wyłączone")
        if ny.get("n", 0) > 0:
            comp = "lepszy" if ny["expR"] > base_expR else "gorszy"
            L.append(f"- 🗽 NY (13–22): ExpR={ny['expR']:+.4f}R, WR={ny['wr']}% — {comp} niż 24h")
        if off.get("n", 0) > 0:
            if off["expR"] > 0.05:
                L.append(f"- 🌙 Off-hours (21–00): ExpR={off['expR']:+.4f}R — zaskakujący edge")
            else:
                L.append(f"- 🌙 Off-hours (21–00): ExpR={off['expR']:+.4f}R — brak edge po zamknięciu NY")
        L.append("")

    # ── Summary table ─────────────────────────────────────────────────────────
    L += [
        "---",
        "",
        "## Tabela zbiorcza — rekomendowane godziny handlu",
        "",
        "| Para | Najlepsza sesja | ExpR najlepsza | ExpR 24h | Obecna konfiguracja | Ocena |",
        "|------|----------------|---------------|---------|---------------------|-------|",
    ]

    CURRENT_CFG = {
        "eurusd": "London+NY  07-21 UTC",
        "usdjpy": "24h (bez filtra)",
        "usdchf": "London+NY  07-21 UTC",
        "audjpy": "24h (bez filtra)",
        "cadjpy": "24h (bez filtra)",
    }

    for symbol, sym_results in all_results.items():
        res       = {name.strip(): m for name, m in sym_results}
        base_expR = next(m["expR"] for name, m in sym_results if "24h" in name)
        best_name = best_session(sym_results)
        best_expR = res.get(best_name, {}).get("expR", 0)

        curr_key  = CURRENT_CFG[symbol].strip()
        curr_m    = res.get(curr_key, res.get("24h (bez filtra)", {}))
        curr_expR = curr_m.get("expR", base_expR)

        # Is current config optimal?
        if best_expR > 0 and curr_expR >= best_expR * 0.9:
            cfg_ok = "✅ optymalna"
        elif curr_expR > 0:
            diff = best_expR - curr_expR
            cfg_ok = f"⚠️  można poprawić (+{diff:.3f}R)"
        else:
            cfg_ok = "❌ zmienić"

        L.append(f"| **{symbol.upper()}** | `{best_name}` | +{best_expR:.4f}R | "
                 f"+{base_expR:.4f}R | `{CURRENT_CFG[symbol].strip()}` | {cfg_ok} |")

    L += [
        "",
        "---",
        "",
        "## Wnioski końcowe",
        "",
    ]

    # Per-symbol recommendations
    for symbol, sym_results in all_results.items():
        res       = {name.strip(): m for name, m in sym_results}
        base_expR = next(m["expR"] for name, m in sym_results if "24h" in name)
        best_name = best_session(sym_results)
        best_expR = res.get(best_name, {}).get("expR", 0)
        curr_key  = CURRENT_CFG[symbol].strip()
        curr_expR = res.get(curr_key, {}).get("expR", base_expR)

        gain = best_expR - curr_expR
        if gain > 0.03:
            action = f"**Zmienić** filtr sesji na `{best_name}` → +{gain:.4f}R poprawy"
        else:
            action = f"Obecna konfiguracja OK (różnica <0.03R)"

        L.append(f"- **{symbol.upper()}**: {action}")

    L += [
        "",
        "### Ogólna zasada:",
        "| Sesja UTC | Pary EUR/CHF | Pary JPY (USDJPY/AUDJPY/CADJPY) |",
        "|-----------|-------------|--------------------------------|",
        "| 00–08 Azja | ❌ brak edge | ⚠️  zależy od pary |",
        "| 08–13 Londyn | ✅ aktywny | ✅ aktywny |",
        "| 13–17 Overlap | ✅ najlepszy | ✅ najlepszy |",
        "| 17–22 NY | ✅ dobry | ✅ dobry |",
        "| 22–00 Off | ❌ brak edge | ❌ brak edge |",
        "",
        f"*Wygenerowano: {now} | OOS 2023–2024*",
    ]

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"Raport zapisany: {REPORT}")


if __name__ == "__main__":
    main()


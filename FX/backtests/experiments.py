"""
backtests/experiments.py
Generator siatki eksperymentów — 2-stage pipeline.
Stage 1: one-factor-at-a-time vs baseline
Stage 2: cross-product top N z każdego bloku
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ── Experiment config dataclass (dict-based) ──────────────────────────────────

def make_experiment(
    name: str,
    adx_gate: Optional[float],
    adx_slope: bool,
    atr_pct_min: float,
    atr_pct_max: float,
    sizing_mode: str,
    fixed_units: float,
    risk_pct: float,
    rr_mode: str,
    rr: float,
    block: str = "baseline",
    # ADX v2 fields
    gate_type: str = "NONE",
    gate_tf: str = "D1",
    adx_threshold: float = 0.0,
    rising_k: int = 3,
    adx_soft_threshold: Optional[float] = None,
    adx_soft_rr_below: float = 2.0,
) -> dict:
    return {
        "name":               name,
        "block":              block,
        "adx_gate":           adx_gate,
        "adx_slope":          adx_slope,
        "atr_pct_min":        atr_pct_min,
        "atr_pct_max":        atr_pct_max,
        "sizing_mode":        sizing_mode,
        "fixed_units":        fixed_units,
        "risk_pct":           risk_pct,
        "rr_mode":            rr_mode,
        "rr":                 rr,
        "gate_type":          gate_type,
        "gate_tf":            gate_tf,
        "adx_threshold":      adx_threshold,
        "rising_k":           rising_k,
        "adx_soft_threshold": adx_soft_threshold,
        "adx_soft_rr_below":  adx_soft_rr_below,
    }


def _baseline() -> dict:
    return make_experiment(
        name="baseline",
        adx_gate=None, adx_slope=False,
        atr_pct_min=0, atr_pct_max=100,
        sizing_mode="fixed_units", fixed_units=5000, risk_pct=0.005,
        rr_mode="fixed", rr=3.0,
        block="baseline",
    )


# ── Stage 1: one-factor-at-a-time ────────────────────────────────────────────

def stage1_experiments(cfg: dict) -> List[dict]:
    """Generuje listę eksperymentów stage 1 (jeden czynnik na raz)."""
    exps = [_baseline()]
    exp_cfg = cfg.get("experiments", {})

    # Block B: ADX gate
    for adx_thr in exp_cfg.get("adx_thresholds", [18, 20, 22, 25]):
        for slope in exp_cfg.get("adx_slope_options", [False, True]):
            name = f"adx{adx_thr}" + ("_slope" if slope else "")
            exps.append(make_experiment(
                name=name, adx_gate=float(adx_thr), adx_slope=slope,
                atr_pct_min=0, atr_pct_max=100,
                sizing_mode="fixed_units", fixed_units=5000, risk_pct=0.005,
                rr_mode="fixed", rr=3.0, block="adx",
            ))

    # Block C: ATR percentile filter
    atr_mins = exp_cfg.get("atr_pct_min_values", [0, 10, 20])
    atr_maxs = exp_cfg.get("atr_pct_max_values", [70, 80, 85, 90, 100])
    for pmin, pmax in itertools.product(atr_mins, atr_maxs):
        if pmin >= pmax:
            continue
        name = f"atr_pct_{pmin}_{pmax}"
        exps.append(make_experiment(
            name=name, adx_gate=None, adx_slope=False,
            atr_pct_min=pmin, atr_pct_max=pmax,
            sizing_mode="fixed_units", fixed_units=5000, risk_pct=0.005,
            rr_mode="fixed", rr=3.0, block="atr_pct",
        ))

    # Block D: Position sizing
    for sz in exp_cfg.get("sizing_modes", []):
        mode = sz["mode"]
        if mode == "fixed_units":
            u = sz.get("units", 5000)
            name = f"size_fixed_{u}"
            exps.append(make_experiment(
                name=name, adx_gate=None, adx_slope=False,
                atr_pct_min=0, atr_pct_max=100,
                sizing_mode="fixed_units", fixed_units=u, risk_pct=0.005,
                rr_mode="fixed", rr=3.0, block="sizing",
            ))
        elif mode == "risk_first":
            rp = sz.get("risk_pct", 0.005)
            name = f"size_risk_{int(rp*10000)}bp"
            exps.append(make_experiment(
                name=name, adx_gate=None, adx_slope=False,
                atr_pct_min=0, atr_pct_max=100,
                sizing_mode="risk_first", fixed_units=5000, risk_pct=rp,
                rr_mode="fixed", rr=3.0, block="sizing",
            ))

    # Block E: Adaptive RR
    for rm in exp_cfg.get("rr_modes", []):
        mode = rm["mode"]
        rr_val = rm.get("rr", 3.0)
        name = f"rr_{mode}"
        if mode == "fixed":
            name = f"rr_fixed_{rr_val}"
        exps.append(make_experiment(
            name=name, adx_gate=None, adx_slope=False,
            atr_pct_min=0, atr_pct_max=100,
            sizing_mode="fixed_units", fixed_units=5000, risk_pct=0.005,
            rr_mode=mode, rr=rr_val, block="rr",
        ))

    return exps


# ── Stage 2: cross-product of top N per block ─────────────────────────────────

def stage2_experiments(
    stage1_results: List[dict],   # lista {exp, metrics_val}
    top_n: int = 10,
    max_total: int = 350,
    seed: int = 42,
) -> List[dict]:
    """
    Wybiera top_n z każdego bloku (po val expectancy_R) i robi cross-product.
    Przycina do max_total jeśli za dużo.
    """
    # Group by block
    blocks: Dict[str, List[dict]] = {}
    for r in stage1_results:
        block = r["exp"].get("block", "other")
        blocks.setdefault(block, []).append(r)

    # Top N per block (by val expectancy_R)
    top_per_block: Dict[str, List[dict]] = {}
    for block, results in blocks.items():
        if block == "baseline":
            top_per_block[block] = [results[0]["exp"]]
            continue
        ranked = sorted(results, key=lambda r: r["metrics_val"].get("expectancy_R", -99),
                        reverse=True)
        top_per_block[block] = [r["exp"] for r in ranked[:top_n]]

    # Cross-product: bierzemy jeden z każdego bloku i łączymy
    # Łączymy bloki: adx, atr_pct, sizing, rr
    adx_tops    = top_per_block.get("adx", [_baseline()])
    atr_tops    = top_per_block.get("atr_pct", [_baseline()])
    sizing_tops = top_per_block.get("sizing", [_baseline()])
    rr_tops     = top_per_block.get("rr", [_baseline()])

    cross = []
    for adx_exp, atr_exp, size_exp, rr_exp in itertools.product(
        adx_tops, atr_tops, sizing_tops, rr_tops
    ):
        name = f"cross_{adx_exp['name']}_{atr_exp['name']}_{size_exp['name']}_{rr_exp['name']}"
        cross.append(make_experiment(
            name=name,
            adx_gate=adx_exp["adx_gate"], adx_slope=adx_exp["adx_slope"],
            atr_pct_min=atr_exp["atr_pct_min"], atr_pct_max=atr_exp["atr_pct_max"],
            sizing_mode=size_exp["sizing_mode"], fixed_units=size_exp["fixed_units"],
            risk_pct=size_exp["risk_pct"],
            rr_mode=rr_exp["rr_mode"], rr=rr_exp["rr"],
            block="cross",
        ))

    # Przytnij do max_total
    if len(cross) > max_total:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(cross), size=max_total, replace=False)
        cross = [cross[i] for i in sorted(idx)]

    return cross


def all_experiments(cfg: dict) -> List[dict]:
    """
    Zwraca listę wszystkich eksperymentów stage1 (do uruchomienia w batch).
    Stage2 wymaga wyników stage1 — generowana osobno w run_experiments.py.
    """
    return stage1_experiments(cfg)


# ── ADX v2 experiments ────────────────────────────────────────────────────────

def _adx_v2_context_a() -> dict:
    """Context A: baseline (fixed_units, brak ATR filter, RR=3.0)."""
    return dict(sizing_mode="fixed_units", fixed_units=5000, risk_pct=0.005,
                atr_pct_min=0, atr_pct_max=100, rr_mode="fixed", rr=3.0)


def _adx_v2_context_b() -> dict:
    """Context B: Opcja C (risk_first 0.5%, ATR 10-80 tylko CADJPY — symulowany jako globalny 10-80 dla uproszczenia badania)."""
    # Uwaga: w research ATR filtr stosujemy globalnie dla wszystkich symboli
    # (w produkcji tylko CADJPY). To konserwatywniejsze dla research — gorsza
    # pozycja wyjściowa, ale porównywalna między wariantami ADX v2.
    return dict(sizing_mode="risk_first", fixed_units=5000, risk_pct=0.005,
                atr_pct_min=10, atr_pct_max=80, rr_mode="fixed", rr=3.0)


def adx_v2_experiments() -> List[dict]:
    """
    Generuje 32 warianty ADX v2 × 2 konteksty = 64 eksperymenty.

    Warianty:
      H4 threshold: progi {14, 16, 18, 20, 22}              = 5
      D1 threshold (niższe): progi {14, 16, 18}             = 3
      ADX rising H4: k ∈ {2, 3, 5}                         = 3
      ADX rising D1: k ∈ {2, 3, 5}                         = 3
      ADX slope_pos H4                                       = 1
      ADX slope_pos D1                                       = 1
      ADX_SOFT H4: threshold ∈ {18, 22}, rr_below=2.0      = 2
    Razem: 18 wariantów × 2 konteksty = 36 (+ baseline ×2 = 38)
    """
    exps: List[dict] = []

    for ctx_name, ctx in [("ctxA", _adx_v2_context_a()),
                           ("ctxB", _adx_v2_context_b())]:

        # ── Baseline per context ──────────────────────────────────────────────
        exps.append(make_experiment(
            name=f"adxv2_baseline_{ctx_name}",
            adx_gate=None, adx_slope=False,
            gate_type="NONE", gate_tf="D1",
            block="adx_v2",
            **ctx,
        ))

        # ── H4 threshold: progi 14, 16, 18, 20, 22 ───────────────────────────
        for thr in [14, 16, 18, 20, 22]:
            exps.append(make_experiment(
                name=f"adxv2_h4_thr{thr}_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_THRESHOLD", gate_tf="H4",
                adx_threshold=float(thr),
                block="adx_v2",
                **ctx,
            ))

        # ── D1 threshold (niższe progi): 14, 16, 18 ──────────────────────────
        for thr in [14, 16, 18]:
            exps.append(make_experiment(
                name=f"adxv2_d1_thr{thr}_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_THRESHOLD", gate_tf="D1",
                adx_threshold=float(thr),
                block="adx_v2",
                **ctx,
            ))

        # ── ADX rising H4: k ∈ {2, 3, 5} ─────────────────────────────────────
        for k in [2, 3, 5]:
            exps.append(make_experiment(
                name=f"adxv2_h4_rising{k}_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_RISING", gate_tf="H4",
                rising_k=k,
                block="adx_v2",
                **ctx,
            ))

        # ── ADX rising D1: k ∈ {2, 3, 5} ─────────────────────────────────────
        for k in [2, 3, 5]:
            exps.append(make_experiment(
                name=f"adxv2_d1_rising{k}_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_RISING", gate_tf="D1",
                rising_k=k,
                block="adx_v2",
                **ctx,
            ))

        # ── ADX slope_pos H4 i D1 ────────────────────────────────────────────
        for tf in ["H4", "D1"]:
            exps.append(make_experiment(
                name=f"adxv2_{tf.lower()}_slope_pos_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_SLOPE_POS", gate_tf=tf,
                block="adx_v2",
                **ctx,
            ))

        # ── ADX_SOFT H4: threshold 18 i 22, rr_below=2.0 ────────────────────
        for thr in [18, 22]:
            exps.append(make_experiment(
                name=f"adxv2_h4_soft{thr}_{ctx_name}",
                adx_gate=None, adx_slope=False,
                gate_type="ADX_THRESHOLD", gate_tf="H4",
                adx_threshold=float(thr),
                adx_soft_threshold=float(thr),
                adx_soft_rr_below=2.0,
                block="adx_v2",
                **ctx,
            ))

    return exps



# ADX v2 Test — Raport

> Wygenerowano: 2026-03-04 14:31 UTC
> Symbole: PORTFOLIO
> Foldy: 9-fold walk-forward (1 hist + 8 kwartalnych OOS 2024/2025)

---

## 1. Podsumowanie — Top 5 ADX v2 (val, portfolio)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ val→test | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_h4_thr16_ctxA` | ctxA | +0.1794 | +0.1868 | +0.0074 | 0 | 12878 |
| `adxv2_h4_rising2_ctxB` | ctxB | +0.1591 | +0.2000 | +0.0409 | 1 | 3620 |
| `adxv2_h4_thr16_ctxB` | ctxB | +0.1525 | +0.0818 | -0.0707 | 1 | 6438 |
| `adxv2_h4_thr14_ctxA` | ctxA | +0.1467 | +0.2459 | +0.0992 | 1 | 13365 |
| `adxv2_h4_slope_pos_ctxB` | ctxB | +0.1408 | +0.1564 | +0.0156 | 1 | 3599 |

**Baseline (ctxA, brak filtrów):** `+0.1156`R
**ADX v1 best (adx25 D1):** `+0.0920`R  | **ADX v1 worst (adx22 D1):** `+0.0396`R

---

## 2. Grupy eksperymentów

### 2a. H4 threshold (niższe progi niż v1)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_h4_thr16_ctxA` | ctxA | +0.1794 | +0.1868 | +0.0074 | 0 | 12878 |
| `adxv2_h4_thr16_ctxB` | ctxB | +0.1525 | +0.0818 | -0.0707 | 1 | 6438 |
| `adxv2_h4_thr14_ctxA` | ctxA | +0.1467 | +0.2459 | +0.0992 | 1 | 13365 |
| `adxv2_h4_thr14_ctxB` | ctxB | +0.1266 | +0.0948 | -0.0318 | 1 | 6796 |
| `adxv2_h4_thr18_ctxA` | ctxA | +0.1212 | +0.1935 | +0.0723 | 0 | 12083 |
| `adxv2_h4_thr18_ctxB` | ctxB | +0.1114 | +0.1010 | -0.0104 | 1 | 5914 |

### 2b. D1 threshold (niższe progi: 14, 16, 18)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_d1_thr14_ctxA` | ctxA | +0.1176 | +0.0875 | -0.0301 | 0 | 11961 |
| `adxv2_d1_thr14_ctxB` | ctxB | +0.1160 | +0.0930 | -0.0230 | 1 | 6065 |
| `adxv2_d1_thr16_ctxA` | ctxA | +0.1157 | +0.1574 | +0.0417 | 0 | 9959 |
| `adxv2_d1_thr18_ctxB` | ctxB | +0.1127 | +0.0740 | -0.0387 | 1 | 4393 |

### 2c. ADX Rising (H4 i D1, k=2/3/5)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_h4_rising2_ctxB` | ctxB | +0.1591 | +0.2000 | +0.0409 | 1 | 3620 |
| `adxv2_h4_rising3_ctxB` | ctxB | +0.1244 | +0.1429 | +0.0185 | 1 | 3588 |
| `adxv2_h4_rising5_ctxB` | ctxB | +0.0835 | +0.0732 | -0.0103 | 1 | 3608 |
| `adxv2_d1_rising2_ctxA` | ctxA | +0.0645 | +0.1086 | +0.0441 | 0 | 5805 |
| `adxv2_d1_rising5_ctxA` | ctxA | +0.0519 | +0.0178 | -0.0341 | 0 | 5484 |
| `adxv2_d1_rising2_ctxB` | ctxB | +0.0280 | +0.0464 | +0.0184 | 0 | 3280 |

### 2d. ADX Slope SMA>0 (H4 i D1)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_h4_slope_pos_ctxB` | ctxB | +0.1408 | +0.1564 | +0.0156 | 1 | 3599 |
| `adxv2_d1_slope_pos_ctxA` | ctxA | +0.0486 | +0.0314 | -0.0172 | 1 | 5770 |
| `adxv2_d1_slope_pos_ctxB` | ctxB | +0.0122 | +0.0280 | +0.0158 | 0 | 3171 |
| `adxv2_h4_slope_pos_ctxA` | ctxA | -0.0563 | -0.0059 | +0.0504 | 1 | 7243 |

### 2e. ADX Soft Gate H4 (threshold 18/22, RR↓2.0 gdy ADX niski)

| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |
|---|---|---|---|---|---|---|
| `adxv2_h4_soft18_ctxB` | ctxB | +0.1261 | +0.1047 | -0.0214 | 1 | 7314 |
| `adxv2_h4_soft22_ctxA` | ctxA | +0.1153 | +0.1041 | -0.0112 | 0 | 13982 |
| `adxv2_h4_soft22_ctxB` | ctxB | +0.1009 | +0.0874 | -0.0135 | 1 | 7212 |
| `adxv2_h4_soft18_ctxA` | ctxA | +0.0971 | +0.1593 | +0.0622 | 0 | 13904 |

---

## 3. Analiza per-symbol

| Symbol | Najlepszy wariant | Val ExpR | Baseline ExpR | Δ | Ocena |
|---|---|---|---|---|---|
| **AUDJPY** | `adxv2_h4_thr14_ctxA` | +0.3292 | +0.1852 | +0.1440 | ✅ |
| **CADJPY** | `adxv2_baseline_ctxB` | +0.2468 | +0.2468 | +0.0000 | ❌ |
| **EURUSD** | `adxv2_h4_rising5_ctxA` | +0.4807 | +0.4024 | +0.0782 | ✅ |
| **USDCHF** | `adxv2_d1_rising5_ctxA` | +0.1822 | +0.0207 | +0.1614 | ✅ |
| **USDJPY** | `adxv2_h4_thr16_ctxA` | +0.3642 | +0.3455 | +0.0187 | ⚠️ |

---

## 4. Porównanie ADX v1 vs v2 (portfolio)

| Wersja | Opis | Val ExpR | Wniosek |
|---|---|---|---|
| **Baseline** | Brak filtru ADX | `+0.1156` | punkt odniesienia |
| ADX v1 best | D1 thr=25 | `+0.0920` | -20% vs baseline |
| ADX v1 worst | D1 thr=22 | `+0.0396` | -66% vs baseline |
| **ADX v2 best** | `adxv2_h4_thr16_ctxA` | `+0.1794` | vs baseline: +0.0638 |

---

## 5. Rekomendacja końcowa

✅ **adxv2_h4_thr16_ctxA** bije baseline o +0.0638R z niskim overfittem (delta=+0.0074R). Warto rozważyć wdrożenie.

### Czy H4 pomaga względem D1?
≈ H4 (avg=+0.1042) ≈ D1 (avg=+0.1024) — brak istotnej różnicy

### Czy 'ADX rising' lepszy od hard threshold?
❌ Rising (avg=+0.0410) ≤ Threshold H4 (avg=+0.1042) — hard threshold nie gorszy

---

_Raport wygenerowany automatycznie przez `backtests/reporting.py`_

---

## 6. CADJPY — szczegółowa analiza: czy H4 ADX thr=16 niszczy parę?

**Pytanie:** CADJPY ma już wdrożony filtr ATR 10–80 (P2). Czy globalny H4 ADX thr=16
koliduje z tym filtrem i obniża jego wyniki?

### 6.1 Tabela wariantów (val ExpR, śr. 9 foldów)

| Konfiguracja | Val ExpR | Test ExpR | Δ | Trades | Pos Q% |
|---|---|---|---|---|---|
| **ATR 10–80 only** *(produkcja)* | **+0.247R** | +0.165R | -0.082 | 1925 | **78%** |
| H4 rising k=2 + ATR 10–80 | +0.228R | +0.290R | +0.061 | 1025 | **86%** |
| H4 ADX16 + ATR 10–80 | +0.188R | +0.074R | **-0.114** | 1712 | 64% |
| H4 ADX14 + ATR 10–80 | +0.160R | +0.044R | **-0.117** | 1778 | 67% |
| H4 ADX16 only (bez ATR) | +0.142R | +0.250R | +0.108 | 3666 | 58% |
| H4 ADX14 only | +0.119R | +0.349R | +0.230 | 3706 | 67% |
| H4 ADX18 + ATR 10–80 | +0.076R | +0.058R | -0.019 | 1547 | 50% |
| NO FILTERS (raw baseline) | +0.001R | +0.165R | +0.163 | 3787 | 44% |

### 6.2 Per-fold (val) dla 3 kluczowych wariantów

| Fold | ATR 10–80 *(produkcja)* | H4 ADX16 + ATR 10–80 | H4 ADX16 only |
|---|---|---|---|
| Q1 2024 | +0.333 | +0.212 | +0.846 |
| Q2 2024 | +0.517 | **-0.111** | -0.077 |
| Q3 2024 | +0.182 | +0.238 | +0.556 |
| Q4 2024 | +0.539 | +0.818 | **-0.333** |
| Q1 2025 | -0.692 | -0.692 | +0.263 |
| Q2 2025 | +0.053 | **-0.250** | +0.500 |
| Q3 2025 | -0.027 | +0.263 | -0.158 |
| Q4 2025 | +0.895 | +1.000 | **-0.273** |
| fold hist | +0.422 | +0.216 | -0.045 |

### 6.3 Wnioski

**❌ H4 ADX thr=16 NISZCZY CADJPY gdy stosowany razem z ATR 10–80:**

- `H4_ADX16 + ATR 10–80` = +0.188R vs `ATR 10–80 only` = **+0.247R** (delta = **-0.059R**, -24%)
- Overfit combo bardzo duży: val=+0.188R → test=+0.074R (Δ = -0.114R)
- Stabilność kw. spada z 78% → 64%
- Przyczyną jest podwójne odfiltrowanie: ATR usuwa sygnały przy złej zmienności,
  ADX dodatkowo usuwa sygnały przy słabym trendzie → za mało sygnałów (~1712 vs 1925),
  te które zostają nie są lepsze jakościowo

**✅ Aktualny stan produkcji (ATR 10–80 only) jest OPTYMALNY dla CADJPY:**
- Najwyższy val ExpR (+0.247R), najwyższa stabilność (78% pos. kwartałów)
- Nie ma sensu dodawać H4 ADX filtra do CADJPY

**⚠️ Jedyny wariant który nie niszczy i nawet nieznacznie poprawia CADJPY:**
- `H4 rising k=2 + ATR 10–80`: +0.228R val, +0.290R test, Δ=+0.061 (test lepszy!) — ale val niższy niż produkcja
- Nie rekomendowany — poprawa na test może być losowa (tylko 1025 trades)

### 6.4 Rekomendacja dla wdrożenia globalnego H4 ADX thr=16

Jeśli H4 ADX thr=16 zostanie wdrożony globalnie (dla EURUSD/USDJPY/USDCHF/AUDJPY),
**CADJPY musi pozostać z własnym filtrem ATR 10–80 i BEZ H4 ADX gate.**

Implementacja: per-symbol `adx_gate` w `config.yaml`:
```yaml
symbols:
  CADJPY:
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
    adx_h4_gate: null          # wyłączony — ATR filtr wystarczy
  EURUSD:
    adx_h4_gate: 16            # włączony
  USDJPY:
    adx_h4_gate: 16
  USDCHF:
    adx_h4_gate: 16
  AUDJPY:
    adx_h4_gate: 16
```


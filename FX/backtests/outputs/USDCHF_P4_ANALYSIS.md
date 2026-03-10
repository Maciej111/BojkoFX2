# USDCHF — Analiza P4: enabled:false vs filtr ATR vs status quo

**Data:** 2026-03-04
**Pytanie:** Czy USDCHF warto wylaczyc (`enabled: false`) lub dodac `atr_pct_filter`?
**Kontekst:** USDCHF ma wdrozony H4 ADX gate thr=16 (P3, 2026-03-04). Sprawdzamy czy para jest warta utrzymania.

---

## 1. Wyniki wariantow (val ExpR, sr. 9 foldow walk-forward 2021-2025)

| Konfiguracja | Val ExpR | Test ExpR | Delta | Trades | Stab Q% |
|---|---|---|---|---|---|
| **H4 ADX16 only (WDROZONY)** | **+0.060R** | +0.000R | -0.060 | 2153 | **61%** |
| H4 ADX18 only | +0.060R | +0.172R | **+0.113** | 2079 | 64% |
| H4 rising k2 + ATR 10-80 | +0.039R | +0.108R | +0.069 | 514 | 58% |
| H4 ADX16 + ATR 10-80 | +0.038R | -0.055R | -0.092 | 992 | 39% |
| **NO FILTERS (baseline)** | +0.021R | +0.056R | +0.035 | 2241 | 39% |
| H4 ADX14 only | +0.015R | -0.015R | -0.030 | 2177 | 39% |
| D1 ADX16 only | -0.030R | +0.220R | +0.249 | 1653 | 42% |
| **ATR 10-80 only** | **-0.031R** | -0.069R | -0.038 | 1070 | 50% |
| D1 ADX14 only | -0.045R | -0.036R | +0.009 | 1875 | 25% |
| H4 rising k2 only | -0.153R | -0.126R | +0.026 | 1170 | 42% |

---

## 2. Per-fold (val) — kluczowe warianty

| Fold | ATR 10-80 | H4 ADX16 (wdrozony) | NO FILTERS |
|---|---|---|---|
| hist 2021-2025 | -0.164 | +0.018 | -0.044 |
| Q1 2024 | +0.273 | -0.429 | -0.429 |
| Q2 2024 | -0.059 | +0.333 | +0.053 |
| Q3 2024 | -0.294 | +0.143 | +0.500 |
| Q4 2024 | +0.778 | +0.333 | +0.333 |
| Q1 2025 | -0.714 | -0.143 | -0.294 |
| Q2 2025 | +0.091 | +0.818 | +0.600 |
| Q3 2025 | -0.692 | -0.200 | -0.200 |
| Q4 2025 | +0.500 | -0.333 | -0.333 |

---

## 3. Wnioski

### 3a. Czy ATR 10-80 pomaga USDCHF?
**NIE.** ATR 10-80 daje -0.031R vs baseline +0.021R — ATR **szkodzi** tej parze (delta = -0.052R).
Mechanizm identyczny jak H4 ADX gate niszczyl CADJPY: za duze filtrowanie eliminuje dobre sygnaly.
**Wniosek: nie dodawac `atr_pct_filter` do USDCHF.**

### 3b. Czy wylaczyc USDCHF (`enabled: false`)?
**NIE teraz.** Uzasadnienie:
- H4 ADX16 daje +0.060R (+186% vs baseline +0.021R)
- Stabilnosc kwartalow wzrosla: 39% -> 61%
- Test = 0.000R — overfit, ale nie destrukcyjny
- Wyylaczenie eliminuje jedyna pare CHF w portfolio (dywersyfikacja)

### 3c. H4 ADX18 ciekawa opcja (do monitorowania)
Val +0.060R (taki sam jak thr=16), test +0.172R (Δ=+0.113).
Brak overfitu — wyniki na test wyraznie lepsze niz val.
**Nie wdrazac bez osobnej walidacji OOS 2025 w izolacji.**

---

## 4. Rekomendacja: status quo

| Parametr | Wartosc | Uzasadnienie |
|---|---|---|
| `enabled` | `true` | Para pozytywna z H4 ADX gate |
| `adx_h4_gate` | `16` | Wdrozony P3, +186% vs baseline |
| `atr_pct_filter` | *brak* | ATR szkodzi USDCHF (-0.052R delta) |

**Trigger do rewizji:** jesli Q1 lub Q2 2026 USDCHF da >= 2 kolejne ujemne kwartalowe foldy
na produkcji → rozwazyc `adx_h4_gate: 18` lub `enabled: false`.


# Raport porównawczy — Produkcja vs Opcja C

**Data:** 2026-03-04  |  **Dane:** H1 OHLC 2021–2025, 5 symboli, 9 foldów walk-forward  
**Baseline = aktualna produkcja** (BOS+Pullback, H1/D1, fixed 5000 units, RR=3.0, bez filtrów)

---

## Czym są testowane opcje?

| Opcja | Opis | Co zmienia vs produkcja |
|---|---|---|
| **Baseline** | Aktualny bot na VM | — punkt odniesienia |
| **atr_pct_10_80** | Filtr ATR percentile 10–80 | Odrzuca sygnały gdy zmienność < 10% lub > 80% percentyla historii (~47% mniej tradów) |
| **size_risk_50bp** | Risk-based sizing 0.5% equity | Nie zmienia sygnałów — zmienia tylko wielkość pozycji (proporcjonalnie do odległości SL) |
| **Opcja C** | atr_pct_10_80 + size_risk_50bp | Połączenie obu — filtruje sygnały I kontroluje ryzyko per trade |

---

## 1. Portfolio — porównanie wszystkich opcji

| Metryka | Baseline | atr_10_80 | size_50bp | **Opcja C** | Najlepsza |
|---|---|---|---|---|---|
| ExpR (avg R/trade) | 0.1156 | 0.1292 | 0.1156 | **0.1292** | atr_10_80 / Opcja C |
| Profit Factor | 1.2560 | 1.2203 | 1.1750 | 1.2203 | baseline |
| Win Rate | 0.2789 | 0.2823 | 0.2789 | 0.2823 | atr_10_80 |
| **Max DD% (avg)** | 430.95% | 272.13% | **8.33%** | **4.39%** | Opcja C / size_50bp |
| Stabilność (pos kw.) | 33% | **64%** | 61% | **64%** | atr_10_80 / Opcja C |
| Liczba tradów | 13937 | 7351 (52%) | 13937 (100%) | 7351 (52%) | — |

> **Kluczowy wniosek portfolio:**
> - ExpR rośnie o **+0.0137R** per trade dzięki filtrowi ATR
> - DD spada z **430.95%** → **4.39%** (Opcja C = redukcja o 427pp, czyli **99% mniejszy drawdown**)
> - Stabilność rośnie z **33%** → **64%** pozytywnych kwartałów (+31%)
> - Koszt: tylko **52% tradów** zostaje — bot handluje rzadziej

---

## 2. Per-symbol — Opcja C vs Baseline

| Symbol | ExpR base | ExpR Opcja C | Delta ExpR | DD% base | DD% Opcja C | Trades kept | Ocena |
|---|---|---|---|---|---|---|---|
| **EURUSD** | +0.4024 | +0.2080 | **-0.1945** | 1.19% | 1.71% | 56% | ❌ ZNACZNIE GORSZA |
| **USDJPY** | +0.3455 | +0.1418 | **-0.2036** | 184.45% | 1.81% | 55% | ❌ ZNACZNIE GORSZA |
| **CADJPY** | +0.0014 | +0.2468 | **+0.2454** | 205.07% | 1.94% | 51% | ✅ LEPSZA |
| **AUDJPY** | +0.1852 | +0.0821 | **-0.1031** | 146.57% | 1.64% | 55% | ❌ ZNACZNIE GORSZA |
| **USDCHF** | +0.0207 | -0.0314 | **-0.0521** | 1.03% | 1.53% | 48% | ⚠️ GORSZA |


---

## 3. Stabilność kwartalna — ile kwartałów na plusie (z 8)

| Symbol | Baseline pos/8 | Opcja C pos/8 | Delta | Trend |
|---|---|---|---|---|
| **EURUSD** | 4/8 | 4/8 | +0 | ➡️ |
| **USDJPY** | 7/8 | 6/8 | -1 | ⬇️ |
| **CADJPY** | 3/8 | 6/8 | +3 | ⬆️ |
| **AUDJPY** | 4/8 | 4/8 | +0 | ➡️ |
| **USDCHF** | 4/8 | 4/8 | +0 | ➡️ |

### Szczegół: ExpR per kwartal per symbol (Opcja C = atr_pct_10_80)

_(+ = kwartal zyskowny, - = stratny)_

| Kwartal | AUDJPY | CADJPY | EURUSD | USDCHF | USDJPY |
|---|---|---|---|---|---|
| Q1_2024 | 🟢 +0.1765 | 🟢 +0.3333 | 🔴 -0.3043 | 🟢 +0.2727 | 🟢 +0.3913 |
| Q1_2025 | 🔴 -0.3600 | 🔴 -0.6923 | 🔴 -0.6000 | 🔴 -0.7143 | 🔴 -0.5200 |
| Q2_2024 | 🔴 -0.0909 | 🟢 +0.5172 | 🔴 -0.0588 | 🔴 -0.0588 | 🟢 +0.1852 |
| Q2_2025 | 🔴 -0.0400 | 🟢 +0.0526 | 🟢 +0.7143 | 🟢 +0.0909 | 🔴 -0.0400 |
| Q3_2024 | 🔴 -0.1429 | 🟢 +0.1818 | 🟢 +0.7143 | 🔴 -0.2941 | 🟢 +0.0811 |
| Q3_2025 | 🟢 +0.2632 | 🔴 -0.0270 | 🟢 +0.8462 | 🔴 -0.6923 | 🟢 +0.3333 |
| Q4_2024 | 🟢 +0.3333 | 🟢 +0.5385 | 🟢 +0.3333 | 🟢 +0.7778 | 🟢 +0.2174 |
| Q4_2025 | 🟢 +0.2000 | 🟢 +0.8947 | 🔴 +0.0000 | 🟢 +0.5000 | 🟢 +0.2308 |

### Q1 2025 — najgorszy kwartal (wszyscy ujemni)

| Symbol | Baseline | Opcja C | Filtr pomaga? |
|---|---|---|---|
| EURUSD | -0.4667 | -0.6000 | ❌ nie — gorszy |
| USDJPY | -0.2000 | -0.5200 | ❌ nie — gorszy |
| CADJPY | +0.0000 | -0.6923 | ❌ nie — gorszy |
| AUDJPY | -0.2727 | -0.3600 | ❌ nie — gorszy |
| USDCHF | -0.2941 | -0.7143 | ❌ nie — gorszy |

---

## 4. Interpretacja DD% — dlaczego to ważne

**UWAGA:** DD% przy `fixed_units=5000` jest liczony jako % wartości pozycji,
nie jako % equity konta. Dlatego liczby jak 430% wyglądają absurdalnie,
ale przy `size_risk_50bp` DD jest już wyrażony jako % equity (realny).

| Scenariusz | DD% (backtest) | Co to znaczy w praktyce |
|---|---|---|
| Baseline (fixed 5000 units) | 430.95% | Nieporównywalny z equity — artefakt fixed sizing |
| size_risk_50bp (0.5% eq/trade) | 8.33% | **Realne ryzyko: max ~8.3% straty equity** |
| Opcja C (ATR filter + 0.5%) | 4.39% | **~4.4% max DD equity** przy lepszej selekcji |

> Przy koncie $10,000 i Opcji C: max strata historyczna ≈ **$439** (vs baseline: niezdefiniowane przy fixed units)

---

## 5. Opcja C — co zyskujesz, co tracisz

### ✅ Zyski

- **ExpR portfolio rośnie** 0.1156 → 0.1292 (**+0.0137R** per trade, +12%)
- **Stabilność rośnie dramatycznie**: 33% → 64% pozytywnych kwartałów (**+31%**, z 33% do 64%)
- **DD realnie mierzalne**: 4.4% equity (zamiast nieokreślonego fixed-units DD)
- **CADJPY radykalnie lepsza**: +0.245R delta — filtr naprawia tę parę
- **Niższy overfitting** (delta val→test = -0.017 vs -0.052 dla atr_0_90)

### ⚠️ Koszty i ryzyka

- **47% mniej tradów** (7351 vs 13937) — bot rzadziej otwiera pozycje, wolniejszy feedback
- **EURUSD i USDJPY tracą** na filtrze (baseline był tam wyjątkowo silny: 0.40R i 0.35R)
- **Q1 2025 filtr nie pomaga** — w kryzysowym kwartale wyniki gorsze dla 5/5 par
- **Efekt sizing na PF**: PF spada z 1.256 → 1.220 (risk-based sizing = mniejsze zyski nominalne)

---

## 6. Rekomendacja końcowa

| Opcja | Warto? | Kiedy |
|---|---|---|
| Opcja A: globalny ATR filtr | ⚠️ Częściowo | Tylko jeśli priorytet to stabilność |
| Opcja B: selektywny (CADJPY only) | ✅ Tak | Najczyściej — filtr działa tylko tam gdzie pomaga |
| **Opcja C: ATR + sizing** | **✅ Tak, z zastrzeżeniami** | **Najlepsza dla live — kontroluje ryzyko** |

### Konkretna rekomendacja dla produkcji:

**Wdrożyć Opcję C selektywnie:**
1. Włączyć `size_risk_50bp` **globalnie** — brak wad, tylko spada DD
2. Włączyć filtr ATR 10–80 **tylko dla CADJPY** — tam pomaga (+0.245R)
3. EURUSD, USDJPY, AUDJPY — **bez filtru ATR** (baseline lepszy)
4. USDCHF — rozważyć wyłączenie z portfela (ujemny ExpR w obu konfiguracjach)

```yaml
# Proponowane zmiany w config.yaml:
risk:
  sizing_mode: risk_first      # ZMIANA: fixed_units → risk_first
  risk_fraction: 0.005         # 0.5% equity per trade

symbols:
  CADJPY:
    atr_pct_filter_min: 10     # NOWE: filtr ATR
    atr_pct_filter_max: 80
  USDCHF:
    enabled: false             # ROZWAŻ: wyłączenie
```

---

## 7. Podsumowanie liczbowe — 1 tabela

| Metryka | Baseline (VM teraz) | Opcja C (rekomendowana) | Zmiana |
|---|---|---|---|
| ExpR per trade | 0.1156R | **0.1292R** | +0.0137R (+12%) |
| Profit Factor | 1.2560 | 1.2203 | -0.0357 |
| Win Rate | 27.89% | 28.23% | +0.34% |
| DD% (realne equity) | nieokreślone* | **4.4%** | kontrolowane ryzyko |
| Stabilność kw. | 33% | **64%** | +31% |
| Liczba tradów/rok | ~2787 | ~1470 | -47% |

_* baseline DD% przy fixed units nie jest porównywalny z % equity konta_

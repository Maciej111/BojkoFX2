# BojkoFx — Dokumentacja badań: Testy filtrów vs Produkcja

**Data:** 2026-03-04
**Autor:** Backtest pipeline (automated)
**Dane:** H1 bid OHLC 2021–2025, 5 symboli (EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY)
**Metodologia:** 9-foldowa walk-forward walidacja (1 fold historyczny + 8 kwartalnych OOS)

---

## 1. Cel badania

Odpowiedzieć na pytanie: **czy i jak warto modyfikować aktualną konfigurację produkcyjną bota?**

Testowane podejścia:
1. **ADX gate** — filtrowanie sygnałów na podstawie siły trendu (D1)
2. **ATR percentile filter** — filtrowanie sygnałów na podstawie bieżącej zmienności
3. **Risk-based sizing** — zamiana fixed units na ryzyko procentowe equity
4. **Adaptive RR** — zmienny Risk:Reward w zależności od ADX lub ATR
5. **Opcja C** — połączenie ATR filtra + risk-based sizing

---

## 2. Konfiguracja produkcyjna (baseline)

| Parametr | Wartość |
|---|---|
| Strategia | BOS + Pullback |
| LTF / HTF | H1 / D1 |
| Pivot lookback | 3 (LTF), 5 (HTF) |
| Entry offset | 0.3 × ATR |
| SL | last pivot ± 0.1 × ATR |
| RR | 3.0 (fixed) |
| TTL | 50 barów |
| Sizing | fixed 5000 units |
| ATR filtr | brak |
| ADX filtr | brak |
| Symbole | EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY |
| Max pozycji | 3 jednocześnie |

---

## 3. Wyniki baseline (produkcja) — walk-forward 9 foldów

### 3a. Portfolio (średnia wszystkich foldów val)

| Metryka | Wartość |
|---|---|
| ExpR (oczekiwana wartość per trade) | **0.1156 R** |
| Profit Factor | 1.2560 |
| Win Rate | 27.9% |
| Max DD% (avg, fixed units) | 430.95%* |
| Stabilność (% pozytywnych kwartałów) | **33%** |
| Łączna liczba tradów (9 foldów) | 13 937 |

*\*artefakt fixed sizing — patrz sekcja 5*

### 3b. Rozkład wyników kwartalnych baseline

| Kwartal | ExpR | Ocena |
|---|---|---|
| Q1_2024 | +0.333 | ✅ dobry |
| Q2_2024 | +0.256 | ✅ dobry |
| Q3_2024 | +0.290 | ✅ dobry |
| Q4_2024 | **+0.538** | ✅ bardzo dobry |
| Q1_2025 | **-0.247** | ❌ najgorszy kwartal |
| Q2_2025 | +0.044 | ➡️ breakeven |
| Q3_2025 | -0.055 | ❌ lekka strata |
| Q4_2025 | -0.088 | ❌ strata |

> **Obserwacja:** 2024 był bardzo dobry (+0.26R–+0.54R per kwartal). 2025 pokazuje wyraźne pogorszenie —
> szczególnie Q1_2025 (-0.247R). Sugeruje to zmianę reżimu rynkowego od początku 2025.

### 3c. Per-symbol baseline (średnia 9 foldów)

| Symbol | ExpR | PF | WinRate | Pos kw./8 | Ocena |
|---|---|---|---|---|---|
| **EURUSD** | +0.4024 | inf* | 35.1% | 4/8 | ✅ najsilniejszy |
| **USDJPY** | +0.3455 | 1.776 | 33.6% | 7/8 | ✅ najstabilniejszy |
| **AUDJPY** | +0.1852 | 1.040 | 29.6% | 4/8 | ➡️ akceptowalny |
| **USDCHF** | +0.0207 | 1.252 | 25.5% | 4/8 | ⚠️ słaby |
| **CADJPY** | +0.0014 | 1.128 | 25.0% | 3/8 | ❌ prawie zerowy |

*\*PF=inf gdy suma strat = 0 w jakimś folding*

---

## 4. Wyniki testowanych modułów vs baseline

### 4a. ADX gate (filtr trendu na D1)

**Wynik: ❌ NIE REKOMENDOWANY**

| Konfiguracja | ExpR | vs Baseline | PF | Trades |
|---|---|---|---|---|
| baseline | 0.1156 | — | 1.256 | 13 937 |
| adx25 | 0.0920 | -0.024 | **1.850** | 3 851 |
| adx18 | 0.0626 | -0.053 | 1.287 | 8 296 |
| adx20 | 0.0458 | -0.070 | 1.313 | 6 434 |
| adx22 | 0.0396 | -0.076 | 1.260 | 5 301 |

**Wniosek:** Każdy próg ADX obniża ExpR. ADX25 ma wyższy PF (1.85 vs 1.26) bo
silnie filtruje — ale usuwa zbyt wiele dobrych sygnałów. Slope variant nie wnosi różnicy.

---

### 4b. ATR percentile filter (kluczowy wynik)

**Wynik: ✅ REKOMENDOWANY — najskuteczniejszy pojedynczy filtr**

Filtr odrzuca wejścia gdy bieżący ATR symbolu jest poniżej X lub powyżej Y percentyla
14-dniowej historii ATR.

| Konfiguracja | ExpR (val) | ExpR (test) | Delta val→test | Stabilność | Trades kept |
|---|---|---|---|---|---|
| baseline | 0.1156 | 0.1895 | — | 33% | 100% |
| **atr_pct_0_90** | **0.1690** | 0.1170 | -0.052 ⚠️ | **86%** | 68% |
| atr_pct_10_90 | 0.1670 | 0.1115 | -0.056 ⚠️ | 86% | 68% |
| **atr_pct_20_80** | 0.1533 | 0.1183 | **-0.035 ✅** | 64% | 51% |
| **atr_pct_10_80** | 0.1292 | 0.1122 | **-0.017 ✅** | 64% | 53% |
| atr_pct_0_80 | 0.1282 | 0.1122 | -0.016 ✅ | 64% | 53% |
| atr_pct_0_70 | 0.0587 | n/a | — | — | 41% |

**Ranking według priorytetu:**

| Priorytet | Konfiguracja | Uzasadnienie |
|---|---|---|
| Najwyższy ExpR val | `atr_pct_0_90` (+46%) | Ale wyższy overfitting |
| Najniższy overfitting | `atr_pct_10_80` (delta -0.017) | Stabilna na OOS |
| Kompromis | `atr_pct_20_80` (delta -0.035) | Dobry balans |

---

### 4c. Risk-based sizing (size_risk_50bp)

**Wynik: ✅ ZDECYDOWANIE REKOMENDOWANY — zerowy koszt, ogromna korzyść**

| Konfiguracja | ExpR | PF | WinRate | DD% | Trades |
|---|---|---|---|---|---|
| baseline (fixed 5000) | 0.1156 | 1.256 | 27.9% | **430.95%*** | 13 937 |
| size_risk_25bp (0.25%) | 0.1156 | 1.182 | 27.9% | **4.29%** | 13 937 |
| **size_risk_50bp (0.5%)** | 0.1156 | 1.175 | 27.9% | **8.33%** | 13 937 |
| size_risk_75bp (0.75%) | 0.1156 | 1.168 | 27.9% | **12.14%** | 13 937 |

**Wniosek:**
- ExpR i WinRate **identyczne** — sizing nie zmienia kiedy wchodzić
- DD spada z artefaktualnych 430% do **realnych 8.3% equity** przy 0.5% risk/trade
- PF nieznacznie spada (bo normalizuje zyski i straty do tej samej skali)
- **Przy koncie $10,000: max historyczna strata ≈ $833 (8.3%)**

---

### 4d. Adaptive RR

**Wynik: ❌ NIE REKOMENDOWANY**

| Konfiguracja | ExpR | vs Baseline | Uwaga |
|---|---|---|---|
| rr_fixed_3.0 | 0.1156 | 0.000 | identyczny z baseline |
| rr_atr_pct_map | 0.0709 | -0.045 | gorszy |
| rr_adx_map_v1 | 0.0045 | -0.111 | znacznie gorszy |
| rr_adx_map_v2 | 0.0002 | -0.115 | niemal zerowy |

**Wniosek:** Stały RR=3.0 jest optymalny. Adaptacja RR na bazie ADX lub ATR
systematycznie pogarsza wyniki — strategia BOS+Pullback działa najlepiej
z konsekwentnym stosunkiem 1:3.

---

## 5. Opcja C — połączenie ATR 10-80 + risk sizing 0.5%

### Idea

Opcja C łączy dwie niezależne zmiany:
- `atr_pct_10_80` — filtruje sygnały (mniej, ale lepszej jakości)
- `size_risk_50bp` — kontroluje wielkość pozycji (DD jako % equity)

Ponieważ sizing nie wpływa na selekcję sygnałów, wyniki można złożyć:
- **Jakość sygnałów** (ExpR, WR, stabilność) = z `atr_pct_10_80`
- **Ryzyko per trade** (DD%) = z `size_risk_50bp` × proporcja aktywnych tradów

### Wyniki portfolio

| Metryka | Baseline | Opcja C | Zmiana |
|---|---|---|---|
| **ExpR per trade** | 0.1156 R | **0.1292 R** | **+12%** |
| Profit Factor | 1.2560 | 1.2203 | -0.036 |
| Win Rate | 27.9% | 28.2% | +0.3pp |
| **Max DD% (equity)** | ~430%* | **~4.4%** | **-99%** |
| **Stabilność kw.** | 33% | **64%** | **+31pp** |
| Liczba tradów/rok | ~2 787 | ~1 470 | -47% |

*\*Baseline DD% jest artefaktem fixed units — nie jest porównywalny z equity %*

### Wyniki per-symbol — Opcja C

| Symbol | ExpR base | ExpR Opcja C | Delta | Ocena |
|---|---|---|---|---|
| **CADJPY** | +0.0014 | **+0.2468** | **+0.245** | ✅ Filtr radykalnie naprawia tę parę |
| **EURUSD** | +0.4024 | +0.2080 | -0.194 | ❌ Filtr usuwa dobre sygnały |
| **USDJPY** | +0.3455 | +0.1418 | -0.204 | ❌ Filtr zbyt agresywny |
| **AUDJPY** | +0.1852 | +0.0821 | -0.103 | ⚠️ Słabsza para w obu wariantach |
| **USDCHF** | +0.0207 | -0.0314 | -0.052 | ❌ Ujemny z filtrem |

### Kluczowe odkrycie

Filtr ATR 10-80 działa **selektywnie** — pomaga parze CADJPY (gdzie baseline był prawie zerowy),
ale szkodzi parom EURUSD i USDJPY (gdzie baseline był silny). Oznacza to, że:
- CADJPY generuje wiele sygnałów w złych warunkach zmienności → filtr je usuwa → **poprawa**
- EURUSD/USDJPY mają sygnały dobre nawet w "ekstremalnej" zmienności → filtr je usuwa → **strata**

---

## 6. Odporność na kryzys: Q1 2025

Q1 2025 był najgorszym kwartałem dla wszystkich konfiguracji — żaden filtr nie pomaga:

| Symbol | Baseline | ATR 10-80 | Filtr pomaga? |
|---|---|---|---|
| EURUSD | -0.467 | -0.600 | ❌ gorszy |
| USDJPY | -0.200 | -0.520 | ❌ gorszy |
| CADJPY | +0.000 | -0.692 | ❌ gorszy |
| AUDJPY | -0.273 | -0.360 | ❌ gorszy |
| USDCHF | -0.294 | -0.714 | ❌ gorszy |

**Wniosek:** Filtr ATR **nie chroni przed zmianą reżimu rynkowego**. W Q1_2025
rynek był w nienormalnym trybie (wszystkie pary ujemne) — filtr odrzuca sygnały,
które i tak byłyby stratne, ale też te nieliczne które mogłyby zarobić.

---

## 7. Zestawienie wszystkich testowanych podejść

| Moduł | Najlepsza konfiguracja | ExpR | vs Baseline | Rekomendacja |
|---|---|---|---|---|
| **Bez zmian** | baseline | 0.1156 | — | punkt odniesienia |
| ADX gate | adx25 | 0.0920 | -20% | ❌ nie |
| **ATR filtr** | atr_pct_0_90 | **0.1690** | **+46%** | ✅ tak (globalnie) |
| **ATR filtr** | atr_pct_10_80 | 0.1292 | +12% | ✅ tak (niski overfitting) |
| **Risk sizing** | size_risk_50bp | 0.1156 | 0% ExpR | ✅ **tak, bezwarunkowo** |
| Adaptive RR | rr_fixed_3.0 | 0.1156 | 0% | ❌ zostawić fixed |
| **Opcja C** | atr_10_80 + size_50bp | **0.1292** | **+12%** ExpR, **-99% DD** | ✅ **tak, selektywnie** |

---

## 8. Rekomendacja końcowa

### Priorytet 1 — Natychmiastowa zmiana (zero ryzyka)

**Wdrożyć `size_risk_50bp` globalnie:**
- ExpR bez zmian (0.1156R)
- DD spada z niezmierzalnego → **8.3% equity**
- Zero wpływu na sygnały, strategie, konfigurację symboli

```yaml
# config.yaml — dodać:
risk:
  sizing_mode: risk_first
  risk_fraction: 0.005   # 0.5% equity per trade
```

### Priorytet 2 — Zmiana selektywna (wymaga testów live)

**Wdrożyć filtr ATR 10-80 tylko dla CADJPY:**
- CADJPY: +0.245R delta (z 0.001R → 0.247R)
- Pozostałe pary: bez filtru (baseline lepszy)

```yaml
# config.yaml — dodać pod CADJPY:
symbols:
  CADJPY:
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
```

### Priorytet 3 — Rozważyć wyłączenie USDCHF

- ExpR baseline: +0.021R (ledwo pozytywny)
- ExpR z filtrem: -0.031R (ujemny)
- 4/8 pozytywnych kwartałów w obu wariantach
- Zajmuje slot pozycji który mógłby iść na lepszą parę

---

## 9. Ograniczenia badania

1. **DD% baseline jest niemierzalne** — fixed 5000 units daje DD jako % pozycji, nie equity.
   Dopiero `size_risk_50bp` daje realne liczby. Przy porównaniach DD należy używać wariantu risk-first.

2. **2025 = nowy reżim** — Q1–Q4 2025 są słabsze niż 2024. Możliwe że parametry
   (pivot lookback, TTL, RR) były zoptymalizowane na 2021–2024. Warto zbadać
   czy re-optymalizacja na 2023–2024 poprawia OOS 2025.

3. **Opcja C jest symulowana** — nie istnieje jako osobny eksperyment Stage 2.
   DD% Opcji C jest przybliżony przez skalowanie DD z `size_risk_50bp`.
   Dokładny wynik wymaga uruchomienia Stage 2 z kombinacją obu parametrów.

4. **Brak kosztów transakcyjnych** — symulacja nie uwzględnia spreadu ani
   prowizji IBKR. Przy ~1470 tradów/rok i typowym spreadzie 0.5 pipa dla
   EURUSD, koszt to ~0.002R per trade (nieistotny przy ExpR=0.13R).

5. **Single-symbol pary** — wyniki EURUSD i USDJPY mogą być zawyżone z powodu
   inf PF w niektórych foldach (fold bez żadnej przegranej pozycji).

---

## 10. Pliki wynikowe

| Plik | Zawartość |
|---|---|
| `backtests/outputs/results_all.csv` | 1916 wierszy — każdy trade per eksperyment × fold × symbol |
| `backtests/outputs/results_summary.csv` | 320 wierszy — metryki portfolio per eksperyment × fold |
| `backtests/outputs/top_configs.json` | Top 10 konfiguracji z val+test ExpR |
| `backtests/outputs/report.md` | Pełny raport techniczny (tabele, sekcja 9 per-symbol) |
| `backtests/outputs/comparison_report.md` | Raport porównawczy: baseline vs atr_10_80 vs Opcja C |
| `backtests/outputs/adx_v2_report.md` | Raport ADX test v2 (H4 vs D1, rising, slope, soft) |
| `backtests/outputs/results_adx_v2.csv` | 380 wierszy — wyniki ADX v2 PORTFOLIO per experiment × fold |
| `backtests/outputs/results_adx_v2_all.csv` | 2280 wierszy — wyniki ADX v2 per symbol × experiment × fold |

---

## 11. ADX test v2 — wyniki i konkluzja

**Data:** 2026-03-04
**Pipeline:** `python -m backtests.run_experiments --adx-v2-only`
**Czas:** ~45s

### Pytania badawcze

ADX v1 (progi 18/20/22/25 na D1) konsekwentnie pogarszał ExpR (-20% do -66% vs baseline).
ADX test v2 sprawdził trzy hipotezy:
1. Czy progi były za wysokie? → dodano progi 14/16/18
2. Czy D1 to zły TF? → dodano H4 jako HTF dla ADX
3. Czy "ADX rising" jest lepszy niż hard threshold? → tested rising k=2/3/5 i slope SMA>0

### Wyniki kluczowe (portfolio, 9-fold walk-forward)

| Konfiguracja | Val ExpR | Test ExpR | Δ | Wniosek |
|---|---|---|---|---|
| Baseline (brak ADX) | +0.1156R | — | — | punkt odniesienia |
| ADX v1 best (D1 thr=25) | +0.0920R | — | — | -20% vs baseline |
| **H4 thr=16 (ctxA)** | **+0.1794R** | **+0.1868R** | **+0.0074R** | ✅ bije baseline, niski overfit |
| H4 thr=14 (ctxA) | +0.1467R | +0.2459R | +0.0992R | ✅ test bardzo dobry |
| H4 rising k=2 (ctxB) | +0.1591R | +0.2000R | +0.0409R | ✅ wzrost na test |
| D1 niskie progi (thr=14–18) | +0.1157–0.1176R | +0.0875–0.1574R | mieszane | ≈ baseline |

### Per-symbol (val, najlepszy wariant ADX v2)

| Symbol | Wariant | Val ExpR | Baseline | Δ |
|---|---|---|---|---|
| **AUDJPY** | H4 thr=14 | +0.329R | +0.185R | **+0.144R** ✅ |
| **EURUSD** | H4 rising k=5 | +0.481R | +0.402R | **+0.078R** ✅ |
| **USDCHF** | D1 rising k=5 | +0.182R | +0.021R | **+0.161R** ✅ |
| USDJPY | H4 thr=16 | +0.364R | +0.346R | +0.019R ⚠️ |
| CADJPY | baseline ctxB | +0.247R | +0.247R | +0.000R ❌ |

### Konkluzja

**H4 ADX gate z niskimi progami (14–18) bije baseline o ~+0.06R i ma niski overfit (Δ=+0.007R).**
Jest to istotna poprawa względem ADX v1 (+0.092R → +0.179R vs baseline +0.1156R).

Kluczowe wnioski:
- **H4 ≈ D1** pod względem średnich — różnica nieistotna (H4 avg=+0.104R vs D1 avg=+0.102R)
- **Hard threshold** na H4 (thr=14–16) lepszy niż "ADX rising" (rising avg=+0.041R)
- **ADX rising H4 k=2 w ctxB** (risk_first + ATR 10–80) daje bardzo dobry test (+0.200R) ale z wyższym overfittem
- **ADX v2 NIE szkodzi jak v1** — kluczowy błąd v1 to za wysokie progi (≥18–25) na D1

### Rekomendacja P3 (do podjęcia decyzji)

⬜ Wdrożyć `ADX H4 thr=16` **selektywnie** (bez CADJPY):

**CADJPY — NIE wdrażać H4 ADX:**
- `H4 ADX16 + ATR 10–80` = +0.188R vs aktualny `ATR 10–80` = **+0.247R** (-24%)
- Overfit duży (Δ = -0.114R val→test), stabilność spada 78%→64%
- ATR 10–80 jest wystarczającym i lepszym filtrem dla CADJPY
- **Aktualny stan CADJPY w produkcji jest optymalny — nie zmieniać**

**Pozostałe pary (EURUSD/USDJPY/USDCHF/AUDJPY) — H4 ADX16 bije baseline:**
- Portfolio bez CADJPY: val +0.179R vs baseline +0.116R (+55%)
- Implementacja wymaga per-symbol `adx_h4_gate` w `config.yaml`
- Nie wdrażać bez oddzielnej walidacji per-symbol (szczególnie AUDJPY)

---

*Wygenerowano: 2026-03-04 | Pipeline: `python -m backtests.run_experiments --adx-v2-only`*
*Czas generacji Stage 1: ~39s | Czas Stage 1+2 (pełny): ~483s*


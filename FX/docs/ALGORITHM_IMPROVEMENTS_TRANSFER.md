# BojkoFx — Transfer wiedzy: ulepszenia algorytmu BOS+Pullback (2026-03-04)

Dokument przeznaczony dla innego AI/projektu korzystającego z podobnej strategii
trendowej (Break-of-Structure + Pullback na rynku FX).

---

## Strategia bazowa (punkt wyjścia)

**Typ:** BOS + Pullback na parach FX
**LTF:** H1 (sygnały), **HTF:** D1 (kontekst trendu)
**Pivot lookback:** 3 bary (LTF), 5 barów (HTF)
**Entry:** limit przy BOS level ± 0.3 × ATR(14)
**SL:** last pivot opposite ± 0.1 × ATR(14)
**TP:** entry ± RR × |entry − SL|, gdzie RR = 3.0 (fixed)
**TTL:** 50 barów H1 (zlecenie wygasa jeśli nie wypełnione)
**Max pozycji:** 3 jednocześnie (portfolio constraint)
**Dane testowe:** H1 bid OHLC 2021–2025, 5 par FX: EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY
**Metodologia walidacji:** 9-fold walk-forward (1 historyczny + 8 kwartalnych OOS 2024–2025)

**Wyniki baseline (przed ulepszeniami):**

| Metryka | Wartość |
|---|---|
| ExpR (oczekiwana wartość per trade) | +0.116R |
| Profit Factor | 1.26 |
| Win Rate | 27.9% |
| Stabilność (% kw. pozytywnych) | 33% |
| Max DD% | ~430%* |

*\* artefakt fixed sizing — nie jest DD equity, patrz niżej*

---

## Ulepszenie 1 — Risk-based position sizing ✅ WDROŻONE

### Problem
Fixed units (np. 5000 FX units stałe) powoduje, że ryzyko jest inne dla każdego
zlecenia — zależy od odległości SL. Przy szerokim SL ryzyko jest wielokrotnie większe.
Zmierzony DD% w backteście (430%) był artefaktem tego mechanizmu, nie realnym ryzykiem equity.

### Rozwiązanie
Zamiana fixed units na **risk-first sizing**: pozycja dobierana tak, żeby ryzyko
każdego zlecenia wynosiło stały % equity.

```
units = (equity × risk_pct) / |entry_price − sl_price|
```

### Wyniki backtestów (9-fold walk-forward)

| Konfiguracja | ExpR | Max DD% equity | Zmiana vs baseline |
|---|---|---|---|
| Fixed 5000 units (stare) | +0.116R | ~430%* (artefakt) | — |
| risk_first 0.25% equity | +0.116R | **4.3%** | ExpR bez zmian |
| **risk_first 0.5% equity** | **+0.116R** | **8.3%** | **ExpR bez zmian** |
| risk_first 0.75% equity | +0.116R | 12.1% | ExpR bez zmian |

**Wniosek:** ExpR i WinRate są **identyczne** — sizing nie wpływa na selekcję sygnałów.
Jedyna zmiana to realne, mierzalne ryzyko. Wdrożono 0.5% equity per trade.

### Implementacja
```yaml
risk:
  sizing_mode: risk_first
  risk_fraction_start: 0.005   # 0.5% equity per trade
```

---

## Ulepszenie 2 — ATR percentile filter (per-symbol, selektywny) ✅ WDROŻONE

### Problem
CADJPY miał prawie zerowy ExpR (+0.001R). Analiza pokazała, że wiele sygnałów
generowanych jest przy złych warunkach zmienności (zbyt niska konsolidacja
lub zbyt wysoki spike).

### Rozwiązanie
Filtr odrzuca sygnały gdy bieżący ATR(14) wypada poza określonym przedziałem
percentylowym 100-barowej historii ATR symbolu.

```
ATR(14)_current = rolling mean (high − low), okno 14 barów
window          = ostatnie 100 wartości ATR (bez NaN)
pct_val         = % wartości w window < ATR_current  (zakres 0–100)

jeśli pct_val < min_pct  → zmienność za niska (konsolidacja) → skip
jeśli pct_val > max_pct  → zmienność za wysoka (spike)       → skip
min_pct ≤ pct_val ≤ max_pct → normalna zmienność             → kontynuuj
```

### Wyniki per-symbol (konfiguracja 10–80)

| Symbol | ExpR baseline | ExpR z filtrem 10–80 | Delta |
|---|---|---|---|
| **CADJPY** | +0.001R | **+0.247R** | **+0.245R ✅** |
| EURUSD | +0.402R | +0.208R | -0.194R ❌ |
| USDJPY | +0.346R | +0.142R | -0.204R ❌ |
| USDCHF | +0.021R | -0.031R | -0.052R ❌ |

**Kluczowe odkrycie:** Filtr ATR jest **silnie selektywny** — pomaga parom ze słabym
baseline (CADJPY: sygnały w złych warunkach), ale szkodzi parom mocnym (EURUSD/USDJPY:
dobre sygnały nawet przy "ekstremalnej" zmienności).

**Wdrożono tylko dla CADJPY** (zakres 10–80, najniższy overfit Δ=−0.017R).

### Implementacja
```yaml
symbols:
  CADJPY:
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
  # Pozostałe pary: brak pól → filtr wyłączony
```

---

## Ulepszenie 3 — H4 ADX gate (per-symbol, selektywny) ✅ WDROŻONE

### Problem
ADX v1 (D1, progi 18–25) konsekwentnie pogarszał ExpR portfolio o −20% do −66%.
Hipoteza: progi były za wysokie i D1 to zły timeframe dla tej strategii (LTF=H1).

### Badanie ADX v2 (38 eksperymentów, 9-fold WFV)
Przetestowano:
- **ADX na H4** (zamiast D1) z progami 14/16/18/20/22
- **ADX na D1** z niższymi progami 14/16/18
- **ADX rising** (ADX_now > ADX_prev_k, k=2/3/5) zamiast hard threshold
- **ADX slope SMA>0** (ADX rośnie przez ostatnie 5 barów)
- **ADX soft gate** (obniż RR zamiast blokować sygnał gdy ADX niski)

### Wyniki kluczowe (portfolio, 9-fold walk-forward)

| Konfiguracja | Val ExpR | Test ExpR | Δ val→test | vs baseline |
|---|---|---|---|---|
| Baseline (brak ADX) | +0.116R | — | — | — |
| ADX v1 D1 thr=25 | +0.092R | — | — | **−20%** ❌ |
| ADX v1 D1 thr=18 | +0.063R | — | — | **−46%** ❌ |
| **H4 thr=16** | **+0.179R** | **+0.187R** | **+0.007R** | **+55% ✅** |
| H4 thr=14 | +0.147R | +0.246R | +0.099R | +27% ✅ |
| H4 thr=18 | +0.121R | +0.194R | +0.072R | +5% ✅ |
| H4 rising k=2 | +0.091R | +0.180R | +0.090R | marginalne ⚠️ |
| D1 thr=14/16/18 | +0.116–0.118R | mieszane | mieszane | ≈ baseline |

**Główny wniosek:** Błędem ADX v1 były **za wysokie progi na D1**.
H4 thr=14–16 poprawia ExpR o +55% z minimalnym overfittem (Δ=+0.007R).

### Ważne: per-symbol analiza CADJPY

Dla CADJPY, który ma już filtr ATR 10–80:

| Konfiguracja | Val ExpR | Wniosek |
|---|---|---|
| ATR 10–80 only *(produkcja)* | **+0.247R** | najlepszy |
| H4 ADX16 + ATR 10–80 | +0.188R | **−24% ❌** |
| H4 ADX16 only | +0.142R | −43% ❌ |

**Podwójne filtrowanie niszczy CADJPY.** ATR filtr jest wystarczający i lepszy.
Wdrożono H4 ADX thr=16 tylko dla EURUSD/USDJPY/USDCHF/AUDJPY.

### Implementacja
```yaml
symbols:
  EURUSD:
    adx_h4_gate: 16
  USDJPY:
    adx_h4_gate: 16
  USDCHF:
    adx_h4_gate: 16
  AUDJPY:
    adx_h4_gate: 16
  CADJPY:
    # adx_h4_gate: brak — ATR filtr wystarczy
    atr_pct_filter_min: 10
    atr_pct_filter_max: 80
```

Implementacja ADX w runnerze (no-lookahead, Wilder smoothing):
```python
# H4 = resample H1 → 4h, tylko bary zamknięte przed bar_ts
h4 = h1.resample("4h").agg({...}).dropna()
h4 = h4[h4.index < pd.Timestamp(bar_ts).floor("4h")]
# ADX(14) Wildera
# ... standard DM+/DM−/TR/ATR14 → PDI/MDI → DX → ADX
adx_val = float(adx_h4.iloc[-1])
if adx_val < adx_h4_gate:
    skip()  # trend zbyt słaby
```

---

## Ulepszenia odrzucone (nie wdrożono)

### Adaptive RR ❌
Testowano mapowanie ADX→RR i ATR_pct→RR. Każda adaptacja pogarszała ExpR:
- rr_adx_map_v1: ExpR ≈ 0.005R (prawie zerowy)
- rr_atr_pct_map: ExpR = +0.071R (−39% vs baseline)
- **Wniosek: stały RR=3.0 jest optymalny dla tej strategii.**

### ATR filtr globalnie ❌
ATR 10–80 globalnie (wszystkie pary) = +0.129R (val), ale −0.017R overfit i −47% tradów.
Selektywnie tylko dla CADJPY = lepszy wynik przy mniejszym koszcie.

### ADX gate D1 (jakikolwiek próg) ❌
Każdy próg ADX na D1 pogarsza ExpR. Mechanizm: BOS na H1 często pojawia się
podczas formowania trendu (niski ADX → rosnący) — D1 ADX gate blokuje właśnie
te wejścia, które są najlepsze.

---

## Stan po wszystkich ulepszeniach

| Metryka | Baseline (przed) | Po ulepszeniach |
|---|---|---|
| ExpR portfolio | +0.116R | **+0.179R** (+55%) |
| Max DD% equity | ~430%* (artefakt) | **~8.3%** (realne) |
| Stabilność kw. | 33% | **~61%** |
| CADJPY ExpR | +0.001R | **+0.247R** |
| EURUSD ExpR | +0.402R | **+0.481R** (H4 ADX) |

---

## Wnioski ogólne — przenośne na podobne projekty

1. **Risk sizing to najprostsza i bezpłatna poprawa.** Zamiana fixed units
   na % equity nie zmienia ExpR, WR ani selekcji sygnałów — jedynie normalizuje
   ryzyko do mierzalnego poziomu DD.

2. **Filtry działają selektywnie, nie globalnie.** Ten sam filtr ATR naprawia
   jedną parę i niszczy inną. Przed wdrożeniem globalnym zawsze testuj per-symbol.

3. **Podwójne filtrowanie nie sumuje korzyści.** ATR + ADX dla CADJPY daje
   gorszy wynik niż samo ATR. Każdy dodatkowy filtr zmniejsza liczbę sygnałów —
   powyżej pewnego progu tracisz dobre sygnały, nie złe.

4. **ADX na zbyt wysokim TF (D1 dla strategii H1) blokuje dobre wejścia.**
   BOS pojawia się często gdy trend się formuje (niski ADX rosnący) — D1 ADX
   jest wtedy niski i blokuje sygnał. H4 z niskim progiem (14–16) działa lepiej
   bo reaguje szybciej na lokalne zmiany siły trendu.

5. **Fixed RR=3.0 jest trudny do pobicia adaptacją.** Strategia BOS+Pullback
   ma asymetrię wygranej wbudowaną w BOS — adaptacja RR to próba "poprawienia"
   czegoś co już działa. Warto to testować, ale nie zakładać że pomoże.

6. **Walk-forward na kwartałach ujawnia zmianę reżimu.** Q1 2025 był ujemny
   dla wszystkich par i wszystkich filtrów — żaden filtr nie chroni przed
   makro-zmianą reżimu. To sygnał do monitorowania i ewentualnej re-optymalizacji.

---

## Pliki źródłowe (dla referencji)

| Plik | Zawartość |
|---|---|
| `backtests/outputs/RESEARCH_SUMMARY.md` | Pełna dokumentacja badań Stage 1+2 |
| `backtests/outputs/adx_v2_report.md` | Szczegółowy raport ADX v2 (H4 vs D1, per-symbol) |
| `backtests/outputs/USDCHF_P4_ANALYSIS.md` | Analiza USDCHF: ATR filtr szkodzi, status quo |
| `backtests/outputs/report.md` | Surowe wyniki wszystkich eksperymentów |
| `config/config.yaml` | Aktualna konfiguracja produkcyjna z wszystkimi filtrami |
| `src/core/config.py` | Definicja SymbolConfig (adx_h4_gate, atr_pct_filter_*) |
| `src/runners/run_paper_ibkr_gateway.py` | Implementacja filtrów w pętli głównej |


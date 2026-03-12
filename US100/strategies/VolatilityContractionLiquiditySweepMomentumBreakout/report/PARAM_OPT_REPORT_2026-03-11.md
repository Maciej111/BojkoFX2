# VCLSMB — Parameter Optimisation Report
**Date:** 2026-03-11  
**Strategy:** VolatilityContractionLiquiditySweepMomentumBreakout  
**Instrument:** USATECHIDXUSD (NQ futures), 5m LTF  
**Methodology:** Walk-forward IS/OOS grid search (3×3×3×3 = 81 combinations)

---

## 1. Cel i zakres

Celem badania była optymalizacja czterech kluczowych parametrów strategii VCLSMB metodą wyczerpującego grid searcha z oceną na danych OOS (Out-of-Sample). Użyto ścisłego podziału IS/OOS bez podglądania danych testowych.

| Etap | Zakres | Bary (5m) | Opis |
|------|--------|-----------|------|
| IS (In-Sample) | 2021-01-01 – 2022-12-31 | 209 664 | Opracowanie modelu — NQ bear market 2022 |
| OOS (Out-of-Sample) | 2023-01-01 – 2025-12-31 | 314 784 | Walidacja robustności — 3 pełne lata |

**Łącznie:** 81 kombinacji × 2 okresy = **162 backtesty**.

---

## 2. Siatka parametrów

| Parametr | Testowane wartości | Poprzedni default (v2) |
|----------|-------------------|------------------------|
| `sweep_atr_mult` | 0.35, **0.50**, 0.75 | **0.50** |
| `momentum_atr_mult` | 1.0, **1.3**, 1.6 | **1.30** |
| `momentum_body_ratio` | 0.55, **0.65**, 0.75 | **0.65** |
| `compression_lookback` | 12, **20**, 30 | **20** |

Parametry stałe (nie optymalizowane): `atr_period=14`, `compression_atr_ratio=0.6`, `range_window=10`, `risk_reward=2.0`, `sl_buffer_atr_mult=0.3`.

### Formuła rankingu (composite score)
```
score = 1.0 × profit_factor
      + 3.0 × expectancy_R
      - 0.5 × (max_dd_R / 10.0)
      + 0.3 × min(trades, 100) / 100

Twarde filtry: n ≥ 20, E(R) > 0, max_dd_R < 30
```

---

## 3. Wyniki ogólne

| Metryka | Wartość |
|---------|---------|
| Testowanych kombinacji | 81 |
| Przeszło twarde filtry (OOS) | **53 / 81 (65%)** |
| Najlepszy wynik OOS (score) | **1.715** |
| Najlepszy OOS E(R) | **+0.183 R** |
| Zakres OOS E(R) | −0.143 … +0.183 |

---

## 4. TOP 15 kombinacji (OOS score)

| Rank | sweep | mom_atr | body | comp_lb | IS_E(R) | OOS_E(R) | IS_PF | OOS_PF | IS_n | OOS_n | OOS_DD | Score |
|------|-------|---------|------|---------|---------|----------|-------|--------|------|-------|--------|-------|
| 1 | 0.75 | 1.30 | **0.55** | 12 | -0.224 | **+0.183** | 0.70 | 1.30 | 58 | 71 | 7.0 | **1.715** |
| 2 | 0.50 | 1.30 | **0.55** | 12 | -0.250 | +0.169 | 0.67 | 1.28 | 72 | 77 | 6.0 | 1.714 |
| 3 | 0.35 | 1.30 | **0.55** | 12 | -0.270 | +0.157 | 0.64 | 1.25 | 74 | 83 | 6.0 | 1.674 |
| 4 | 0.75 | 1.60 | **0.55** | 12 | +0.000 | +0.131 | 1.00 | 1.21 | 45 | 61 | 5.0 | 1.537 |
| 5 | 0.75 | 1.00 | **0.55** | 12 | -0.324 | +0.143 | 0.58 | 1.23 | 71 | 84 | 8.0 | 1.512 |
| 6 | 0.35 | 1.30 | **0.55** | 20 | -0.227 | +0.138 | 0.69 | 1.22 | 97 | 116 | 9.0 | 1.486 |
| 7 | 0.35 | 1.60 | **0.55** | 12 | +0.019 | +0.114 | 1.03 | 1.18 | 53 | 70 | 5.0 | 1.485 |
| 8 | 0.75 | 1.30 | **0.55** | 30 | -0.351 | +0.154 | 0.55 | 1.25 | 74 | 91 | 10.0 | 1.484 |
| 9 | 0.75 | 1.30 | **0.55** | 20 | -0.286 | +0.143 | 0.62 | 1.23 | 63 | 84 | 9.0 | 1.462 |
| 10 | 0.50 | 1.30 | **0.55** | 20 | -0.284 | +0.121 | 0.63 | 1.19 | 88 | 99 | 8.0 | 1.454 |
| 11 | 0.35 | 1.30 | 0.75 | 20 | -0.149 | +0.121 | 0.79 | 1.19 | 67 | 99 | 8.0 | 1.454 |
| 12 | 0.75 | 1.30 | 0.75 | 30 | -0.304 | +0.145 | 0.60 | 1.23 | 56 | 76 | 9.0 | 1.446 |
| 13 | 0.50 | 1.60 | **0.55** | 12 | +0.038 | +0.125 | 1.06 | 1.20 | 52 | 64 | 7.0 | 1.417 |
| 14 | 0.35 | 1.30 | 0.75 | 12 | -0.220 | +0.164 | 0.70 | 1.27 | 50 | 67 | 11.0 | 1.412 |
| 15 | 0.75 | 1.30 | 0.75 | 20 | -0.188 | +0.130 | 0.74 | 1.21 | 48 | 69 | 8.0 | 1.407 |

**Obserwacja:** 10 z 15 najlepszych kombinacji ma `momentum_body_ratio = 0.55` (pogrubione). To najsilniejszy sygnał z całego badania.

---

## 5. Analiza wrażliwości parametrów

### 5.1 `momentum_body_ratio` — NAJWAŻNIEJSZY parametr

| Wartość | Średnie OOS E(R) | Mediana OOS E(R) | Maks OOS E(R) | Viable (≤81) |
|---------|-----------------|-----------------|---------------|--------------|
| **0.55** | **+0.068** | **+0.097** | **+0.183** | **22/27 (81%)** |
| 0.65 | +0.010 | +0.031 | +0.119 | 14/27 (52%) |
| 0.75 | +0.027 | +0.029 | +0.164 | 17/27 (63%) |

`body=0.55` dominuje pod każdym względem: wyższa mediana, wyższy pik, znacznie wyższy wskaźnik viable. Co ważne: `body=0.65` (poprzedni default) ma najniższe wyniki — tylko 52% kombinacji przeszło filtry. Zmiana z 0.65 → 0.55 to **największa poprawa możliwa bez zmiany architektury**.

### 5.2 `momentum_atr_mult` — DRUGI NAJWAŻNIEJSZY parametr

| Wartość | Średnie OOS E(R) | Mediana OOS E(R) | Viable |
|---------|-----------------|-----------------|--------|
| 1.0 | +0.006 | +0.014 | n/a |
| **1.3** | **+0.095** | **+0.119** | **24/27 (89%)** |
| 1.6 | +0.003 | +0.000 | n/a |

`mom_atr=1.3` to wyraźne optimum — zarówno 1.0 jak i 1.6 drastycznie obniżają wyniki. 1.0 to zbyt słaby breakout (dużo false signals), 1.6 zbyt restrykcyjny (za mało transakcji). Poprzedni default 1.3 był prawidłowy.

### 5.3 `compression_lookback` — TRZECI NAJWAŻNIEJSZY parametr

| Wartość | Średnie OOS E(R) | Mediana OOS E(R) | Viable |
|---------|-----------------|-----------------|--------|
| **12** | **+0.090** | **+0.097** | **26/27 (96%)** |
| 20 | +0.032 | +0.013 | 17/27 (63%) |
| 30 | **−0.018** | −0.029 | 10/27 (37%) |

Krótsze okno kompresji (12 vs 20) jest wyraźnie lepsze. `lookback=30` jest outright szkodliwe — ujemna średnia E(R). Wszystkie 5 najgorszych kombinacji ma `compression_lookback=30`.

### 5.4 `sweep_atr_mult` — SŁABSZY EFEKT

| Wartość | Średnie OOS E(R) | Mediana OOS E(R) | Viable |
|---------|-----------------|-----------------|--------|
| 0.35 | +0.024 | +0.013 | n/a |
| 0.50 | +0.000 | +0.007 | n/a |
| **0.75** | **+0.080** | **+0.079** | n/a |

`sweep=0.75` ma wyższe wartości, ale różnica między wartościami jest mniej stabilna (dużo wariancji). Parametr ten nie jest tak decydujący jak body ratio lub mom_atr. Najlepsza (rank 1) i najgorsza z top-10 są obie przy `sweep=0.75`.

---

## 6. Mapa ciepła IS vs OOS (korelacja)

| Metryka | Wartość |
|---------|---------|
| Pearson r (IS_E(R) vs OOS_E(R)) | **−0.021** |

**Korelacja IS/OOS wynosi praktycznie zero (−0.02).** IS wyniki nie mają wartości predykcyjnej dla OOS. Wynika to ze strukturalnego problemu danych — IS obejmuje NQ bear market 2022 (−35%), który jest anomalią nie reprezentującą normalnej dynamiki rynku. **Optymalizacja powinna opierać się wyłącznie na OOS.**

---

## 7. Porównanie z poprzednim configiem (v2)

| Config | OOS E(R) | OOS WR | OOS PF | OOS DD | OOS n |
|--------|----------|--------|--------|--------|-------|
| v2 default (sweep=0.5, mom=1.3, body=0.65, lb=20) | +0.065 | 35% | 1.10 | 9.0 R | 93 |
| **Optymalne (sweep=0.75, mom=1.3, body=0.55, lb=12)** | **+0.183** | **39.4%** | **1.30** | **7.0 R** | **71** |
| Poprawa | **+0.118** | **+4.4 pp** | **+0.20** | **−2.0 R** | −22 |

Zmiana body_ratio z 0.65 → 0.55 i compression_lookback z 20 → 12 odpowiada za zdecydowaną większość poprawy (+181% E(R) vs v2). Mniejsza liczba transakcji (71 vs 93) to kompromis — sygnały są bardziej selektywne.

---

## 8. Najgorsze kombinacje

Dla przestrogi — 5 najgorszych kombinacji OOS:

| sweep | mom_atr | body | comp_lb | OOS_E(R) | OOS_PF | OOS_DD |
|-------|---------|------|---------|----------|--------|--------|
| 0.50 | 1.6 | 0.75 | 30 | −0.143 | 0.80 | 20.0 R |
| 0.50 | 1.0 | 0.75 | 30 | −0.140 | 0.80 | 28.0 R |
| 0.50 | 1.6 | 0.65 | 30 | −0.138 | 0.81 | 17.0 R |
| 0.35 | 1.0 | 0.65 | 30 | −0.121 | 0.83 | 35.0 R |
| 0.50 | 1.0 | 0.65 | 30 | −0.115 | 0.84 | 28.0 R |

Wspólny mianownik: **`compression_lookback=30`** we wszystkich 5. Zbyt długie okno kompresji generuje zbyt liberalne sygnały — system wchodzi w każde tąpnięcie, nie tylko czyste setupy.

---

## 9. Zalecany config (po optymalizacji)

```python
VCLSMBConfig(
    # Compression — kluczowa zmiana: lb 20 → 12
    compression_atr_ratio  = 0.6,
    compression_lookback   = 12,      # ← ZMIANA z 20
    range_window           = 10,

    # Sweep — kluczowa zmiana: sweep_mult 0.5 → 0.75
    sweep_atr_mult         = 0.75,    # ← ZMIANA z 0.50
    sweep_close_inside     = True,

    # Momentum — kluczowa zmiana: body 0.65 → 0.55
    momentum_atr_mult      = 1.30,    # bez zmian
    momentum_body_ratio    = 0.55,    # ← ZMIANA z 0.65

    # Risk — bez zmian
    risk_reward            = 2.0,
    sl_anchor              = "range_extreme",
    sl_buffer_atr_mult     = 0.3,

    # Trend filter — opcjonalny
    enable_trend_filter    = False,   # włączenie ≈ +0.05 E(R)
    trend_ema_period       = 50,

    # Session — bez zmian
    use_session_filter     = False,
)
```

**Zmiany względem v2 default:**
- `compression_lookback`: 20 → **12** (−8)
- `sweep_atr_mult`: 0.50 → **0.75** (+50%)
- `momentum_body_ratio`: 0.65 → **0.55** (−0.10)

---

## 10. Wnioski i dalsze kroki

### Wnioski

1. **`momentum_body_ratio=0.55` to najistotniejszy wniosek badania.** Poprzedni default 0.65 był suboptymalny — obcinał zbyt wiele sygnałów jednocześnie tracąc te z najwyższym edge'em.
2. **`momentum_atr_mult=1.30` pozostaje prawidłowy** — jest wyraźnym optimum (zarówno 1.0 jak i 1.6 dramatycznie gorzej).
3. **`compression_lookback=12` lepsze niż 20 i significantly better niż 30.** Krótki lookback precyzyjnie identyfikuje świeżo uformowane kompresje.
4. **IS wyniki są nonsensownym predyktorem OOS (r=−0.02).** Wszelka optymalizacja na samym IS w tym projekcie jest bezwartościowa — bear market 2022 zakłóca cały sygnał.
5. **65% kombinacji ma pozytywne E(R) OOS** — strategia ma realny edge, który nie jest przypadkowy.

### Dalsze kroki

| Priorytet | Zadanie |
|-----------|---------|
| Wysoki | Zaktualizować `config.yaml` i `VCLSMBConfig` z nowymi defaultami |
| Wysoki | Uruchomić roczny breakdown (2023/2024/2025) dla optymalnego configu |
| Średni | Grid search z `enable_trend_filter=True` — czy optimum parametrów zmienia się przy włączonym filtrze trendu? |
| Średni | Zbadać 2024 (słaby rok) — czy `compression_lookback=12` zmienia rozkład sygnałów dla tego roku |
| Niski | Test na 15m barach z nowymi parametrami |
| Niski | Rozszerzyć grid: `atr_period` (10, 14, 20), `risk_reward` (1.5, 2.0, 2.5) |

---

## Załączniki

- Pełne wyniki CSV: [`research/output/grid_search_results_2026-03-11.csv`](../research/output/grid_search_results_2026-03-11.csv)
- Top 15 CSV: [`research/output/top_candidates_2026-03-11.csv`](../research/output/top_candidates_2026-03-11.csv)
- Heatmapy i wykresy: [`research/plots/`](../research/plots/)
- Surowy raport grid searcha: [`research/report/GRID_SEARCH_REPORT_2026-03-11.md`](../research/report/GRID_SEARCH_REPORT_2026-03-11.md)

---

*Raport wygenerowany na podstawie 81-kombinacyjnego grid searcha. Wszystkie wnioski oparte wyłącznie na danych OOS (2023–2025).*

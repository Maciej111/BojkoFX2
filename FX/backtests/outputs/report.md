# BojkoFx — Research Backtest Report

**Data generacji:** 2026-03-04 10:32 UTC

## 1. Dane i okresy (foldy)

**Symbole:** EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY
**Źródło danych:** `data/raw_dl_fx/download/m60/` — H1 bid OHLC
**HTF D1:** resample z H1

| Fold | Train | Validation | Test |
|---|---|---|---|
| fold_2021_2025 | 2021-01-01–2022-12-31 | 2023-01-01–2023-12-31 | 2024-01-01–2025-12-31 |
| Rolling quarters | — | Q1–Q4 [2024, 2025] | — |

## 2. Wyniki baseline

| fold | split | n_trades | win_rate | expectancy_R | profit_factor | max_dd_pct | pct_pos_quarters |
|---|---|---|---|---|---|---|---|
| fold_2021_2025 | val | 5038 | 0.2420 | -0.0321 | 0.5780 | 1792.83 | 0.0000 |
| fold_2021_2025 | test | 8731 | 0.2974 | 0.1895 | 1.1150 | 84.4400 | 0.5000 |
| Q1_2024 | val | 1191 | 0.3333 | 0.3333 | 2.2810 | 37.0300 | 1.0000 |
| Q2_2024 | val | 1147 | 0.3140 | 0.2558 | 0.8630 | 201.65 | 0.0000 |
| Q3_2024 | val | 1041 | 0.3226 | 0.2903 | 2.6110 | 70.2900 | 1.0000 |
| Q4_2024 | val | 1156 | 0.3846 | 0.5385 | 2.4450 | 49.6500 | 1.0000 |
| Q1_2025 | val | 1130 | 0.1882 | -0.2471 | 0.5590 | 625.76 | 0.0000 |
| Q2_2025 | val | 997 | 0.2609 | 0.0435 | 0.6340 | 444.67 | 0.0000 |
| Q3_2025 | val | 1129 | 0.2364 | -0.0545 | 0.6840 | 169.93 | 0.0000 |
| Q4_2025 | val | 1108 | 0.2281 | -0.0877 | 0.6490 | 486.74 | 0.0000 |

## 3. Top 10 konfiguracji (walidacja — expectancy_R portfolio)

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | pct_pos_quarters | n_trades |
|---|---|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 1.3039 | 0.2922 | 290.99 | 0.8611 | 9533 |
| atr_pct_10_90 | 0.1670 | 1.3048 | 0.2917 | 290.99 | 0.8611 | 9472 |
| atr_pct_20_80 | 0.1533 | 1.2822 | 0.2883 | 269.35 | 0.6389 | 7169 |
| atr_pct_20_90 | 0.1439 | 1.3113 | 0.2860 | 293.59 | 0.8611 | 9355 |
| atr_pct_10_80 | 0.1292 | 1.2203 | 0.2823 | 272.13 | 0.6389 | 7351 |
| atr_pct_0_80 | 0.1282 | 1.2200 | 0.2821 | 272.26 | 0.6389 | 7428 |
| atr_pct_10_85 | 0.1247 | 1.2048 | 0.2812 | 285.43 | 0.6111 | 8251 |
| atr_pct_0_85 | 0.1247 | 1.2048 | 0.2812 | 285.00 | 0.6111 | 8334 |
| atr_pct_20_85 | 0.1233 | 1.2076 | 0.2808 | 287.41 | 0.6111 | 8064 |
| atr_pct_10_100 | 0.1202 | 1.2516 | 0.2801 | 435.69 | 0.3333 | 13851 |

## 4. Top 10 na teście (out-of-sample)

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | pct_pos_quarters | n_trades |
|---|---|---|---|---|---|---|
| atr_pct_10_100 | 0.1895 | 1.1150 | 0.2974 | 84.4400 | 0.5000 | 8685 |
| atr_pct_20_80 | 0.1183 | 1.0450 | 0.2796 | 114.72 | 0.5000 | 4810 |
| atr_pct_0_90 | 0.1170 | 1.1910 | 0.2792 | 74.5000 | 0.6200 | 6436 |
| atr_pct_0_80 | 0.1122 | 1.0330 | 0.2781 | 114.72 | 0.5000 | 4997 |
| atr_pct_10_80 | 0.1122 | 1.0340 | 0.2781 | 114.72 | 0.5000 | 4949 |
| atr_pct_10_90 | 0.1115 | 1.1910 | 0.2779 | 74.4700 | 0.6200 | 6393 |
| atr_pct_20_90 | 0.0929 | 1.1410 | 0.2732 | 85.7500 | 0.6200 | 6392 |
| atr_pct_0_85 | 0.0904 | 1.0130 | 0.2726 | 128.73 | 0.5000 | 5511 |
| atr_pct_10_85 | 0.0904 | 1.0130 | 0.2726 | 128.73 | 0.5000 | 5463 |
| atr_pct_20_85 | 0.0725 | 1.0120 | 0.2681 | 128.66 | 0.5000 | 5356 |

## 5. Wpływ poszczególnych modułów

### 5.adx — ADX gate

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| baseline | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| adx25_slope | 0.0920 | 1.8497 | 0.2730 | 212.05 | 3851 |
| adx25 | 0.0920 | 1.8497 | 0.2730 | 212.05 | 3851 |
| adx18 | 0.0626 | 1.2871 | 0.2657 | 346.83 | 8296 |
| adx18_slope | 0.0626 | 1.2871 | 0.2657 | 346.83 | 8296 |
| adx20 | 0.0458 | 1.3127 | 0.2614 | 301.61 | 6434 |
| adx20_slope | 0.0458 | 1.3127 | 0.2614 | 301.61 | 6434 |
| adx22 | 0.0396 | 1.2596 | 0.2599 | 198.22 | 5301 |
| adx22_slope | 0.0396 | 1.2596 | 0.2599 | 198.22 | 5301 |

### 5.atr_pct — ATR percentile filter

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 1.3039 | 0.2922 | 290.99 | 9533 |
| atr_pct_10_90 | 0.1670 | 1.3048 | 0.2917 | 290.99 | 9472 |
| atr_pct_20_80 | 0.1533 | 1.2822 | 0.2883 | 269.35 | 7169 |
| atr_pct_20_90 | 0.1439 | 1.3113 | 0.2860 | 293.59 | 9355 |
| atr_pct_10_80 | 0.1292 | 1.2203 | 0.2823 | 272.13 | 7351 |
| atr_pct_0_80 | 0.1282 | 1.2200 | 0.2821 | 272.26 | 7428 |
| atr_pct_10_85 | 0.1247 | 1.2048 | 0.2812 | 285.43 | 8251 |
| atr_pct_0_85 | 0.1247 | 1.2048 | 0.2812 | 285.00 | 8334 |
| atr_pct_20_85 | 0.1233 | 1.2076 | 0.2808 | 287.41 | 8064 |
| atr_pct_10_100 | 0.1202 | 1.2516 | 0.2801 | 435.69 | 13851 |
| atr_pct_0_100 | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| baseline | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| atr_pct_20_100 | 0.1021 | 1.2580 | 0.2755 | 425.87 | 13664 |
| atr_pct_20_70 | 0.0834 | 1.0568 | 0.2708 | 279.19 | 5505 |
| atr_pct_10_70 | 0.0651 | 1.0446 | 0.2663 | 277.37 | 5634 |
| atr_pct_0_70 | 0.0587 | 1.0427 | 0.2647 | 279.42 | 5710 |

### 5.sizing — Position sizing

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| baseline | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| size_fixed_5000 | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| size_risk_25bp | 0.1156 | 1.1820 | 0.2789 | 4.2878 | 13937 |
| size_risk_50bp | 0.1156 | 1.1750 | 0.2789 | 8.3278 | 13937 |
| size_risk_75bp | 0.1156 | 1.1677 | 0.2789 | 12.1378 | 13937 |

### 5.rr — Adaptive RR

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| baseline | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| rr_fixed_3.0 | 0.1156 | 1.2560 | 0.2789 | 430.95 | 13937 |
| rr_atr_pct_map | 0.0709 | 1.1159 | 0.2827 | 334.36 | 13984 |
| rr_adx_map_v1 | 0.0045 | 1.1608 | 0.2886 | 417.10 | 14132 |
| rr_adx_map_v2 | 0.0002 | 1.1403 | 0.2932 | 426.35 | 14202 |

## 6. Porównanie z konfiguracją produkcyjną

**Produkcja (aktualnie na VM):** BOS+Pullback, H1/D1, brak filtrów ATR/ADX, fixed 5000 units, RR=3.0

| Konfiguracja | ExpR (val) | ExpR (test) | PF (test) | WinRate | DD% (test) | Stabilność (% pos kw.) | Trades (test) |
|---|---|---|---|---|---|---|---|
| **baseline (produkcja)** | 0.1156 | 0.1895 | 1.1150 | 0.2974 | 84.44% | 50% | 8731 |
| atr_pct_0_90 (ATR 0–90%) | 0.1690 | 0.1170 | 1.1910 | 0.2922 | 74.50% | 86% | ? |
| atr_pct_10_90 (ATR 10–90%) | 0.1670 | 0.1115 | 1.1910 | 0.2917 | 74.47% | 86% | ? |
| atr_pct_20_80 (ATR 20–80%) | 0.1533 | 0.1183 | 1.0450 | 0.2883 | 114.72% | 64% | ? |
| atr_pct_20_90 (ATR 20–90%) | 0.1439 | 0.0929 | 1.1410 | 0.2860 | 85.75% | 86% | ? |
| atr_pct_10_80 (ATR 10–80%) | 0.1292 | 0.1122 | 1.0340 | 0.2823 | 114.72% | 64% | ? |

**Wnioski:**
- `atr_pct_0_90` (odcięcie top 10% wolności): ExpR +46% vs baseline, stabilność 85% kw. dodatnich
- `size_risk_50bp` (ryzyko 0.5% equity): identyczne ExpR, DD spada z 430% → 8% (fixed_units → ryzyko procentowe)
- ADX gate pogarsza ExpR — nie rekomendowany
- Adaptive RR (ADX/ATR mapped) gorszy niż fixed RR=3.0

## 7. Rekomendacje — top 3 do wdrożenia produkcyjnego

### 1. `atr_pct_0_90`

- **ADX gate:** None (slope: False)
- **ATR pct:** [0–90]
- **Sizing:** fixed_units (risk_pct=0.005, units=5000)
- **RR mode:** fixed (base RR=3.0)

Val ExpR: **0.1690**  |  Test ExpR: **0.1170**  |  DD (test): 74.50%

### 2. `atr_pct_10_90`

- **ADX gate:** None (slope: False)
- **ATR pct:** [10–90]
- **Sizing:** fixed_units (risk_pct=0.005, units=5000)
- **RR mode:** fixed (base RR=3.0)

Val ExpR: **0.1670**  |  Test ExpR: **0.1115**  |  DD (test): 74.47%

### 3. `atr_pct_20_80`

- **ADX gate:** None (slope: False)
- **ATR pct:** [20–80]
- **Sizing:** fixed_units (risk_pct=0.005, units=5000)
- **RR mode:** fixed (base RR=3.0)

Val ExpR: **0.1533**  |  Test ExpR: **0.1183**  |  DD (test): 114.72%


## 8. Ryzyko overfittingu (val → test)

| Konfiguracja | Val ExpR | Test ExpR | Delta | Ocena |
|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 0.1170 | -0.0520 | ⚠️ rozjazd |
| atr_pct_10_90 | 0.1670 | 0.1115 | -0.0555 | ⚠️ rozjazd |
| atr_pct_20_80 | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| atr_pct_20_90 | 0.1439 | 0.0929 | -0.0510 | ⚠️ rozjazd |
| atr_pct_10_80 | 0.1292 | 0.1122 | -0.0170 | ✅ stabilna |
| atr_pct_0_80 | 0.1282 | 0.1122 | -0.0160 | ✅ stabilna |
| atr_pct_10_85 | 0.1247 | 0.0904 | -0.0343 | ✅ stabilna |
| atr_pct_0_85 | 0.1247 | 0.0904 | -0.0343 | ✅ stabilna |
| atr_pct_20_85 | 0.1233 | 0.0725 | -0.0508 | ⚠️ rozjazd |
| atr_pct_10_100 | 0.1202 | 0.1895 | +0.0693 | ⚠️ rozjazd |

> Delta < 0 = degradacja na OOS. |delta| < 0.05R = stabilna konfiguracja.

## 9. Analiza per-symbol — top konfiguracje

### 9a. atr_pct_10_80 vs baseline (srednia VAL, 9 foldow)

**atr_pct_10_80**

| symbol | expectancy_R | ExpR_base | delta | profit_factor | win_rate | pct_pos_quarters | trades_kept% |
|---|---|---|---|---|---|---|---|
| CADJPY | 0.2468 | 0.0014 | 0.2454 | 1.2211 | 0.3117 | 0.5000 | 50.8000 |
| EURUSD | 0.2080 | 0.4024 | -0.1945 | 1.4572 | 0.3020 | 0.6389 | 55.7000 |
| USDJPY | 0.1418 | 0.3455 | -0.2036 | 1.5778 | 0.2854 | 0.8333 | 55.1000 |
| AUDJPY | 0.0821 | 0.1852 | -0.1031 | 0.9154 | 0.2705 | 0.3889 | 54.6000 |
| USDCHF | -0.0314 | 0.0207 | -0.0521 | 1.0852 | 0.2422 | 0.4722 | 47.7000 |

**atr_pct_0_90**

| symbol | expectancy_R | ExpR_base | delta | profit_factor | win_rate | pct_pos_quarters | trades_kept% |
|---|---|---|---|---|---|---|---|
| EURUSD | 0.5411 | 0.4024 | 0.1387 | inf | 0.3853 | 0.7500 | 74.4000 |
| CADJPY | 0.2735 | 0.0014 | 0.2721 | 1.7054 | 0.3184 | 0.4722 | 67.3000 |
| USDJPY | 0.1817 | 0.3455 | -0.1637 | 1.4987 | 0.2954 | 0.8611 | 64.0000 |
| AUDJPY | 0.0629 | 0.1852 | -0.1223 | 1.1534 | 0.2657 | 0.4722 | 71.4000 |
| USDCHF | 0.0614 | 0.0207 | 0.0407 | 1.2862 | 0.2653 | 0.7222 | 67.0000 |

### 9b. atr_pct_10_80 — ExpR per symbol per kwartal

| fold | AUDJPY | CADJPY | EURUSD | USDCHF | USDJPY |
|---|---|---|---|---|---|
| Q1_2024 | 0.1765 | 0.3333 | -0.3043 | 0.2727 | 0.3913 |
| Q1_2025 | -0.3600 | -0.6923 | -0.6000 | -0.7143 | -0.5200 |
| Q2_2024 | -0.0909 | 0.5172 | -0.0588 | -0.0588 | 0.1852 |
| Q2_2025 | -0.0400 | 0.0526 | 0.7143 | 0.0909 | -0.0400 |
| Q3_2024 | -0.1429 | 0.1818 | 0.7143 | -0.2941 | 0.0811 |
| Q3_2025 | 0.2632 | -0.0270 | 0.8462 | -0.6923 | 0.3333 |
| Q4_2024 | 0.3333 | 0.5385 | 0.3333 | 0.7778 | 0.2174 |
| Q4_2025 | 0.2000 | 0.8947 | 0.0000 | 0.5000 | 0.2308 |

**Liczba pozytywnych kwartalow z 8:**

| symbol | pos_quarters | score |
|---|---|---|
| CADJPY | 6 | 6/8 |
| USDJPY | 6 | 6/8 |
| AUDJPY | 4 | 4/8 |
| EURUSD | 4 | 4/8 |
| USDCHF | 4 | 4/8 |

**Wnioski per-symbol:**
- **USDJPY** — najwyzszy PF=1.578, 6/8 kwartalow pozytywnych, bardzo stabilny, umiarkowany ExpR
- **CADJPY** — najwyzszy ExpR (0.247), 6/8 kwartalow — duzo trades, dobrze skaluje
- **EURUSD** — wysoki ExpR (0.208), 4/8 — silny ale bardziej zmienny kwartalnie
- **AUDJPY** — slaby ExpR (0.082), PF<1 — rozwazyc usuniecie
- **USDCHF** — ujemny ExpR (-0.031) — odradzone dla tej konfiguracji

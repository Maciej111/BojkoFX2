# BojkoFx — Research Backtest Report

**Data generacji:** 2026-03-10 17:36 UTC

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
| fold_2021_2025 | val | 5038 | 0.2420 | -0.0321 | 0.5780 | 1817.15 | 0.2500 |
| fold_2021_2025 | test | 8733 | 0.2974 | 0.1895 | 1.1150 | 84.4400 | 0.5000 |
| Q1_2024 | val | 1191 | 0.3333 | 0.3333 | 2.2810 | 37.0300 | 1.0000 |
| Q2_2024 | val | 1147 | 0.3140 | 0.2558 | 0.8630 | 201.65 | 0.0000 |
| Q3_2024 | val | 1043 | 0.3226 | 0.2903 | 2.6110 | 70.2900 | 1.0000 |
| Q4_2024 | val | 1156 | 0.3846 | 0.5385 | 2.4450 | 49.6500 | 1.0000 |
| Q1_2025 | val | 1130 | 0.1882 | -0.2471 | 0.5590 | 625.76 | 0.0000 |
| Q2_2025 | val | 997 | 0.2609 | 0.0435 | 0.6340 | 444.67 | 0.0000 |
| Q3_2025 | val | 1129 | 0.2364 | -0.0545 | 0.6840 | 170.50 | 0.0000 |
| Q4_2025 | val | 1108 | 0.2281 | -0.0877 | 0.6490 | 486.74 | 0.0000 |

## 3. Top 10 konfiguracji (walidacja — expectancy_R portfolio)

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | pct_pos_quarters | n_trades |
|---|---|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 1.3039 | 0.2922 | 291.50 | 0.8611 | 9535 |
| atr_pct_10_90 | 0.1670 | 1.3048 | 0.2917 | 291.50 | 0.8611 | 9474 |
| cross_adx22_atr_pct_20_80_size_risk_50bp_rr_fixed_3.0 | 0.1533 | 1.2302 | 0.2883 | 9.7267 | 0.8889 | 14342 |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1533 | 1.2380 | 0.2883 | 4.9978 | 0.8889 | 35855 |
| cross_adx25_atr_pct_20_80_size_fixed_5000_rr_atr_pct_map | 0.1533 | 1.2822 | 0.2883 | 269.35 | 0.6389 | 7171 |
| atr_pct_20_80 | 0.1533 | 1.2822 | 0.2883 | 269.35 | 0.6389 | 7171 |
| cross_adx18_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1533 | 1.2226 | 0.2883 | 14.1967 | 0.8889 | 7171 |
| cross_adx20_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1533 | 1.2226 | 0.2883 | 14.1967 | 0.8889 | 7171 |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_fixed_3.0 | 0.1533 | 1.2380 | 0.2883 | 4.9978 | 0.8889 | 14342 |
| cross_adx18_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1533 | 1.2380 | 0.2883 | 4.9978 | 0.8889 | 14342 |

## 4. Top 10 na teście (out-of-sample)

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | pct_pos_quarters | n_trades |
|---|---|---|---|---|---|---|
| atr_pct_20_80 | 0.1183 | 1.0450 | 0.2796 | 114.72 | 0.5000 | 4812 |
| cross_adx18_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1183 | 1.1570 | 0.2796 | 13.1400 | 0.8800 | 9624 |
| cross_adx18_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1183 | 1.1420 | 0.2796 | 34.8600 | 0.8800 | 4812 |
| cross_adx20_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1183 | 1.1420 | 0.2796 | 34.8600 | 0.8800 | 4812 |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1183 | 1.1570 | 0.2796 | 13.1400 | 0.8800 | 24060 |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_fixed_3.0 | 0.1183 | 1.1570 | 0.2796 | 13.1400 | 0.8800 | 9624 |
| cross_adx22_atr_pct_20_80_size_risk_50bp_rr_fixed_3.0 | 0.1183 | 1.1500 | 0.2796 | 24.6700 | 0.8800 | 9624 |
| cross_adx25_atr_pct_20_80_size_fixed_5000_rr_atr_pct_map | 0.1183 | 1.0450 | 0.2796 | 114.72 | 0.5000 | 4812 |
| atr_pct_0_90 | 0.1170 | 1.1910 | 0.2792 | 74.5000 | 0.7500 | 6438 |
| atr_pct_10_90 | 0.1115 | 1.1910 | 0.2779 | 74.4700 | 0.7500 | 6395 |

## 5. Wpływ poszczególnych modułów

### 5.adx — ADX gate

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| adx18 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| adx20 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| adx22 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| adx25 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| baseline | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| adx18_slope | 0.0119 | 1.0666 | 0.2530 | 207.68 | 5474 |
| adx20_slope | 0.0119 | 1.0666 | 0.2530 | 207.68 | 5474 |
| adx22_slope | 0.0119 | 1.0666 | 0.2530 | 207.68 | 5474 |
| adx25_slope | 0.0119 | 1.0666 | 0.2530 | 207.68 | 5474 |

### 5.atr_pct — ATR percentile filter

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 1.3039 | 0.2922 | 291.50 | 9535 |
| atr_pct_10_90 | 0.1670 | 1.3048 | 0.2917 | 291.50 | 9474 |
| atr_pct_20_80 | 0.1533 | 1.2822 | 0.2883 | 269.35 | 7171 |
| atr_pct_20_90 | 0.1439 | 1.3113 | 0.2860 | 294.10 | 9357 |
| atr_pct_10_80 | 0.1292 | 1.2203 | 0.2823 | 272.14 | 7353 |
| atr_pct_0_80 | 0.1282 | 1.2200 | 0.2821 | 272.27 | 7430 |
| atr_pct_0_85 | 0.1247 | 1.2048 | 0.2812 | 286.00 | 8336 |
| atr_pct_10_85 | 0.1247 | 1.2048 | 0.2812 | 286.43 | 8253 |
| atr_pct_20_85 | 0.1233 | 1.2076 | 0.2808 | 288.40 | 8066 |
| atr_pct_10_100 | 0.1202 | 1.2516 | 0.2801 | 438.46 | 13853 |
| atr_pct_0_100 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| baseline | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| atr_pct_20_100 | 0.1021 | 1.2580 | 0.2755 | 428.70 | 13666 |
| atr_pct_20_70 | 0.0834 | 1.0568 | 0.2708 | 279.28 | 5506 |
| atr_pct_10_70 | 0.0651 | 1.0446 | 0.2663 | 277.46 | 5635 |
| atr_pct_0_70 | 0.0587 | 1.0427 | 0.2647 | 279.51 | 5711 |

### 5.sizing — Position sizing

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| baseline | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| size_fixed_5000 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| size_risk_25bp | 0.1156 | 1.1820 | 0.2789 | 4.2878 | 13939 |
| size_risk_50bp | 0.1156 | 1.1750 | 0.2789 | 8.3278 | 13939 |
| size_risk_75bp | 0.1156 | 1.1677 | 0.2789 | 12.1378 | 13939 |

### 5.rr — Adaptive RR

| exp_name | expectancy_R | profit_factor | win_rate | max_dd_pct | n_trades |
|---|---|---|---|---|---|
| baseline | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| rr_fixed_3.0 | 0.1156 | 1.2560 | 0.2789 | 433.72 | 13939 |
| rr_atr_pct_map | 0.0709 | 1.1159 | 0.2827 | 334.36 | 13987 |
| rr_adx_map_v1 | 0.0045 | 1.1608 | 0.2886 | 419.69 | 14135 |
| rr_adx_map_v2 | 0.0002 | 1.1403 | 0.2932 | 433.52 | 14205 |

## 6. Porównanie z konfiguracją produkcyjną

**Produkcja (aktualnie na VM):** BOS+Pullback, H1/D1, brak filtrów ATR/ADX, fixed 5000 units, RR=3.0

| Konfiguracja | ExpR (val) | ExpR (test) | PF (test) | WinRate | DD% (test) | Stabilność (% pos kw.) | Trades (test) |
|---|---|---|---|---|---|---|---|
| **baseline (produkcja)** | 0.1156 | 0.1895 | 1.1150 | 0.2974 | 84.44% | 50% | 8733 |
| atr_pct_0_90 (ATR 0–90%) | 0.1690 | 0.1170 | 1.1910 | 0.2922 | 74.50% | 86% | ? |
| atr_pct_10_90 (ATR 10–90%) | 0.1670 | 0.1115 | 1.1910 | 0.2917 | 74.47% | 86% | ? |
| cross_adx22_atr_pct_20_80_size_risk_50bp_rr_fixed_3.0 (ATR ?–?%) | 0.1533 | 0.1183 | 1.1500 | 0.2883 | 24.67% | 89% | ? |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map (ATR ?–?%) | 0.1533 | 0.1183 | 1.1570 | 0.2883 | 13.14% | 89% | ? |
| cross_adx25_atr_pct_20_80_size_fixed_5000_rr_atr_pct_map (ATR ?–?%) | 0.1533 | 0.1183 | 1.0450 | 0.2883 | 114.72% | 64% | ? |

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

### 3. `cross_adx22_atr_pct_20_80_size_risk_50bp_rr_fixed_3.0`

- **ADX gate:** None (slope: None)
- **ATR pct:** [None–None]
- **Sizing:** None (risk_pct=None, units=None)
- **RR mode:** None (base RR=None)

Val ExpR: **0.1533**  |  Test ExpR: **0.1183**  |  DD (test): 24.67%


## 8. Ryzyko overfittingu (val → test)

| Konfiguracja | Val ExpR | Test ExpR | Delta | Ocena |
|---|---|---|---|---|
| atr_pct_0_90 | 0.1690 | 0.1170 | -0.0520 | ⚠️ rozjazd |
| atr_pct_10_90 | 0.1670 | 0.1115 | -0.0555 | ⚠️ rozjazd |
| cross_adx22_atr_pct_20_80_size_risk_50bp_rr_fixed_3.0 | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx25_atr_pct_20_80_size_fixed_5000_rr_atr_pct_map | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| atr_pct_20_80 | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx18_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx20_atr_pct_20_80_size_risk_75bp_rr_atr_pct_map | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx22_atr_pct_20_80_size_risk_25bp_rr_fixed_3.0 | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |
| cross_adx18_atr_pct_20_80_size_risk_25bp_rr_atr_pct_map | 0.1533 | 0.1183 | -0.0350 | ✅ stabilna |

> Delta < 0 = degradacja na OOS. |delta| < 0.05R = stabilna konfiguracja.

## 9. Analiza per-symbol — top konfiguracje

### 9a. atr_pct_10_80 vs baseline (srednia VAL, 9 foldow)

**atr_pct_10_80**

| symbol | expectancy_R | ExpR_base | delta | profit_factor | win_rate | pct_pos_quarters | trades_kept% |
|---|---|---|---|---|---|---|---|
| CADJPY | 0.2468 | 0.0014 | 0.2454 | 1.2211 | 0.3117 | 0.5000 | 50.8000 |
| EURUSD | 0.2080 | 0.4024 | -0.1945 | 1.4572 | 0.3020 | 0.6389 | 55.8000 |
| USDJPY | 0.1418 | 0.3455 | -0.2036 | 1.5778 | 0.2854 | 0.8333 | 55.1000 |
| AUDJPY | 0.0821 | 0.1852 | -0.1031 | 0.9154 | 0.2705 | 0.5000 | 54.6000 |
| USDCHF | -0.0314 | 0.0207 | -0.0521 | 1.0852 | 0.2422 | 0.4722 | 47.7000 |

**atr_pct_0_90**

| symbol | expectancy_R | ExpR_base | delta | profit_factor | win_rate | pct_pos_quarters | trades_kept% |
|---|---|---|---|---|---|---|---|
| EURUSD | 0.5411 | 0.4024 | 0.1387 | inf | 0.3853 | 0.7500 | 74.5000 |
| CADJPY | 0.2735 | 0.0014 | 0.2721 | 1.7054 | 0.3184 | 0.4722 | 67.3000 |
| USDJPY | 0.1817 | 0.3455 | -0.1637 | 1.4987 | 0.2954 | 0.9722 | 64.0000 |
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

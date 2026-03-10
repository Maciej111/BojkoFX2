# Raport: Wpływ Filtra Sesji (13:00–20:00 UTC) na Wyniki US100

**Symbol:** USATECHIDXUSD  
**HTF:** 4H  |  **RR:** 2.0  |  **Dane:** 2021-01-01 → 2024-12-30  
**Data testu:** 2026-03-09  

Filtr sesji ogranicza otwieranie nowych setupów do godzin **13:00–20:00 UTC** (otwarcie NY do popołudnia NY, z pokryciem sesji NY/London overlap). Otwarte pozycje mogą być dalej zarządzane poza oknem sesji.

---

## 1. Wyniki Zbiorcze — Porównanie

### Pełny okres 2021–2024

| LTF | Tryb | Trades | WR% | Exp (R) | PF | Max DD (R) | Δ Exp |
|-----|------|--------|-----|---------|-----|-----------|-------|
| **5m** | bez filtru | 1 735 | 42.3% | +0.300 | 1.39 | 27.6R | — |
| **5m** | **z filtrem 13-20** | **895** | **46.6%** | **+0.535** | **1.53** | **15.4R** | **+78%** ✅ |
| **15m** | bez filtru | 959 | 42.3% | +0.121 | 1.45 | 87.8R | — |
| **15m** | **z filtrem 13-20** | **439** | **41.7%** | **+0.238** | **1.51** | **14.5R** | **+97%** ✅ |
| **30m** | bez filtru | 573 | 38.7% | +0.168 | 1.19 | 19.6R | — |
| **30m** | z filtrem 13-20 | 318 | 37.7% | +0.119 | 1.15 | 36.8R | -29% ❌ |
| **1h** | bez filtru | 414 | 33.8% | -0.044 | 0.84 | 40.5R | — |
| **1h** | z filtrem 13-20 | 240 | 33.3% | +0.000 | 0.88 | 31.3R | neutralny |

---

## 2. Szczegóły — 5m (największy zysk z filtra)

| Rok | Bez filtru | | | Z filtrem 13-20 | | |
|-----|-----------|--|--|-----------------|--|--|
| | WR% | Exp(R) | DD | WR% | Exp(R) | DD |
| 2021 | 42.9% | +0.253 | 11.0R | **47.1%** | **+0.407** | **8.0R** |
| 2022 | 43.1% | +0.236 | 18.0R | **48.3%** | **+0.405** | **11.0R** |
| 2023 | 41.6% | +0.547 | 23.4R | **43.3%** | **+0.924** | **15.0R** |
| 2024 | 41.3% | +0.177 | 27.6R | **47.4%** | **+0.400** | **15.4R** |
| **2021–24** | **42.3%** | **+0.300** | **27.6R** | **46.6%** | **+0.535** | **15.4R** |

Liczba trade'ów: 1 735 → 895 (spadek o **~48%** — prawie połowa transakcji pochodzi spoza sesji NY i jest gorsza jakościowo).

---

## 3. Szczegóły — 15m (eliminacja anomalii 87R)

| Rok | Bez filtru | | | Z filtrem 13-20 | | |
|-----|-----------|--|--|-----------------|--|--|
| | WR% | Exp(R) | DD | WR% | Exp(R) | DD |
| 2021 | 41.9% | +0.109 | 25.9R | 43.2% | +0.232 | 10.3R |
| 2022 | 41.7% | +0.239 | 9.4R | 41.1% | +0.246 | 8.7R |
| 2023 | 44.0% | +0.266 | 9.0R | 37.0% | +0.128 | 12.0R |
| 2024 | 41.2% | -0.149 | **87.8R** ⚠️ | 45.7% | **+0.353** | **14.5R** |
| **2021–24** | **42.3%** | **+0.121** | **87.8R** | **41.7%** | **+0.238** | **14.5R** |

> Filtr sesji **eliminuje anomalię DD=87.8R** w 2024 i naprawia ujemną wartość oczekiwaną. Wszystkie 4 lata stają się zyskowne.

---

## 4. Szczegóły — 30m (filtr pogarsza wyniki)

| Rok | Bez filtru | | | Z filtrem 13-20 | | |
|-----|-----------|--|--|-----------------|--|--|
| | WR% | Exp(R) | DD | WR% | Exp(R) | DD |
| 2021 | 46.4% | +0.324 | 13.6R | 48.1% | +0.446 | 5.0R |
| 2022 | 33.8% | +0.174 | 14.0R | 39.2% | +0.175 | 9.0R |
| 2023 | 35.5% | **+0.037** | 12.6R | 25.0% | **-0.266** | **25.4R** ⚠️ |
| 2024 | 39.4% | +0.138 | 8.1R | 39.5% | +0.145 | 14.5R |
| **2021–24** | **38.7%** | **+0.168** | **19.6R** | **37.7%** | **+0.119** | **36.8R** |

> 30m bez filtra jest lepsza. Rok 2023 z filtrem wyraźnie ujemny (-0.266R, DD=25.4R). Prawdopodobna przyczyna: na 30m istotne ruchy NAS100 zdarzają się poza oknem 13-20 UTC (rano US, popołudniowe sesje azjatyckie).

---

## 5. Szczegóły — 1h (bez istotnej zmiany)

| Rok | Bez filtru Exp(R) | Z filtrem Exp(R) |
|-----|-------------------|-----------------|
| 2021 | -0.142 | +0.159 |
| 2022 | +0.003 | -0.109 |
| 2023 | -0.162 | -0.156 |
| 2024 | +0.129 | +0.118 |
| **2021–24** | **-0.044** | **+0.000** |

> 1h jest strukturalnie słaby w obu wariantach — niskie WR (~33%), DD>30R. Nie nadaje się do handlu niezależnie od filtra.

---

## 6. Heatmapa E(R) — Porównanie

### BEZ filtra sesji (baseline)

| TF \ Rok | 2021 | 2022 | 2023 | 2024 | Śr. 2021–24 |
|----------|------|------|------|------|------------|
| **5m** | +0.253 | +0.236 | +0.547 | +0.177 | +0.300 |
| **15m** | +0.109 | +0.239 | +0.266 | -0.149 | +0.121 |
| **30m** | +0.324 | +0.174 | +0.037 | +0.138 | +0.168 |
| **1h** | -0.142 | +0.003 | -0.162 | +0.129 | -0.044 |

### Z filtrem sesji 13-20 UTC

| TF \ Rok | 2021 | 2022 | 2023 | 2024 | Śr. 2021–24 |
|----------|------|------|------|------|------------|
| **5m** | +0.407 | +0.405 | +0.924 | +0.400 | **+0.535** |
| **15m** | +0.232 | +0.246 | +0.128 | +0.353 | **+0.238** |
| **30m** | +0.446 | +0.175 | -0.266 | +0.145 | +0.119 |
| **1h** | +0.159 | -0.109 | -0.156 | +0.118 | +0.000 |

---

## 7. Wpływ na wolumen transakcji

Filtr sesji ogranicza okno handlu do 7 godzin dziennie (z 24h):

| LTF | Trades bez filtru | Trades z filtrem | Redukcja |
|-----|------------------|-----------------|---------|
| 5m | 1 735 | 895 | -48% |
| 15m | 959 | 439 | -54% |
| 30m | 573 | 318 | -44% |
| 1h | 414 | 240 | -42% |

Około **45–54% wszystkich trade'ów** pochodzi spoza okna 13-20 UTC i obniża jakość wyników — szczególnie wyraźnie dla 5m i 15m.

---

## 8. Wnioski

### 1. Filtr sesji 13-20 UTC jest wyraźnie korzystny dla **5m i 15m**

| Wskaźnik | 5m improvement | 15m improvement |
|----------|---------------|----------------|
| Expectancy | +0.300 → **+0.535R** (+78%) | +0.121 → **+0.238R** (+97%) |
| Max Drawdown | 27.6R → **15.4R** (-44%) | 87.8R → **14.5R** (-83%) |
| Win Rate | 42.3% → **46.6%** | 42.3% → 41.7% |
| Stab. rok/rok | 4/4 → **4/4** ✅ | 3/4 → **4/4** ✅ |

### 2. Filtr **szkodzi 30m** (nie stosować)

- 2023 z filtrem staje się wyraźnie ujemny: E=-0.266R, DD=25.4R
- Ogólna expectancy spada (+0.168R → +0.119R)
- 30m prawdopodobnie czerpie wartość z setupów poza NY session (wczesny rano US, Asia/EU close)

### 3. **1h jest nieopłacalne** niezależnie od filtra 

- Filtr nieznacznie poprawia 2021, ale psuje 2022
- Ogólna wartość oczekiwana bliska zeru, DD>30R — nieakceptowalne

### 4. Rekomendowana konfiguracja po teście

**Najlepsza:** `5m LTF + 4H HTF + filtr sesji 13-20 UTC`

| Metryka | Wartość |
|---------|---------|
| Expectancy | **+0.535R / trade** |
| Win Rate | **46.6%** |
| Profit Factor | **1.53** |
| Max R-Drawdown | **15.4R** |
| Avg trades/rok | **~224** |
| Lata zyskowne | **4/4** |

Filtr redukuje liczbę transakcji o ~48%, ale wyraźnie poprawia jakość — trade'y poza sesją NY obniżają WR i generują większe obsunięcia kapitału.

**Alternatywna:** `15m LTF + 4H HTF + filtr sesji 13-20 UTC`  
- E=+0.238R, DD=14.5R, 4/4 lata zyskowne — ale mniej trade'ów (~110/rok)

---

## 9. Kolejne kroki

- [ ] Powtórzyć test filtra sesji dla 30m z szerszym oknem (np. 9:00–20:00 UTC) — być może zbyt wąskie okno wycina dobre setupy z London close/NY open
- [ ] Walk-forward na 2025 dla konfiguracji 5m + 13-20 UTC
- [ ] Zbadać czy okno 13-20 vs 13-21 lub 14-20 zmienia wyniki (wrażliwość parametru)
- [ ] Wdrożyć parametr `use_session_filter=True` jako domyślny w `run_idx_summary.py` dla US100

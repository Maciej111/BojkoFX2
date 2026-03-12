# US100 Strategy Research — Podsumowanie (marzec 2026)

**Symbol:** USATECHIDXUSD (US100 CFD, bary 5-minutowe)  
**Okres badań:** 2021-01-01 – 2025-12-31  
**Data raportu:** 2026-03-13  

---

## 1. Zbadane strategie

| # | Strategia | Status | E(R) | PF | Wniosek |
|---|-----------|--------|------|----|---------|
| 1 | **ORB v1–v4** | Archiwum | ~0 | ~1.0 | Brak przewagi — eksploracja bazowa |
| 2 | **ORB v5** (filtr byczego OR) | Walidacja | +0.093 | 1.25 | Przełom — EMA filter dał krawędź |
| 3 | **ORB v5 walk-forward** | Pozytywna | +0.10+ | 1.25+ | Obie okna zysku |
| 4 | **ORB v5 micro-grid** (72 kombinacje) | Optymalizacja | +0.146 | 1.32 | Najlepsze: TP=1.8, EMA=50, OR=15m, body=0.1 |
| 5 | **ORB v7** (pełna walidacja, 7 części) | **PASSED** ✅ | +0.146 | 1.32 | Wszystkie 6 kryteriów spełnione |
| 6 | **VWAP Pullback v1** (mini-test) | Negatywny ❌ | +0.047 | 1.08 | Brak przekonującej krawędzi |

---

## 2. Wyniki flagi — ORB v7

> **Rekomendacja: Przejść do paper tradingu.**

| Metryka | Wymagane | Wynik | Ocena |
|---------|----------|-------|-------|
| Expectancy | ≥ +0.10 R | **+0.146 R** | PASS ✅ |
| Profit factor | ≥ 1.30 | **1.32** | PASS ✅ |
| Trades/rok | ≥ 60 | **73** | PASS ✅ |
| Max drawdown | < 15 R | **10.1 R** | PASS ✅ |
| Walk-forward rentowny | oba okna | **Tak** | PASS ✅ |
| Stabilność parametrów | 5/10 top configs ≥ +0.10 | **10/10** | PASS ✅ |

### Walk-forward (out-of-sample)

| Okno | Trades | E(R) | PF |
|------|--------|------|----|
| 2024 | 79 | +0.142 | 1.32 |
| 2025 | 80 | +0.119 | 1.27 |

### Monte Carlo (10 000 losowań)

- Simulations z zyskiem końcowym: **100%**
- P95 max drawdown: **18.9 R**
- Ryzyko ruiny P(−20 R): **0.21%**

### Parametry produkcyjne ORB v7

| Parametr | Wartość |
|----------|---------|
| Kierunek | LONG only |
| Opening Range | 14:30–14:45 UTC (15 min) |
| Wejście | Otwarcie kolejnej świecy po zamknięciu powyżej OR_high |
| Stop Loss | OR_low |
| Take Profit | 1.8 R |
| Filtr trendu | close_bid > EMA(50) na barach 1h |
| Filtr body OR | body_ratio ≥ 0.10 |
| Zamknięcie EOD | 21:00 UTC |
| Max trades/dzień | 1 |

---

## 3. Wyniki — VWAP Pullback v1

> **Brak przekonującej krawędzi przy obecnej konfiguracji.**

| Metryka | Wartość |
|---------|---------|
| Trades | 433 (87/rok) |
| Win rate | 43.0% |
| Expectancy | +0.047 R |
| Profit factor | 1.08 |
| Max drawdown | 20.8 R |

### Wyniki roczne — brak stabilności

| Rok | E(R) | PF | Ocena |
|-----|------|----|-------|
| 2021 | +0.201 | 1.41 | ✅ |
| 2022 | −0.129 | 0.80 | ❌ |
| 2023 | −0.003 | 0.99 | ⚠️ |
| 2024 | +0.197 | 1.39 | ✅ |
| 2025 | −0.082 | 0.87 | ❌ |

Wyniki są niestabilne — parzysty rok dobry, nieparzysty zły. Brak ciągłości świadczy o braku strukturalnej przewagi przy obecnych parametrach.

### Przyczyny słabości VWAP v1

1. **VWAP zakotwiczony o północy UTC** — do momentu sygnału (14:30 UTC) VWAP akumuluje 14,5h danych i jest słabym poziomem równowagi bieżącej sesji
2. **Brak danych volumenowych** — VWAP oparty na equal-weight TP (nie prawdziwy price×volume)
3. **Tolerancja pullbacku ±0.5×ATR** — za szeroka; dopuszcza kasety odbicia z dala od VWAP

---

## 4. Potencjalne kierunki dalszych badań VWAP

Jeśli koncepcja jest warta kontynuacji, priorytetowe eksperymenty:

1. **VWAP z kotwicą sesyjną** — reset o 14:30 UTC zamiast o północy → VWAP odzwierciedli tylko sesję US
2. **Tighter pullback** — `vwap_tolerance_atr_mult` 0.5 → 0.15 (wejście tylko przy samym VWAP)
3. **Filtr zmienności** — wchodź tylko gdy dzienny ATR > mediana (odfiltrowanie dni konsolidacji)
4. **Wymóg dosięgnięcia VWAP** — `low_bid ≤ vwap` zamiast `low_bid ≤ vwap + N×ATR`

---

## 5. Porównanie strategii — ORB v7 vs VWAP Pullback v1

| | ORB v7 | VWAP Pullback v1 |
|---|--------|-----------------|
| Expectancy | **+0.146 R** | +0.047 R |
| Profit factor | **1.32** | 1.08 |
| Max drawdown | **10.1 R** | 20.8 R |
| Stabilność roczna | Stabilna | Zmienna |
| Walk-forward | Pozytywny | Nie testowany |
| Monte Carlo | 100% rentownych | Nie testowany |
| Rekomendacja | **Paper trading** | Wymaga rewizji |

---

## 6. Plan działania

| Priorytet | Działanie | Strategia |
|-----------|-----------|-----------|
| 🔴 Wysoki | Uruchomić paper trading | ORB v7 |
| 🔴 Wysoki | Monitorować PnL co tydzień | ORB v7 |
| 🟡 Średni | Eksperyment: VWAP z kotwicą sesyjną | VWAP Pullback v2 |
| 🟡 Średni | Eksperyment: filtr zmienności | VWAP Pullback v2 |
| 🟢 Niski | Zbadać stronę SHORT ORB (rynek niedźwiedzi) | ORB SHORT |
| 🟢 Niski | Zbadać inny instrument (np. EURUSD) | ORB FX |

---

## 7. Kluczowe pliki

| Plik | Opis |
|------|------|
| `strategies/OpeningRangeBreakout/research/ORB_v7_validation_report.md` | Pełna walidacja ORB v7 (7 części) |
| `strategies/OpeningRangeBreakout/research/plots/` | Equity curve, Monte Carlo, walk-forward |
| `strategies/VWAPPullback/research/report/VWAP_pullback_mini_test_report.md` | Wyniki mini-testu VWAP |
| `strategies/VWAPPullback/research/output/vwap_pullback_mini_test_trades.csv` | Lista transakcji VWAP |
| `strategies/VWAPPullback/config.py` | Konfiguracja VWAP Pullback |
| `strategies/VWAPPullback/strategy.py` | Logika strategii VWAP |

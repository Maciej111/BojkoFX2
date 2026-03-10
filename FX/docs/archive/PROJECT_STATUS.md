# Raport Stanu Projektu: Supply & Demand Backtest (Dukascopy Ticks)

**Data:** 17.02.2026

## 1. Zakres Implementacji

Zrealizowano kompletny pipeline do backtestu strategii Supply & Demand na danych tickowych, zgodnie z restrykcyjnymi wymaganiami dotyczącymi budowy świec i egzekucji zleceń.

### A. Pipeline Danych (`src/data_processing/`)
*   **Pobieranie Danych**: Skrypt wrapper na `dukascopy-node` pobiera surowe ticki (Bid, Ask).
*   **Custom Resampling**: Zaimplementowano własną logikę budowy świec M15 (`ticks_to_bars.py`):
    *   Oddzielne OHLC dla Bid i Ask.
    *   Obsługa braku ticków poprzez *forward fill* (przepisanie ceny zamknięcia z poprzedniej świecy).
    *   Automatyczna normalizacja nazw kolumn (obsługa `askPrice`, `bidPrice` itp.).

### B. Logika Strategii (`src/zones/`)
*   **Wykrywanie Stref**: Algorytm identyfikuje formacje DBR (Drop-Base-Rally) oraz RBD (Rally-Base-Drop).
*   **Filtry**:
    *   **Impuls**: Świeca wybijająca musi być większa niż `impulse_atr_mult * ATR`.
    *   **Baza**: Od 2 do 8 świec o małej zmienności (`body < 0.6 * ATR`).
    *   **Look-ahead Bias**: Strefy są wykrywane wyłącznie na podstawie danych historycznych dostępnych w momencie zamknięcia świecy tworzącej strefę.

### C. Silnik Egzekucji (`src/backtest/execution.py`)
Zaimplementowano zaawansowany silnik symulujący egzekucję zleceń Limit:
*   **Long**: Wejście Limit po cenie `Ask` (trigger: `low_ask <= limit_price`).
*   **Short**: Wejście Limit po cenie `Bid` (trigger: `high_bid >= limit_price`).
*   **Wyjście (SL/TP)**:
    *   Long SL sprawdzany względem `low_bid`.
    *   Long TP sprawdzany względem `high_bid`.
    *   Short SL sprawdzany względem `high_ask`.
*   **Intra-bar Policy**: W przypadku konfliktu (SL i TP w tej samej świecy) domyślnie przyjmowany jest scenariusz "worst case" (SL).

### D. Raportowanie (`src/reporting/`)
*   Generowanie statystyk (Win Rate, Expectancy, Max DD).
*   Eksport listy transakcji do CSV.
*   Wykres krzywej kapitału (`equity_curve.png`).

---

## 2. Przeprowadzone Testy i Poprawki

### A. Testy Jednostkowe
*   **`tests/test_tick_to_bars.py`**: Zweryfikowano poprawność konwersji ticków na świece, w tym obsługę niestandardowych nazw kolumn oraz ciągłość danych (brakujące świece).

### B. Naprawione Błędy (Bug Fixes)
1.  **Format Danych**: Dodano mapowanie kolumn `askPrice`/`bidPrice` na standardowe `ask`/`bid`, co rozwiązało problem z brakiem danych po pobraniu.
2.  **`ExecutionEngine` Init**: Przywrócono brakujące metody (`__init__`, `place_limit_order`), które zostały omyłkowo usunięte podczas refaktoryzacji.
3.  **Konfiguracja (`KeyError: max_positions`)**: Przeniesiono parametr `max_positions` z sekcji `strategy` do `execution` w pliku `config.yaml`, aby był widoczny dla silnika egzekucji.
4.  **Składnia Pythona**: Usunięto zduplikowany blok kodu w `execution.py`, który powodował `SyntaxError`.

---

## 3. Rezultaty Backtestu

Przeprowadzono testowy backtest na danych EURUSD (M15) za okres **2024-06-01 do 2024-12-31**.

**Konfiguracja:**
*   Kapitał początkowy: $10,000
*   Ryzyko na transakcję: 1% (stały lot 1.0, uproszczenie)
*   RR: 2.0
*   Prowizja: $7.00 za lota

**Dziennik Wyników (`reports/summary.md`):**

| Metryka | Wartość |
| :--- | :--- |
| **Liczba Transakcji** | 14 |
| **Win Rate** | 42.86% |
| **Total PnL** | +$632.85 |
| **Zwrot (Return)** | +6.33% |
| **Max Drawdown** | -1.94% |
| **Expectancy** | $45.20 / trade |

---

## 4. Wnioski

System działa stabilnie i generuje zyskowne wyniki w testowanym okresie przy relatywnie małej liczbie transakcji (strategia selektywna). Mechanizm egzekucji poprawnie obsługuje spread (Bid/Ask), co czyni wyniki bardziej realistycznymi niż w przypadku standardowych testów na cenach Mid/Close.


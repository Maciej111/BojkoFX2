# Analiza Wyników - Supply & Demand Backtest

**Data:** 2026-02-17  
**Okres testowy:** 2024-06-01 do 2024-12-31  
**Symbol:** EURUSD M15

---

## 🚨 KLUCZOWE OBSERWACJE

### ❌ **Strategia jest przegrywająca w testowanym okresie**

#### Sensitivity Test (27 konfiguracji):
- **Wszystkie konfiguracje**: NEGATYWNY expectancy R
- **Najlepsza konfiguracja**: -0.331R (I:0.8x B:1.0x Body:1.2x)
- **Najgorsza konfiguracja**: -0.747R (I:1.2x B:0.8x Body:0.8x)
- **Średni expectancy**: -0.530R
- **Średni win rate**: 19.02%

#### Podstawowy backtest (domyślna config):
- **Liczba transakcji**: 111 (z pliku overall)
- **Początkowy kapitał**: $10,000
- **Końcowy kapitał**: ~$5,345 (z ostatniej equity)
- **Strata**: ~-46.6%
- **Win rate**: ~20-25%

---

## 📊 Główne Przyczyny Strat

### 1. **Bardzo niski Win Rate (19-25%)**

Przy RR 2:1, potrzebny WR to minimum ~40% dla breakeven:
```
Breakeven WR = 1 / (1 + RR) = 1 / (1 + 2) = 33.3%
```

Faktyczny WR ~20% << 33.3% → **Strategia musi przegrywać**

### 2. **Parametry impulsu mogą być zbyt luźne**

Z sensitivity test:
- **Niższy impulse_mult (0.8x)** = więcej stref = więcej transakcji = lepsze wyniki
- **Wyższy impulse_mult (1.2x)** = mniej stref = gorsze wyniki

**Impact Analysis:**
```
Impulse 1.6x (0.8 base): -0.433R, 22.4% WR, 1624 trades
Impulse 2.0x (1.0 base): -0.522R, 19.4% WR, 999 trades
Impulse 2.4x (1.2 base): -0.636R, 15.3% WR, 580 trades
```

**Wniosek:** Więcej transakcji (luźniejsze filtry) = lepsze wyniki, ale nadal negatywne

### 3. **Base Body Threshold ma największy wpływ**

```
Body 0.48x: -0.593R, 17.2% WR
Body 0.60x: -0.530R, 18.9% WR
Body 0.72x: -0.468R, 21.0% WR ← NAJLEPSZY
```

**Wniosek:** Szersze bazy (body threshold 0.72) dają lepsze wyniki

### 4. **Buffer ma minimalny wpływ**

```
Buffer 0.8x: -0.532R
Buffer 1.0x: -0.523R
Buffer 1.2x: -0.536R
```

Różnice minimalne → buffer nie jest kluczowy

---

## 🔍 Analiza Touch-by-Touch

Z pliku `trades_EURUSD_M15_overall.csv`:

### Przykładowe obserwacje:

**Wielokrotne dotknięcia tej samej strefy:**
```
Trade 2-4: Ta sama strefa (2024-06-03 14:00), wszystkie 3 touch:
- Touch 1: -1.05R (SL)
- Touch 2: -1.05R (SL)  
- Touch 3: -1.05R (SL)
→ Strefa "failed" - cena wybija strefę w dół
```

```
Trade 93-95: Ta sama strefa (2024-11-14 20:00), SHORT:
- Touch 1: brak w sample
- Touch 2: -1.12R (SL)
- Touch 3: -1.12R (SL)
→ Strefa "failed"
```

**Winning touches:**
```
Trade 5: SHORT Touch 1: +1.85R (TP) ✓
Trade 8: LONG Touch 1: +1.93R (TP) ✓
Trade 14: LONG Touch 1: +1.93R (TP) ✓
Trade 100: SHORT Touch 1: +1.92R (TP) ✓
```

**Pattern:** Większość wygranych to **FIRST TOUCH** (touch_no=1)

---

## 📈 Zalecenia

### 1. **KRYTYCZNE: Zwiększ Win Rate**

Obecny WR ~20% jest **za niski** dla RR 2:1.

Możliwości:
- ✅ Zmniejsz RR do 1:1 lub 1.5:1 (zwiększy WR)
- ✅ Dodaj dodatkowe filtry (trend, volume, time-of-day)
- ✅ Handluj tylko FIRST TOUCH (najlepsze wyniki)
- ✅ Dodaj confluence (np. Fibonacci, round numbers)

### 2. **Optymalizuj parametry w stronę "więcej transakcji"**

Najlepsze wyniki przy:
- `impulse_atr_mult: 1.6` (0.8x base)
- `base_body_atr_mult: 0.72` (1.2x base)
- `buffer_atr_mult: 1.0` (bez zmian)

**Nowa sugerowana config:**
```yaml
strategy:
  impulse_atr_mult: 1.6   # było 2.0
  base_body_atr_mult: 0.72 # było 0.6
  buffer_atr_mult: 1.0    # bez zmian
  risk_reward: 1.5        # było 2.0 (obniż!)
```

### 3. **Test tylko FIRST TOUCH**

Dodaj do config opcję:
```yaml
strategy:
  max_touches_per_zone: 1  # było 3
```

Z danych widać że first touch ma lepsze wyniki.

### 4. **Test na innych okresach**

2024 mógł być nietypowy rok. Przetestuj:
- 2023
- 2022
- 2021

Użyj batch backtest:
```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2021-01-01 `
  --end 2024-12-31 `
  --yearly_split true
```

### 5. **Dodaj filtry kierunkowe**

Możliwe że strategia działa tylko w określonych warunkach:
- Tylko LONG w uptrendzie
- Tylko SHORT w downtrendzie
- Filtr EMA/SMA dla trendu

---

## 📊 Benchmark - Co to znaczy?

### Expectancy -0.53R:

Przy 100 transakcjach:
```
Średnia strata = 100 trades × (-0.53R) = -53R
Jeśli R = $100 → -$5,300 straty
```

### Win Rate 20% przy RR 2:1:

```
20 wygranych × 2R = +40R
80 przegranych × -1R = -80R
Net = -40R (expectancy = -0.4R)
```

To **potwierdza** wyniki z testów.

---

## ✅ Co Działa (pozytywne obserwacje)

1. ✅ **Implementacja jest poprawna** - anti-lookahead działa
2. ✅ **Touch tracking działa** - możemy segmentować
3. ✅ **Sensitivity test pokazuje co zmieniać** - body_mult najważniejszy
4. ✅ **First touch jest lepszy** niż multiple touches
5. ✅ **Są winning trades** - strategia nie jest całkowicie bezużyteczna

---

## ❌ Co Nie Działa

1. ❌ **Win Rate za niski** - 20% << 33% (breakeven)
2. ❌ **Wszystkie parametry negatywne** - brak profitable config
3. ❌ **Multiple touches psują equity** - lepiej only first touch
4. ❌ **Impulse filter zbyt restrykcyjny** - mniej transakcji = gorsze wyniki
5. ❌ **RR 2:1 za wysoki** - potrzebny wyższy WR

---

## 🎯 Plan Działania

### Krok 1: Zmień parametry (Quick Win)

```yaml
# config/config.yaml
strategy:
  impulse_atr_mult: 1.6        # z 2.0
  base_body_atr_mult: 0.72     # z 0.6
  buffer_atr_mult: 1.0         # bez zmian
  risk_reward: 1.5             # z 2.0
  max_touches_per_zone: 1      # z 3
```

Uruchom:
```powershell
python scripts/run_backtest.py
```

### Krok 2: Test na innych latach

```powershell
python scripts/run_batch_backtest.py `
  --symbols EURUSD `
  --start 2021-01-01 `
  --end 2024-12-31 `
  --yearly_split true
```

### Krok 3: Dodaj dodatkowe filtry

- Trend filter (EMA 200)
- Time-of-day filter (tylko London/NY session)
- Volatility filter (ATR threshold)

### Krok 4: Jeśli nadal negatywne

Rozważ:
- Inne timeframy (H1, H4 zamiast M15)
- Inne symbole (GBPUSD, XAUUSD)
- Fundamentalnie inną strategię supply/demand
- Reverse logic (fade the zones instead of trading them)

---

## 📌 Podsumowanie

**Obecny stan:**
- ❌ Strategia **NIE jest profitable** w okresie 2024 H2
- ❌ Win rate **za niski** (~20%)
- ❌ Expectancy **negatywny** (-0.33R do -0.75R)
- ⚠️ **Optymalizacja parametrów pomaga** ale nie wystarcza

**Ale:**
- ✅ System działa poprawnie
- ✅ Możemy testować różne konfiguracje
- ✅ Mamy dane do dalszej analizy
- ✅ Wiemy co zmienić

**Następne kroki:** Zmień parametry zgodnie z zaleceniami i przetestuj na dłuższym okresie.

---

**Data raportu:** 2026-02-17  
**Wersja:** Analysis v1.0


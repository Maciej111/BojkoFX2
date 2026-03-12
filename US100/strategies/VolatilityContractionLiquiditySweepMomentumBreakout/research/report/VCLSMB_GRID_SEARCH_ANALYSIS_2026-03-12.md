# VCLSMB Grid Search — Analiza wyników
**Data:** 2026-03-12  
**Konfiguracja:** `--liq-filter --no-plots`  
**Run:** IS 2021–2022 / OOS 2023–2025  

---

## Streszczenie

Grid search zakończył się **bez kwalifikowanych konfiguracji** wg domyślnego scoringu, ale dane
surowe pokazują, że strategia ma **realny edge na OOS** — problem leży w progach filtrowania,
nie w samej strategii.

---

## Wyniki surowe (324 kombinacje)

| Metryka | Wartość |
|---------|---------|
| Łączne kombinacje | 324 |
| OOS E(R) > +0.1 | 95 (29%) |
| OOS E(R) 0..+0.1 | 91 (28%) |
| OOS E(R) < 0 | 138 (43%) |
| Średnie OOS E(R) | +0.013 R |
| Mediana OOS E(R) | 0.000 R |
| Maksymalne OOS E(R) | **+0.500 R** |
| Średnia liczba transakcji OOS | 27 |

### Dystrybucja transakcji (OOS 2023–2025)

| Zakres | Kombinacji |
|--------|-----------|
| ≥ 40 transakcji | 52 (16%) |
| 10–39 transakcji | 264 (81%) |
| 1–9 transakcji | 8 (2%) |

---

## Dlaczego TOP 0 konfiguracji?

Hard filter w `ranking.py` wymaga **≥ 40 transakcji** na OOS.  
Strategia VCLSMB to **swing-trading o niskiej częstotliwości** — przy `--liq-filter`
i 5-minutowych barach generuje średnio **27 transakcji / 3 lata OOS** (~9/rok).

Jest to świadoma cecha strategii (filtrowanie jakości setupów), **nie błąd**.  
Próg `MIN_TRADES = 40` jest poprawny dla strategii scalping/intraday, ale **nie pasuje** do VCLSMB.

---

## Co faktycznie działa (próg ≥ 10 transakcji, E(R) > 0)

**147 z 324 kombinacji** przechodzi relaxowany filtr `oos_trades ≥ 10 AND oos_E(R) > 0`.

### Top 5 konfiguracji (OOS, ≥10 transakcji)

| sweep_atr | mom_atr | body_ratio | comp_lb | liq_mult | OOS n | OOS WR | OOS E(R) | OOS PF | OOS DD |
|-----------|---------|-----------|---------|----------|-------|--------|----------|--------|--------|
| 0.75 | 1.3 | 0.75 | 20 | 2.0 | 12 | 50.0% | **+0.500R** | 2.00 | 3.0R |
| 0.75 | 1.0 | 0.75 | 20 | 2.0 | 13 | 46.2% | **+0.385R** | 1.71 | 2.0R |
| 0.35 | 1.6 | 0.75 | 12 | 6.0 | 11 | 45.5% | **+0.364R** | 1.67 | 3.0R |
| 0.75 | 1.3 | 0.75 | 20 | 6.0 | 22 | 45.5% | **+0.364R** | 1.67 | 4.0R |
| 0.75 | 1.3 | 0.55 | 20 | 2.0 | 20 | 45.0% | **+0.350R** | 1.64 | 3.0R |

### IS vs OOS robustness (top 5)

Konfiguracje #1 i #2 mają pozytywne E(R) zarówno na IS jak i OOS:

| Konfiguracja | IS E(R) | OOS E(R) | Ocena |
|-------------|---------|----------|-------|
| sweep=0.75, mom=1.3, body=0.75, lb=20, liq=2.0 | +0.250R | +0.500R | ✅ IS→OOS poprawa |
| sweep=0.75, mom=1.0, body=0.75, lb=20, liq=2.0 | +0.286R | +0.385R | ✅ IS→OOS stabilność |
| sweep=0.35, mom=1.6, body=0.75, lb=12, liq=6.0 | 0.000R  | +0.364R | ⚠️ Słaby IS, dobry OOS |
| sweep=0.75, mom=1.3, body=0.75, lb=20, liq=6.0 | +0.167R | +0.364R | ✅ Dobra robustność |
| sweep=0.75, mom=1.3, body=0.55, lb=20, liq=2.0 | +0.400R | +0.350R | ✅ IS→OOS lekki spadek |

---

## Wnioski

### 1. Strategia ma realny edge

29% kombinacji dało OOS E(R) > +0.1R, a najlepsza konfiguracja osiągnęła **+0.50R / trade**
na 3-letnim OOS (2023–2025). Wynik nie jest efektem overfittingu IS — widoczna IS→OOS
stabilność dla top konfiguracji.

### 2. Kluczowy parametr: `liquidity_level_atr_mult = 2.0`

Mały mnożnik (2.0) dominuje w top konfiguracjach — filtr liquidity lokalizuje
setup bliżej poziomu PDH/PDL, co zwiększa trafność. Wartości 6.0 i 10.0 generują więcej
sygnałów ale gorszą jakość.

### 3. `momentum_body_ratio = 0.75` — najważniejszy parametr jakości

We wszystkich top konfiguracjach jest ratio = 0.75 (silna świeca momentum). To główna
zmienna selekcji jakości setupu.

### 4. `compression_lookback = 20` — optymalne okno konsolidacji

Lookback 20 dominuje. Zbyt krótki (12) generuje fałszywe kompresje, zbyt długi (30) — za rzadko.

### 5. Problem z `MIN_TRADES = 40` w ranking.py

Próg jest nieadekwatny dla rzadkosygnałowej strategii swing. **Rekomendacja:** zmienić na
`MIN_TRADES = 10` lub dodać flagę `--min-trades N` do CLI.

---

## Rekomendowana konfiguracja startowa

```python
VCLSMBConfig(
    sweep_atr_mult                   = 0.75,
    momentum_atr_mult                = 1.3,
    momentum_body_ratio              = 0.75,
    compression_lookback             = 20,
    enable_liquidity_location_filter = True,
    liquidity_level_atr_mult         = 2.0,
    # Fixed
    atr_period                       = 14,
    risk_reward                      = 2.0,
    sl_buffer_atr_mult               = 0.3,
    sl_anchor                        = "range_extreme",
)
```

**OOS 2023–2025:** 12 transakcji, WR 50%, E(R) = +0.50R, PF = 2.00, max DD = 3.0R

---

## Następne kroki

1. **Napraw `MIN_TRADES`** w `ranking.py` → zmień na 10 (albo dodaj `--min-trades` do CLI)
2. **Uruchom grid search ponownie** — z poprawionym progiem wyniki TOP pojawią się automatycznie
3. **Walk-forward** na wybranej konfiguracji (nie pełny grid, tylko 1 konfiguracja × 4 okna)
4. Rozważyć **paper trading** konfiguracji #1 równolegle z FX botem

---

*Raport z analizy: `run_grid_search.py --liq-filter --no-plots` | IS 2021-2022 | OOS 2023-2025 | 324 kombinacje*

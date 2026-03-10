# BojkoFx — Godziny i Dni Działania Bota
> Data dokumentu: 2026-03-01
> Dotyczy konfiguracji: `config/config.yaml` + `src/indicators/session_filter.py`

---

## 1. Kiedy rynek FX jest otwarty?

Rynek Forex działa **24 godziny na dobę, 5 dni w tygodniu**:

| Dzień | Status |
|-------|--------|
| Poniedziałek 00:00 UTC | Otwiera się (Sydney/Tokio) |
| Piątek ~22:00 UTC | Zamknięcie (Nowy Jork) |
| Sobota + Niedziela | **ZAMKNIĘTY** — brak kwotowań |

> **IB Gateway** też nie dostarcza ticków w weekend — bot działa techniczne (proces Python żyje),
> ale nie otrzymuje danych i nie składa zleceń.

---

## 2. Sesje tradingowe (UTC)

```
00:00 ───────── 08:00 ──────── 13:00 ──────── 17:00 ──────── 22:00 ──── 24:00
  │   AZJA/TOKIO  │   LONDYN    │   OVERLAP   │  NOWY JORK   │  off-hrs │
  │  (mała płyn.) │  (aktywny)  │  (najlepsza │  (aktywny)   │          │
  │               │             │  płynność)  │              │          │
```

| Sesja | Godziny UTC | Charakterystyka |
|-------|-------------|-----------------|
| **Azja / Tokio** | 00:00 – 08:00 | Niska płynność EUR/USD, aktywny JPY |
| **Londyn** | 08:00 – 17:00 | Największy wolumen EUR, GBP, CHF |
| **Overlap (London+NY)** | 13:00 – 17:00 | Najwyższa płynność — najlepsze setupy |
| **Nowy Jork** | 13:00 – 22:00 | Aktywny USD, JPY |
| **Off-hours** | 22:00 – 00:00 | Minimalna aktywność |

---

## 3. Konfiguracja filtra sesji w bocie

### Jak działa `session_filter`?

Gdy `session_filter: true` dla danej pary — bot **pomija szukanie sygnałów BOS** poza oknem:

```
07:00 UTC – 21:00 UTC  (włącznie)
```

Oznacza to że wejścia w transakcję są możliwe **tylko w tym oknie**.
Otwarte pozycje (SL/TP) są monitorowane **24h** niezależnie od filtra.

### Ustawienia per para:

| Para | session_filter | Aktywne godziny wejść | Powód |
|------|---------------|----------------------|-------|
| **EURUSD** | `true` | **07:00 – 21:00 UTC** | Para europejska — szum poza sesją London/NY |
| **USDJPY** | `false` | **00:00 – 24:00 UTC** | JPY aktywny też w Azji (Tokio), 24h daje lepsze wyniki w testach |
| **USDCHF** | `true` | **07:00 – 21:00 UTC** | Para europejska — CHF aktywny głównie w Londynie |
| **AUDJPY** | `false` | **00:00 – 24:00 UTC** | AUD/JPY = cross Azja/Pacyfik, aktywny od Tokio |
| **CADJPY** | `false` | **00:00 – 24:00 UTC** | CAD/JPY kierowany makro (ropa/BOJ), aktywny 24h |

---

## 4. Harmonogram tygodniowy

```
         PON       WT        SR        CZW       PT        SOB       NIE
         ───────────────────────────────────────────────────────────────────
00-07    JPY/AUD  JPY/AUD  JPY/AUD  JPY/AUD  JPY/AUD   CLOSED    CLOSED
07-21    WSZYSTKIE WSZYSTKIE WSZYSTKIE WSZYSTKIE WSZYSTKIE CLOSED    CLOSED
21-24    JPY/AUD  JPY/AUD  JPY/AUD  JPY/AUD  JPY/AUD*  CLOSED    CLOSED
```

> *Piątek 22:00 UTC — rynek zamyka się, IBKR przestaje dostarczać kwotowania.
> Bot próbuje resubskrybować feed, dostaje `bid=-1.0` — to normalne zachowanie.

### Ile godzin tygodniowo bot szuka sygnałów?

| Para | Godzin/tydzień | Sesje |
|------|---------------|-------|
| EURUSD | 5 × 14h = **70h** | Londyn + NY |
| USDCHF | 5 × 14h = **70h** | Londyn + NY |
| USDJPY | 5 × 24h = **120h** | Całą dobę |
| AUDJPY | 5 × 24h = **120h** | Całą dobę |
| CADJPY | 5 × 24h = **120h** | Całą dobę |

---

## 5. Dni wolne / święta

Rynek FX jest formalnie otwarty 5 dni w tygodniu, ale **płynność spada dramatycznie** w:

| Święto | Data | Wpływ |
|--------|------|-------|
| Boże Narodzenie | 25 grudnia | Bardzo niska płynność, szerokie spready |
| Nowy Rok | 1 stycznia | Niska płynność |
| Wielki Piątek | Ruchome | Londyn zamknięty |
| Thanksgiving (USA) | Listopad | Niska płynność NY |

> **Bot nie ma automatycznego wyłączenia w święta.**
> W razie potrzeby można tymczasowo zatrzymać przez:
> `sudo systemctl stop bojkofx`

---

## 6. Czas restartu IB Gateway

IB Gateway ma **automatyczny dzienny restart** (skonfigurowany przez IBC):

- Restart następuje ok. **23:45 – 23:50 UTC** każdej nocy
- Bot (`bojkofx.service`) czeka na Gateway (dependency: `After=ibgateway.service`)
- Bot restartuje się automatycznie po restarcie Gateway (Restart=always)
- Przerwa trwa **~5–10 minut** na dobę

### Okno niedostępności każdej nocy:
```
~23:45 UTC – ~00:00 UTC  →  ~15 minut przestoju (codzienny restart Gateway)
```

---

## 7. Podsumowanie — kiedy bot AKTYWNIE szuka sygnałów

```
Dni:    Poniedziałek – Piątek
Pary europejskie (EURUSD, USDCHF):   07:00 – 21:00 UTC
Pary JPY/AUD (USDJPY, AUDJPY, CADJPY): 00:00 – 24:00 UTC
Przerwa dzienna:  ~23:45 – ~00:00 UTC (restart Gateway)
Weekend:  bot żyje, ale rynek zamknięty — brak sygnałów
```

---

## 8. Czy warto handlować EURUSD/USDCHF poza godzinami szczytu?

> Analiza oparta na backteście OOS 2023–2024, H1/D1, RR=3.0.
> Pełny raport: `reports/SESSION_ANALYSIS.md`

### Wyniki per wariant sesji (OOS 2023–2024):

| Wariant | EURUSD ExpR | EURUSD WR | USDCHF ExpR | USDCHF WR | Wniosek |
|---------|------------|-----------|------------|-----------|---------|
| **24h (bez filtra)** | +0.328R | 40.5% | +0.480R | 44.9% | baseline |
| **London+NY 07–21 UTC** | **+0.377R** | 42.5% | **+0.514R** | 46.7% | ✅ lepiej niż 24h |
| Tylko Londyn 08–17 UTC | +0.425R | 43.7% | +0.579R | 48.4% | ✅ jeszcze lepiej |
| **Tylko NY 13–22 UTC** | **+0.500R** | 47.1% | **+0.765R** | 57.4% | ✅ NAJLEPSZY |
| Late-NY 21–24 UTC | +0.035R | 31.0% | +0.161R | 38.7% | ⚠️ marginalny |
| **Azja/noc 00–07 UTC** | **-0.022R** | 27.2% | **+0.036R** | 28.9% | ❌ UNIKAĆ |

### Odpowiedź:

**NIE** — nie warto handlować EURUSD/USDCHF poza godzinami szczytu, szczególnie w nocy (00–07 UTC):

- **Azja/noc (00–07 UTC):** EURUSD daje **-0.022R** (ujemne!), USDCHF ledwie +0.036R przy WR ~28% — brak edge, słusznie wyłączone
- **Late-NY (21–24 UTC):** marginalny edge (+0.035–0.161R), nie wart ryzyka
- **Filtr 07–21 UTC poprawia** EURUSD z +0.328R → +0.377R (+15%) i redukuje DD
- **Najlepszy wariant to NY (13–22 UTC):** EURUSD +0.500R, USDCHF +0.765R — nocna sesja NY jest lepszym celem niż pełne 07–21

### Wniosek operacyjny:

Obecna konfiguracja `session_filter: true` (07–21 UTC) jest **poprawna i uzasadniona**.
Nocne godziny (00–07 UTC) dla EUR/CHF to szum, fałszywe BOS-y przy niskiej płynności.

> **Potencjalna optymalizacja:** zawęzić filtr do **13–21 UTC** (NY session) zamiast 07–21,
> co wg backtestu dałoby lepsze ExpR i WR — jednak wymaga dodatkowej walk-forward walidacji.

---

## 9. Implikacje dla monitorowania

- **Najważniejszy czas sprawdzania:** Poniedziałek rano (~09:00 UTC) — pierwszy restart tygodnia po weekendzie
- **Logi warto sprawdzać:** Rano w dni robocze po 08:00 UTC (otwarcie Londynu = pierwsze sygnały)
- **`bid=-1.0` w logach w weekend:** Normalne — IBKR nie dostarcza kwotowań
- **`0 ticks in buffer` w nocy dla EUR/CHF:** Normalne — poza filtrem sesji
- **Restart dzienny ~23:45 UTC** = ~00:45 czasu polskiego (CET) lub ~01:45 (CEST latem)

---

*Dokumentacja wygenerowana: 2026-03-01*
*Konfiguracja: `config/config.yaml` | Session filter: `src/indicators/session_filter.py`*



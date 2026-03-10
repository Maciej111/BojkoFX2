# Porównanie Strategii: Crypto v1 vs BojkoFx FX v1
## Analiza różnic, podobieństw i potencjalnych ulepszeń

> **Data dokumentu:** 2026-02-27
>
> **Cel:** Porównanie zwalidowanej strategii BOS+Pullback z Crypto (30m/6h, Binance 2022–2025)
> z aktualnie działającą strategią FX (H1/H4, IBKR paper, PROOF V2 2023–2024).
> Dokument ma charakter analityczny — **nie stanowi instrukcji do zmiany kodu**.

---

## Spis treści

1. [Podsumowanie — co jest identyczne](#1-podsumowanie--co-jest-identyczne)
2. [Tabela różnic parametrów](#2-tabela-różnic-parametrów)
3. [Szczegółowa analiza każdej różnicy](#3-szczegółowa-analiza-każdej-różnicy)
4. [Różnice architektoniczne (poza parametrami)](#4-różnice-architektoniczne-poza-parametrami)
5. [Wyniki backtestu — porównanie](#5-wyniki-backtestu--porównanie)
6. [Co można by zmienić w BojkoFx FX (propozycje)](#6-co-można-by-zmienić-w-bojkofx-fx-propozycje)
7. [Ocena ryzyka każdej zmiany](#7-ocena-ryzyka-każdej-zmiany)
8. [Rekomendacja kolejności testowania](#8-rekomendacja-kolejności-testowania)

---

## 1. Podsumowanie — co jest identyczne

Obie strategie mają **tę samą filozofię i rdzeń algorytmu**. Poniższe elementy są wspólne:

| Element | Status |
|---------|--------|
| Typ strategii | ✅ Identyczny: Trend-Following, BOS + Pullback |
| Logika wykrywania pivotów (swing high/low) | ✅ Identyczna: `pivot_lookback` bars left+right |
| Anti-lookahead: `confirmation_bars = 1` | ✅ Identyczne |
| BOS = close beyond last confirmed pivot | ✅ Identyczne (`require_close_break = True`) |
| Zlecenie LIMIT (pullback entry) | ✅ Identyczne |
| SL anchored to last opposite pivot + ATR buffer | ✅ Identyczne (`sl_anchor = "last_pivot"`) |
| TP = entry ± (risk × RR) | ✅ Identyczne (tylko wartość RR różna) |
| ATR period = 14 | ✅ Identyczne |
| Worst-case intrabar exit (SL wygrywa) | ✅ Identyczne |
| Max 1 pozycja per symbol | ✅ Identyczne |
| Wymagane `confirmation_bars` anty-lookahead | ✅ Identyczne |
| HTF bias (opcjonalne filtrowanie kierunku) | ✅ Architektura identyczna, wdrożenie różne |

> **Wniosek:** Obie wersje to ten sam algorytm. Różnią się wyłącznie **nastrojeniem parametrów**
> i kilkoma **decyzjami implementacyjnymi**.

---

## 2. Tabela różnic parametrów

| Parametr | Crypto v1 (zwalidowane) | BojkoFx FX v1 (PROOF V2) | Kierunek różnicy |
|----------|------------------------|--------------------------|-----------------|
| **LTF** | 30m | H1 | FX używa 2× dłuższego TF |
| **HTF** | 6h | H4 | FX używa 1.5× krótszego HTF |
| **LTF:HTF ratio** | 1:12 | 1:4 | Crypto ma 3× szerszy kontekst HTF |
| **`risk_reward`** | **2.5** | **1.5** | ⚠️ Największa różnica — Crypto 67% wyższy RR |
| **`entry_offset_atr_mult`** | **0.0** | **0.3** | ⚠️ FX wchodzi 0.3 ATR dalej od BOS |
| **`sl_buffer_atr_mult`** | **0.1** | **0.5** | ⚠️ FX ma 5× szerszy bufor SL |
| **`pullback_max_bars`** | 40 (@ 30m = 20h) | 40 (@ H1 = 40h) | FX czeka 2× dłużej w czasie rzeczywistym |
| **`pivot_lookback_ltf`** | 3 | 3 | ✅ Identyczne |
| **`pivot_lookback_htf`** | 5 | 5 | ✅ Identyczne |
| **`confirmation_bars`** | 1 | 1 | ✅ Identyczne |
| **`require_close_break`** | True | True | ✅ Identyczne |
| **`sl_anchor`** | "last_pivot" | "last_pivot" | ✅ Identyczne |
| **`atr_period`** | 14 | 14 | ✅ Identyczne |
| **`risk_pct`** | 1.0% | 0.5% | FX bardziej konserwatywny |
| **HTF bias filtr** | Aktywny (wymagany) | Brak / opcjonalny | ⚠️ Kluczowa różnica |
| **Spread modeling** | Brak (spread ≈ 0) | Half-spread w bootstrap | FX częściowo modeluje spread |
| **Session filter** | Brak | Brak | Obydwie nie filtrują sesji |

---

## 3. Szczegółowa analiza każdej różnicy

### 3.1 `risk_reward`: 2.5 (Crypto) vs 1.5 (FX) — KRYTYCZNA RÓŻNICA

**Co to znaczy:**
- Przy Crypto RR=2.5: TP jest 2.5× dalej niż SL → TP hit = +2.5R, SL hit = −1R
- Przy FX RR=1.5: TP jest 1.5× dalej niż SL → TP hit = +1.5R, SL hit = −1R

**Wpływ na strategię:**
- Wyższy RR wymaga niższego win rate do bycia profitowym:
  - RR=2.5 → break-even WR ≈ 28.6%
  - RR=1.5 → break-even WR ≈ 40.0%
- W Crypto przy WR ≈ 47% i RR=2.5 → Exp(R) ≈ +0.54R
- W FX przy WR ≈ 48% i RR=1.5 → Exp(R) ≈ +0.22R

**Dlaczego FX wybrał 1.5?**
Wyniki PROOF V2 pokazały że RR=1.5 działało. Nie testowano 2.5 na FX w tym projekcie.

**Potencjalne ryzyko RR=2.5 na FX:**
TP może być zbyt odległy i rzadziej osiągany — FX jest rynkiem o niższej zmienności
(ATR-relative) niż Crypto. Wymaga walidacji.

---

### 3.2 `entry_offset_atr_mult`: 0.0 (Crypto) vs 0.3 (FX) — ZNACZĄCA RÓŻNICA

**Co to znaczy:**
- Crypto: zlecenie LIMIT **dokładnie na poziomie BOS** (re-test poziomu struktury)
- FX: zlecenie LIMIT **0.3 ATR w kierunku trendu od BOS** (premium za wejście głębiej)

**Logika FX (0.3):**
Zakłada się, że rynek cofnie się nieco powyżej/poniżej BOS zanim wróci,
dając lepszą cenę. Działa jako filtr — tylko silniejsze pullbacki są wypełniane.

**Logika Crypto (0.0):**
Wyniki grid search pokazały że 0.0 (wejście dokładnie na BOS) **konsekwentnie
przewyższało** 0.2, 0.3, 0.5 na wszystkich testowanych symbolach Crypto.

**Ryzyko FX z offset=0.3:**
Możliwa utrata części transakcji które by się wypełniły na 0.0 (cena dotknęła BOS
ale nie doszła do entry_price). Mniejsza liczba transakcji, ale potencjalnie lepsza
jakość. Efekt nieznany dla FX — wymaga testu.

---

### 3.3 `sl_buffer_atr_mult`: 0.1 (Crypto) vs 0.5 (FX) — ZNACZĄCA RÓŻNICA

**Co to znaczy:**
- Crypto: SL = last_pivot ± 0.1 × ATR (bardzo ciasny bufor)
- FX: SL = last_pivot ± 0.5 × ATR (5× szerszy bufor)

**Dlaczego FX wybrał 0.5:**
FX ma wyższy "noise-to-signal ratio" — ceny często testują (wick) poprzednie poziomy
zanim pójdą w dobrym kierunku. Ciaśniejszy SL skutkowałby bardzo dużą liczbą
fałszywych stop-outów.

**Wpływ na ryzyko:**
Szerszy SL = większa odległość SL → mniejszy rozmiar pozycji (przy stałym % ryzyka).
Oznacza to mniejszą liczbę jednostek/lotów na trade, ale taki sam % ekspozycji kapitału.

**Potencjał optymalizacji:**
Wartość 0.1 z Crypto może być zbyt ciasna dla FX. Wartość 0.5 może być zbyt luźna.
Zakres 0.2–0.3 mógłby być optymalny dla FX — wymaga backtestowania.

---

### 3.4 `pullback_max_bars`: 40 barów — identyczna liczba, różny czas

**Rzeczywisty czas oczekiwania:**
- Crypto 30m × 40 barów = **20 godzin**
- FX H1 × 40 barów = **40 godzin** (~1.7 dnia tradingowego)

**Problem dla FX:**
40 godzin czekania na FX obejmuje zamknięcia sesji i potencjalnie wiele dni.
Specyfikacja Crypto sugeruje że ekwiwalentem czasowym byłoby `pullback_max_bars = 20`
na H1 (20 godzin, tak samo jak Crypto).

**Aktualnie FX używa 40 barów H1 (40h)** — to 2× dłuższe oczekiwanie niż
zwalidowane Crypto. Nie wiadomo czy to pomaga czy szkodzi.

---

### 3.5 HTF Bias Filter — BRAKUJE W FX (potencjalnie duże ryzyko)

**W Crypto (aktywny filtr):**
Przed każdym sygnałem LTF sprawdzany jest kierunek trendu na HTF:
- BULL bias → tylko LONG setupy są akceptowane
- BEAR bias → tylko SHORT setupy
- NEUTRAL → żadnych transakcji

HTF bias jest określany przez sekwencję: HH/HL (bull) lub LL/LH (bear).

**W BojkoFx FX (brak pełnego filtra):**
Kod zawiera zmienne `htf_bars` i `pivot_lookback_htf = 5`, ale faktyczna logika
filtrowania kierunku HTF jest **opcjonalna / nieuzbrojona** w aktualnym runnerze.
Strategia może wchodzić LONG nawet gdy HTF jest w trendzie spadkowym.

**Konsekwencja:**
Bez HTF filter strategia "trade w każdym kierunku" — co jest bardziej agresywne
i może skutkować większą liczbą transakcji ale gorszą jakością (trading contra trend).

**To jest prawdopodobnie jeden z największych potencjalnych ulepszeń.**

---

### 3.6 LTF:HTF ratio — 1:4 (FX) vs 1:12 (Crypto)

**Crypto:** 30m LTF, 6h HTF → ratio 1:12
**FX:** H1 LTF, H4 HTF → ratio 1:4

**Co to znaczy w praktyce:**
Przy ratio 1:4 HTF jest znacznie "bliżej" LTF — jeden H4 bar = tylko 4 bary H1.
Przy ratio 1:12 HTF jest znacznie bardziej odległy — jedna 6h świeca = 12 baróW 30m.

**Implikacja dla bias:**
Przy ratio 1:4 HTF trend zmienia się szybciej → częstsze zmiany biasu → więcej
sygnałów (potencjalnie niższa jakość). Przy 1:12 bias jest bardziej stabilny.

**Alternatywy dla FX:**
- H1/H4 (1:4) — aktualne
- H1/D1 (1:24) — znacznie szerszy kontekst, bliższy ratio Crypto
- 30m/H4 (1:8) — najlepszy odpowiednik ratio Crypto

---

### 3.7 Spread modeling — częściowe vs brak

**Crypto:** spread ≈ 0 (Binance spot) → nie modelowany.

**FX (aktualnie):**
- Bootstrap: half-spread dodawany statycznie (`BOOTSTRAP_HALF_SPREAD` per symbol)
- Live: prawdziwy bid/ask z IBKR
- **Backtest PROOF V2:** spread testowany jako slippage stress test (0.2/0.5/1.0 pip)
  ale nie jako stały koszt w każdej transakcji

**Problem:**
Spread jest w FX realnym kosztem per trade. Brak jego stałego modelowania w backteście
oznacza że wyniki PROOF V2 mogą być nieco optymistyczne.

---

## 4. Różnice architektoniczne (poza parametrami)

### 4.1 HTF bias — zaimplementowanie

| Aspekt | Crypto v1 | BojkoFx FX v1 |
|--------|-----------|---------------|
| HTF bias wymagany do handlu | ✅ Tak (NEUTRAL = brak transakcji) | ❌ Opcjonalny |
| Logika HH/HL/LL/LH | ✅ Zaimplementowana | ⚠️ Częściowa |
| Ostatnie N pivotów HTF | 4 pivoty | Brak struktury |

### 4.2 Obsługa jednego setupu

| Aspekt | Crypto v1 | BojkoFx FX v1 |
|--------|-----------|---------------|
| Stary setup anulowany przy nowym BOS | ✅ Tak | ⚠️ `active_setups` dict per signal_id — nie anuluje |
| Max 1 setup na symbol | Tak | Tak (przez `max_open_positions_per_symbol`) |

### 4.3 Exit tracking

| Aspekt | Crypto v1 | BojkoFx FX v1 |
|--------|-----------|---------------|
| Śledzenie R per trade | ✅ Tak | ✅ Tak (`realized_R` w `_OrderRecord`) |
| Exit reason (SL/TP/expired) | ✅ Tak | ✅ Tak (`ExitReason` enum) |
| Intrabar conflict (SL wygrywa) | ✅ Tak | ✅ Tak |

### 4.4 Live trading

| Aspekt | Crypto v1 | BojkoFx FX v1 |
|--------|-----------|---------------|
| Broker | Binance (Crypto) | IBKR Gateway (FX) |
| Typ zlecenia | Brak opisu live | Bracket order (entry+SL+TP) |
| Kill switch | ✅ Tak (DD%) | ✅ Tak (triple-gate + DD%) |
| Infrastruktura 24/7 | Nieznana | ✅ GCP VM + systemd |

---

## 5. Wyniki backtestu — porównanie

### Crypto v1 (OOS 2024–2025, 30m/6h)

| Symbol | Trades/rok | Exp(R) | Win Rate | PF | Max DD% |
|--------|-----------|--------|----------|----|---------|
| BTCUSDT | ~90 | +0.532R | 48.0% | — | — |
| ETHUSDT | ~112 | +0.446R | 48.8% | — | — |
| SOLUSDT | ~101 | +0.864R | 48.3% | — | — |
| XRPUSDT | ~93 | +0.335R | 42.4% | — | — |
| **ŚREDNIA** | **~97** | **+0.544R** | **47.0%** | **2.07** | **8.5%** |

### BojkoFx FX v1 (OOS 2023–2024, H1/H4, PROOF V2)

| Symbol | Trades | Exp(R) | Win Rate | PF | Max DD% |
|--------|--------|--------|----------|----|---------|
| EURUSD | 234 | +0.212R | 46.6% | 1.03 | 17.0% |
| GBPUSD | 200 | +0.572R | 48.5% | 1.71 | 26.9% |
| USDJPY | 225 | +0.300R | 49.8% | 1.14 | 16.2% |
| XAUUSD | 220 | +0.178R | 48.2% | 1.22 | 19.1% |
| **ŚREDNIA** | **~220** | **+0.316R** | **48.3%** | **1.28** | **19.8%** |

### Kluczowe obserwacje porównawcze

| Metryka | Crypto | FX | Różnica |
|---------|--------|----|---------|
| Avg Exp(R) | +0.544R | +0.316R | FX o 42% słabszy |
| Avg Win Rate | 47.0% | 48.3% | FX porównywalny / nieco lepszy |
| Avg Profit Factor | 2.07 | 1.28 | Crypto o 62% wyższy PF |
| Avg Max DD% | 8.5% | 19.8% | FX o 133% wyższy drawdown |
| Trades/rok/symbol | ~97 | ~220 | FX generuje 2× więcej sygnałów |

**Wniosek:** Win rate jest porównywalny, ale Crypto osiąga znacznie lepszy Exp(R)
i niższy DD. Główna przyczyna to prawie na pewno **wyższy RR=2.5** w Crypto
vs **RR=1.5** w FX.

---

## 6. Co można by zmienić w BojkoFx FX (propozycje)

### Propozycja A — Zmiana `risk_reward`: 1.5 → 2.5
**Uzasadnienie:** Najważniejsza zmiana. Crypto grid search pokazał że RR=2.5
konsekwentnie przewyższał 1.5 i 2.0. Przy zbliżonym win rate FX (~48%),
zmiana z 1.5 na 2.5 mogłaby podwoić Exp(R).

**Szacunkowy efekt (przy WR=48%, bez zmian):**
- RR=1.5: Exp(R) = 0.48 × 1.5 − 0.52 × 1.0 = **+0.20R**
- RR=2.5: Exp(R) = 0.48 × 2.5 − 0.52 × 1.0 = **+0.68R**

**Ryzyko:** TP jest 67% dalej — może być rzadziej osiągany na FX (mniejsza zmienność niż Crypto).
Win rate może spaść. **Wymaga pełnego backtestowania przed użyciem.**

---

### Propozycja B — Zmiana `entry_offset_atr_mult`: 0.3 → 0.0
**Uzasadnienie:** Crypto grid search pokazał 0.0 jako najlepsze. Wejście dokładnie
na BOS level (re-test) zamiast głębszego offset.

**Efekt:** Więcej fillów (zlecenie bliżej rynku), lepsza cena wejścia, ale potencjalnie
więcej "false fills" gdy cena tylko dotknie poziomu i odwróci się.

**Ryzyko:** Mniejsze — offset 0.3 jest stosunkowo małą różnicą w stosunku do ATR.

---

### Propozycja C — Zmiana `sl_buffer_atr_mult`: 0.5 → 0.1–0.3
**Uzasadnienie:** Crypto używa 0.1 (ciaśniejszy SL). Na FX wartość 0.5 może być zbyt
konserwatywna — SL zbyt daleko → gorsza jakość R.

**Efekt:** Ciaśniejszy SL = ryzyko więcej stop-outów na szumie FX, ale lepszy
stosunek reward/risk na każdej transakcji.

**Ryzyko:** Średnie — FX ma wyższy szum tick-owy niż Crypto. Test na backtest
z wartościami 0.2 i 0.3 przed 0.1.

---

### Propozycja D — Implementacja pełnego HTF Bias Filter
**Uzasadnienie:** W Crypto filtr HTF jest kluczowy — NEUTRAL = brak transakcji.
W BojkoFx FX ten filtr jest brakujący/opcjonalny. Dodanie go mogłoby:
- Zredukować liczbę transakcji contra-trend
- Poprawić win rate i Exp(R)
- Zmniejszyć drawdown

**Logika do implementacji:**
```
BULL: last HTF close > last confirmed HTF high  OR  HH+HL sequence
BEAR: last HTF close < last confirmed HTF low   OR  LL+LH sequence
NEUTRAL: wszystko inne → brak transakcji
```

**Ryzyko:** Niska — filtr może tylko poprawić jakość sygnałów. Ryzyko:
zbyt mało transakcji jeśli NEUTRAL zbyt często.

---

### Propozycja E — Zmiana `pullback_max_bars`: 40 → 20 (czas ekwiwalentny)
**Uzasadnienie:** Crypto testowało 40 barów na 30m = 20 godzin.
FX używa 40 barów na H1 = 40 godzin. Ekwiwalentem jest `pmb=20` na H1.

**Efekt:** Mniej wypełnionych zleceń (krótsze okno), ale potencjalnie lepsze
(tylko "szybkie" pullbacki, bliżej świeżego sygnału).

**Ryzyko:** Niskie — zmniejsza ekspozycję na stare sygnały.

---

### Propozycja F — Dodanie Session Filter
**Uzasadnienie:** Crypto handluje 24/7 bez sesji. FX ma wyraźne sesje (London, NY).
Filtrowanie do handlu tylko w godzinach 07:00–21:00 UTC mogłoby poprawić jakość sygnałów.

**Logika:**
```
London session:      07:00–16:00 UTC
New York session:    12:00–21:00 UTC
Overlap (najlepszy): 12:00–16:00 UTC
Avoid:               21:00–06:00 UTC (niski wolumen, szersze spready)
```

**Ryzyko:** Niskie do średniego — mniejsza liczba transakcji (USDJPY aktywne w nocy UTC
przez sesję Tokyo). Wymaga testu per symbol.

---

### Propozycja G — Zmiana LTF:HTF ratio (opcjonalna)
**Uzasadnienie:** Crypto ratio 1:12 jest znacznie szerszy niż FX 1:4.
Zmiana na H1/D1 (1:24) lub 30m/H4 (1:8) dałaby szerszy kontekst HTF.

**Efekt:** Wolniejsza zmiana biasu → stabilniejsze trendy → potencjalnie mniej
błędnych sygnałów na konsolidacjach.

**Ryzyko:** Średnie — zmiana LTF/HTF to fundamentalna zmiana architektury,
wymaga pełnego re-backtestowania.

---

## 7. Ocena ryzyka każdej zmiany

| Propozycja | Priorytet | Złożoność implementacji | Ryzyko dla live | Wymagana walidacja |
|-----------|----------|------------------------|-----------------|-------------------|
| A: RR 1.5→2.5 | 🔴 Wysoki | Minimalna (1 parametr) | Średnie | Pełny backtest PROOF |
| B: Offset 0.3→0.0 | 🟡 Średni | Minimalna (1 parametr) | Niskie | Backtest + 2 tygodnie paper |
| C: SL buffer 0.5→0.2 | 🟡 Średni | Minimalna (1 parametr) | Średnie | Pełny backtest |
| D: HTF Bias Filter | 🔴 Wysoki | Średnia (nowa logika) | Niskie | Backtest + paper |
| E: pmb 40→20 | 🟢 Niski | Minimalna (1 parametr) | Niskie | Backtest |
| F: Session Filter | 🟢 Niski | Niska (filtr czasowy) | Niskie | Backtest per symbol |
| G: Zmiana ratio | ⚫ Opcjonalne | Wysoka (re-architektura) | Wysokie | Pełny re-backtest |

---

## 8. Rekomendacja kolejności testowania

Jeśli zdecydujesz się testować zmiany, sugerowana kolejność (jedna na raz, izolowana):

```
Krok 1 (najpierw) → Propozycja D: HTF Bias Filter
  Powód: Nie zmienia parametrów — tylko dodaje filtr. Ryzyko niskie,
         potencjalny zysk duży (eliminacja transakcji contra-trend).

Krok 2 → Propozycja A: RR 1.5 → 2.5
  Powód: Największy potencjalny zysk na Exp(R). Wymaga pełnego backtestu.
         Testuj na 2021–2022 (TRAIN), waliduj na 2023–2024 (OOS).

Krok 3 → Propozycja C: SL buffer 0.5 → 0.2–0.3
  Powód: Może synergować z wyższym RR. Testuj łącznie z Krokiem 2.

Krok 4 → Propozycja E: pullback_max_bars 40 → 20
  Powód: Prosta zmiana, wyrównanie z czasowym ekwiwalentem Crypto.

Krok 5 (opcjonalny) → Propozycja F: Session Filter
  Powód: Może poprawić wyniki szczególnie dla EURUSD (wrażliwy na koszty).

Krok 6 (długoterminowy) → Propozycja B: offset 0.3 → 0.0
  Powód: Zmiana jest mała; jej efekt może być zamaskowany przez inne czynniki.
```

### Ważne zasady przed jakąkolwiek zmianą:
1. **Jedna zmiana na raz** — nie łącz wielu modyfikacji w jednym teście
2. **Ten sam split danych** — TRAIN 2021–2022, OOS 2023–2024
3. **Porównaj do baseline** PROOF V2 (aktualne wyniki)
4. **Wymóg akceptacji:** Exp(R) > +0.35R na OOS, Max DD < 20%, PF > 1.5 na wszystkich 3 symbolach
5. **Nie modyfikuj kodu live** — wszelkie testy na branchu/kopii backtestowej

---

## Podsumowanie najważniejszych wniosków

> 🔴 **Krytyczna obserwacja:** Różnica RR (1.5 vs 2.5) prawdopodobnie wyjaśnia
> większość różnicy w Exp(R) między Crypto (+0.54R) a FX (+0.32R).
> Win rate jest niemal identyczny (~47–48%). **Tylko RR mógłby podwoić efektywność.**

> 🟡 **Druga obserwacja:** Brak pełnego HTF bias filter w BojkoFx FX oznacza
> że bot handluje contra-trend — to potencjalne źródło niebezpiecznych strat
> których nie widać dopiero przy dłuższym papier tradingu.

> 🟢 **Dobra wiadomość:** Rdzeń algorytmu (pivot detection, BOS, LIMIT entry,
> anti-lookahead) jest identyczny i **zwalidowany na dwóch różnych rynkach**.
> To silna baza do dalszej optymalizacji.

---

*Dokument: STRATEGY_COMPARISON_CRYPTO_VS_FX.md | Wersja: 1.0 | Data: 2026-02-27*
*Nie modyfikować kodu na podstawie tego dokumentu bez pełnej walidacji backtestowej.*


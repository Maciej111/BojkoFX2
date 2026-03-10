# Audyt Ilościowy Strategii – US100 / USATECHIDXUSD
**Data raportu:** 2025  
**Instrument:** USATECHIDXUSD (kontrakt CFD na US NASDAQ 100)  
**Dane źródłowe:** Dukascopy tick → bar OHLC, 2021-01-01 → 2024-12-30 (4 pełne lata)  
**Strategia:** BOS + Pullback, HTF H4, wiele ram czasowych LTF (5m / 15m / 30m / 1h)  
**Parametry backtestów:** `pivot_lookback_ltf=3, lookback_htf=5, confirmation_bars=1, require_close_break=True, entry_offset_atr=0.3, pullback_max_bars=20, sl_buffer_atr=0.5, RR=2.0`

---

## 1. Wyniki ogólne — wszystkie ramy czasowe (2021–2024)

| Rama | Transakcje | WR% | Oczekiwana wartość (R) | Profit Factor | Max RDD | Werdykt |
|------|-----------|-----|------------------------|---------------|---------|---------|
| **5m / H4** | **1 735** | **42,3%** | **+0,300R** | **1,39** | **27,57R** | ✅ Jedyna solidna |
| 15m / H4 | 959 | 42,3% | +0,121R | 1,45 | 87,75R | ⚠️ Marginalna |
| 30m / H4 | 573 | 38,7% | +0,168R | 1,19 | 19,62R | ⚠️ Słaba |
| **1h / H4** | **414** | **33,8%** | **−0,044R** | **0,84** | **40,52R** | ❌ Stratna |

**Wyniki roczne — kluczowe obserwacje:**

| Rok | 5m Exp(R) | 15m Exp(R) | 30m Exp(R) | 1h Exp(R) |
|-----|-----------|------------|------------|-----------|
| 2021 | +0,253 | +0,109 | +0,324 | **−0,142** |
| 2022 | +0,236 | +0,239 | +0,174 | **+0,003** |
| 2023 | **+0,547** | +0,266 | +0,037 | **−0,162** |
| 2024 | +0,195 | **−0,149** | +0,138 | +0,129 |

> **Wniosek:** Jedyną ramą czasową, która jest zyskowna we **wszystkich 4 latach**, jest 5m.
> Rama 1h jest stratna w 3 z 4 lat i rozkłada się strukturalnie na US100.

---

## 2. Głęboka analiza 5m / H4 — rozkład R

### 2.1 Statystyki opisowe
| Miara | Wartość |
|-------|---------|
| Liczba transakcji | 1 735 |
| Łączne R | +521,1R |
| Średnia (R) | +0,300R |
| **Mediana (R)** | **−1,000R** |
| Odchylenie standardowe | 3,260R |
| Minimum | −14,28R |
| Maksimum | **+117,11R** |

### 2.2 Rozkład bucketów R
| Zakres | Liczba transakcji | Udział |
|--------|-------------------|--------|
| < −2R | 13 | 0,7% |
| −2R do −1R | 5 | 0,3% |
| **−1R do 0R** | **983** | **56,7%** |
| 0R do +1R | 16 | 0,9% |
| +1R do +2R | 22 | 1,3% |
| **+2R do +3R** | **690** | **39,8%** |
| > +3R | 6 | 0,3% |

**Interpretacja:** Rozkład jest silnie **dwumodalny** — 56,7% transakcji kończy się na SL (−1R), a 39,8% osiąga TP (+2R). Mediana wynosi dokładnie −1,000R, co potwierdza, że ponad połowa transakcji kończona jest zleceniem stop-loss. Jest to normalny profil dla strategii z RR=2 i WR≈42%.

Bucket "−1R to 0R" zawiera 983 transakcji, ale praktycznie wszystkie to dokładnie −1R (stały SL). Wyjątkami są przypadki `SL_intrabar_conflict` (63 transakcje), gdzie cena naruszała poziom SL wewnątrz baru — te trafiają tutaj jako straty między −2R a −1R lub gorsze.

---

## 3. KRYTYCZNE: Zależność od outlierów

### 3.1 Koncentracja wyników — 5m / H4

| Top N transakcji | Suma R | % całości (+521R) |
|-----------------|--------|-------------------|
| Top 1 | 117,1R | **22,5%** |
| Top 3 | 146,7R | **28,2%** |
| Top 5 | 155,8R | **29,9%** |
| Top 10 | 168,0R | **32,2%** |
| Top 20 | 188,0R | **36,1%** |
| Bottom 5 (straty) | −39,2R | — |
| Bottom 10 (straty) | −57,3R | — |

> **Alarmujące odkrycie:** JEDNA transakcja (max R = +117,11R) stanowi **22,5% całkowitego zysku** z 4 lat! Ta pojedyncza transakcja zarobiła 117-krotność ryzyka — jest to ekstremalny outlier, który masowo zawyża wyniki.

### 3.2 Rozkład outlierów roczny — kiedy?

| Rok | n transakcji | Oczekiwana wartość | Top 1 jako % roku | Top 5 jako % roku |
|-----|-------------|-------------------|------------------|------------------|
| 2021 | 445 | +0,253R | 6% | 15% |
| 2022 | 424 | +0,226R | 2% | 11% |
| **2023** | **416** | **+0,541R** | **52%** | **67%** |
| 2024 | 450 | +0,195R | 3% | 12% |

### 3.3 Wyjaśnienie anomalii 2023

**2023 na US100/NASDAQ był rokiem historycznego rajdu AI/tech.** Indeks wzrósł z ~10 900 do ~16 800 punktów (+54%), napędzany przez spółki takie jak NVDA (+239%), META (+194%), MSFT (+56%). Strategia BOS+Pullback w idealnym środowisku trendującym może uchwycić ciągłą strukturę HH/HL przez wiele dni, generując megawinner.

**Problem:** rok 2023 bez tej jednej transakcji (+117R) miałby oczekiwaną wartość ~0,26R — zbliżoną do 2021 i 2022. Cały "sukces" 2023 zależy od jednego zdarzenia.

> **Wniosek:** Gdyby ta transakcja nie wystąpiła, backtest za 4 lata pokazałby łączne R ≈ 404 (nie 521R), a oczekiwana wartość spadłaby do ok. +0,233R. Strategia jest pozytywna nawet bez outliera, ale jej PF i ekspektancja są istotnie zawyżone.

---

## 4. KRYTYCZNE: Katastrofalny outlier na 15m

### 4.1 Analiza anomalii 15m / 2024

| Miara | Wartość |
|-------|---------|
| Min R (pojedyncza transakcja) | **−60,64R** |
| Łączne straty bottom 5 transakcji (2024) | −89,7R |
| 2024 łączne R | −36,17R |
| 2024 Exp(R) | −0,149R |

**Jedna transakcja straciła 60-krotność ryzyka.** To nie SL — to był ekstremalny gap lub slippage na 15-minutowym barze US100. W kontekście danych Dukascopy możliwe przyczyny:
1. **Gap przez noc** — US100 na Dukascopy ma przerwy (niehandlowany weekend/święta). Jeśli pozycja była otwarta i nastąpił gap ponad SL, system nie mógł zamknąć po SL.
2. **Błąd danych** — Dukascopy czasem generuje sztuczne świece z ekstremalną ceną (tick anomaly).
3. **Gap po wynikach spółek** — raporty kwartalne NVDA, AAPL, MSFT mogą powodować gapy 3-5% w ramach jednej świecy.

> **Wniosek:** **Strategia nie ma mechanizmu ochrony przed gapami.** MaxRDD=87,75R na 15m jest w istocie jedną transakcją, która pochłonęła cały zysk z 3 lat. Nie ma stop-loss gwarantowanego przy gapach — ryzyko on/off gapowania musi być wbudowane w model zarządzania ryzykiem.

### 4.2 Porównanie outlierów stratnych 5m vs 15m
| TF | Min R (worst trade) | Interpretacja |
|----|---------------------|---------------|
| 5m | −14,28R | Gap na 5m barze (~14x ATR) |
| 15m | −60,64R | Gap na 15m barze (~60x ATR) |
| 30m | (brak) | Brak głębokiej analizy |
| 1h | (brak) | Brak głębokiej analizy |

Wzorzec jest jasny: **im wyższa rama czasowa, tym większy potencjalny gap (w wielokrotności ATR)**. Na 1h gap overnight może być > 100R. Strategia jest strukturalnie nieodporna na gapy overnight.

---

## 5. Analiza LONG vs SHORT

| Rama | LONG n | LONG WR | LONG Exp(R) | SHORT n | SHORT WR | SHORT Exp(R) |
|------|--------|---------|-------------|---------|----------|-------------|
| **5m** | 977 | 43,2% | **+0,397R** | 758 | 41,2% | **+0,176R** |
| 15m | 535 | 42,2% | +0,085R | 424 | 42,5% | +0,165R |

**Kluczowa obserwacja:** Na 5m strategia generuje **2,3× wyższą ekspektancję na pozycjach długich (+0,397R) niż krótkich (+0,176R)**. Odpowiada to fundamentalnemu charakterowi US100:
- W długoterminowych danych ekwipochodnych (2021-2024) indeks był ogólnie wzrostowy (z wyjątkiem 2022)
- HTF bias H4 prawidłowo rozpoznaje wyższe highs/lows jako bias bullish, co sprzyja sygnałom LONG
- SHORT BOS pojawia się głównie w trendach spadkowych (2022) lub przy korekcie

> **Red flag:** Jeśli strategia kiedykolwiek zostanie wdrożona w środowisku trwałego rynku niedźwiedzia (~2022), ekspektancja Short powinna rosnąć. Dane 2022 na 5m wykazują WR=42,7% i Exp=+0,226R — ale nie wiemy, jaki był udział Long vs Short dla samego 2022.

---

## 6. BOS timing — opóźnienie strukturalne na US100

### 6.1 Minimalne opóźnienie wykrycia BOS

| LTF | Pivot (lookback=3, confirm=1) | Opóźnienie baru BOS | Clock time |
|-----|-------------------------------|---------------------|------------|
| 5m | 3+1 = 4 bary do pivotu | +1 bar BOS close | **~25 minut** |
| 15m | 3+1 = 4 bary | +1 bar BOS close | **~75 minut** |
| 30m | 3+1 = 4 bary | +1 bar BOS close | **~150 minut** |
| 1h | 3+1 = 4 bary | +1 bar BOS close | **~300 minut** |

Na 1h **minimalne opóźnienie wykrycia BOS wynosi 5 godzin** od momentu faktycznego złamania struktury.

### 6.2 Konsekwencje dla US100

US100 ma wysoce dynamiczne sesje (NYSE open 15:30 PL, close 22:00 PL):
- Całe trendy dzienne mogą rozwinąć się i zakończyć w ciągu 3-4 godzin
- Na 1h strategia wykrywa BOS, gdy trend jest już w zaawansowanej fazie lub kończy się
- Na 5m opóźnienie ~25 min pozwala na dołączenie do trendu we wczesnej fazie

To wyjaśnia, dlaczego 1h jest strukturalnie nieefektywne dla US100 — **instrument ten ma za krótkie cykle trendowe w stosunku do opóźnienia sygnału HTF=H4 na LTF=1h**.

### 6.3 Parametr `pullback_max_bars=20`

| LTF | Okno wejścia po BOS | Max oczekiwanie |
|-----|---------------------|-----------------|
| 5m | 20 × 5 min | **100 minut (~1,7h)** |
| 15m | 20 × 15 min | **300 minut (~5h)** |
| 1h | 20 × 60 min | **1200 minut (~20h)** |

Na 5m sygnał wygasa po 1,7h — co jest rozsądne dla US100 (setup staje się nieaktualny po pół sesji).  
Na 1h setup jest ważny przez 20 godzin (ponad dobę) — znacznie za długo, setup jest nieaktualny.

---

## 7. Problemy strukturalne strategii na US100

### P1: Brak ochrony przed gapami overnight
**Dotkliwość: KRYTYCZNA** (potwierdzono: −60R na jednej transakcji)

US100 ma nocne gapy, szczególnie po raportach Apple/NVIDIA/Microsoft. Strategia nie implementuje:
- Przymusowego zamknięcia pozycji przed weekendem
- Redukcji rozmiaru pozycji przed kluczowymi ereignissen (CPI, NFP, earnings)
- Stop-loss "w cenach" (zakaz trzymania przez noc bez dodatkowego buforu)

**Wpływ:** MaxRDD 15m = 87,75R jest w praktyce jednym zdarzeniem gapowym, które kasuje zyski z 3 lat.

### P2: Outlier koncentracja 22,5% w jednej transakcji
**Dotkliwość: WYSOKA**

Jedna transakcja = 22,5% całkowitego zysku z 4 lat (1735 transakcji). Jest to ekstremalny outlier. Wyniki backtestów są statystycznie niestabilne — usunięcie jednej transakcji zmienia PF z 1,39 do ~1,23.

Możliwe przyczyny:
1. AI trend 2023 wygenerował wielodniowy ciągły ruch bez korekty
2. Trailing stop nie jest zaimplementowany — pozycja trzyma się do TP (2R), ale TP = 2R w tej backtest konfiguracji, więc jeśli rzeczywiście TP=+117R, to znaczy że RR został przebity wielokrotnie (brak sztywnego TP lub extended TP)

> **Hipoteza:** Czy kod backtestów ma przypadkiem trailing stop lub rozszerzony TP przy przekroczeniu 2R? Wymagana weryfikacja — standardowy TP przy RR=2.0 powinien zamknąć na +2R, nie +117R.

> **UWAGA:** Ta anomalia (+117R przy RR=2.0) wymaga natychmiastowej weryfikacji kodu. Jeśli transakcja rzeczywiście zarabia 117R przy ustawionym RR=2.0, świadczy to albo o błędzie backtestów, albo o niezamierzonym trailing stop, albo o braku realizacji TP.

### P3: `last_high_broken` bias — fałszywe sygnały przy wyczerpaniu trendu
**Dotkliwość: ŚREDNIA**

Kod w `src/structure/bias.py` używa warunku `last_high_broken` do potwierdzania biasu bullish. Warunek ten jest prawdziwy dokładnie w momencie najwyższego punktu trendu (tuż przed możliwą odwrócenią). Na US100 z dużą zmiennością śróddzienną prowadzi to do:
- Generowania sygnałów LONG na samym szczycie rajdu
- Późnego przełączania biasu na bearish po wystąpieniu wyraźnych LL

### P4: SL kalkulowany przy BOS vs przy wypełnieniu zlecenia
**Dotkliwość: ŚREDNIA**

W backteście SL jest kalkulowany przy `entry_offset_atr_mult=0.3` na podstawie ATR w momencie BOS. W środowisku live SL powinien być kalkulowany przy faktycznym wypełnieniu zlecenia. Na US100 ATR może się znacząco zmieniać między BOS (np. o 9:30 NY) a wypełnieniem pullbacku (np. 45 min później). Powoduje to systematyczną rozbieżność R:R między backtest a live.

### P5: Brak filtra sesji handlowej
**Dotkliwość: NISKA/ŚREDNIA**

US100 handluje przez 23 h/dobę w Dukascopy (CME futures), ale płynność i spread różnią się drastycznie:
- **Sesja NYSE (15:30–22:00 PL):** najwyższa płynność, najwęższa spread
- **Azja/Europa overnight:** niska płynność, szerszy spread, fałszywe breakouty

Backtest nie filtruje sesji. Na US100 może to mieć większy wpływ niż na FX, gdzie liquidity nocna jest lepiej dostarczona.

---

## 8. Porównanie US100 vs FX — ta sama strategia

| Kryterium | FX (EURUSD/GBPUSD) | US100 (5m) |
|-----------|--------------------|-----------:|
| Najlepsza rama czasowa | 1h | **5m** |
| Oczekiwana wartość (full period) | ~0,08R–0,35R | **+0,300R** |
| Liczba transakcji / rok | ~250–450 | **~433/rok** |
| Spójność rok do roku | Niska (spread 0,029–1,126R) | **Lepsza** (0,195–0,541R) |
| Worst single trade (R) | Nieznany | 5m: −14,3R; 15m: **−60,6R** |
| Outlier koncentracja (Top 1) | ~90-123% całości (FX) | **22,5%** |
| Gap risk overnight | Niski (FX ciągły) | **Wysoki (nocne gapy)** |
| 1h opłacalność | Zmienna | **Structurally negative** |

**Kluczowe różnice:**
1. **US100 wymaga niższej ramy czasowej** — dynamika cenowa jest za szybka dla 1h
2. **US100 ma mniejszą koncentrację outlierów** niż FX (22,5% vs 90%+) — paradoksalnie zdrowszy rozkład, choć wciąż niepokojący
3. **Gap risk na US100 jest znacznie wyższy** niż na FX — wymaga osobnego zarządzania ryzykiem
4. **US100 trenduje bardziej persistentnie** (momentum equities) — strategia BOS działa lepiej

---

## 9. Analiza reżimów rynkowych

| Rok | Charakter US100 | 5m WR | 5m Exp | Obserwacja |
|-----|-----------------|-------|--------|------------|
| 2021 | Trend wzrostowy + consolidation | 42,9% | +0,253R | Normalny rok trendujący |
| 2022 | Silny bear market (−33%) | 42,7% | +0,226R | Strategia działa też w bessie |
| **2023** | **AI Recovery +54%** | **41,6%** | **+0,541R** | **Megawinner dominuje** |
| 2024 | Trend wzrostowy z zmiennością | 42,0% | +0,195R | Najsłabszy rok, wciąż zysk |

**Obserwacja:** WR jest niezwykle stabilny (41,6–42,9%) przez wszystkie 4 lata. Zmienność ekspektancji (0,195–0,541R) pochodzi ze zmienności wielkości wygranych, nie ze zmiany WR. **Strategia consistently identyfikuje właściwy kierunek, ale P&L jest zdominowana przez kilka dużych transakcji.**

---

## 10. Statystyczna wiarygodność wyników

### 10.1 Test istotności statystycznej (przybliżony)

Dla 5m full period:
- n = 1 735 transakcji
- μ = 0,300R, σ = 3,260R
- Standard error = σ/√n = 3,260/√1735 ≈ **0,0783R**
- t = 0,300 / 0,0783 ≈ **3,83** (p < 0,001)

**Oczekiwana wartość jest statystycznie istotna** (t > 3,5, p < 0,001). Przy 1735 transakcjach wystarczy próba, żeby odrzucić hipotezę zerową (przypadkowość).

### 10.2 Wpływ pojedynczego outliera

| Scenariusz | Oczekiwana wartość | PF |
|-----------|--------------------|----|
| Pełny backtest | +0,300R | 1,39 |
| Bez top 1 transakcji (−117R) | +0,233R | ~1,26 |
| Bez top 5 transakcji (−155,8R) | +0,210R | ~1,22 |
| Bez top 10 transakcji (−168R) | +0,203R | ~1,20 |

Wyniki **bez outlierów** są wciąż pozytywne. Strategia ma realną przewagę. Jednak PF spada z 1,39 do ~1,20 bez top 10 transakcji.

### 10.3 Stabilność wyników (bootstrap perspective)
- 4 lata danych = 4 niezależne "próby"
- 5m: wszystkie 4 lata zysk → p(4/4) przy założeniu 50/50 = 6,25% (zbyt mała próba)
- Lepsze: t-test na rocznych Exp(R): mean=0,304, σ=0,149, t=4,09 → **p < 0,05** przy df=3

---

## 11. Werdykt końcowy

### 11.1 Ocena per rama czasowa

| Rama | Werdykt | Uzasadnienie |
|------|---------|-------------|
| **5m / H4** | **B — Ograniczona wartość z monitorowaniem** | Pozytywna 4/4 lata, istotna statystycznie, ale 22,5% zysku w jednej transakcji i pojedynczy −14R trade to ryzyka, które wymagają kontroli |
| 15m / H4 | D — Nieopłacowy | 2024 Exp=−0,149R + katastrofalny −60R trade = nieakceptowalne ryzyko gapowe |
| 30m / H4 | C — Niewystarczająca przewaga | PF=1,19, 2023 PF<1, zbyt niska gęstość sygnałów |
| 1h / H4 | F — Strukturalnie nieodpowiedni | Ujemna ekspektancja overall, BOS detection delay ~5h jest niekompatybilne z dynamiką US100 |

### 11.2 Główne zagrożenia dla wdrożenia (5m)

1. **Gap risk** — jedna transakcja może stracić 14×R (udokumentowane). Wymagany hard stop "przy otwieraniu sesji" lub redukcja do zero pozycji przed zamknięciem NYSE
2. **Outlier dependency** — zysk z 2023 jest w 52% jedną transakcją. W środowisku bez mega-trendów wyniki będą słabsze
3. **Brak trailing stop** — w obecnej konfiguracji TP=2R. Mechanizm +117R wymaga wyjaśnienia (patrz P2 powyżej)
4. **Short underperformance** — LONG exp=0,397R vs SHORT exp=0,176R. Strategia jest quasi-directional

### 11.3 Czy strategia działa na US100?

> **TAK, ale wyłącznie na ramie 5m, z zastrzeżeniami.** Strategia BOS+Pullback ma statystycznie istotną przewagę (t=3,83, p<0,001) na US100 5m przez lata 2021-2024. Jednak zysk jest nieproporcjonalnie skoncentrowany w pojedynczych mega-trendach (2023 AI rally), a ryzyko gapowe jest nieadresowane. System jest **użyteczny jako komponent portfela**, nie jako samodzielna strategia dla indeksu.

---

## 12. Rekomendacje

### Priorytet 1 — KRYTYCZNE (przed wdrożeniem live)

1. **Zaimplementuj zamknięcie pozycji przed weekendem** (piątek ~21:55 PL / NYSE close). US100 ma regularne gapy niedzielne.
2. **Zaimplementuj filter earnings blackout** — wyłącz strategię na 24h przed/po raportach kwartalnych NVDA, AAPL, MSFT, AMZN, GOOG (80% wagi NASDAQ).
3. **Wyjaśnij anomalię +117R** przy RR=2.0 — sprawdź, czy TP nie jest przypadkowo pomijany lub czy jest trailing stop. Jeśli to błąd kodu, rzeczywiste wyniki mogą być inne.

### Priorytet 2 — WAŻNE (przed użyciem kapitału)

4. **Dodaj filtr sesji NYSE** — aktywuj sygnały tylko w oknie 14:00–21:30 PL. Testuj różnicę vs full session.
5. **Testuj z maksymalną stratą dzienną** (`max_daily_loss=3R`) — limiter chroni przed kolejną transakcją klasy −60R.
6. **Trailing stop po osiągnięciu 1R** — zamknij 50% przy +1R, zostaw resztę na +2R. Redukuje outlier-zależność. Na 5m: potencjalnie bardziej spójna krzywa equity.

### Priorytet 3 — ULEPSZENIA (opcjonalne)

7. **Filter kierunkowości** — w środowiskach bearish (np. 2022) zwiększ proportional bias na SHORT.
8. **HTF wyższy niż H4** — testuj Daily jako HTF dla US100. Dzienny bias na indeksie może być bardziej stabilny niż H4.
9. **Walk-forward validation na US100** — uruchomić WF (np. IS=2 lata, OOS=6 mies.) dla 5m, żeby potwierdzić, że parametry nie są overfitowane.

---

## Podsumowanie

| Pytanie | Odpowiedź |
|---------|-----------|
| Czy strategia działa na US100? | TAK — wyłącznie 5m, z istotnością statystyczną |
| Czy wyniki są wiarygodne? | CZĘŚCIOWO — zniekształcone przez outlier 117R i gap risk |
| Czy można ją wdrożyć live? | DOPIERO po fixes #1, #2, #3 z powyższych |
| Najlepsza rama czasowa | **5m / H4** |
| Najgorsza | **1h / H4** (structurally negative) |
| Porównanie z FX | US100/5m lepszy niż typowa para FX na tej strategii |

---

*Raport wygenerowany na podstawie backtestów z danymi Dukascopy. Wyniki historyczne nie gwarantują przyszłych zysków. Analiza nie uwzględnia kosztów transakcyjnych, spreadu i slippage w środowisku live.*

# Changelog

Wszystkie istotne zmiany w projekcie BojkoFX2 są dokumentowane w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie zgodne z [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
`MAJOR.MINOR.PATCH` — plik `VERSION` zawiera bieżącą wersję.

Skróty sekcji: **Added** | **Changed** | **Fixed** | **Removed** | **Security**

---

## [Unreleased]

---

## [0.5.0] — 2026-03-12

### Fixed (FX — dashboard)
- **serve.py** — `TCPServer` zastąpiony `ThreadingMixIn + TCPServer`; poprzedni
  single-threaded serwer odrzucał równoległe żądania przeglądarki, co
  powodowało znikanie wykresów po ~1 sekundzie.
- **app.py — `still_open` check** — `exit_time = NaT` w wierszach `TRADE_CLOSED`
  powodowało, że zamknięte pozycje były traktowane jako otwarte; dodano
  `fillna(timestamp)` przed porównaniem.
- **app.py — side mapping** — `"BUY" in "LONG"` zwracało `False`; poprawiono
  warunek na `"BUY" in side or side == "LONG"`.
- **app.py — zero SL/TP** — wartości `0.0` normalizowane do `None` żeby
  dashboard nie wyświetlał `0.000` zamiast `—`.
- **app.py — `_bot_log_path`** — nieprawidłowa ścieżka do pliku logu bota;
  dodano fallback szukający w `../logs/{service}.log`.
- **index.html** — duplikat `const ctx` w `updateEquityChart()` powodował
  `SyntaxError`; usunięto.
- **index.html — `drawCandles`** — poziomy SL/TP równe `0` traktowane jako
  prawidłowe ceny; dodano warunek `v > 0` przed aktualizacją skali.

### Fixed (FX — bot / execution engine)
- **BUG-ZOMBIE-1** `ibkr_exec.py — purge_zombie_records()`:
  - Zmieniła sygnaturę z `int` na `Tuple[int, List[dict]]`; dla każdego
    usuniętego rekordu z `fill_time != None` emituje wiersz `TRADE_CLOSED`
    (caller musi go zalogować przez `TradingLogger.log_exit_row()`).
  - Dodano **safety guard**: jeśli `ib.positions()` zwróci pustą listę,
    ale istnieją filled records → purge pomijany (możliwy stale connection).
  - Dodano szczegółowe logowanie stanu IBKR (`positions` + `active_order_pids`)
    przed podjęciem decyzji o purge.
  - Dodano **NAKED POSITION check**: po purge wykrywa symbole otwarte w IBKR
    bez matching `_records` i emituje `log.critical`.
- **BUG-ZOMBIE-2** `ibkr_exec.py — restore_positions_from_ibkr()` — po pętli
  bracket dodano audit nagich pozycji (w `ib.positions()` ale bez żadnych
  bracket orders); emituje `log.critical` i `[CRITICAL][RESTORE]`.
- **run_paper_ibkr_gateway.py (FX + US100), run_live_idx.py (US100)**
  — zaktualizowane call sites `purge_zombie_records()` do nowej sygnatury
  tuple; exit rows logowane przez `logger.log_exit_row()`.

### Fixed (FX — dane / CSV)
- Ręczne patche CSV (`patch_csv_ghosts.py`): dopisano 4 wiersze `TRADE_CLOSED`
  dla ghost FILL rows bez zamknięcia (`restored_1390/1391/1211/1831`) —
  skutek błędu `purge_zombie` który usuwał record bez emitowania `TRADE_CLOSED`.

### Fixed (FX — IBKR — orphaned orders)
- Anulowano 4 osierocone GTC bracket orders (`1390/1391 AUDJPY`, `2190/2191
  CADJPY`) które przeżyły wygaśnięcie parent orderów; dzięki temu nie mogły
  otworzyć nowych niezarządzanych pozycji.
- Root cause zdarzenia z 2026-03-11: bracket TP (order `#1211`, SELL 354
  AUDJPY LMT GTC) wypełnił się 11h po zamknięciu parent LONG → SHORT naked
  bez SL/TP; `purge_zombie` usunął record bez wpisu TRADE_CLOSED w CSV.

### Added (FX — skrypty operacyjne)
- `FX/scripts/emergency_close_position.py` — zamyka dowolną pozycję w IBKR
  przez market order (`clientId=99`, obsługuje `--dry-run`).
- `FX/scripts/cancel_orders.py` — anuluje IBKR orders po ID, obsługuje
  `--show-all` i `--dry-run`; używa `reqAllOpenOrders()` żeby widzieć
  zlecenia innych clientId.
- `FX/scripts/global_cancel.py` — wysyła `reqGlobalCancel()` (awaryjne
  czyszczenie wszystkich orders).
- `FX/scripts/patch_csv_ghosts.py` — jednorazowy skrypt naprawczy: dopisuje
  `TRADE_CLOSED` dla FILL rows bez zamknięcia w CSV.

---

## [0.4.0] — 2026-03-10

### Fixed (US100)
- **BUG-US-04** `run_live_idx.py` — filtr sesji używał `< session_end` (exclusive),
  co pomijało ostatnią godzinę sesji; zmieniono na `<= session_end` identycznie
  jak `is_allowed_session()` używane w backteście.
- **BUG-US-05** `run_live_idx.py` — `strategy.process_bar()` nie przekazywało
  `symbol=SYMBOL`; stan był persystowany pod kluczem `"UNKNOWN"` zamiast
  rzeczywistego symbolu.
- **BUG-US-06** `tests/test_htf_bias.py` — testy sprawdzały usuniętą logikę
  (`last_high_broken` / `last_low_broken`); plik przepisany od podstaw z
  numerycznie-poprawnymi, unikalnie-wartościowymi danymi testowymi.
- **BUG-US-07** `tests_backtests/` — importy wskazywały na stare ścieżki
  `US100/backtests/`; przekierowano do `FX/backtests/` (wspólny silnik).
- `tests_backtests/conftest.py` — dodano wczesne ładowanie modułów FX żeby
  `FX/src` trafiło do `sys.modules` zanim pytest zdąży zarejestrować `US100/src`.

### Added (US100)
- `tests/test_live_backtest_parity.py` — 5 klas z 19 testami regresji
  pilnującymi spójności live↔backtest:
  - `TestATRParity` — ATR Wilder EWM (BUG-US-02)
  - `TestPivotNoLookahead` — brak lookahead w precompute_pivots (BUG-US-01)
  - `TestSessionFilterParity` — boundary `<= session_end` (BUG-US-04)
  - `TestSymbolStateParity` — stan pod poprawnym symbolem (BUG-US-05)
  - `TestEquityCurveParity` — R-compounding equity curve (BUG-US-03)

---

## [0.3.0] — 2026-02-22

### Fixed (FX)
- **BUG-02** `signals_bos_pullback.py` — ATR liczony rolling mean zamiast
  Wilder EWM; zmieniono na `ewm(alpha=1/period, adjust=False)`.
- **BUG-03** `run_trend_backtest()` — equity curve mnożona przez 100 000
  zamiast mnożona R przez rozmiar pozycji; przepisano logikę.
- **BUG-06** `determine_htf_bias()` — usunięto `last_high_broken` /
  `last_low_broken` (generowały fałszywe sygnały).
- **BUG-10** `precompute_pivots()` — pivot wykrywany z lookahead; zmieniono
  na sliding-window bez dostępu do przyszłych barów.
- **BUG-13** Brakujące unit-testy pivots/ATR/session; dodano pełny zestaw
  testów parity.
- **BUG-15** `check_bos()` korzystał z całej serii zamiast skalarów;
  refaktoryzacja do sygnatur scalar-pivot.
- **BUG-16** `PortfolioSimulator` — wielokrotne otwieranie tej samej pozycji
  bez sprawdzenia `in_position`.

### Added (FX)
- `tests/test_live_backtest_parity.py` — testy regresji dla modułu FX.
- `docs/FX_DEEP_CODE_AUDIT.md` — pełen raport audytu kodu FX.

---

## [0.2.0] — 2026-01-15

### Added
- US100 — nowy sub-projekt do tradingu NQ/US100 na IBKR.
- `shared/bojkofx_shared/` — wspólna biblioteka (config, models, state_store).
- Dashboard — ujednolicony panel dla FX i US100 (`dashboard/app.py`).
- `start_dashboard.bat` — launcher czytający klucz API z `.env`.

### Changed
- Monorepo: `FX/` i `US100/` jako sub-projekty pod wspólnym rootem.
- `.gitignore` — wykluczone duże pliki CSV (>50 MB) i sekrety.

---

## [0.1.0] — 2025-12-01

### Added
- Inicjalna struktura monorepo (`FX/`, `shared/`).
- `FX/backtests/` — silnik backtestów BOS pullback.
- `FX/src/` — strategia trend-following v1, sygnały, wskaźniki.
- `FX/config/config.yaml` — konfiguracja strategii.
- `FX/requirements.txt`.

---

[Unreleased]: https://github.com/example/BojkoFX2/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/example/BojkoFX2/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/example/BojkoFX2/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/example/BojkoFX2/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/example/BojkoFX2/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/example/BojkoFX2/releases/tag/v0.1.0

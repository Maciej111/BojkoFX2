# Changelog

Wszystkie istotne zmiany w projekcie BojkoFX2 są dokumentowane w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Wersjonowanie zgodne z [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
`MAJOR.MINOR.PATCH` — plik `VERSION` zawiera bieżącą wersję.

Skróty sekcji: **Added** | **Changed** | **Fixed** | **Removed** | **Security**

---

## [Unreleased]

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

[Unreleased]: https://github.com/example/BojkoFX2/compare/v0.4.0...HEAD
[0.5.0]: https://github.com/example/BojkoFX2/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/example/BojkoFX2/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/example/BojkoFX2/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/example/BojkoFX2/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/example/BojkoFX2/releases/tag/v0.1.0

"""conftest.py for tests_backtests/
Ensure FX/backtests (and FX/src) are importable before any test module loads.

Root cause: pytest adds US100/ to sys.path early. FX/backtests/signals_bos_pullback
does `from src.signals...` which would resolve to US100/src (no signals sub-package)
unless FX/ is inserted first AND the FX modules are eagerly imported so Python
caches FX/src before US100/src can shadow it.

After the eager imports we RESTORE sys.path priority (US100 first) and evict
FX/src from sys.modules so that test files in tests/ still get US100/src.
The backtests.* modules have already bound the symbols they need; removing the
src.* cache entries only affects future bare `import src` lookups.
"""
import sys
from pathlib import Path

_FX_ROOT = Path(__file__).resolve().parents[2] / "FX"
_FX_ROOT_STR = str(_FX_ROOT)
_US100_ROOT = Path(__file__).resolve().parents[1]
_US100_ROOT_STR = str(_US100_ROOT)

# Re-insert FX at position 0 so it precedes US100/ on sys.path.
if _FX_ROOT_STR in sys.path:
    sys.path.remove(_FX_ROOT_STR)
sys.path.insert(0, _FX_ROOT_STR)

# Eagerly import FX modules so src.* is cached from FX/src before any test
# module is collected (collection triggers US100/src imports via tests/).
import backtests.signals_bos_pullback  # noqa: F401
import backtests.indicators             # noqa: F401

# Restore sys.path so US100/ takes priority over FX/ for everything ELSE.
# tests/ files import from US100/src and must not be misrouted to FX/src.
if _FX_ROOT_STR in sys.path:
    sys.path.remove(_FX_ROOT_STR)
if _US100_ROOT_STR not in sys.path:
    sys.path.insert(0, _US100_ROOT_STR)
# Keep FX available for any remaining resolution, just at lower priority.
sys.path.append(_FX_ROOT_STR)

# Evict src.* from sys.modules so tests/ files re-import from US100/src.
# backtests.* have already bound the symbols they need via FX/src.
for _k in list(sys.modules):
    if _k == "src" or _k.startswith("src."):
        del sys.modules[_k]


# Forwarding shim — actual code lives in shared/bojkofx_shared/
# Install the shared package: pip install -e ../../shared
# Or this shim adds the path automatically.
import sys as _sys
import pathlib as _pl
_SHARED = _pl.Path(__file__).resolve().parents[3] / "shared"
if str(_SHARED) not in _sys.path:
    _sys.path.insert(0, str(_SHARED))
from bojkofx_shared.indicators.session_filter import *  # noqa: F401, F403
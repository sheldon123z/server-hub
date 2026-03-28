"""pytest 配置 — 确保项目根在 sys.path"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import httpx

    if "app" not in inspect.signature(httpx.Client.__init__).parameters:
        _orig_client_init = httpx.Client.__init__

        def _patched_client_init(self, *args, app=None, **kwargs):
            return _orig_client_init(self, *args, **kwargs)

        httpx.Client.__init__ = _patched_client_init  # type: ignore[assignment]
except Exception:
    pass

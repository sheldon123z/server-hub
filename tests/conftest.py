"""pytest 配置 — 确保项目根在 sys.path"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

"""ServerHub Agent 配置 — 从环境变量读取"""

import os
import sys

AGENT_PORT: int = int(os.environ.get("AGENT_PORT", "9901"))
AGENT_TOKEN: str = os.environ.get("AGENT_TOKEN", "")
HUB_URL: str = os.environ.get("HUB_URL", "")

if not AGENT_TOKEN:
    print("ERROR: AGENT_TOKEN 环境变量未设置，agent 拒绝启动", file=sys.stderr)
    sys.exit(1)

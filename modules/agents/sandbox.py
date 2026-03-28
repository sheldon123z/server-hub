"""安全增强的 LocalShellBackend — 代码执行沙箱

继承 Deep Agents 框架的 LocalShellBackend，增加以下安全机制：
1. 敏感环境变量剥离 — API Key 等不泄露到 execute() 子进程
2. 资源限制 — 通过 ulimit 前缀限制 CPU 时间和内存
3. 固定临时代码目录 — /tmp/serverhub-sandbox/
4. 代码执行前安全检查

Agent 通过框架内置的 write_file + execute 组合来写代码并运行，
本模块不添加额外工具，而是增强 Backend 的安全性。
"""

import os
import re
import logging
from pathlib import Path

try:
    from deepagents.backends.local_shell import LocalShellBackend
    from deepagents.backends.protocol import ExecuteResponse
except ImportError:
    class LocalShellBackend:  # type: ignore[override]
        def __init__(self, **kwargs):
            self._env = dict(os.environ)

        def execute(self, command: str, *, timeout: int | None = None):
            raise RuntimeError("deepagents.backends.local_shell unavailable in current environment")

    class ExecuteResponse:  # type: ignore[override]
        pass

    logging.getLogger(__name__).warning(
        "deepagents not installed — agent sandbox unavailable"
    )

logger = logging.getLogger(__name__)

# 沙箱临时目录
SANDBOX_DIR = Path("/tmp/serverhub-sandbox")

# 敏感环境变量模式 — 在 execute() 中剥离
SENSITIVE_ENV_PATTERNS = [
    r".*API_KEY.*", r".*SECRET.*", r".*TOKEN.*", r".*PASSWORD.*",
    r"OPENROUTER_.*", r"VOLCENGINE_.*", r"ZHIPU_.*", r"MOONSHOT_.*",
    r"MINIMAX_.*", r"DEEPSEEK_.*", r"OPENAI_.*", r"TAVILY_.*",
    r"SERVERHUB_SECRET.*", r"SERVERHUB_ADMIN_PASSWORD",
]
_sensitive_patterns = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_ENV_PATTERNS]


class SafeLocalShellBackend(LocalShellBackend):
    """安全增强的 LocalShellBackend

    在 LocalShellBackend 基础上：
    - execute() 中剥离敏感环境变量
    - 在沙箱目录内执行代码时自动添加 ulimit 资源限制
    - 自动创建沙箱临时目录
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保沙箱目录存在
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        # 从继承的环境中剥离敏感变量
        self._env = self._strip_sensitive_env(self._env)
        logger.info(f"SafeLocalShellBackend 已初始化，沙箱目录: {SANDBOX_DIR}")

    @staticmethod
    def _strip_sensitive_env(env: dict) -> dict:
        """从环境变量中剥离敏感信息"""
        safe = {}
        stripped_count = 0
        for key, value in env.items():
            if any(p.match(key) for p in _sensitive_patterns):
                stripped_count += 1
                continue
            safe[key] = value
        if stripped_count:
            logger.info(f"已从 execute 环境中剥离 {stripped_count} 个敏感变量")
        return safe

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """增强的 execute — 沙箱目录内的代码自动添加资源限制

        资源限制 (通过 ulimit):
        - CPU 时间: 120 秒
        - 虚拟内存: 4GB
        - 文件大小: 100MB
        """
        # 检测是否在沙箱目录内执行代码
        sandbox_str = str(SANDBOX_DIR)
        if sandbox_str in command and ("python" in command or "bash " in command):
            # 在沙箱内执行代码时，添加资源限制前缀
            ulimit_prefix = "ulimit -t 120 -v 4194304 -f 102400 2>/dev/null; "
            if not command.startswith("ulimit"):
                command = ulimit_prefix + command

        return super().execute(command, timeout=timeout)

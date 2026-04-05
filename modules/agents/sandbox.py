"""安全增强的 LocalShellBackend — 代码执行沙箱

继承 Deep Agents 框架的 LocalShellBackend，增加以下安全机制：
1. 敏感环境变量剥离 — API Key 等不泄露到 execute() 子进程
2. 资源限制 — 通过 ulimit 前缀限制 CPU 时间和内存
3. 固定临时代码目录 — /tmp/serverhub-sandbox/
4. 代码执行前安全检查
5. 按风险等级记录所有 Shell 命令审计日志

Agent 通过框架内置的 write_file + execute 组合来写代码并运行，
本模块不添加额外工具，而是增强 Backend 的安全性。
"""

import asyncio
import logging
import os
import re
import time
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

    logging.getLogger(__name__).warning("deepagents not installed — agent sandbox unavailable")

logger = logging.getLogger(__name__)

# 沙箱临时目录
SANDBOX_DIR = Path("/tmp/serverhub-sandbox")

# 敏感环境变量模式 — 在 execute() 中剥离
SENSITIVE_ENV_PATTERNS = [
    r".*API_KEY.*",
    r".*SECRET.*",
    r".*TOKEN.*",
    r".*PASSWORD.*",
    r"OPENROUTER_.*",
    r"VOLCENGINE_.*",
    r"ZHIPU_.*",
    r"MOONSHOT_.*",
    r"MINIMAX_.*",
    r"DEEPSEEK_.*",
    r"OPENAI_.*",
    r"TAVILY_.*",
    r"SERVERHUB_SECRET.*",
    r"SERVERHUB_ADMIN_PASSWORD",
]
_sensitive_patterns = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_ENV_PATTERNS]


# 风险等级分类 — 用于命令审计
_HIGH_RISK_PATTERNS = [
    re.compile(p)
    for p in [
        r"\brm\s+.*-\s*[^\s]*r[^\s]*f",  # rm -rf / rm -fr
        r"\brm\s+-rf\b",
        r"\bmkfs\b",
        r"\bdd\s+",
        r"\bfdisk\b",
        r"\bparted\b",
        r"\bshred\b",
        r"\bwipefs\b",
        r">\s*/dev/sd",
        r"\bformat\b.*disk",
    ]
]

_MEDIUM_RISK_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bsudo\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bkill\b",
        r"\bkillall\b",
        r"\bpkill\b",
        r"\bsystemctl\s+(stop|restart|disable)\b",
        r"\bservice\s+\S+\s+(stop|restart)\b",
        r"\bdocker\s+(rm|rmi|stop|kill)\b",
        r"\biptables\b",
        r"\bufw\b",
        r"\busermod\b",
        r"\buserdel\b",
        r"\bgroupdel\b",
        r"\bcrontab\s+-[re]\b",
        r"\breboot\b",
        r"\bshutdown\b",
        r"\bpoweroff\b",
    ]
]


class SafeLocalShellBackend(LocalShellBackend):
    """安全增强的 LocalShellBackend

    在 LocalShellBackend 基础上：
    - execute() 中剥离敏感环境变量
    - 在沙箱目录内执行代码时自动添加 ulimit 资源限制
    - 自动创建沙箱临时目录
    - 按风险等级记录所有 Shell 命令审计日志
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保沙箱目录存在
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        # 从继承的环境中剥离敏感变量
        self._env = self._strip_sensitive_env(self._env)
        # 获取事件循环（用于异步审计写入）
        self._loop: asyncio.AbstractEventLoop | None = None
        logger.info("SafeLocalShellBackend 已初始化，沙箱目录: %s", SANDBOX_DIR)

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
            logger.info("已从 execute 环境中剥离 %d 个敏感变量", stripped_count)
        return safe

    @staticmethod
    def _classify_risk(command: str) -> str:
        """按命令内容返回风险等级: high / medium / low"""
        for pat in _HIGH_RISK_PATTERNS:
            if pat.search(command):
                return "high"
        for pat in _MEDIUM_RISK_PATTERNS:
            if pat.search(command):
                return "medium"
        return "low"

    def _write_audit_log(
        self,
        command: str,
        risk_level: str,
        result_length: int,
        duration_ms: int,
        blocked: bool,
    ) -> None:
        """异步非阻塞写入审计日志到数据库"""
        try:
            loop = self._loop or asyncio.get_event_loop()
        except RuntimeError:
            logger.debug("无法获取事件循环，跳过审计写入")
            return

        async def _insert():
            try:
                from database import get_db

                db = await get_db()
                await db.execute(
                    "INSERT INTO agent_command_audit"
                    " (command, risk_level, result_length, duration_ms, blocked)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (command[:500], risk_level, result_length, duration_ms, int(blocked)),
                )
                await db.commit()
            except Exception:
                logger.debug("审计日志写入失败", exc_info=True)

        # fire-and-forget: 不阻塞命令执行
        try:
            loop.create_task(_insert())
        except RuntimeError:
            logger.debug("事件循环未运行，跳过审计写入")

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """增强的 execute — 沙箱目录内的代码自动添加资源限制 + 审计日志

        资源限制 (通过 ulimit):
        - CPU 时间: 120 秒
        - 虚拟内存: 4GB
        - 文件大小: 100MB
        """
        risk_level = self._classify_risk(command)
        if risk_level != "low":
            logger.info("命令风险等级 [%s]: %s", risk_level, command[:200])

        # 检测是否在沙箱目录内执行代码
        sandbox_str = str(SANDBOX_DIR)
        if sandbox_str in command and ("python" in command or "bash " in command):
            # 在沙箱内执行代码时，添加资源限制前缀
            ulimit_prefix = "ulimit -t 120 -v 4194304 -f 102400 2>/dev/null; "
            if not command.startswith("ulimit"):
                command = ulimit_prefix + command

        start = time.monotonic()
        response = super().execute(command, timeout=timeout)
        duration_ms = int((time.monotonic() - start) * 1000)

        # 计算结果长度
        result_text = getattr(response, "output", "") or ""
        result_length = len(result_text)

        # 异步写入审计日志
        self._write_audit_log(
            command=command,
            risk_level=risk_level,
            result_length=result_length,
            duration_ms=duration_ms,
            blocked=False,
        )

        return response

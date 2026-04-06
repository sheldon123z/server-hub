"""Shell Step 执行器 — 调用 SafeLocalShellBackend 执行本地命令"""

import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("shell")
class ShellStepExecutor:
    """在本地沙箱中执行 shell 命令"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.agents.sandbox import SafeLocalShellBackend

        command = config.get("command", "")
        timeout = config.get("timeout")
        if not command:
            return {"output": "", "exit_code": 1, "error": "缺少 command 参数"}

        try:
            backend = SafeLocalShellBackend(root_dir=str(config.get("root_dir", "~")))
            kwargs = {}
            if timeout:
                kwargs["timeout"] = int(timeout)
            response = backend.execute(command, **kwargs)
            output = getattr(response, "output", "") or ""
            exit_code = getattr(response, "exit_code", 0) or 0
            return {"output": output, "exit_code": exit_code}
        except Exception as e:
            logger.exception("Shell step 执行失败: %s", command[:200])
            return {"output": "", "exit_code": 1, "error": str(e)}

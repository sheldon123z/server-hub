"""SSH Step 执行器 — 通过 TOFU SSH 连接远程执行命令"""

import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("ssh")
class SSHStepExecutor:
    """通过 SSH (TOFU) 在远程服务器执行命令"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.servers.ssh_tofu import tofu_connect

        host = config.get("host", "")
        command = config.get("command", "")
        port = int(config.get("port", 22))
        username = config.get("username")
        timeout = int(config.get("timeout", 30))

        if not host or not command:
            return {"output": "", "exit_code": 1, "error": "缺少 host 或 command 参数"}

        connect_kwargs: dict = {}
        if username:
            connect_kwargs["username"] = username
        # 支持通过 state 中的凭据传入密码/密钥
        password = config.get("password")
        if password:
            connect_kwargs["password"] = password

        try:
            conn = await tofu_connect(host, port, **connect_kwargs)
            try:
                result = await conn.run(command, timeout=timeout)
                exit_code = result.exit_status or 0
                output = (result.stdout or "") + (result.stderr or "")
                return {"output": output.strip(), "exit_code": exit_code}
            finally:
                conn.close()
        except Exception as e:
            logger.exception("SSH step 执行失败: %s@%s", username or "default", host)
            return {"output": "", "exit_code": 1, "error": str(e)}

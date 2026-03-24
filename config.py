"""ServerHub 配置管理"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

class Settings:
    """应用配置，优先读取环境变量 SERVERHUB_*"""

    def __init__(self):
        self.secret_key: str = os.getenv("SERVERHUB_SECRET_KEY", "change-me-to-a-random-string")
        self.admin_username: str = os.getenv("SERVERHUB_ADMIN_USERNAME", "admin")
        self.admin_password: str = os.getenv("SERVERHUB_ADMIN_PASSWORD", "admin123")

        self.db_path: str = str(BASE_DIR / "data" / "server-hub.db")
        self.quota_file: str = "/home/zhengxiaodong/scripts/config/user-quotas.conf"
        self.telegram_script: str = "/home/zhengxiaodong/scripts/notification/send-telegram-report.sh"
        self.admin_linux_users: set = {"zhengxiaodong", "root"}

        # JWT
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = 60 * 24  # 24 hours
        self.refresh_token_expire_days: int = 30

        # 监控
        self.metrics_interval_seconds: int = 60
        self.metrics_retention_days: int = 90

        # 日志路径白名单
        self.log_dirs: list = [
            "/home/zhengxiaodong/logs",
            "/var/log",
        ]

        # 管理的 systemd 服务列表
        self.managed_services: list = [
            "nginx", "docker", "clash", "ollama", "jupyterlab",
            "login-time-monitor", "sunny", "haproxy", "fail2ban",
            "webmin", "mysql", "smbd", "nmbd", "xrdp",
        ]

        # AI Agent 配置
        self.agent_checkpoint_db: str = str(BASE_DIR / "data" / "agent-checkpoints.db")
        self.agent_default_model: str = os.getenv("SERVERHUB_AGENT_MODEL", "openrouter:deepseek/deepseek-chat")
        self.agent_patrol_model: str = os.getenv("SERVERHUB_PATROL_MODEL", "openrouter:deepseek/deepseek-chat")

        # 服务商 API Key 通过环境变量注入，模型/服务商列表在 modules/agents/llm.py 中定义
        self.agent_shell_timeout: int = 30
        self.agent_shell_max_output: int = 8000

        # Docker compose 堆栈
        self.compose_stacks: dict = {
            "dify": {
                "path": "/home/zhengxiaodong/projects/dify/docker",
                "display_name": "Dify AI",
                "script": "/home/zhengxiaodong/scripts/docker/dify-manage.sh",
            },
            "lobe": {
                "path": "/mnt/sda/container_mount/lobe-chat-db",
                "display_name": "LobeChat",
                "script": "/home/zhengxiaodong/scripts/docker/lobe-manage.sh",
            },
            "grid-autopilot": {
                "path": "/home/zhengxiaodong/exps/grid-autopilot",
                "display_name": "Grid AutoPilot",
                "script": None,
            },
        }


# 单例
settings = Settings()

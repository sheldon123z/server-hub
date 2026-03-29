"""ServerHub 配置管理"""

import logging
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def _write_secret_file(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        logger.warning("无法调整文件权限: %s", path)
    return value


def _load_or_create_secret(env_name: str, fallback_file: str, *, nbytes: int, label: str) -> str:
    value = os.getenv(env_name)
    if value:
        return value

    path = BASE_DIR / "data" / fallback_file
    if path.exists():
        return path.read_text(encoding="utf-8").strip()

    generated = secrets.token_urlsafe(nbytes)
    logger.warning("%s 未通过环境变量提供，已生成并保存到 %s", label, path)
    return _write_secret_file(path, generated)


def get_or_create_bootstrap_admin_password() -> str:
    """按需生成首次启动管理员密码。"""
    return _load_or_create_secret(
        "SERVERHUB_ADMIN_PASSWORD",
        "bootstrap-admin-password.txt",
        nbytes=18,
        label="SERVERHUB_ADMIN_PASSWORD",
    )


class Settings:
    """应用配置，优先读取环境变量 SERVERHUB_*"""

    def __init__(self):
        self.secret_key: str = _load_or_create_secret(
            "SERVERHUB_SECRET_KEY",
            "serverhub-secret.key",
            nbytes=48,
            label="SERVERHUB_SECRET_KEY",
        )
        self.admin_username: str = os.getenv("SERVERHUB_ADMIN_USERNAME", "admin")
        self.admin_password: str = os.getenv("SERVERHUB_ADMIN_PASSWORD", "")

        self.db_path: str = str(BASE_DIR / "data" / "server-hub.db")
        self.quota_file: str = "/home/zhengxiaodong/scripts/config/user-quotas.conf"
        self.telegram_script: str = "/home/zhengxiaodong/scripts/notification/send-telegram-report.sh"
        self.admin_linux_users: set = {"zhengxiaodong", "root"}

        # JWT
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = 60 * 24  # 24 hours
        self.refresh_token_expire_days: int = 30
        self.cookie_secure_mode: str = os.getenv("SERVERHUB_COOKIE_SECURE", "always").lower()
        self.cookie_samesite: str = os.getenv("SERVERHUB_COOKIE_SAMESITE", "lax").lower()

        # 监控
        self.metrics_interval_seconds: int = 60
        self.metrics_retention_days: int = 90
        self.gpu_metrics_ttl_seconds: int = int(os.getenv("SERVERHUB_GPU_METRICS_TTL_SECONDS", "20"))
        self.top_processes_cache_seconds: int = int(os.getenv("SERVERHUB_TOP_PROCESSES_CACHE_SECONDS", "10"))
        self.metrics_cache_ttl_seconds: int = 30

        # WebSocket
        self.ws_metrics_interval: int = 5          # WS快速推送间隔(秒)
        self.ws_full_metrics_interval: int = 60    # WS全量快照间隔(秒)
        self.top_processes_limit: int = 15         # 进程排行数量

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

        # RAG 知识库配置
        self.rag_embedding_model: str = os.getenv("SERVERHUB_RAG_EMBEDDING_MODEL", "bge-m3")
        self.rag_ollama_url: str = os.getenv("SERVERHUB_RAG_OLLAMA_URL", "http://localhost:11434")
        self.rag_chunk_size: int = int(os.getenv("SERVERHUB_RAG_CHUNK_SIZE", "800"))
        self.rag_chunk_overlap: int = int(os.getenv("SERVERHUB_RAG_CHUNK_OVERLAP", "100"))
        self.rag_top_k: int = int(os.getenv("SERVERHUB_RAG_TOP_K", "5"))

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

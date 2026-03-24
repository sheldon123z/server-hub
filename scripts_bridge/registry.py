"""
脚本注册表
白名单方式管理可通过 Web UI 执行的运维脚本
"""

SCRIPT_REGISTRY = {
    "dify_manage": {
        "path": "/home/zhengxiaodong/scripts/docker/dify-manage.sh",
        "display_name": "Dify 管理",
        "allowed_args": ["start", "stop", "restart", "update", "status", "logs"],
        "required_role": "admin",
        "timeout": 120,
        "sudo": False,
    },
    "lobe_manage": {
        "path": "/home/zhengxiaodong/scripts/docker/lobe-manage.sh",
        "display_name": "LobeChat 管理",
        "allowed_args": ["start", "stop", "update", "status", "logs"],
        "required_role": "admin",
        "timeout": 120,
        "sudo": False,
    },
    "ollama_manage": {
        "path": "/home/zhengxiaodong/scripts/docker/ollama-manage.sh",
        "display_name": "Ollama 管理",
        "allowed_args": ["update", "models", "list", "status"],
        "required_role": "admin",
        "timeout": 120,
        "sudo": False,
    },
    "block_baidupan": {
        "path": "/home/zhengxiaodong/scripts/network/block-baidupan.sh",
        "display_name": "封禁百度网盘",
        "allowed_args": [],
        "required_role": "admin",
        "timeout": 30,
        "sudo": True,
    },
    "unblock_baidupan": {
        "path": "/home/zhengxiaodong/scripts/network/unblock-baidupan.sh",
        "display_name": "解封百度网盘",
        "allowed_args": [],
        "required_role": "admin",
        "timeout": 30,
        "sudo": True,
    },
    "send_telegram": {
        "path": "/home/zhengxiaodong/scripts/notification/send-telegram-report.sh",
        "display_name": "Telegram 通知",
        "allowed_args": ["--morning-report", "--stdin"],
        "required_role": "admin",
        "timeout": 30,
        "sudo": False,
    },
    "health_check": {
        "path": "/home/zhengxiaodong/scripts/monitoring/server-health-check.sh",
        "display_name": "健康检查",
        "allowed_args": [],
        "required_role": "admin",
        "timeout": 60,
        "sudo": False,
    },
    "idle_user_monitor": {
        "path": "/home/zhengxiaodong/scripts/resource-control/idle-user-monitor.sh",
        "display_name": "空闲用户监控",
        "allowed_args": ["--group", "students", "--time", "2", "3"],
        "required_role": "admin",
        "timeout": 30,
        "sudo": True,
    },
}

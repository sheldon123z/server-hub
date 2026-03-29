"""通知渠道策略模式 — 多渠道消息发送抽象层"""

import asyncio
import base64
import hashlib
import hmac
import logging
import smtplib
import time
import urllib.parse
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)


class NotificationChannel:
    """通知渠道基类"""

    channel_type: str = ""
    display_name_template: str = ""

    def __init__(self, channel_id: str, display_name: str, config: dict):
        self.channel_id = channel_id
        self.display_name = display_name
        self.config = config

    async def send(self, message: str) -> dict:
        """发送消息，返回 {"success": bool, "error": str|None}"""
        raise NotImplementedError

    async def test(self) -> dict:
        """发送测试消息"""
        return await self.send(f"ServerHub 测试通知 ({self.display_name})")

    @classmethod
    def config_schema(cls) -> list[dict]:
        """返回配置字段定义列表"""
        raise NotImplementedError


class TelegramChannel(NotificationChannel):
    """Telegram 渠道 — 调用本地发送脚本"""

    channel_type = "telegram"
    display_name_template = "Telegram"

    @classmethod
    def config_schema(cls) -> list[dict]:
        return [
            {
                "name": "script_path",
                "label": "发送脚本路径",
                "type": "text",
                "required": True,
                "sensitive": False,
                "default": "/home/zhengxiaodong/scripts/notification/send-telegram-report.sh",
            }
        ]

    async def send(self, message: str) -> dict:
        try:
            script_path = self.config.get("script_path", "")
            proc = await asyncio.create_subprocess_exec(
                "bash",
                script_path,
                message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip() or stdout.decode().strip()
                return {"success": False, "error": f"脚本退出码 {proc.returncode}: {err}"}
            return {"success": True, "error": None}
        except Exception as e:
            logger.exception("Telegram 发送失败")
            return {"success": False, "error": str(e)}


class WeComChannel(NotificationChannel):
    """企业微信渠道 — Webhook 机器人"""

    channel_type = "wecom"
    display_name_template = "企业微信"

    @classmethod
    def config_schema(cls) -> list[dict]:
        return [
            {
                "name": "webhook_url",
                "label": "Webhook URL",
                "type": "password",
                "required": True,
                "sensitive": True,
            }
        ]

    async def send(self, message: str) -> dict:
        try:
            webhook_url = self.config.get("webhook_url", "")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    webhook_url,
                    json={"msgtype": "text", "text": {"content": message}},
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    return {"success": False, "error": data.get("errmsg", "未知错误")}
                return {"success": True, "error": None}
        except Exception as e:
            logger.exception("企业微信发送失败")
            return {"success": False, "error": str(e)}


class DingtalkChannel(NotificationChannel):
    """钉钉渠道 — Webhook 机器人（支持加签）"""

    channel_type = "dingtalk"
    display_name_template = "钉钉"

    @classmethod
    def config_schema(cls) -> list[dict]:
        return [
            {
                "name": "webhook_url",
                "label": "Webhook URL",
                "type": "password",
                "required": True,
                "sensitive": True,
            },
            {
                "name": "secret",
                "label": "加签密钥",
                "type": "password",
                "required": False,
                "sensitive": True,
                "default": "",
            },
        ]

    async def send(self, message: str) -> dict:
        try:
            webhook_url = self.config.get("webhook_url", "")
            secret = self.config.get("secret", "")

            if secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f"{timestamp}\n{secret}"
                hmac_code = hmac.new(
                    secret.encode("utf-8"),
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode())
                webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    webhook_url,
                    json={"msgtype": "text", "text": {"content": message}},
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    return {"success": False, "error": data.get("errmsg", "未知错误")}
                return {"success": True, "error": None}
        except Exception as e:
            logger.exception("钉钉发送失败")
            return {"success": False, "error": str(e)}


class QQBotChannel(NotificationChannel):
    """QQ 机器人渠道 — QQ 开放平台 API"""

    channel_type = "qqbot"
    display_name_template = "QQ 机器人"

    @classmethod
    def config_schema(cls) -> list[dict]:
        return [
            {
                "name": "app_id",
                "label": "AppID",
                "type": "text",
                "required": True,
                "sensitive": False,
            },
            {
                "name": "app_secret",
                "label": "AppSecret",
                "type": "password",
                "required": True,
                "sensitive": True,
            },
            {
                "name": "channel_id",
                "label": "子频道 ID",
                "type": "text",
                "required": True,
                "sensitive": False,
            },
        ]

    async def send(self, message: str) -> dict:
        try:
            app_id = self.config.get("app_id", "")
            app_secret = self.config.get("app_secret", "")
            channel_id = self.config.get("channel_id", "")

            async with httpx.AsyncClient(timeout=10) as client:
                # 获取 access_token
                token_resp = await client.post(
                    "https://bots.qq.com/app/getAppAccessToken",
                    json={"appId": app_id, "clientSecret": app_secret},
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return {"success": False, "error": f"获取 token 失败: {token_data}"}

                # 发送消息到子频道
                msg_resp = await client.post(
                    f"https://api.sgroup.qq.com/channels/{channel_id}/messages",
                    headers={"Authorization": f"QQBot {access_token}"},
                    json={"content": message},
                )
                if msg_resp.status_code not in (200, 201):
                    return {"success": False, "error": f"发送失败 HTTP {msg_resp.status_code}: {msg_resp.text}"}
                return {"success": True, "error": None}
        except Exception as e:
            logger.exception("QQ 机器人发送失败")
            return {"success": False, "error": str(e)}


class EmailChannel(NotificationChannel):
    """邮件渠道 — SMTP 发送"""

    channel_type = "email"
    display_name_template = "邮件"

    @classmethod
    def config_schema(cls) -> list[dict]:
        return [
            {"name": "smtp_host", "label": "SMTP 服务器", "type": "text", "required": True, "sensitive": False},
            {
                "name": "smtp_port",
                "label": "端口",
                "type": "number",
                "required": True,
                "sensitive": False,
                "default": 465,
            },
            {"name": "username", "label": "用户名", "type": "text", "required": True, "sensitive": False},
            {"name": "password", "label": "密码", "type": "password", "required": True, "sensitive": True},
            {
                "name": "use_tls",
                "label": "使用 TLS",
                "type": "boolean",
                "required": False,
                "sensitive": False,
                "default": True,
            },
            {"name": "from_addr", "label": "发件地址", "type": "text", "required": True, "sensitive": False},
            {"name": "to_addrs", "label": "收件地址(逗号分隔)", "type": "text", "required": True, "sensitive": False},
        ]

    async def send(self, message: str) -> dict:
        try:
            result = await asyncio.to_thread(self._smtp_send, message)
            return result
        except Exception as e:
            logger.exception("邮件发送失败")
            return {"success": False, "error": str(e)}

    def _smtp_send(self, message: str) -> dict:
        smtp_host = self.config.get("smtp_host", "")
        smtp_port = int(self.config.get("smtp_port", 465))
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        use_tls = self.config.get("use_tls", True)
        from_addr = self.config.get("from_addr", "")
        to_addrs = [a.strip() for a in self.config.get("to_addrs", "").split(",") if a.strip()]

        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = "ServerHub 通知"
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)

        if use_tls:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)

        try:
            server.login(username, password)
            server.sendmail(from_addr, to_addrs, msg.as_string())
            return {"success": True, "error": None}
        finally:
            server.quit()


def mask_sensitive(value: str) -> str:
    """掩码敏感值，保留最后 4 字符"""
    if not value or len(value) <= 4:
        return "****"
    return "****" + value[-4:]


CHANNEL_TYPES: dict[str, type[NotificationChannel]] = {
    "telegram": TelegramChannel,
    "wecom": WeComChannel,
    "dingtalk": DingtalkChannel,
    "qqbot": QQBotChannel,
    "email": EmailChannel,
}

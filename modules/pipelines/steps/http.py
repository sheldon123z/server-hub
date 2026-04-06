"""HTTP Step 执行器 — 发送 HTTP 请求并返回响应"""

import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("http")
class HTTPStepExecutor:
    """发送 HTTP 请求（GET/POST/PUT/DELETE）"""

    async def execute(self, config: dict, state: dict) -> dict:
        import httpx

        url = config.get("url", "")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body")
        timeout = int(config.get("timeout", 30))

        if not url:
            return {"output": "", "error": "缺少 url 参数"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                kwargs: dict = {"headers": headers}
                if body is not None:
                    if isinstance(body, dict):
                        kwargs["json"] = body
                    else:
                        kwargs["content"] = str(body)

                response = await client.request(method, url, **kwargs)

                # 尝试解析 JSON 响应
                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                return {
                    "output": response_body,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                }
        except Exception as e:
            logger.exception("HTTP step 执行失败: %s %s", method, url)
            return {"output": "", "error": str(e)}

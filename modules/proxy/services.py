"""Clash 代理管理服务层"""

import asyncio
import os
import subprocess
import httpx

CLASH_API = "http://127.0.0.1:9090"
CLASH_SECRET = "clash2026"
CLASH_DIR = "/opt/clash"
CLASH_BIN = f"{CLASH_DIR}/clash_linux"
ACTIVE_CONFIG = f"{CLASH_DIR}/config_active.yaml"
SWITCH_SCRIPT = "/home/zhengxiaodong/scripts/clash_switch_config.sh"

HEADERS = {"Authorization": f"Bearer {CLASH_SECRET}"}

CONFIGS = {
    "original": {"name": "原机场", "file": f"{CLASH_DIR}/config.yaml"},
    "fastfly": {"name": "FastFly", "file": f"{CLASH_DIR}/config_fastfly.yaml"},
}


async def _clash_api(method: str, path: str, json=None) -> dict | list | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.request(method, f"{CLASH_API}{path}",
                                        headers=HEADERS, json=json)
            if resp.status_code == 204:
                return {}
            return resp.json()
    except Exception:
        return None


async def get_clash_status() -> dict:
    version = await _clash_api("GET", "/version")
    running = version is not None

    # 通过符号链接检测当前配置
    current_config = "unknown"
    try:
        if os.path.islink(ACTIVE_CONFIG):
            real_path = os.path.realpath(ACTIVE_CONFIG)
            for cfg_key, cfg_info in CONFIGS.items():
                if os.path.realpath(cfg_info["file"]) == real_path:
                    current_config = cfg_key
                    break
    except Exception:
        pass

    return {
        "running": running,
        "version": version.get("version", "") if version else "",
        "premium": version.get("premium", False) if version else False,
        "current_config": current_config,
        "current_config_name": CONFIGS.get(current_config, {}).get("name", "未知"),
        "configs": CONFIGS,
    }


async def get_proxy_groups() -> list:
    data = await _clash_api("GET", "/proxies")
    if not data or "proxies" not in data:
        return []

    groups = []
    proxies = data["proxies"]
    for name, info in proxies.items():
        if info.get("type") in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            groups.append({
                "name": name,
                "type": info["type"],
                "now": info.get("now", ""),
                "all": info.get("all", []),
            })

    groups.sort(key=lambda g: (0 if g["type"] == "Selector" else 1, g["name"]))
    return groups


async def switch_proxy_node(group: str, node: str) -> bool:
    result = await _clash_api("PUT", f"/proxies/{group}", json={"name": node})
    return result is not None


async def test_group_delays(group: str) -> dict:
    data = await _clash_api("GET", f"/group/{group}/delay")
    return data or {}


async def switch_config(config_key: str) -> dict:
    if config_key not in CONFIGS:
        return {"ok": False, "msg": f"未知配置: {config_key}"}

    config_name = CONFIGS[config_key]["name"]

    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", SWITCH_SCRIPT, config_key,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode() + stderr.decode()

        if proc.returncode == 0 or "已启动" in output:
            return {"ok": True, "msg": f"已切换到 {config_name}", "output": output}
        else:
            return {"ok": False, "msg": "切换失败", "output": output}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def update_subscription() -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", SWITCH_SCRIPT, "update",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode() + stderr.decode()

        if "已更新" in output:
            return {"ok": True, "msg": "订阅更新成功", "output": output}
        else:
            return {"ok": False, "msg": "订阅更新失败", "output": output}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def restart_clash() -> dict:
    status = await get_clash_status()
    config_key = status["current_config"]
    if config_key == "unknown":
        config_key = "original"
    return await switch_config(config_key)

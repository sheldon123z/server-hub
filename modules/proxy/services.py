"""通用代理实例管理服务层."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx


BASE_DIR = Path(__file__).resolve().parents[2]
PROXY_REGISTRY_FILE = BASE_DIR / "data" / "proxy_instances.json"
PROFILE_DIR_NAME = "serverhub-profiles"
DEFAULT_USER_AGENT = "clash-verge/v2.0"

DEFAULT_PROXY_REGISTRY: dict[str, Any] = {
    "default_instance_id": "clash-main",
    "instances": [
        {
            "id": "clash-main",
            "name": "Clash 主实例",
            "type": "clash",
            "plugin": "clash",
            "service_name": "clash",
            "listen_ports": [
                {"label": "Mixed Port", "port": 7890, "description": "HTTP / SOCKS5"}
            ],
            "admin_api": {
                "base_url": "http://127.0.0.1:9090",
                "secret": "clash2026",
            },
            "active_config_link": "/opt/clash/config_active.yaml",
            "config_profiles": [
                {
                    "key": "original",
                    "name": "原机场",
                    "file": "/opt/clash/config.yaml",
                    "switch_arg": "original",
                    "subscription_url": "https://subscribe.kyapi.xyz/sub/auto?s=178774&t=rdI4DVgVMg9g",
                },
                {
                    "key": "fastfly",
                    "name": "FastFly",
                    "file": "/opt/clash/config_fastfly.yaml",
                    "switch_arg": "fastfly",
                    "subscription_url": "https://sbbcc.gggay.cn/api/v1/client/gjP3Lu9jMNU5LmjH9X?token=48d8afb5f402f2860705de309869f1a0",
                    "preferred_after_update": True,
                },
            ],
            "commands": {
                "switch_config": {
                    "argv": [
                        "sudo",
                        "/home/zhengxiaodong/scripts/clash_switch_config.sh",
                        "{config_arg}",
                    ],
                    "timeout": 15,
                    "success_any_of": ["已启动"],
                },
                "update_subscription": {
                    "argv": [
                        "sudo",
                        "/home/zhengxiaodong/scripts/clash_switch_config.sh",
                        "update",
                    ],
                    "timeout": 30,
                    "success_any_of": ["已更新"],
                },
            },
            "capabilities": {
                "systemd_actions": ["start", "stop", "restart"],
                "config_switch": True,
                "subscription_update": True,
                "node_switch": True,
                "delay_test": True,
            },
        }
    ],
}

ACTION_LABELS = {
    "start": "启动",
    "stop": "停止",
    "restart": "重启",
    "reload": "重载",
    "update_subscription": "更新订阅",
}


def _deepcopy_default_registry() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_PROXY_REGISTRY)


def _read_registry_raw() -> dict[str, Any]:
    registry = _deepcopy_default_registry()
    if PROXY_REGISTRY_FILE.exists():
        try:
            raw = json.loads(PROXY_REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                registry = raw
        except Exception:
            registry = _deepcopy_default_registry()
    return registry


def _save_registry_raw(registry: dict[str, Any]) -> None:
    PROXY_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROXY_REGISTRY_FILE.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _subscription_preview(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc or "unknown"
    path = parsed.path or "/"
    preview = f"{host}{path}"
    return preview[:80] + ("..." if len(preview) > 80 else "")


def _profile_base_dir(instance: dict[str, Any]) -> Path:
    active_link = str(instance.get("active_config_link", "")).strip()
    if active_link:
        return Path(active_link).parent
    return Path("/opt/clash")


def _slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def _ensure_unique_profile_key(instance: dict[str, Any], name: str, subscription_url: str) -> str:
    existing = {str(item.get("key", "")).strip() for item in instance.get("config_profiles", [])}
    base = _slugify(name)
    if not base:
        base = _slugify(urlparse(subscription_url).netloc) or "subscription"

    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _get_command_spec_from_instance(instance: dict[str, Any], action: str) -> dict[str, Any] | None:
    commands = instance.get("commands") or {}
    raw = commands.get(action)
    if not raw:
        return None

    if isinstance(raw, list):
        return {"argv": raw, "timeout": 15, "success_any_of": []}

    if isinstance(raw, dict) and isinstance(raw.get("argv"), list):
        return {
            "argv": raw["argv"],
            "timeout": int(raw.get("timeout", 15)),
            "success_any_of": [str(item) for item in raw.get("success_any_of", [])],
        }

    return None


def _normalize_profile(raw_profile: dict[str, Any], instance: dict[str, Any]) -> dict[str, Any]:
    profile = copy.deepcopy(raw_profile)
    key = str(profile.get("key", "")).strip()
    profile["key"] = key
    profile.setdefault("name", key or "未命名配置")
    profile.setdefault("file", "")
    profile.setdefault("switch_arg", key)
    profile.setdefault("subscription_url", "")
    profile["has_subscription"] = bool(str(profile.get("subscription_url", "")).strip())
    profile["subscription_url_preview"] = _subscription_preview(str(profile.get("subscription_url", "")))

    if not profile["file"]:
        profile_dir = _profile_base_dir(instance) / PROFILE_DIR_NAME
        profile["file"] = str(profile_dir / f"{key}.yaml")

    return profile


def _load_proxy_registry() -> dict[str, Any]:
    registry = _read_registry_raw()

    instances = []
    for raw_instance in registry.get("instances", []):
        if not isinstance(raw_instance, dict):
            continue
        instance_id = str(raw_instance.get("id", "")).strip()
        if not instance_id:
            continue

        instance = copy.deepcopy(raw_instance)
        instance["id"] = instance_id
        instance.setdefault("name", instance_id)
        instance.setdefault("type", "generic")
        if not instance.get("plugin") and instance["type"] in {"clash", "mihomo"}:
            instance["plugin"] = "clash"
        instance.setdefault("plugin", "")
        instance.setdefault("service_name", "")
        instance.setdefault("listen_ports", [])
        instance.setdefault("commands", {})

        profiles = []
        for raw_profile in instance.get("config_profiles", []):
            if not isinstance(raw_profile, dict):
                continue
            normalized = _normalize_profile(raw_profile, instance)
            if normalized["key"]:
                profiles.append(normalized)
        instance["config_profiles"] = profiles

        capabilities = instance.get("capabilities")
        if not isinstance(capabilities, dict):
            capabilities = {}
        capabilities.setdefault(
            "systemd_actions",
            ["start", "stop", "restart"] if instance.get("service_name") else [],
        )
        capabilities.setdefault("config_switch", bool(instance["config_profiles"]))
        capabilities.setdefault(
            "subscription_update",
            any(profile["has_subscription"] for profile in instance["config_profiles"])
            or bool(_get_command_spec_from_instance(instance, "update_subscription")),
        )
        capabilities.setdefault("node_switch", instance.get("plugin") == "clash")
        capabilities.setdefault("delay_test", instance.get("plugin") == "clash")
        instance["capabilities"] = capabilities

        instances.append(instance)

    default_instance_id = registry.get("default_instance_id")
    known_ids = {item["id"] for item in instances}
    if default_instance_id not in known_ids:
        default_instance_id = instances[0]["id"] if instances else None

    return {
        "default_instance_id": default_instance_id,
        "instances": instances,
    }


def _load_registry_for_update() -> dict[str, Any]:
    registry = _load_proxy_registry()
    if not registry.get("default_instance_id") and registry["instances"]:
        registry["default_instance_id"] = registry["instances"][0]["id"]
    return registry


def _persist_registry(registry: dict[str, Any]) -> None:
    data = {
        "default_instance_id": registry.get("default_instance_id"),
        "instances": [],
    }
    for instance in registry.get("instances", []):
        record = copy.deepcopy(instance)
        for profile in record.get("config_profiles", []):
            profile.pop("has_subscription", None)
            profile.pop("subscription_url_preview", None)
        data["instances"].append(record)
    _save_registry_raw(data)


def _require_instance(instance_id: str) -> dict[str, Any]:
    registry = _load_proxy_registry()
    for instance in registry["instances"]:
        if instance["id"] == instance_id:
            return instance
    raise ValueError(f"未知代理实例: {instance_id}")


def _require_instance_from_registry(registry: dict[str, Any], instance_id: str) -> dict[str, Any]:
    for instance in registry["instances"]:
        if instance["id"] == instance_id:
            return instance
    raise ValueError(f"未知代理实例: {instance_id}")


def _find_profile(instance: dict[str, Any], profile_key: str) -> dict[str, Any]:
    for profile in instance.get("config_profiles", []):
        if profile.get("key") == profile_key:
            return profile
    raise ValueError(f"未知配置: {profile_key}")


def get_default_instance_id() -> str | None:
    return _load_proxy_registry()["default_instance_id"]


def _to_configs_mapping(instance: dict[str, Any]) -> dict[str, dict[str, Any]]:
    configs = {}
    for profile in instance.get("config_profiles", []):
        key = str(profile.get("key", "")).strip()
        if not key:
            continue
        configs[key] = {
            "name": profile.get("name", key),
            "file": profile.get("file", ""),
        }
    return configs


def _resolve_current_config(instance: dict[str, Any]) -> tuple[str, str]:
    profiles = instance.get("config_profiles", [])
    active_link = str(instance.get("active_config_link", "")).strip()

    if active_link:
        try:
            if os.path.islink(active_link):
                real_path = os.path.realpath(active_link)
                for profile in profiles:
                    file_path = str(profile.get("file", "")).strip()
                    if file_path and os.path.exists(file_path):
                        if os.path.realpath(file_path) == real_path:
                            return profile.get("key", "unknown"), profile.get("name", "未知")
        except Exception:
            pass

    default_key = str(instance.get("default_config_key", "")).strip()
    for profile in profiles:
        if profile.get("key") == default_key:
            return profile["key"], profile.get("name", profile["key"])

    return "unknown", "未知"


async def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(cmd)}")

    output = stdout.decode("utf-8", errors="replace").strip()
    return proc.returncode, output


async def _query_systemd(service_name: str) -> dict[str, Any]:
    if not service_name:
        return {
            "running": False,
            "enabled": False,
            "status_text": "unmanaged",
            "pid": None,
        }

    active_task = _run(["systemctl", "is-active", service_name], timeout=10)
    enabled_task = _run(["systemctl", "is-enabled", service_name], timeout=10)
    show_task = _run(["systemctl", "show", service_name, "-p", "MainPID,SubState"], timeout=10)

    (active_rc, active_out), (_, enabled_out), (_, show_out) = await asyncio.gather(
        active_task,
        enabled_task,
        show_task,
    )

    details: dict[str, str] = {}
    for line in show_out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            details[key] = value.strip()

    pid = details.get("MainPID")
    pid_value = int(pid) if pid and pid.isdigit() and int(pid) > 0 else None

    return {
        "running": active_rc == 0,
        "enabled": enabled_out.strip() == "enabled",
        "status_text": active_out.strip(),
        "sub_state": details.get("SubState", ""),
        "pid": pid_value,
    }


async def _clash_api(
    instance: dict[str, Any],
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any] | None:
    admin_api = instance.get("admin_api") or {}
    base_url = str(admin_api.get("base_url", "")).rstrip("/")
    if not base_url:
        return None

    secret = str(admin_api.get("secret", "")).strip()
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.request(
                method,
                f"{base_url}{path}",
                headers=headers,
                json=json_data,
            )
        if response.status_code == 204:
            return {}
        return response.json()
    except Exception:
        return None


def _preferred_update_config_key(instance: dict[str, Any]) -> str | None:
    for profile in instance.get("config_profiles", []):
        if profile.get("preferred_after_update"):
            return str(profile.get("key"))
    return None


def _supported_actions(instance: dict[str, Any]) -> list[str]:
    capabilities = instance.get("capabilities") or {}
    supported: list[str] = []

    for action in capabilities.get("systemd_actions", []):
        if action not in supported:
            supported.append(action)

    if instance.get("config_profiles"):
        supported.append("switch_config")

    if any(profile.get("has_subscription") for profile in instance.get("config_profiles", [])) or _get_command_spec_from_instance(instance, "update_subscription"):
        supported.append("update_subscription")

    return supported


async def get_proxy_instance_status(instance_id: str) -> dict[str, Any]:
    instance = _require_instance(instance_id)
    systemd_state = await _query_systemd(instance.get("service_name", ""))
    current_config, current_config_name = _resolve_current_config(instance)
    supported_actions = _supported_actions(instance)

    result = {
        "id": instance["id"],
        "name": instance.get("name", instance["id"]),
        "type": instance.get("type", "generic"),
        "plugin": instance.get("plugin", ""),
        "service_name": instance.get("service_name", ""),
        "running": systemd_state["running"],
        "enabled": systemd_state["enabled"],
        "status_text": systemd_state["status_text"],
        "sub_state": systemd_state.get("sub_state", ""),
        "pid": systemd_state.get("pid"),
        "listen_ports": instance.get("listen_ports", []),
        "admin_api": {
            "base_url": (instance.get("admin_api") or {}).get("base_url", "")
        },
        "current_config": current_config,
        "current_config_name": current_config_name,
        "config_profiles": instance.get("config_profiles", []),
        "preferred_update_config_key": _preferred_update_config_key(instance),
        "supported_actions": supported_actions,
        "capabilities": {
            "config_switch": "switch_config" in supported_actions,
            "subscription_update": "update_subscription" in supported_actions,
            "node_switch": bool((instance.get("capabilities") or {}).get("node_switch")),
            "delay_test": bool((instance.get("capabilities") or {}).get("delay_test")),
        },
        "available_extensions": [instance["plugin"]] if instance.get("plugin") else [],
    }

    if instance.get("plugin") == "clash":
        version = await _clash_api(instance, "GET", "/version")
        result["version"] = version.get("version", "") if isinstance(version, dict) else ""
        result["premium"] = bool(version.get("premium", False)) if isinstance(version, dict) else False
    else:
        result["version"] = ""
        result["premium"] = False

    return result


async def list_proxy_instances() -> dict[str, Any]:
    registry = _load_proxy_registry()
    tasks = [get_proxy_instance_status(instance["id"]) for instance in registry["instances"]]
    instances = await asyncio.gather(*tasks) if tasks else []
    return {
        "default_instance_id": registry["default_instance_id"],
        "instances": instances,
    }


def _materialize_command(
    argv: list[str],
    instance: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
) -> list[str]:
    profile = profile or {}
    values = {
        "instance_id": instance.get("id", ""),
        "instance_name": instance.get("name", ""),
        "service_name": instance.get("service_name", ""),
        "config_key": profile.get("key", ""),
        "config_name": profile.get("name", ""),
        "config_arg": profile.get("switch_arg") or profile.get("key", ""),
    }
    return [str(part).format(**values) for part in argv]


def _is_command_success(returncode: int, output: str, success_any_of: list[str]) -> bool:
    if returncode == 0:
        return True
    return any(pattern and pattern in output for pattern in success_any_of)


def _unsupported(action: str) -> dict[str, Any]:
    return {
        "ok": False,
        "unsupported": True,
        "msg": f"当前实例不支持操作: {ACTION_LABELS.get(action, action)}",
    }


def _prepare_clash_config_content(raw_content: str, instance: dict[str, Any]) -> str:
    admin_api = instance.get("admin_api") or {}
    base_url = str(admin_api.get("base_url", "")).strip()
    parsed = urlparse(base_url) if base_url else None
    controller = parsed.netloc if parsed and parsed.netloc else "0.0.0.0:9090"
    secret = str(admin_api.get("secret", "")).strip()
    ui_dir = str(instance.get("external_ui") or "/opt/clash/ui").strip()

    content = raw_content.replace("\r\n", "\n")
    content = re.sub(r"(?m)^external-ui:\s*.*\n?", "", content)
    content = re.sub(r"(?m)^secret:\s*.*\n?", "", content)

    controller_line = f"external-controller: '{controller}'"
    if re.search(r"(?m)^external-controller:\s*.*$", content):
        content = re.sub(
            r"(?m)^external-controller:\s*.*$",
            controller_line,
            content,
            count=1,
        )
    else:
        content = controller_line + "\n" + content

    insert_lines = f"external-ui: {ui_dir}\n"
    if secret:
        insert_lines += f'secret: "{secret}"\n'
    content = re.sub(
        r"(?m)^(external-controller:\s*.*)$",
        r"\1\n" + insert_lines.rstrip("\n"),
        content,
        count=1,
    )
    if not content.endswith("\n"):
        content += "\n"
    return content


async def _write_config_file(target_file: str, content: str) -> None:
    target = Path(target_file)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.access(target.parent, os.W_OK):
            target.write_text(content, encoding="utf-8")
            return
    except Exception:
        pass

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        await _run(["sudo", "install", "-D", "-m", "0644", tmp_path, target_file], timeout=20)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


async def _download_subscription_to_profile(instance: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    subscription_url = str(profile.get("subscription_url", "")).strip()
    if not subscription_url:
        return _unsupported("update_subscription")

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(subscription_url, headers=headers)
            response.raise_for_status()
            raw_content = response.text
    except Exception as exc:
        return {"ok": False, "msg": f"订阅拉取失败: {exc}"}

    if not raw_content.strip():
        return {"ok": False, "msg": "订阅返回内容为空"}

    content = _prepare_clash_config_content(raw_content, instance)
    target_file = str(profile.get("file", "")).strip()
    if not target_file:
        return {"ok": False, "msg": "配置文件路径未定义"}

    try:
        await _write_config_file(target_file, content)
    except Exception as exc:
        return {"ok": False, "msg": f"配置写入失败: {exc}"}

    return {
        "ok": True,
        "msg": f"已更新 {profile.get('name', profile.get('key', '订阅配置'))}",
        "profile_key": profile.get("key"),
        "output": f"saved to {target_file}",
    }


async def _switch_by_symlink(instance: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    target_file = str(profile.get("file", "")).strip()
    active_link = str(instance.get("active_config_link", "")).strip()
    service_name = str(instance.get("service_name", "")).strip()

    if not target_file:
        return {"ok": False, "msg": "配置文件路径未定义"}
    if not os.path.exists(target_file):
        return {"ok": False, "msg": f"配置文件不存在: {target_file}"}
    if not active_link:
        return {"ok": False, "msg": "实例未定义活动配置链接"}

    outputs = []
    try:
        _, out = await _run(["sudo", "ln", "-sfn", target_file, active_link], timeout=15)
        if out:
            outputs.append(out)
        if service_name:
            _, out = await _run(["sudo", "systemctl", "restart", service_name], timeout=30)
            if out:
                outputs.append(out)
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}

    return {
        "ok": True,
        "msg": f"已切换到 {profile.get('name', profile.get('key', '配置'))}",
        "output": "\n".join(outputs).strip(),
    }


def _select_subscription_profile(instance: dict[str, Any], profile_key: str | None = None) -> dict[str, Any] | None:
    profiles = instance.get("config_profiles", [])

    if profile_key:
        profile = _find_profile(instance, profile_key)
        return profile if profile.get("has_subscription") else None

    current_key, _ = _resolve_current_config(instance)
    for profile in profiles:
        if profile.get("key") == current_key and profile.get("has_subscription"):
            return profile

    preferred_key = _preferred_update_config_key(instance)
    for profile in profiles:
        if profile.get("key") == preferred_key and profile.get("has_subscription"):
            return profile

    for profile in profiles:
        if profile.get("has_subscription"):
            return profile

    return None


async def run_proxy_instance_action(instance_id: str, action: str) -> dict[str, Any]:
    instance = _require_instance(instance_id)
    capabilities = instance.get("capabilities") or {}
    systemd_actions = set(capabilities.get("systemd_actions", []))

    if action in systemd_actions:
        service_name = str(instance.get("service_name", "")).strip()
        if not service_name:
            return _unsupported(action)

        try:
            returncode, output = await _run(
                ["sudo", "systemctl", action, service_name],
                timeout=30,
            )
        except Exception as exc:
            return {"ok": False, "msg": str(exc)}

        ok = returncode == 0
        label = ACTION_LABELS.get(action, action)
        return {
            "ok": ok,
            "msg": f"{instance.get('name', instance_id)}已{label}" if ok else f"{label}失败",
            "output": output,
        }

    if action == "update_subscription":
        return await update_subscription(instance_id)

    return _unsupported(action)


async def switch_proxy_config(instance_id: str, config_key: str) -> dict[str, Any]:
    instance = _require_instance(instance_id)
    profile = _find_profile(instance, config_key)

    active_link = str(instance.get("active_config_link", "")).strip()
    if active_link:
        return await _switch_by_symlink(instance, profile)

    spec = _get_command_spec_from_instance(instance, "switch_config")
    if not spec:
        return _unsupported("switch_config")

    try:
        returncode, output = await _run(
            _materialize_command(spec["argv"], instance, profile=profile),
            timeout=spec["timeout"],
        )
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}

    ok = _is_command_success(returncode, output, spec["success_any_of"])
    return {
        "ok": ok,
        "msg": f"已切换到 {profile.get('name', config_key)}" if ok else "切换失败",
        "output": output,
    }


async def update_subscription(instance_id: str | None = None, profile_key: str | None = None) -> dict[str, Any]:
    if not instance_id:
        instance_id = get_default_instance_id()
    if not instance_id:
        return {"ok": False, "msg": "未配置默认代理实例"}

    instance = _require_instance(instance_id)
    profile = _select_subscription_profile(instance, profile_key=profile_key)
    if profile:
        return await _download_subscription_to_profile(instance, profile)

    spec = _get_command_spec_from_instance(instance, "update_subscription")
    if not spec:
        return _unsupported("update_subscription")

    try:
        returncode, output = await _run(
            _materialize_command(spec["argv"], instance),
            timeout=spec["timeout"],
        )
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}

    ok = _is_command_success(returncode, output, spec["success_any_of"])
    return {
        "ok": ok,
        "msg": "订阅更新成功" if ok else "订阅更新失败",
        "output": output,
    }


async def add_subscription_profile(
    instance_id: str,
    name: str,
    subscription_url: str,
    switch_after_add: bool = False,
) -> dict[str, Any]:
    name = name.strip()
    subscription_url = subscription_url.strip()
    if not name:
        raise ValueError("名称不能为空")
    if not subscription_url.startswith(("http://", "https://")):
        raise ValueError("订阅链接必须以 http:// 或 https:// 开头")

    registry = _load_registry_for_update()
    instance = _require_instance_from_registry(registry, instance_id)

    key = _ensure_unique_profile_key(instance, name, subscription_url)
    profile_dir = _profile_base_dir(instance) / PROFILE_DIR_NAME
    profile = {
        "key": key,
        "name": name,
        "file": str(profile_dir / f"{key}.yaml"),
        "switch_arg": key,
        "subscription_url": subscription_url,
    }
    normalized_profile = _normalize_profile(profile, instance)

    update_result = await _download_subscription_to_profile(instance, normalized_profile)
    if not update_result.get("ok"):
        return update_result

    instance.setdefault("config_profiles", []).append(normalized_profile)
    instance.setdefault("capabilities", {})
    instance["capabilities"]["config_switch"] = True
    instance["capabilities"]["subscription_update"] = True
    _persist_registry(registry)

    result = {
        "ok": True,
        "msg": f"已添加机场配置: {name}",
        "profile": normalized_profile,
    }

    if switch_after_add:
        switch_result = await _switch_by_symlink(instance, normalized_profile)
        result["switch"] = switch_result
        if switch_result.get("ok"):
            result["msg"] = f"已添加并切换到 {name}"
        else:
            result["msg"] = f"已添加 {name}，但切换失败"

    return result


def _require_clash_plugin(instance: dict[str, Any]) -> None:
    if instance.get("plugin") != "clash":
        raise ValueError(f"实例 {instance.get('name', instance['id'])} 不支持 Clash 扩展能力")


async def get_clash_proxy_groups(instance_id: str) -> list[dict[str, Any]]:
    instance = _require_instance(instance_id)
    _require_clash_plugin(instance)

    data = await _clash_api(instance, "GET", "/proxies")
    if not isinstance(data, dict) or "proxies" not in data:
        return []

    groups = []
    proxies = data["proxies"]
    for name, info in proxies.items():
        if info.get("type") in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            groups.append(
                {
                    "name": name,
                    "type": info["type"],
                    "now": info.get("now", ""),
                    "all": info.get("all", []),
                }
            )

    groups.sort(key=lambda group: (0 if group["type"] == "Selector" else 1, group["name"]))
    return groups


async def switch_proxy_node(instance_id: str, group: str, node: str) -> bool:
    instance = _require_instance(instance_id)
    _require_clash_plugin(instance)

    result = await _clash_api(
        instance,
        "PUT",
        f"/proxies/{quote(group, safe='')}",
        json_data={"name": node},
    )
    return result is not None


async def test_group_delays(instance_id: str, group: str) -> dict[str, Any]:
    instance = _require_instance(instance_id)
    _require_clash_plugin(instance)

    data = await _clash_api(
        instance,
        "GET",
        f"/group/{quote(group, safe='')}/delay",
    )
    return data if isinstance(data, dict) else {}


async def get_clash_status() -> dict[str, Any]:
    instance_id = get_default_instance_id()
    if not instance_id:
        return {
            "running": False,
            "version": "",
            "premium": False,
            "current_config": "unknown",
            "current_config_name": "未知",
            "configs": {},
        }

    status = await get_proxy_instance_status(instance_id)
    return {
        "running": status["running"],
        "version": status.get("version", ""),
        "premium": status.get("premium", False),
        "current_config": status["current_config"],
        "current_config_name": status["current_config_name"],
        "configs": _to_configs_mapping(_require_instance(instance_id)),
        "instance_id": status["id"],
        "name": status["name"],
    }


async def get_proxy_groups() -> list[dict[str, Any]]:
    instance_id = get_default_instance_id()
    if not instance_id:
        return []
    try:
        return await get_clash_proxy_groups(instance_id)
    except ValueError:
        return []


async def switch_config(config_key: str) -> dict[str, Any]:
    instance_id = get_default_instance_id()
    if not instance_id:
        return {"ok": False, "msg": "未配置默认代理实例"}
    return await switch_proxy_config(instance_id, config_key)


async def restart_clash() -> dict[str, Any]:
    instance_id = get_default_instance_id()
    if not instance_id:
        return {"ok": False, "msg": "未配置默认代理实例"}
    return await run_proxy_instance_action(instance_id, "restart")

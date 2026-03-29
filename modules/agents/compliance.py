"""安全合规检查与修复。"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from utils.command import run_command

from config import BASE_DIR

logger = logging.getLogger(__name__)

BASELINES_PATH = Path(BASE_DIR) / "data" / "compliance_baselines.json"
SSH_CONFIG_PATH = Path("/etc/ssh/sshd_config")
LOGIN_DEFS_PATH = Path("/etc/login.defs")
COMMON_PASSWORD_PATH = Path("/etc/pam.d/common-password")
SUDOERS_PATH = Path("/etc/sudoers")
SUDOERS_DIR = Path("/etc/sudoers.d")


def load_compliance_baselines() -> list[dict]:
    """加载合规基线元数据。"""
    if not BASELINES_PATH.exists():
        raise FileNotFoundError("合规基线文件不存在: data/compliance_baselines.json")

    data = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("baselines", data.get("checks", []))
    return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _first_matching_line(path: Path, pattern: str) -> str:
    regex = re.compile(pattern)
    for line in _read_text(path).splitlines():
        if regex.search(line):
            return line.strip()
    return ""


def _matching_lines(paths: list[Path], pattern: str, limit: int = 5) -> list[str]:
    regex = re.compile(pattern)
    matches: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for line in _read_text(path).splitlines():
            if regex.search(line):
                matches.append(line.strip())
                if len(matches) >= limit:
                    return matches
    return matches


def _run_output(args: list[str], timeout: int = 10) -> str:
    try:
        return run_command(args, timeout=timeout, check=False).output
    except RuntimeError:
        return ""


def _systemctl_active(unit: str) -> str:
    return _run_output(["systemctl", "is-active", unit], timeout=10) or "inactive"


def _iptables_input_status() -> str:
    output = _run_output(["sudo", "iptables", "-L", "INPUT", "-n"], timeout=10)
    return "1" if "Chain INPUT" in output else "0"


def _tmp_mount_options() -> str:
    for line in _read_text(Path("/proc/mounts")).splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/tmp":
            return line.strip()
    return "NOT_SEPARATE"


def _find_world_writable_files() -> str:
    output = _run_output(
        ["find", "/etc", "/usr/bin", "/usr/sbin", "-maxdepth", "1", "-perm", "-o+w", "-type", "f"],
        timeout=20,
    )
    if not output:
        return "NONE"
    return "\n".join(output.splitlines()[:5])


def _sudoers_nopasswd_lines() -> str:
    paths = [SUDOERS_PATH]
    if SUDOERS_DIR.exists():
        paths.extend(sorted(path for path in SUDOERS_DIR.iterdir() if path.is_file()))
    matches = _matching_lines(paths, r"NOPASSWD.*ALL")
    filtered = [line for line in matches if not line.lstrip().startswith("#")]
    return "\n".join(filtered[:5]) if filtered else "NO_NOPASSWD"


def _password_min_length_line() -> str:
    matches = _matching_lines(
        [LOGIN_DEFS_PATH, COMMON_PASSWORD_PATH],
        r"(PASS_MIN_LEN|minlen\s*=\s*\d+)",
    )
    return "\n".join(matches) if matches else "MIN_LEN 5"


def _replace_or_append_line(path: Path, pattern: str, replacement: str) -> None:
    regex = re.compile(pattern)
    content = _read_text(path)
    lines = content.splitlines()
    replaced = False
    new_lines: list[str] = []
    for line in lines:
        if regex.match(line):
            if not replaced:
                new_lines.append(replacement)
                replaced = True
            continue
        new_lines.append(line)
    if not replaced:
        new_lines.append(replacement)

    rendered = "\n".join(new_lines).rstrip() + "\n"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
            tmp.write(rendered)
            tmp_path = tmp.name
        run_command(["sudo", "install", "-m", "0644", tmp_path, str(path)], timeout=20, check=True)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning("临时文件清理失败: %s", tmp_path)


def _reload_sshd() -> None:
    run_command(["sudo", "systemctl", "reload", "sshd"], timeout=15, check=True)


def _fix_ssh_empty_password() -> str:
    _replace_or_append_line(SSH_CONFIG_PATH, r"^\s*#?\s*PermitEmptyPasswords\b.*$", "PermitEmptyPasswords no")
    _reload_sshd()
    return "已设置 PermitEmptyPasswords no，并重载 sshd"


def _fix_ssh_max_auth_tries() -> str:
    _replace_or_append_line(SSH_CONFIG_PATH, r"^\s*#?\s*MaxAuthTries\b.*$", "MaxAuthTries 4")
    _reload_sshd()
    return "已设置 MaxAuthTries 4，并重载 sshd"


COMPLIANCE_CHECKS: dict[str, Callable[[], str]] = {
    "ssh_root_login": lambda: _first_matching_line(SSH_CONFIG_PATH, r"^\s*PermitRootLogin\b.*$") or "NOT_FOUND",
    "ssh_empty_password": lambda: (
        _first_matching_line(SSH_CONFIG_PATH, r"^\s*PermitEmptyPasswords\b.*$") or "NOT_FOUND"
    ),
    "ssh_max_auth_tries": lambda: _first_matching_line(SSH_CONFIG_PATH, r"^\s*MaxAuthTries\b.*$") or "MaxAuthTries 6",
    "ssh_protocol_2": lambda: (
        "FOUND_V1" if _first_matching_line(SSH_CONFIG_PATH, r"^\s*Protocol\s+1\b.*$") else "OK_V2"
    ),
    "password_max_days": lambda: (
        _first_matching_line(LOGIN_DEFS_PATH, r"^\s*PASS_MAX_DAYS\b.*$") or "PASS_MAX_DAYS 99999"
    ),
    "password_min_days": lambda: _first_matching_line(LOGIN_DEFS_PATH, r"^\s*PASS_MIN_DAYS\b.*$") or "PASS_MIN_DAYS 0",
    "password_min_length": _password_min_length_line,
    "sudo_requiretty": _sudoers_nopasswd_lines,
    "world_writable_files": _find_world_writable_files,
    "firewall_active": _iptables_input_status,
    "fail2ban_running": lambda: _systemctl_active("fail2ban"),
    "kernel_randomize_va": lambda: _read_text(Path("/proc/sys/kernel/randomize_va_space")).strip() or "0",
    "syslog_running": lambda: (
        "active"
        if "active" in {_systemctl_active("rsyslog").strip(), _systemctl_active("systemd-journald").strip()}
        else "inactive"
    ),
    "tmp_noexec": _tmp_mount_options,
    "core_dump_restricted": lambda: _read_text(Path("/proc/sys/fs/suid_dumpable")).strip() or "2",
}

COMPLIANCE_FIXERS: dict[str, Callable[[], str]] = {
    "ssh_empty_password": _fix_ssh_empty_password,
    "ssh_max_auth_tries": _fix_ssh_max_auth_tries,
}


def _evaluate_baseline(baseline: dict, output: str) -> tuple[bool, str]:
    passed = True
    detail = output[:100] if output else "无输出"

    if "expect_contains" in baseline and baseline["expect_contains"] not in output:
        passed = False
        detail = f"期望包含 '{baseline['expect_contains']}', 实际: {output[:80]}"

    if "fail_if_contains" in baseline and baseline["fail_if_contains"] in output:
        passed = False
        detail = f"检测到不安全配置: {output[:80]}"

    if "expect_regex" in baseline:
        match = re.search(baseline["expect_regex"], output)
        if match:
            try:
                value = int(match.group(1))
                if "expect_max" in baseline and value > baseline["expect_max"]:
                    passed = False
                    detail = f"当前值 {value} 超过最大值 {baseline['expect_max']}"
                if "expect_min" in baseline and value < baseline["expect_min"]:
                    passed = False
                    detail = f"当前值 {value} 低于最小值 {baseline['expect_min']}"
            except (ValueError, IndexError) as e:
                logger.debug("基线数值解析失败: %s", e)
        else:
            passed = False
            detail = "未匹配到期望模式"

    return passed, detail


def run_compliance_checks(category: str = "") -> str:
    """执行白名单合规检查。"""
    baselines = load_compliance_baselines()
    if category:
        baselines = [item for item in baselines if category.lower() in item.get("category", "").lower()]
    if not baselines:
        return f"没有找到分类 '{category}' 的基线检查项。"

    rows: list[str] = []
    pass_count = 0
    total = len(baselines)

    for baseline in baselines:
        baseline_id = baseline["id"]
        name = baseline["name"]
        severity = baseline.get("severity", "medium")
        checker = COMPLIANCE_CHECKS.get(baseline_id)
        if not checker:
            rows.append(f"| {name} | SKIP | {severity} | 当前版本未实现该检查项 |")
            continue

        try:
            output = checker()
        except Exception as exc:
            logger.exception("执行合规检查失败: %s", baseline_id)
            rows.append(f"| {name} | ERROR | {severity} | {str(exc)[:100]} |")
            continue

        passed, detail = _evaluate_baseline(baseline, output)
        if passed:
            pass_count += 1
        fix_info = ""
        if not passed and baseline.get("fix_guide"):
            fix_info = f" → {baseline['fix_guide']}"
        rows.append(f"| {name} | {'PASS' if passed else 'FAIL'} | {severity} | {detail}{fix_info} |")

    compliance_rate = round(pass_count / total * 100, 1) if total else 0
    header = (
        f"## 安全合规检查报告\n\n"
        f"合规率: **{compliance_rate}%** ({pass_count}/{total} 通过)\n\n"
        f"| 检查项 | 结果 | 严重级别 | 详情 |\n|---|---|---|---|"
    )
    return header + "\n" + "\n".join(rows)


def fix_compliance_item(item_id: str) -> str:
    """执行白名单修复逻辑。"""
    baselines = load_compliance_baselines()
    item = next((baseline for baseline in baselines if baseline["id"] == item_id), None)
    if not item:
        available = ", ".join(sorted(COMPLIANCE_FIXERS))
        return f"未找到基线项 '{item_id}'。可自动修复的项: {available}"

    if not item.get("auto_fixable"):
        return f"基线项 '{item['name']}' 不支持自动修复。修复指导: {item.get('fix_guide', '无')}"

    fixer = COMPLIANCE_FIXERS.get(item_id)
    if not fixer:
        return f"基线项 '{item['name']}' 当前版本未提供自动修复实现。"

    try:
        fix_output = fixer()
    except Exception as exc:
        logger.exception("自动修复失败: %s", item_id)
        return f"修复失败: {exc}"

    checker = COMPLIANCE_CHECKS.get(item_id)
    if not checker:
        return f"修复已执行: {fix_output}"

    try:
        output = checker()
    except Exception as exc:
        return f"修复已执行，但复检失败: {exc}"

    passed, detail = _evaluate_baseline(item, output)
    if passed:
        return f"修复成功: {item['name']}。{fix_output}"
    return f"修复后仍未通过: {item['name']}。当前结果: {detail}"

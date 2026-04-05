"""执行级 Scratchpad — 团队 Worker 间跨智能体知识共享

每次团队执行创建独立目录 /tmp/serverhub-teams/{exec_id}/scratchpad/
Worker 通过 scratchpad_write / scratchpad_read 工具读写。
执行结束后自动清理（可配置）。
"""

import logging
import shutil
from pathlib import Path

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

SCRATCHPAD_BASE = Path("/tmp/serverhub-teams")


def get_scratchpad_dir(exec_id: str) -> Path:
    """获取或创建执行级 scratchpad 目录"""
    path = SCRATCHPAD_BASE / exec_id / "scratchpad"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_stage_dir(exec_id: str, stage_name: str) -> Path:
    """获取 Pipeline 阶段专属工作目录"""
    path = SCRATCHPAD_BASE / exec_id / "stages" / stage_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_scratchpad(exec_id: str) -> None:
    """清理执行的临时目录（fail-safe: 忽略清理错误）"""
    target = SCRATCHPAD_BASE / exec_id
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        logger.info("已清理团队 scratchpad: %s", target)


def _safe_path(base: Path, user_path: str) -> Path:
    """验证路径安全性，防止路径穿越攻击

    Raises:
        ValueError: 路径穿越到 base 目录外
    """
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"路径穿越被阻止: {user_path}")
    return resolved


def create_scratchpad_tools(exec_id: str) -> list[StructuredTool]:
    """为指定执行创建 scratchpad 工具集

    Args:
        exec_id: 执行 ID，用于隔离 scratchpad 目录

    Returns:
        [scratchpad_write, scratchpad_read] 两个工具
    """
    base = get_scratchpad_dir(exec_id)

    def scratchpad_write(path: str, content: str, append: bool = False) -> str:
        """写入内容到团队共享 scratchpad，其他成员可通过 scratchpad_read 读取。

        Args:
            path: 文件路径（相对于 scratchpad 根，如 'findings.md'）
            content: 文件内容
            append: 是否追加模式（默认覆盖）
        """
        try:
            target = _safe_path(base, path)
        except ValueError as e:
            return f"错误: {e}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with open(target, "a") as f:
                f.write(content)
        else:
            target.write_text(content)
        return f"已写入 scratchpad/{path} ({len(content)} 字符)"

    def scratchpad_read(path: str = "") -> str:
        """读取团队共享 scratchpad 内容。留空路径则列出所有文件。

        Args:
            path: 文件路径（留空列出所有文件）
        """
        if not path:
            files = []
            for f in sorted(base.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(base)
                    size = f.stat().st_size
                    files.append(f"  {rel} ({size} bytes)")
            return "Scratchpad 文件列表:\n" + "\n".join(files) if files else "Scratchpad 为空"
        try:
            target = _safe_path(base, path)
        except ValueError as e:
            return f"错误: {e}"
        if not target.exists():
            return f"文件不存在: scratchpad/{path}"
        content = target.read_text()
        if len(content) > 10000:
            return content[:10000] + f"\n\n... [截断，共 {len(content)} 字符]"
        return content

    write_tool = StructuredTool.from_function(
        scratchpad_write,
        name="scratchpad_write",
        description="写入内容到团队共享 scratchpad（其他成员可读取）。参数: path (str), content (str), append (bool, 默认 False)",
    )

    read_tool = StructuredTool.from_function(
        scratchpad_read,
        name="scratchpad_read",
        description="读取团队共享 scratchpad 内容（留空路径列出所有文件）。参数: path (str, 默认 '')",
    )

    return [write_tool, read_tool]


SCRATCHPAD_PROMPT_SUFFIX = """

## 团队共享 Scratchpad
你可以使用 scratchpad_write 和 scratchpad_read 与团队成员共享信息:
- scratchpad_write(path, content): 写入发现、数据、中间结果
- scratchpad_read(path): 读取其他成员写入的内容（留空列出文件）

建议: 开始工作前先 scratchpad_read("") 查看其他成员已共享的内容。
"""

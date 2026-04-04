"""结构化记忆存储 — JSON 文件持久化"""

import json
import logging
import time
import uuid
from datetime import UTC
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MEMORY = {
    "version": "1.0",
    "lastUpdated": "",
    "context": {
        "workContext": {"summary": "", "updatedAt": ""},
        "userPreferences": {"summary": "", "updatedAt": ""},
        "topOfMind": {"summary": "", "updatedAt": ""},
    },
    "history": {
        "recentActivity": {"summary": "", "updatedAt": ""},
        "longTermBackground": {"summary": "", "updatedAt": ""},
    },
    "facts": [],
}


class MemoryStorage:
    """基于 JSON 文件的结构化记忆存储"""

    def __init__(self, memory_dir: Path):
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict | None = None
        self._file_mtime: float = 0.0

    @property
    def _path(self) -> Path:
        return self._dir / "memory.json"

    def load(self) -> dict:
        """加载记忆数据（带文件修改时间缓存）"""
        path = self._path
        if not path.exists():
            self._cache = json.loads(json.dumps(DEFAULT_MEMORY))
            return self._cache

        mtime = path.stat().st_mtime
        if self._cache is not None and mtime <= self._file_mtime:
            return self._cache

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._cache = data
            self._file_mtime = mtime
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("记忆文件读取失败: %s, 使用默认值", e)
            self._cache = json.loads(json.dumps(DEFAULT_MEMORY))
            return self._cache

    def save(self, data: dict) -> None:
        """原子写入记忆数据"""
        from datetime import datetime

        data["lastUpdated"] = datetime.now(UTC).isoformat()
        tmp_path = self._path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)
            self._cache = data
            self._file_mtime = self._path.stat().st_mtime
        except OSError as e:
            logger.error("记忆文件写入失败: %s", e)
            tmp_path.unlink(missing_ok=True)

    def add_fact(
        self,
        content: str,
        category: str = "knowledge",
        confidence: float = 0.8,
        source: str = "",
    ) -> bool:
        """添加一条事实（自动去重）

        Returns:
            True 表示新增成功，False 表示内容为空或已存在（去重）
        """
        data = self.load()
        normalized = content.strip().lower()
        if not normalized:
            return False
        for existing in data["facts"]:
            if existing["content"].strip().lower() == normalized:
                # Update confidence if higher
                if confidence > existing.get("confidence", 0):
                    existing["confidence"] = confidence
                    existing["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self.save(data)
                return False

        fact = {
            "id": str(uuid.uuid4())[:8],
            "content": content,
            "category": category,
            "confidence": confidence,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": source,
        }
        data["facts"].append(fact)
        # Keep max 50 facts, evict lowest confidence
        if len(data["facts"]) > 50:
            data["facts"].sort(key=lambda f: f.get("confidence", 0), reverse=True)
            data["facts"] = data["facts"][:50]
        self.save(data)
        return True

    def remove_fact(self, fact_id: str) -> bool:
        data = self.load()
        original_len = len(data["facts"])
        data["facts"] = [f for f in data["facts"] if f.get("id") != fact_id]
        if len(data["facts"]) < original_len:
            self.save(data)
            return True
        return False

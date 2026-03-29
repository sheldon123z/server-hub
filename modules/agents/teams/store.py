"""团队数据存取层 — 团队/成员/执行/消息的 CRUD 操作

所有 SQL 参数化，写操作先 commit 再执行副作用。
"""

import json
import logging
import uuid

from database import get_db

logger = logging.getLogger(__name__)


class TeamStore:
    """团队数据存取层"""

    # ─── 团队 CRUD ───

    async def create_team(self, data: dict) -> dict:
        """创建团队，返回完整团队记录"""
        db = await get_db()
        team_id = data.get("id") or str(uuid.uuid4())[:8]
        await db.execute(
            "INSERT INTO agent_teams "
            "(id, name, description, topology, config_json, default_model, "
            "safety_mode, max_steps, timeout_seconds, enabled, is_builtin, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                team_id,
                data["name"],
                data.get("description", ""),
                data.get("topology", "supervisor"),
                json.dumps(data.get("config", {}), ensure_ascii=False),
                data.get("default_model"),
                data.get("safety_mode", "supervised"),
                data.get("max_steps", 50),
                data.get("timeout_seconds", 300),
                1 if data.get("enabled", True) else 0,
                data.get("is_builtin", 0),
                data.get("created_by", "system"),
            ),
        )
        await db.commit()
        return await self.get_team(team_id)

    async def get_team(self, team_id: str) -> dict | None:
        """根据 ID 获取单个团队"""
        db = await get_db()
        cursor = await db.execute("SELECT * FROM agent_teams WHERE id = ?", (team_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_teams(self, enabled_only: bool = False) -> list[dict]:
        """列出所有团队，可选只返回启用的"""
        db = await get_db()
        sql = "SELECT * FROM agent_teams"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        cursor = await db.execute(sql)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_team(self, team_id: str, data: dict) -> dict | None:
        """更新团队字段，返回更新后的记录"""
        db = await get_db()
        fields: list[str] = []
        values: list = []

        updatable_keys = (
            "name",
            "description",
            "topology",
            "default_model",
            "safety_mode",
            "max_steps",
            "timeout_seconds",
            "enabled",
        )
        for key in updatable_keys:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])

        if "config" in data:
            fields.append("config_json = ?")
            values.append(json.dumps(data["config"], ensure_ascii=False))

        if not fields:
            return await self.get_team(team_id)

        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(team_id)

        await db.execute(
            f"UPDATE agent_teams SET {', '.join(fields)} WHERE id = ?",  # noqa: S608 — 列名来自代码白名单
            values,
        )
        await db.commit()
        return await self.get_team(team_id)

    async def delete_team(self, team_id: str) -> bool:
        """删除非内置团队，CASCADE 自动删除成员。返回是否实际删除"""
        db = await get_db()
        cursor = await db.execute(
            "DELETE FROM agent_teams WHERE id = ? AND is_builtin = 0",
            (team_id,),
        )
        await db.commit()
        return cursor.rowcount > 0

    # ─── 成员 CRUD ───

    async def get_members(self, team_id: str) -> list[dict]:
        """获取团队所有成员，按 position 排序"""
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM agent_team_members WHERE team_id = ? ORDER BY position, name",
            (team_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_member(self, member_id: str) -> dict | None:
        """根据 ID 获取单个成员"""
        db = await get_db()
        cursor = await db.execute("SELECT * FROM agent_team_members WHERE id = ?", (member_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def add_member(self, team_id: str, data: dict) -> dict:
        """添加团队成员，同时更新团队 updated_at 触发缓存失效"""
        db = await get_db()
        member_id = str(uuid.uuid4())[:8]
        await db.execute(
            "INSERT INTO agent_team_members "
            "(id, team_id, name, agent_type, description, system_prompt, "
            "tools_json, model_id, max_calls, handoff_targets, position, config_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                member_id,
                team_id,
                data["name"],
                data.get("agent_type", "worker"),
                data.get("description", ""),
                data["system_prompt"],
                json.dumps(data.get("tools", []), ensure_ascii=False),
                data.get("model_id"),
                data.get("max_calls", 15),
                json.dumps(data.get("handoff_targets", []), ensure_ascii=False),
                data.get("position", 0),
                json.dumps(data.get("config", {}), ensure_ascii=False),
            ),
        )
        # 更新团队 updated_at 触发图缓存失效
        await db.execute(
            "UPDATE agent_teams SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (team_id,),
        )
        await db.commit()
        return {"id": member_id, "team_id": team_id, **data}

    async def update_member(self, member_id: str, data: dict) -> dict | None:
        """更新成员字段，同时触发所属团队缓存失效"""
        db = await get_db()

        fields: list[str] = []
        values: list = []

        updatable_keys = (
            "name",
            "agent_type",
            "description",
            "system_prompt",
            "model_id",
            "max_calls",
            "position",
        )
        for key in updatable_keys:
            if key in data:
                fields.append(f"{key} = ?")
                values.append(data[key])

        if "tools" in data:
            fields.append("tools_json = ?")
            values.append(json.dumps(data["tools"], ensure_ascii=False))

        if "handoff_targets" in data:
            fields.append("handoff_targets = ?")
            values.append(json.dumps(data["handoff_targets"], ensure_ascii=False))

        if "config" in data:
            fields.append("config_json = ?")
            values.append(json.dumps(data["config"], ensure_ascii=False))

        if not fields:
            return await self.get_member(member_id)

        values.append(member_id)
        await db.execute(
            f"UPDATE agent_team_members SET {', '.join(fields)} WHERE id = ?",  # noqa: S608 — 列名来自代码白名单
            values,
        )

        # 更新所属团队 updated_at 触发缓存失效
        cursor = await db.execute("SELECT team_id FROM agent_team_members WHERE id = ?", (member_id,))
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE agent_teams SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row[0],),
            )

        await db.commit()
        return await self.get_member(member_id)

    async def remove_member(self, member_id: str) -> bool:
        """移除成员，同时触发所属团队缓存失效。返回是否实际删除"""
        db = await get_db()

        # 先查所属团队以便更新 updated_at
        cursor = await db.execute("SELECT team_id FROM agent_team_members WHERE id = ?", (member_id,))
        row = await cursor.fetchone()

        result = await db.execute("DELETE FROM agent_team_members WHERE id = ?", (member_id,))
        if row:
            await db.execute(
                "UPDATE agent_teams SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row[0],),
            )
        await db.commit()
        return result.rowcount > 0

    # ─── 执行记录 ───

    async def create_execution(
        self,
        team_id: str,
        instruction: str,
        username: str,
        topology: str,
    ) -> dict:
        """创建执行记录，初始状态为 running"""
        db = await get_db()
        exec_id = str(uuid.uuid4())[:12]
        await db.execute(
            "INSERT INTO agent_team_executions "
            "(id, team_id, instruction, status, topology, started_by) "
            "VALUES (?, ?, ?, 'running', ?, ?)",
            (exec_id, team_id, instruction, topology, username),
        )
        await db.commit()
        return {
            "id": exec_id,
            "team_id": team_id,
            "instruction": instruction,
            "topology": topology,
            "started_by": username,
        }

    async def complete_execution(
        self,
        exec_id: str,
        status: str,
        result: str | None,
        agent_outputs: dict,
        duration: float,
        steps: int,
        error: str | None = None,
    ) -> None:
        """标记执行完成并记录结果"""
        db = await get_db()
        await db.execute(
            "UPDATE agent_team_executions SET "
            "status = ?, result = ?, agent_outputs = ?, "
            "duration_seconds = ?, total_steps = ?, error = ?, "
            "completed_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (
                status,
                result,
                json.dumps(agent_outputs, ensure_ascii=False),
                duration,
                steps,
                error,
                exec_id,
            ),
        )
        await db.commit()

    async def get_execution(self, exec_id: str) -> dict | None:
        """获取单条执行记录"""
        db = await get_db()
        cursor = await db.execute("SELECT * FROM agent_team_executions WHERE id = ?", (exec_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_executions(
        self,
        team_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """列出执行记录，可按团队过滤"""
        db = await get_db()
        if team_id:
            cursor = await db.execute(
                "SELECT * FROM agent_team_executions WHERE team_id = ? ORDER BY started_at DESC LIMIT ?",
                (team_id, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM agent_team_executions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ─── 消息流 ───

    async def log_message(
        self,
        exec_id: str,
        from_agent: str,
        to_agent: str | None,
        msg_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """记录团队内消息（批量场景下不立即 commit，由调用方控制）"""
        db = await get_db()
        await db.execute(
            "INSERT INTO agent_team_messages "
            "(execution_id, from_agent, to_agent, message_type, content, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                exec_id,
                from_agent,
                to_agent,
                msg_type,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    async def get_messages(self, exec_id: str) -> list[dict]:
        """获取执行的完整消息流"""
        db = await get_db()
        cursor = await db.execute(
            "SELECT * FROM agent_team_messages WHERE execution_id = ? ORDER BY timestamp",
            (exec_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def flush_messages(self) -> None:
        """刷新未提交的消息到数据库"""
        db = await get_db()
        await db.commit()

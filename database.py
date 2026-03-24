"""SQLite 数据库管理"""

import aiosqlite
import os
from config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)
        _db = await aiosqlite.connect(settings.db_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        await init_tables(_db)
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_tables(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS panel_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'user',
            disabled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metric_type TEXT NOT NULL,
            value_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_type_time
            ON metrics(metric_type, timestamp);

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username TEXT,
            action TEXT NOT NULL,
            target TEXT,
            details TEXT,
            ip_address TEXT,
            success INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_audit_time
            ON audit_log(timestamp);

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT 'telegram',
            message TEXT NOT NULL,
            success INTEGER DEFAULT 1,
            error TEXT
        );

        -- Agent 对话线程
        CREATE TABLE IF NOT EXISTS agent_conversations (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '新对话',
            username TEXT NOT NULL,
            safety_mode TEXT DEFAULT 'supervised',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_count INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_conv_user
            ON agent_conversations(username, updated_at);

        -- Agent 事件日志
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            tool_input TEXT,
            tool_output TEXT,
            risk_level TEXT,
            username TEXT,
            details TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_events_conv
            ON agent_events(conversation_id, timestamp);

        -- Agent 待审批队列
        CREATE TABLE IF NOT EXISTS agent_approvals (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tool_name TEXT NOT NULL,
            tool_input TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            resolved_at TIMESTAMP,
            resolved_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_approvals_status
            ON agent_approvals(status, created_at);

        -- Agent 巡检任务
        CREATE TABLE IF NOT EXISTS agent_patrol_tasks (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            description TEXT,
            interval_minutes INTEGER DEFAULT 60,
            enabled INTEGER DEFAULT 1,
            check_tools TEXT NOT NULL,
            prompt TEXT NOT NULL,
            last_run TIMESTAMP,
            last_status TEXT,
            last_report TEXT
        );

        -- Agent 巡检历史
        CREATE TABLE IF NOT EXISTS agent_patrol_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            report TEXT,
            alert_sent INTEGER DEFAULT 0,
            duration_seconds REAL
        );
        CREATE INDEX IF NOT EXISTS idx_patrol_hist
            ON agent_patrol_history(task_id, timestamp);
    """)

    # ─── 增量迁移 ───
    try:
        await db.execute("ALTER TABLE agent_patrol_history ADD COLUMN report_json TEXT")
    except Exception:
        pass
    try:
        await db.execute("ALTER TABLE agent_patrol_history ADD COLUMN triggered_by TEXT DEFAULT 'scheduler'")
    except Exception:
        pass

    await db.commit()

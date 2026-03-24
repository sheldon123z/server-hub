"""SQLite 数据库管理"""

import asyncio
import aiosqlite
import os
from config import settings

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
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
            report_json TEXT,
            alert_sent INTEGER DEFAULT 0,
            duration_seconds REAL
        );
        CREATE INDEX IF NOT EXISTS idx_patrol_hist
            ON agent_patrol_history(task_id, timestamp);

        -- 告警规则
        CREATE TABLE IF NOT EXISTS alert_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            metric TEXT NOT NULL,
            operator TEXT NOT NULL DEFAULT '>',
            warning_threshold REAL,
            critical_threshold REAL,
            cooldown_minutes INTEGER DEFAULT 60,
            notify INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 告警历史
        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT,
            severity TEXT NOT NULL,
            current_value REAL,
            message TEXT,
            notified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_alert_hist_rule
            ON alert_history(rule_id, created_at);

        -- 巡检模板
        CREATE TABLE IF NOT EXISTS patrol_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            description TEXT,
            check_tools TEXT NOT NULL,
            prompt_template TEXT NOT NULL,
            variables TEXT,
            report_schema TEXT,
            is_builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 故障报告
        CREATE TABLE IF NOT EXISTS fault_reports (
            id TEXT PRIMARY KEY,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            severity TEXT,
            affected_components TEXT,
            symptoms TEXT,
            root_cause TEXT,
            evidence TEXT,
            immediate_actions TEXT,
            long_term_solutions TEXT,
            similar_cases TEXT,
            status TEXT DEFAULT 'open',
            resolved_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fault_reports_status
            ON fault_reports(status, detected_at);

        -- 故障案例库
        CREATE TABLE IF NOT EXISTS fault_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            symptoms TEXT,
            root_cause TEXT,
            solution TEXT,
            tags TEXT,
            source TEXT DEFAULT 'manual',
            source_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 资产台账
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'unknown',
            properties TEXT,
            dependencies TEXT,
            is_manual INTEGER DEFAULT 0,
            last_seen TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_assets_type
            ON assets(type);
    """)

    # FTS5 虚拟表（不能在 executescript 中创建）
    try:
        await db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fault_cases_fts USING fts5("
            "title, symptoms, root_cause, solution, tags, content=fault_cases, content_rowid=id)"
        )
    except Exception:
        pass

    # 兼容旧版：为 alert_rules 表添加基线检测相关列
    for col, default in [("rule_type", "'threshold'"), ("baseline_window_hours", "168"), ("stddev_multiplier", "3.0")]:
        try:
            await db.execute(f"SELECT {col} FROM alert_rules LIMIT 0")
        except Exception:
            try:
                await db.execute(f"ALTER TABLE alert_rules ADD COLUMN {col} DEFAULT {default}")
            except Exception:
                pass

    # 兼容旧版：为 agent_patrol_history 表添加 report_json 列（如果不存在）
    try:
        await db.execute("SELECT report_json FROM agent_patrol_history LIMIT 0")
    except Exception:
        try:
            await db.execute("ALTER TABLE agent_patrol_history ADD COLUMN report_json TEXT")
        except Exception:
            pass

    await db.commit()

"""SQLite 数据库管理"""

import asyncio
import logging
import os
import re

import aiosqlite

from config import settings

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
logger = logging.getLogger(__name__)


async def _table_columns(db: aiosqlite.Connection, table_name: str) -> set[str]:
    if not _IDENTIFIER_RE.match(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _ensure_column(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if not _IDENTIFIER_RE.match(column_name):
        raise ValueError(f"Invalid column name: {column_name}")
    columns = await _table_columns(db, table_name)
    if column_name in columns:
        return

    statement = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    try:
        await db.execute(statement)
        logger.info("数据库迁移: %s.%s 已添加", table_name, column_name)
    except Exception:
        logger.exception("数据库迁移失败: %s", statement)
        raise


async def _migrate_assets_composite_pk(db: aiosqlite.Connection) -> None:
    """将 assets 表从单列 PK(id) 迁移为复合 PK(id, server_id)。

    同时清理旧版 server_id 前缀: 'srv1:service:nginx' → 'service:nginx'。
    如果表已经是复合主键则跳过。
    """
    # 检查当前表是否仍为单列 PK — 通过 table_info 检测 pk 列
    cursor = await db.execute("PRAGMA table_info(assets)")
    cols = await cursor.fetchall()
    pk_cols = [c[1] for c in cols if c[5] > 0]  # c[5] = pk flag
    if set(pk_cols) != {"id"}:
        # 已经迁移过（复合主键），或表不存在
        return

    logger.info("数据库迁移: assets 表升级为复合主键 (id, server_id)")
    try:
        # 1. 清理旧版 server_id 前缀 (id 形如 "srv1:service:nginx"，server_id="srv1")
        cursor = await db.execute(
            "SELECT id, server_id FROM assets WHERE server_id != 'local' AND id LIKE server_id || ':%'"
        )
        prefixed_rows = await cursor.fetchall()
        for old_id, sid in prefixed_rows:
            new_id = old_id[len(sid) + 1 :]  # 去掉 "srv1:" 前缀
            await db.execute(
                "UPDATE assets SET id = ? WHERE id = ? AND server_id = ?",
                (new_id, old_id, sid),
            )
        if prefixed_rows:
            logger.info("数据库迁移: 清理了 %d 条 server_id 前缀资产 ID", len(prefixed_rows))

        # 2. 重建表为复合主键
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS assets_new (
                id TEXT NOT NULL,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'unknown',
                properties TEXT,
                dependencies TEXT,
                is_manual INTEGER DEFAULT 0,
                last_seen TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                server_id TEXT NOT NULL DEFAULT 'local',
                PRIMARY KEY (id, server_id)
            );
            INSERT OR IGNORE INTO assets_new
                (id, type, name, status, properties, dependencies, is_manual, last_seen, created_at, server_id)
                SELECT id, type, name, status, properties, dependencies, is_manual, last_seen, created_at, server_id
                FROM assets;
            DROP TABLE assets;
            ALTER TABLE assets_new RENAME TO assets;
            CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
            CREATE INDEX IF NOT EXISTS idx_assets_server ON assets(server_id);
        """)
        logger.info("数据库迁移: assets 表复合主键升级完成")
    except Exception:
        logger.exception("数据库迁移: assets 表复合主键升级失败")
        raise


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
            await _db.execute("PRAGMA busy_timeout=5000")
            await _db.execute("PRAGMA synchronous=NORMAL")
            await init_tables(_db)
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


# ---------------------------------------------------------------------------
# init_tables — 按领域拆分为子函数
# ---------------------------------------------------------------------------


async def _create_auth_tables(db: aiosqlite.Connection):
    """用户认证、审计相关表"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS panel_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'user',
            disabled INTEGER DEFAULT 0,
            token_version INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

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
    """)
    await _ensure_column(db, "panel_users", "token_version", "INTEGER NOT NULL DEFAULT 0")


async def _create_monitoring_tables(db: aiosqlite.Connection):
    """指标采集、告警规则/历史、最新快照相关表"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metric_type TEXT NOT NULL,
            value_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_type_time
            ON metrics(metric_type, timestamp);
        -- idx_metrics_server_time 在 _ensure_column 添加 server_id 后创建

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

        -- 最新指标快照表 (UPSERT，避免自联结查最新行)
        CREATE TABLE IF NOT EXISTS metrics_latest (
            server_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # _ensure_column 迁移
    await _ensure_column(db, "alert_rules", "rule_type", "TEXT DEFAULT 'threshold'")
    await _ensure_column(db, "alert_rules", "baseline_window_hours", "INTEGER DEFAULT 168")
    await _ensure_column(db, "alert_rules", "stddev_multiplier", "REAL DEFAULT 3.0")
    await _ensure_column(db, "metrics", "server_id", "TEXT DEFAULT 'local'")
    await _ensure_column(db, "alert_history", "server_id", "TEXT DEFAULT 'local'")
    # server_id 列就绪后才能创建复合索引
    # idx_metrics_server_time: 清理路径 DELETE WHERE server_id=? AND timestamp<? 使用
    await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_server_time ON metrics(server_id, timestamp)")
    # idx_metrics_server_type_time: 历史查询 WHERE server_id=? AND metric_type=? 使用
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_server_type_time ON metrics(server_id, metric_type, timestamp)"
    )


async def _create_notification_tables(db: aiosqlite.Connection):
    """通知记录、通知渠道配置、站内通知相关表"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT 'telegram',
            message TEXT NOT NULL,
            success INTEGER DEFAULT 1,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS notification_channels (
            id TEXT PRIMARY KEY,
            channel_type TEXT NOT NULL,
            display_name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            config_json TEXT NOT NULL DEFAULT '{}',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_test_at TIMESTAMP,
            last_test_ok INTEGER
        );

        CREATE TABLE IF NOT EXISTS inapp_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            type TEXT NOT NULL DEFAULT 'system',
            title TEXT NOT NULL,
            content TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            read INTEGER NOT NULL DEFAULT 0,
            related_alert_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await _ensure_column(db, "notifications", "channel_id", "TEXT")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_inapp_user_read ON inapp_notifications(user_id, read, created_at)"
    )


async def _create_agent_tables(db: aiosqlite.Connection):
    """Agent 对话、审批、巡检、技能、运行、团队相关表"""
    await db.executescript("""
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
            run_id TEXT,
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

        CREATE TABLE IF NOT EXISTS async_agent_tasks (
            id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            instruction TEXT,
            status TEXT DEFAULT 'running',
            result TEXT,
            created_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            username TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            safety_mode TEXT DEFAULT 'supervised',
            page_context TEXT,
            skill_id TEXT,
            user_message TEXT NOT NULL,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation
            ON agent_runs(conversation_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_run_events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_run
            ON agent_run_events(run_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_conv_type
            ON agent_run_events(conversation_id, event_type);

        CREATE TABLE IF NOT EXISTS agent_skills (
            id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            name TEXT NOT NULL,
            summary TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            install_path TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_skill_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL,
            version TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_skill_versions_skill
            ON agent_skill_versions(skill_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_skill_installs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_skill_installs_skill
            ON agent_skill_installs(skill_id, created_at);

        CREATE TABLE IF NOT EXISTS agent_skill_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT NOT NULL,
            binding_type TEXT NOT NULL,
            binding_target TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_agent_skill_bindings_skill
            ON agent_skill_bindings(skill_id, binding_type, binding_target);

        -- 智能体团队
        CREATE TABLE IF NOT EXISTS agent_teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            topology TEXT NOT NULL DEFAULT 'supervisor',
            config_json TEXT NOT NULL DEFAULT '{}',
            default_model TEXT,
            safety_mode TEXT DEFAULT 'supervised',
            max_steps INTEGER DEFAULT 50,
            timeout_seconds INTEGER DEFAULT 300,
            enabled INTEGER DEFAULT 1,
            is_builtin INTEGER DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_team_members (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            name TEXT NOT NULL,
            agent_type TEXT NOT NULL DEFAULT 'worker',
            description TEXT,
            system_prompt TEXT NOT NULL,
            tools_json TEXT NOT NULL DEFAULT '[]',
            model_id TEXT,
            max_calls INTEGER DEFAULT 15,
            handoff_targets TEXT DEFAULT '[]',
            position INTEGER DEFAULT 0,
            config_json TEXT DEFAULT '{}',
            UNIQUE(team_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_team_members_team ON agent_team_members(team_id);

        CREATE TABLE IF NOT EXISTS agent_team_executions (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            instruction TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            topology TEXT NOT NULL,
            result TEXT,
            agent_outputs TEXT DEFAULT '{}',
            started_by TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            duration_seconds REAL,
            total_steps INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_team_exec_team ON agent_team_executions(team_id, started_at);

        CREATE TABLE IF NOT EXISTS agent_team_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            from_agent TEXT NOT NULL,
            to_agent TEXT,
            message_type TEXT DEFAULT 'text',
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_team_msg_exec ON agent_team_messages(execution_id, timestamp);

        -- 最新指标快照表 (UPSERT，避免自联结查最新行)
        CREATE TABLE IF NOT EXISTS metrics_latest (
            server_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # _ensure_column 迁移
    await _ensure_column(db, "agent_patrol_history", "report_json", "TEXT")
    await _ensure_column(db, "agent_patrol_history", "triggered_by", "TEXT DEFAULT 'scheduler'")
    await _ensure_column(db, "agent_approvals", "run_id", "TEXT")


async def _create_rbac_tables(db: aiosqlite.Connection):
    """RBAC 角色权限相关表"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS roles (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            description TEXT,
            builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id TEXT REFERENCES roles(id) ON DELETE CASCADE,
            resource TEXT NOT NULL,
            action TEXT NOT NULL,
            scope TEXT DEFAULT '*',
            UNIQUE(role_id, resource, action, scope)
        );
        CREATE INDEX IF NOT EXISTS idx_role_permissions_role
            ON role_permissions(role_id);

        CREATE TABLE IF NOT EXISTS user_roles (
            user_id TEXT NOT NULL,
            role_id TEXT REFERENCES roles(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, role_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_roles_user
            ON user_roles(user_id);
    """)


async def _create_server_tables(db: aiosqlite.Connection):
    """多服务器管理相关表"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS servers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            hostname TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            agent_port INTEGER DEFAULT 9901,
            agent_token_hash TEXT,
            ssh_user TEXT,
            ssh_port INTEGER DEFAULT 22,
            ssh_key_credential TEXT,
            os_info TEXT,
            tags TEXT DEFAULT '[]',
            is_local INTEGER DEFAULT 0,
            status TEXT DEFAULT 'unknown',
            last_heartbeat TIMESTAMP,
            agent_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_servers_status ON servers(status);

        CREATE TABLE IF NOT EXISTS server_groups (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            color TEXT DEFAULT '#38bdf8',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS server_group_members (
            group_id TEXT NOT NULL,
            server_id TEXT NOT NULL,
            PRIMARY KEY (group_id, server_id)
        );
    """)
    # Issue #8: agent_token_hash 实际存 Fernet 加密值而非 hash，新增正确命名的字段
    # 不能 ALTER TABLE RENAME COLUMN (旧版 SQLite 不支持)，所以新增并双写
    await _ensure_column(db, "servers", "agent_token_encrypted", "TEXT")
    # Issue #28: Hub→Agent TLS 支持
    await _ensure_column(db, "servers", "use_tls", "BOOLEAN DEFAULT 0")

    # 确保本机服务器记录存在
    import socket as _socket

    _hostname = _socket.gethostname()
    await db.execute(
        "INSERT OR IGNORE INTO servers (id, name, hostname, ip_address, is_local, status) "
        "VALUES ('local', ?, ?, '127.0.0.1', 1, 'online')",
        (_hostname, _hostname),
    )


async def _create_other_tables(db: aiosqlite.Connection):
    """故障报告、资产台账、定时任务日志、配额违规、剧本、凭据等"""
    await db.executescript("""
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

        -- 资产台账 (复合主键: id + server_id，同名资产可分属不同服务器)
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'unknown',
            properties TEXT,
            dependencies TEXT,
            is_manual INTEGER DEFAULT 0,
            last_seen TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            server_id TEXT NOT NULL DEFAULT 'local',
            PRIMARY KEY (id, server_id)
        );
        CREATE INDEX IF NOT EXISTS idx_assets_type
            ON assets(type);
        CREATE INDEX IF NOT EXISTS idx_assets_server
            ON assets(server_id);

        -- 定时任务变更日志
        CREATE TABLE IF NOT EXISTS cron_job_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cron_user TEXT NOT NULL,
            schedule TEXT NOT NULL,
            command TEXT NOT NULL,
            comment TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cron_job_log_user
            ON cron_job_log(cron_user);

        -- 配额违规记录
        CREATE TABLE IF NOT EXISTS quota_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            violation_type TEXT NOT NULL,
            mem_gb REAL,
            quota_mem_gb REAL,
            usage_pct REAL,
            action_taken TEXT,
            first_detected_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_quota_violations_user
            ON quota_violations(username, created_at);

        -- 运维剧本
        CREATE TABLE IF NOT EXISTS playbooks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT DEFAULT 'general',
            system_prompt TEXT NOT NULL,
            parameters TEXT NOT NULL DEFAULT '[]',
            tools_required TEXT NOT NULL DEFAULT '',
            validation_rules TEXT DEFAULT '{}',
            trigger_config TEXT DEFAULT '{"type":"manual"}',
            safety_mode TEXT,
            steps_visual TEXT,
            is_builtin INTEGER DEFAULT 0,
            tags TEXT DEFAULT '',
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_playbooks_category ON playbooks(category);

        -- 剧本执行记录
        CREATE TABLE IF NOT EXISTS playbook_executions (
            id TEXT PRIMARY KEY,
            playbook_id TEXT NOT NULL,
            parameters_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            report TEXT,
            triggered_by TEXT NOT NULL,
            trigger_type TEXT DEFAULT 'manual',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            duration_seconds REAL,
            thread_id TEXT,
            tool_calls_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_pb_exec_playbook
            ON playbook_executions(playbook_id, started_at);

        -- 剧本凭据存储
        CREATE TABLE IF NOT EXISTS playbook_credentials (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            encrypted_value TEXT NOT NULL,
            credential_type TEXT DEFAULT 'generic',
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # assets 表迁移: 旧库可能没有 server_id 列，补列后再升级主键
    await _ensure_column(db, "assets", "server_id", "TEXT DEFAULT 'local'")
    await _migrate_assets_composite_pk(db)


async def init_tables(db: aiosqlite.Connection):
    """初始化所有数据库表 — 按领域分组调用子函数"""
    await _create_auth_tables(db)
    await _create_monitoring_tables(db)
    await _create_notification_tables(db)
    await _create_agent_tables(db)
    await _create_server_tables(db)
    await _create_other_tables(db)
    await _create_rbac_tables(db)

    # FTS5 虚拟表（跨领域，单独创建）
    try:
        await db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fault_cases_fts USING fts5("
            "title, symptoms, root_cause, solution, tags, content=fault_cases, content_rowid=id)"
        )
    except Exception:
        logger.exception("创建 FTS5 虚拟表 fault_cases_fts 失败")
        raise

    await db.commit()

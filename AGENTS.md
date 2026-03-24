# ServerHub Repository Guide

此文件服务于仓库协作中的编码助手。ServerHub 运行时主 Agent 的长期记忆位于 `data/agent-memory.md`，不要再把根目录 `AGENTS.md` 当作应用内存文件使用。

## 项目概述

- ServerHub 是基于 FastAPI 的 Linux 服务器 Web 管理系统，面向实验室/团队运维场景
- 技术栈: FastAPI + Jinja2 + HTMX + Alpine.js + SQLite(aiosqlite) + Deep Agents + xterm.js
- Python 环境必须使用 `serverhub` conda 环境，版本为 Python 3.11
- 启动时 `workers` 必须为 `1`，避免 SQLite 多进程写入问题和 agent checkpoint 不一致

## 关键架构

- `modules/__init__.py` 会自动发现 `modules/*/`，每个模块导出 `router` 和 `MODULE_INFO`
- 页面路由主要定义在 `main.py`，模块目录主要承载 API router
- 模板继承链为 `base.html -> page templates`
- AI Agent 主实现位于 `modules/agents/`
- 运行时长期记忆文件位于 `data/agent-memory.md`
- 自定义系统提示词位于 `data/custom_prompt.txt`
- 自定义 SubAgent 配置位于 `data/custom_subagents.json`

## Agent 相关约定

- 主 Agent 由 `modules/agents/deep_agent.py` 构建
- 管理 API 位于 `modules/agents/routes.py`
- 系统提示词逻辑位于 `modules/agents/prompts.py`
- SubAgent 定义位于 `modules/agents/subagents.py`
- 安全与审批规则位于 `modules/agents/safety.py`
- Shell backend 位于 `modules/agents/sandbox.py`
- 巡检逻辑位于 `modules/agents/patrol.py`

## 开发约束

- 框架优先: 先复用 Deep Agents/LangGraph 现有机制，不要重复造轮子
- 需要定制框架行为时，优先继承扩展，而不是绕开框架
- 配置优先写入 `data/` 下的自定义文件，不直接改源码默认值
- API 路由前缀遵循 `/api/<module>`
- 敏感文件默认禁读: `.env`, `~/.api_keys`, `~/.telegram_config`, `~/config.yaml`

## 开发规范同步

- 提交实现前必须遵循 [docs/CONTRIBUTING.md](/home/zhengxiaodong/scripts/server-hub/docs/CONTRIBUTING.md)；若本文件与其冲突，以 `docs/CONTRIBUTING.md` 为准
- Python 遵循 PEP 8、4 空格缩进、单行不超过 120 字符；导入顺序为标准库、第三方、本地模块；模块顶层优先定义 `logger = logging.getLogger(__name__)`
- 命名遵循：函数/变量 `snake_case`、类 `PascalCase`、常量 `UPPER_CASE`、模块目录小写 `snake_case`
- API 约定：路径段使用 kebab-case，查询参数和路径参数使用 snake_case；写操作返回 `{"ok": true, ...}`，查询接口直接返回数据；错误统一用 `HTTPException`
- 认证与鉴权必须通过依赖注入完成，优先使用 `get_current_user` 和 `require_role("admin")`，不要在 handler 内自行解析 token
- 数据库访问统一走 `get_db()`；SQL 必须参数化，禁止字符串拼接；写操作优先 `commit` 后再执行通知等副作用
- 模块开发遵循 `routes.py` 薄层、`services.py` 厚层原则；新增表统一放在 `database.py:init_tables()` 中
- 前端交互遵循 Alpine.js `init()` 初始化约定；HTMX 与 Alpine.js 不处理同一交互；页面模板统一继承 `base.html`
- Git 提交信息遵循 `feat|fix|docs|refactor|perf|test|chore|style: 中文描述` 格式；涉及功能/API/Agent 工具变更时，同步更新对应 `docs/` 文档

## 运行与验证

- 开发启动: `python main.py`
- 或使用: `uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1`
- 如修改 agent 配置，通常需要调用 `reset_agent_cache()` 或经过管理接口刷新缓存

## 说明

- 根目录 `AGENTS.md` 仅用于仓库协作说明
- 应用内长期记忆请维护在 `data/agent-memory.md`

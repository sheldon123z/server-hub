# 记忆系统

ServerHub Agent 使用三层记忆架构，平衡短期状态保持、长期知识积累和结构化数据存储。

---

## 三层记忆架构

```
┌─────────────────────────────────────────────────────┐
│                   记忆系统架构                       │
├─────────────────┬───────────────┬───────────────────┤
│   短期记忆       │   长期记忆    │   结构化存储       │
│  (Checkpoint)   │  (AGENTS.md)  │  (SQLiteStore)    │
├─────────────────┼───────────────┼───────────────────┤
│ per-conversation│ 跨会话知识    │ namespace+KV 数据  │
│ state 持久化    │ 注入系统提示词 │                   │
├─────────────────┼───────────────┼───────────────────┤
│ AsyncSqliteSaver│ MemoryMiddle  │ AsyncSqliteStore  │
│ LangGraph 标准  │ ware          │ deepagents 框架    │
├─────────────────┼───────────────┼───────────────────┤
│ data/agent-     │ AGENTS.md     │ data/agent-        │
│ checkpoints.db  │ (文件)        │ store.db           │
└─────────────────┴───────────────┴───────────────────┘
```

---

## 短期记忆：Checkpoint

### 技术实现

使用 LangGraph 的 `AsyncSqliteSaver`，将每次对话的完整 state 持久化到 SQLite。

```python
checkpointer = AsyncSqliteSaver(
    await aiosqlite.connect(settings.agent_checkpoint_db)
    # → data/agent-checkpoints.db
)
```

### 工作原理

- 每个对话使用唯一 `thread_id` 隔离（格式：UUID 字符串）
- LangGraph 在每次 agent 步骤后自动保存 state snapshot
- 下次对话请求时携带相同 `thread_id`，自动恢复历史消息和工具调用记录
- 服务器重启后对话历史不丢失

### 配置方式

```python
config = {"configurable": {"thread_id": conversation_id}}
await agent.ainvoke({"messages": [...]}, config=config)
```

### 存储位置

`data/agent-checkpoints.db` — 由 LangGraph 框架管理表结构，不建议直接操作。

---

## 长期记忆：AGENTS.md

### 技术实现

使用 Deep Agents 框架的 `MemoryMiddleware`。通过 `memory=["AGENTS.md 路径"]` 参数启用。

```python
memory_file = str(BASE_DIR / "AGENTS.md")
memory_paths = [memory_file] if Path(memory_file).exists() else []

agent = create_deep_agent(
    ...
    memory=memory_paths if memory_paths else None,
)
```

### 工作原理

1. **加载阶段**：每次 agent 被调用时，MemoryMiddleware 读取 `AGENTS.md` 文件内容，追加到系统提示词末尾
2. **更新阶段**：Agent 可以通过 `edit_file` 工具直接编辑 `AGENTS.md`，更新自己的长期记忆
3. **持久化**：`AGENTS.md` 是普通文件，所有知识以人类可读的 Markdown 格式存储

### AGENTS.md 内容结构

`AGENTS.md` 是 AI 运维助手的知识库，建议包含：

```markdown
# 服务器运维记忆

## 已知问题
- docker-worker-1 容器每隔 2-3 天会重启一次，根因是 OOM
- 内存通常在下午 3-5 点达到峰值（wangtao 的训练任务）

## 用户习惯
- wangtao 每天 9:00-22:00 使用 GPU 进行训练
- 资源需求通知需要提前 30 分钟

## 历史解决方案
- Nginx 502：通常是 Dify API 服务未启动，执行 dify_manage start 即可
- GPU 温度过高：检查机房空调状态
```

### 更新规则

- **Agent 自动更新**：Agent 在处理问题时若发现有价值的运维知识，会主动调用 `edit_file("AGENTS.md", ...)` 更新
- **不建议手动编辑**：`AGENTS.md` 是 Agent 的工作文件，人工编辑可能破坏格式
- **初始化**：项目初次部署时可手动填入服务器基本信息

### 与 CLAUDE.md 的区别

| 文件 | 用途 | 读者 |
|------|------|------|
| `AGENTS.md` | AI 运维助手的长期记忆（运行时知识）| Agent（MemoryMiddleware）|
| `CLAUDE.md` | 开发者指引（架构、约定、规范）| 开发者（Claude Code）|

---

## 结构化存储：AsyncSqliteStore

### 技术实现

使用 Deep Agents 框架的 `AsyncSqliteStore`，基于 namespace + key-value 模型。

```python
store_path = str(Path(settings.db_path).parent / "agent-store.db")
conn = await aiosqlite.connect(store_path)
_store = AsyncSqliteStore(conn)

agent = create_deep_agent(
    ...
    store=store,
)
```

### 存储位置

`data/agent-store.db` — 由 Deep Agents 框架管理。

### 使用场景

Agent 可以在 store 中保存结构化数据，例如：

- 用户偏好配置
- 工具执行统计（某个容器重启了多少次）
- 跨会话的任务状态

### 访问方式

Agent 通过框架提供的 store API 读写，不需要 `@tool` 封装。具体 API 取决于 deepagents 框架版本。

---

## 记忆系统对比

| 维度 | Checkpoint | AGENTS.md | SQLiteStore |
|------|-----------|-----------|-------------|
| 作用范围 | 单次对话 | 全局 | 全局 |
| 数据格式 | LangGraph state（二进制）| Markdown 文本 | KV 结构化数据 |
| 更新方式 | 自动（框架管理）| Agent 主动调用 edit_file | Agent 通过框架 API |
| 人工可读 | 否 | 是 | 部分 |
| 持久化 | 数据库 | 文件 | 数据库 |
| 加载时机 | 对话开始（按 thread_id）| 每次 agent 调用 | 按需查询 |

---

## 配置说明

记忆系统相关的配置项（`config.py`）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `db_path` | 主数据库路径 | `data/server-hub.db` |
| `agent_checkpoint_db` | Checkpoint 数据库 | `data/agent-checkpoints.db` |
| `data/agent-store.db` | Store 数据库（硬编码）| `data/agent-store.db` |

注意：这三个文件均在 `.gitignore` 中排除，不会提交到 Git。

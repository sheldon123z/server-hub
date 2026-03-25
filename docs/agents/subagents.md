# SubAgent 详细说明

SubAgent 定义拆分为独立子模块，存放在 `modules/agents/subagents/` 目录下：

```
modules/agents/subagents/
├── __init__.py              # 导出入口：get_subagents(), load_subagents()
├── _tools.py                # 工具查找（web_search, think, _get_tools_by_names）
├── _config.py               # 配置管理（middleware 构建、持久化、模型映射）
├── _async_specs.py          # 异步 SubAgent 配置（3 个深度分析任务）
├── researcher.py            # 联网研究员
├── log_analyzer.py          # 日志分析师
├── security_auditor.py      # 安全审计员
├── correlation_analyzer.py  # 多源关联分析
├── ops_scheduler.py         # 定时任务调度专家
└── knowledge_retriever.py   # 知识检索专家
```

主 Agent 通过 `task(subagent_type="name", message="...")` 工具委派任务。

---

## 规范说明

每个 SubAgent 定义为 `DEFINITION` 字典，包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | str | 是 | 唯一标识，主 agent 通过此名称委派 |
| `description` | str | 是 | action-oriented 描述，帮助主 agent 决定何时委派 |
| `system_prompt` | str | 是 | 详细工作流指令 + 输出格式 + 长度限制 |
| `tools_fn` | callable | 是 | 返回工具列表的函数（延迟加载避免循环导入） |
| `model_purpose` | str | 否 | 模型用途（`chat` / `patrol`），决定使用哪个模型配置 |
| `middleware_profile` | str | 否 | Middleware 配置档位（`heavy` / `light` / `ops`） |
| `interrupt_on` | dict | 否 | 需要审批的工具（如 `{"create_cron_job": True}`） |

### Middleware 配置档位

| 档位 | 适用场景 | 配置 |
|------|---------|------|
| `heavy` | 工具密集型（correlation-analyzer, log-analyzer） | ModelRetry(2) + ToolRetry(2) + ModelCallLimit(30) |
| `light` | 轻量型（researcher, knowledge-retriever） | ModelRetry(2) + ModelCallLimit(15) |
| `ops` | 操作型（ops-scheduler, security-auditor） | ModelRetry(2) + ToolRetry(1) + ModelCallLimit(20) |

---

## 1. researcher — 联网研究员

**名称**: `researcher`

**描述**: 搜索技术文档、错误解决方案、软件版本信息和最佳实践。每次委派一个主题。

**工具集**（2 个，SubAgent 专属）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `web_search` | SubAgent 专属 | 调用 Tavily API 搜索，支持 general/news/finance 主题 |
| `think` | SubAgent 专属 | 暂停评估，决定是否继续搜索 |

**工作流程**:
1. 使用 `web_search` 搜索（2-3 次，复杂问题最多 5 次）
2. 每次搜索后用 `think` 评估是否需要继续
3. 综合所有搜索结果，给出结构化中文报告
4. 使用 `[1][2][3]` 标注信息来源

**停止条件**: 已有 3+ 相关来源，或最近两次搜索结果相似。

**输出格式**（500 词以内）:
- 结论摘要（2-3 句）
- 详细发现（要点列表）
- 来源列表（URL）

**前置条件**: 需要配置 `TAVILY_API_KEY` 环境变量。未配置时返回错误提示。

**使用场景**:
- 查找特定错误的解决方案（如 Docker 容器崩溃原因）
- 查询软件版本信息和更新日志
- 研究最佳实践和技术文档

**委派示例**:
```
task(subagent_type="researcher", message="搜索 Dify worker 容器 OOM killed 的常见原因和解决方案")
```

---

## 2. log-analyzer — 日志分析师

**名称**: `log-analyzer`

**描述**: 分析服务日志和系统日志，诊断崩溃、识别错误模式、追踪性能问题和调查安全事件。

**工具集**（2 个，从主 agent 工具继承）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `get_container_logs` | 主 agent 工具 | 获取 Docker 容器日志 |
| `get_service_logs` | 主 agent 工具 | 获取 systemd 服务日志 |

注意：SubAgent 还可使用框架内置的 `execute`（运行 journalctl/tail/awk）、`read_file`（读取日志文件）、`grep`（搜索关键词），这些工具由 Filesystem middleware 自动注入。

**工作流程**:
1. 定位相关日志文件或服务
2. 使用 `grep`/`execute` 提取错误和异常条目
3. 分析错误模式、时间线、频率
4. 给出根因分析和修复建议

**输出格式**（500 词以内）:
- 问题摘要（一句话）
- 关键日志条目（带时间戳，最多 10 条）
- 根因分析
- 推荐解决方案（附具体命令）

**限制**: 输出不包含原始日志转储，只呈现分析摘要。

**使用场景**:
- 分析 Docker 容器频繁重启的原因
- 排查 systemd 服务启动失败
- 调查安全事件（SSH 暴力破解、异常登录）
- 性能问题的日志追踪

**委派示例**:
```
task(subagent_type="log-analyzer", message="分析 docker-worker-1 容器最近的日志，找出重启原因")
```

---

## 3. security-auditor — 安全审计员

**名称**: `security-auditor`

**描述**: 审计服务器安全配置，包括 SSH 设置、开放端口、用户权限、防火墙规则和文件权限，返回按风险分级的发现。

**工具集**（1 个，从主 agent 工具继承）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `get_system_overview` | 主 agent 工具 | 获取系统基本信息 |

SubAgent 还可使用框架内置的 `execute`（运行 ss/iptables/ufw/last）、`read_file`（读取配置文件）、`grep`（搜索安全配置）。

**审计范围**:
1. SSH 配置：root 登录、密码认证、端口号
2. 开放端口：`ss -tlnp` 检查不必要的监听端口
3. 用户权限：sudo 配置、`/etc/passwd` 异常用户
4. 防火墙：iptables/ufw 规则
5. 文件权限：`/etc/shadow`、SSH key 权限

**禁止读取**: `~/.api_keys`、`~/.telegram_config`、`~/config.yaml`（在系统提示词中明确禁止）

**输出格式**（500 词以内）:

| 级别 | 处置 |
|------|------|
| HIGH | 需要立即修复（附修复命令）|
| MEDIUM | 建议修复（附修复命令）|
| OK | 配置正常 |

**使用场景**:
- 定期安全巡检
- 新用户加入后的权限验证
- 安全事件后的配置审查

**委派示例**:
```
task(subagent_type="security-auditor", message="审计当前服务器的 SSH 配置和开放端口")
```

---

## 4. correlation-analyzer — 多源关联分析

**名称**: `correlation-analyzer`

**描述**: 跨维度关联分析，将系统指标时间线、容器状态变化、日志异常和历史故障案例关联起来，找出根因。当复杂的多组件异常需要调查时委派。

**工具集**（11 个，从主 agent 工具继承）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `analyze_resource_trend` | 主 agent 工具 | 资源趋势分析（CPU/内存/GPU/磁盘）|
| `get_system_overview` | 主 agent 工具 | 当前系统状态 |
| `list_docker_containers` | 主 agent 工具 | 容器状态（含重启次数）|
| `get_container_logs` | 主 agent 工具 | 异常容器日志 |
| `list_systemd_services` | 主 agent 工具 | 服务状态 |
| `get_service_logs` | 主 agent 工具 | 服务日志 |
| `search_fault_cases` | 主 agent 工具 | 搜索历史类似案例 |
| `get_user_login_history_tool` | 主 agent 工具 | 用户登录历史（关联异常时间点）|
| `get_active_sessions_tool` | 主 agent 工具 | 当前活跃会话 |
| `list_docker_networks` | 主 agent 工具 | Docker 网络拓扑 |
| `get_service_dependencies_tool` | 主 agent 工具 | 服务依赖关系 |

**工作流程**:
1. 调用 `analyze_resource_trend` 获取最近资源趋势
2. 调用 `get_system_overview` 获取当前状态
3. 调用 `list_docker_containers` 检查容器状态
4. 对异常容器调用 `get_container_logs`
5. 调用 `search_fault_cases` 搜索历史类似案例
6. 综合分析时间线上的关联性

**关联分析维度**:
- 时间维度：异常事件发生的先后顺序
- 因果维度：哪些事件可能导致了其他事件
- 资源维度：资源变化与服务异常的关联
- 历史维度：是否有类似的历史案例

**输出格式**（500 词以内）:
- 时间线关联（按时间顺序列出各维度的异常事件）
- 关联推理（哪些事件可能有因果关系）
- 根因判断（最可能的根本原因）
- 处置建议

**使用场景**:
- 多个服务同时出现异常
- 性能突然下降但单一指标无明显问题
- 需要排查跨容器、跨服务的级联故障
- 异常时间点与用户登录活动的关联分析

**委派示例**:
```
task(subagent_type="correlation-analyzer", message="服务器在今天下午 3 点左右出现了内存突增和多个容器重启，请分析可能的根因")
```

---

## 5. ops-scheduler — 定时任务调度专家

**名称**: `ops-scheduler`

**描述**: 管理 cron 定时任务 — 创建、修改、删除和监控。当用户需要安排自动化操作、检查现有调度或设置定期维护任务时委派。

**工具集**（6 个，从主 agent 工具继承）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `list_cron_jobs` | 主 agent 工具 | 列出指定用户的 cron 任务 |
| `validate_cron_expr` | 主 agent 工具 | 验证表达式并预览执行时间 |
| `create_cron_job` | 主 agent 工具 | 创建新任务 |
| `modify_cron_schedule` | 主 agent 工具 | 修改任务时间 |
| `delete_cron_job_tool` | 主 agent 工具 | 删除任务 |
| `toggle_cron_job_tool` | 主 agent 工具 | 启用/禁用任务 |

**工作流程**:
1. 理解用户的调度需求
2. 用 `validate_cron_expr` 验证表达式正确性
3. 用 `list_cron_jobs` 检查是否已有类似任务
4. 创建/修改任务，确保命令路径使用绝对路径
5. 提供任务摘要和下次执行时间

**安全规则**:
- 命令必须使用绝对路径
- 禁止创建含 rm -rf、shutdown、reboot 等危险命令的任务
- 创建前验证表达式合法性
- 创建和删除操作在 supervised 模式下需要审批

**输出格式**（500 词以内）:
- 任务摘要
- 执行时间描述
- 下次执行时间

**使用场景**:
- 添加新的定期监控脚本
- 修改现有任务的执行频率
- 查看和清理过时的定时任务
- 临时禁用/启用某些定时任务

**委派示例**:
```
task(subagent_type="ops-scheduler", message="创建一个每天凌晨 3 点执行的磁盘清理任务")
```

---

## 6. knowledge-retriever — 知识检索专家

**名称**: `knowledge-retriever`

**描述**: 深度知识检索专家，结合语义搜索、关键词匹配和联网搜索获取信息。

**工具集**（4 个）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `retrieve_knowledge` | 主 agent 工具 | RAG 语义 + 关键词混合检索 |
| `search_fault_cases` | 主 agent 工具 | 故障案例库搜索 |
| `web_search` | SubAgent 专属 | 联网搜索补充 |
| `think` | SubAgent 专属 | 暂停评估信息充足性 |

**工作流程**:
1. 分析查询意图，决定检索策略
2. 调用 `retrieve_knowledge` 搜索本地知识库
3. 调用 `search_fault_cases` 搜索历史故障案例
4. 如需补充，用 `web_search` 搜索互联网
5. 综合多源结果，给出结构化回答

**使用场景**:
- 查找运维文档和 API 说明
- 检索历史巡检报告和故障案例
- 结合本地知识和互联网信息回答技术问题

**委派示例**:
```
task(subagent_type="knowledge-retriever", message="查找关于 Docker 容器内存限制的最佳实践")
```

---

## 异步 SubAgent

除了上述 6 个同步 SubAgent，系统还支持 3 个**异步 SubAgent**，它们在后台独立运行，不阻塞主对话：

### 架构

```
modules/agents/async_graphs/
├── __init__.py              # build_all_async_graphs() 编译图
├── researcher.py            # 异步版联网研究
├── security_auditor.py      # 异步版安全审计
└── correlation_analyzer.py  # 异步版关联分析
```

异步 SubAgent 通过 `lg_compat.py`（LangGraph 兼容服务器）运行：
1. Main Agent 的 SubAgentMiddleware 识别 `graph_id` 字段
2. 发送 HTTP 请求到本地 `/lg` 兼容 API
3. LG Compat Server 在独立 `asyncio.Task` 中执行图
4. Main Agent 继续对话，后台并行执行
5. 用户可通过 `/api/agents/async-tasks` 查询进度

### LG Compat Server 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/lg/threads` | 创建线程 |
| POST | `/lg/threads/{id}/runs` | 启动运行 |
| GET | `/lg/threads/{id}/runs/{run_id}` | 查询状态 |
| GET | `/lg/threads/{id}` | 获取结果 |
| POST | `/lg/threads/{id}/runs/{run_id}/cancel` | 取消运行 |

---

## 配置管理

### 默认 vs 自定义配置

SubAgent 配置支持两种方式：

1. **硬编码默认**（`modules/agents/subagents/__init__.py:get_subagents()`）：上述 6 个 SubAgent
2. **自定义 JSON**（`data/custom_subagents.json`）：通过管理面板保存，优先于默认配置

### 自定义 SubAgent 格式

`data/custom_subagents.json` 示例：
```json
[
  {
    "name": "researcher",
    "description": "...",
    "system_prompt": "...",
    "tools": ["web_search", "think"],
    "model": null
  }
]
```

`tools` 字段接受工具名称字符串列表，`load_subagents()` 在加载时自动解析为工具对象。

### 可用工具来源

通过管理面板可以看到所有可选工具（`get_available_tools()` 返回）：

| 来源 | 说明 |
|------|------|
| custom | 主 agent 的 37 个自定义工具（tools.py）|
| subagent | SubAgent 专属工具（web_search, think）|
| builtin | 框架内置工具（execute, read_file 等）|

### SubAgent 工具集汇总

| SubAgent | Middleware 档位 | 工具数量 | 工具列表 |
|----------|---------------|---------|---------|
| researcher | light | 2 | web_search, think |
| log-analyzer | heavy | 2 | get_container_logs, get_service_logs |
| security-auditor | ops | 1+1 | get_system_overview, check_compliance |
| correlation-analyzer | heavy | 11 | analyze_resource_trend, get_system_overview, list_docker_containers, get_container_logs, list_systemd_services, get_service_logs, search_fault_cases, get_user_login_history_tool, get_active_sessions_tool, list_docker_networks, get_service_dependencies_tool |
| ops-scheduler | ops | 6 | list_cron_jobs, validate_cron_expr, create_cron_job, modify_cron_schedule, delete_cron_job_tool, toggle_cron_job_tool |
| knowledge-retriever | light | 4 | retrieve_knowledge, search_fault_cases, web_search, think |

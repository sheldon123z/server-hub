# SubAgent 详细说明

SubAgent 定义在 `modules/agents/subagents.py`，遵循 LangChain 官方规范。主 Agent 通过 `task(subagent_type="name", message="...")` 工具委派任务。

---

## 规范说明

每个 SubAgent 必须包含以下 4 个字段（LangChain 官方 SubAgent 规范要求）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 唯一标识，主 agent 通过此名称委派 |
| `description` | str | action-oriented 描述，帮助主 agent 决定何时委派 |
| `system_prompt` | str | 详细工作流指令 + 输出格式 + 长度限制 |
| `tools` | list | 最小工具集（仅包含完成任务所需的工具）|

可选字段：
- `model: str`：覆盖模型（格式 `provider:model_name`），不指定则继承主 agent 模型

---

## 1. researcher — 联网研究员

**名称**: `researcher`

**描述**: 搜索技术文档、错误解决方案、软件版本信息和最佳实践。每次委派一个主题。

**工具集**（最小化）:

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

**工具集**（最小化）:

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

**工具集**（最小化）:

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

**工具集**（6 个）:

| 工具 | 来源 | 说明 |
|------|------|------|
| `analyze_resource_trend` | 主 agent 工具 | 资源趋势分析（CPU/内存/GPU/磁盘）|
| `get_system_overview` | 主 agent 工具 | 当前系统状态 |
| `list_docker_containers` | 主 agent 工具 | 容器状态（含重启次数）|
| `get_container_logs` | 主 agent 工具 | 异常容器日志 |
| `list_systemd_services` | 主 agent 工具 | 服务状态 |
| `get_service_logs` | 主 agent 工具 | 服务日志 |
| `search_fault_cases` | 主 agent 工具 | 搜索历史类似案例 |

注：实际工具集按顺序为 analyze_resource_trend, get_system_overview, list_docker_containers, get_container_logs, list_systemd_services, get_service_logs, search_fault_cases（共 7 个）。

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

**委派示例**:
```
task(subagent_type="correlation-analyzer", message="服务器在今天下午 3 点左右出现了内存突增和多个容器重启，请分析可能的根因")
```

---

## 配置管理

### 默认 vs 自定义配置

SubAgent 配置支持两种方式：

1. **硬编码默认**（`modules/agents/subagents.py:get_subagents()`）：上述 4 个 SubAgent
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
| custom | 主 agent 的 22 个自定义工具（tools.py）|
| subagent | SubAgent 专属工具（web_search, think）|
| builtin | 框架内置工具（execute, read_file 等）|

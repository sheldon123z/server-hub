# 技术债注册表

> 项目: ServerHub (server-hub)
> 创建: 2026-04-09
> 最后更新: 2026-04-09

---

## TD-20260409-001

| 字段 | 值 |
|------|-----|
| title | SSH 密码明文暴露 (SSE/审计日志/checkpoint 三通道泄漏) |
| status | open |
| severity | P0 |
| category | security |
| source | Issue #1 C-1, 全面代码审查 Phase 2A |
| files | `modules/agents/tools/playbook.py:25-67`, `modules/agents/teams/safety.py:171`, `agent-checkpoints.db` |
| created_at | 2026-04-09 |
| effort | 60 |

### 问题描述

`ssh_execute_command` 工具接受明文 `password` 参数，密码通过三个通道暴露：
- SSE stream 的 `tool_call` 事件包含完整工具参数，密码发送到浏览器
- 审计日志 `teams/safety.py:171` 记录 `args={...}` 含密码
- LangGraph checkpoint 将工具调用参数持久化到 `agent-checkpoints.db`

### 延期原因

用户指示安全类问题统一暂缓，需要整体安全加固规划后一并处理。此问题修复涉及凭据管理架构改造（引入 `credential_id` 引用机制），需要设计讨论。

### 建议修复方案

1. 将 `ssh_execute_command` 的 `password` 参数改为 `credential_id`，引用 `servers` 表中已注册服务器的凭据
2. SSE 事件序列化时对 `password`/`token`/`secret` 字段做脱敏（`***`）
3. 审计日志 `_sanitize_args()` 过滤敏感字段
4. 如需临时密码，走 `HumanInTheLoop` 审批通道而非工具参数

### 关联

- Issue: #1
- 依赖: 无

---

## TD-20260409-002

| 字段 | 值 |
|------|-----|
| title | Zip 符号链接遍历 — skill 导入/导出可外泄敏感文件 |
| status | open |
| severity | P0 |
| category | security |
| source | Issue #1 C-2, 全面代码审查 Phase 2A |
| files | `modules/agents/skill_service.py:390-398` |
| created_at | 2026-04-09 |
| effort | 15 |

### 问题描述

`_safe_extract_archive` 检查了路径遍历（`..`）但未过滤 zip 中的 symlink。攻击者可上传含指向 `~/.api_keys` 的 symlink 的 zip 包，通过 `export_skill` API 外泄。tar 已用 `filter="data"` 安全处理。

### 延期原因

用户指示安全类问题统一暂缓。此项修复极简单（约 5 行代码），建议优先处理。

### 建议修复方案

在 `_safe_extract_archive` 解压后添加 symlink 检测：
```python
for path in destination.rglob("*"):
    if path.is_symlink():
        path.unlink()
        raise ValueError(f"Symlink detected and removed: {path}")
```

### 关联

- Issue: #1

---

## TD-20260409-003

| 字段 | 值 |
|------|-----|
| title | Shell 黑名单绕过 — 包装命令前缀未处理 |
| status | open |
| severity | P0 |
| category | security |
| source | Issue #1 C-3, 全面代码审查 Phase 2A |
| files | `modules/agents/safety.py:149-176` |
| created_at | 2026-04-09 |
| effort | 30 |

### 问题描述

`_normalize_command` 不处理命令前缀包装器，以下命令绕过黑名单：
- `env rm -rf /`, `nice shutdown -h now`, `nohup reboot &`
- `xargs -a /dev/null rm -rf /`, `busybox rm`, `command rm`

### 延期原因

用户指示安全类问题统一暂缓。

### 建议修复方案

1. 添加包装命令 (`env`, `nice`, `nohup`, `xargs`, `busybox`, `command`, `exec`) 到黑名单
2. `_normalize_command` 中 strip 已知包装前缀后再匹配实际命令
3. 添加对应的单元测试用例验证绕过向量

### 关联

- Issue: #1

---

## TD-20260409-004

| 字段 | 值 |
|------|-----|
| title | TOOL_RISK_MAP 与 @register_tool 双源真相 — 新工具可能跳过审批 |
| status | open |
| severity | P1 |
| category | architecture |
| source | Issue #3 H-1, 全面代码审查 Phase 1+2 |
| files | `modules/agents/safety.py:19-93`, `modules/agents/tools/registry.py:201-203` |
| created_at | 2026-04-09 |
| effort | 45 |

### 问题描述

- `TOOL_RISK_MAP` 手动维护 33 个工具，`@register_tool(risk=...)` 声明另一套
- `build_tool_risk_map()` 从未被调用，`@register_tool` 的 risk 参数形同虚设
- 不在 TOOL_RISK_MAP 中的工具默认 SAFE，新增 DANGER 工具可能跳过审批
- 例: `kill_single_process_tool` 在 registry 标 DANGER，safety 标 MODERATE

### 延期原因

涉及安全策略架构调整，需要完整设计 + 充分测试。RiskLevel 重复定义已在本次修复中统一（Issue #4-1），但双源真相的根本问题仍需处理。

### 建议修复方案

1. 废弃 `TOOL_RISK_MAP` 硬编码字典
2. 在 `build_interrupt_config` 中调用 `build_tool_risk_map()` 从 registry 动态获取
3. 为未注册的内建工具（execute, write_file 等）设置 fallback risk level
4. 添加启动时校验：检查所有工具都有 risk 声明

### 关联

- Issue: #3
- 依赖: Issue #4-1 (RiskLevel 统一) — 已完成

---

## TD-20260409-005

| 字段 | 值 |
|------|-----|
| title | Autonomous 模式零审批门控 — admin 可无确认执行高危操作 |
| status | open |
| severity | P1 |
| category | security |
| source | Issue #3 H-4, 全面代码审查 Phase 2A |
| files | `modules/agents/safety.py:108-109` |
| created_at | 2026-04-09 |
| effort | 20 |

### 问题描述

admin + autonomous = 空 `interrupt_config`，LLM 可执行 `manage_linux_user`、`ssh_execute_command`、`docker_prune` 等无需确认。

### 延期原因

用户指示安全类问题统一暂缓。需要确定最小 always-interrupt 工具集的范围。

### 建议修复方案

在 `build_interrupt_config` 中，即使 autonomous 模式也保持最小 always-interrupt 工具集：
```python
ALWAYS_INTERRUPT = {"manage_linux_user", "ssh_execute_command", "delete_cron_job_tool", "docker_prune"}
```

### 关联

- Issue: #3

---

## TD-20260409-006

| 字段 | 值 |
|------|-----|
| title | Docker exec newline 注入 |
| status | open |
| severity | P1 |
| category | security |
| source | Issue #3 H-5, 全面代码审查 Phase 2A |
| files | `modules/docker/services.py:461` |
| created_at | 2026-04-09 |
| effort | 10 |

### 问题描述

`sh -c` 传递命令未过滤 `\n`，`"ls\nrm -rf /"` 可注入多条命令。

### 延期原因

用户指示安全类问题统一暂缓。此项修复极简单（一行正则），建议优先处理。

### 建议修复方案

在 `_EXEC_INJECTION_PATTERNS` 中添加 `\n`, `\r`, `\x00` 检测。

### 关联

- Issue: #3

---

## TD-20260409-007

| 字段 | 值 |
|------|-----|
| title | server_id dispatch 10 处重复样板代码 |
| status | open |
| severity | P2 |
| category | code-quality |
| source | Issue #4-3, 全面代码审查 Phase 1+2 |
| files | `modules/agents/tools/system.py`, `modules/agents/tools/docker.py`, `modules/agents/tools/services.py`, `modules/agents/tools/users.py` |
| created_at | 2026-04-09 |
| effort | 45 |

### 问题描述

每个支持远程执行的工具都有相同的 `get_agent_client + 错误处理` 样板代码（10 处），错误消息格式不一致（"远程获取失败" vs "远程执行失败"）。

### 延期原因

每处的 client 方法调用和结果处理都不同（`get_metrics`, `get_docker_containers`, `docker_action` 等），共同部分仅 3 行。提取通用 helper 收益不大但改动面广（4 文件 10 处），风险比价值高。

### 建议修复方案

如果确定要做，提取 `tools/_remote.py`：
```python
async def remote_dispatch(server_id: str, method: str, **kwargs) -> dict:
    client = await get_agent_client(server_id)
    result = await getattr(client, method)(**kwargs)
    if not result.get("ok"):
        raise RemoteError(f"远程执行失败 ({server_id}): {result.get('error', '未知')}")
    return result
```
但需评估 `getattr` 动态调用带来的可读性损失。

### 关联

- Issue: #4

---

## TD-20260409-008

| 字段 | 值 |
|------|-----|
| title | execute 中断模式 + PID 验证 + sandbox ulimit + playbook 注入 + 审计截断 |
| status | open |
| severity | P2 |
| category | security |
| source | Issue #5, 全面代码审查 Phase 2A |
| files | `modules/agents/safety.py:132-135`, `modules/agents/tools/users.py:153-161`, `modules/agents/sandbox.py:198-204`, `modules/agents/tools/playbook.py:110-160`, `modules/agents/sandbox.py:176` |
| created_at | 2026-04-09 |
| effort | 120 |

### 问题描述

5 个中等安全问题：
- M-1: supervised 模式 execute 的 pattern 不覆盖 curl/wget/python -c/crontab/nc/apt 等
- M-2: kill_single_process_tool 无 PID 归属验证
- M-4: sandbox ulimit 仅限特定路径命令
- M-5: playbook_create 允许存储型 prompt 注入
- M-6: 审计日志截断 500 字符可被利用

### 延期原因

用户指示安全类问题统一暂缓。5 个问题各自独立，每个都需仔细验证，适合作为独立 Sprint 任务。

### 建议修复方案

参见 Issue #5 中每个子项的详细修复建议。优先级建议：M-1 > M-5 > M-2 > M-4 > M-6。

### 关联

- Issue: #5

---

## TD-20260409-009

| 字段 | 值 |
|------|-----|
| title | 核心模块缺失单元测试 + 测试基础设施问题 |
| status | open |
| severity | P2 |
| category | testing |
| source | Issue #6 T-1/T-2, 全面代码审查 Phase 3+4 |
| files | `modules/agents/deep_agent.py`, `modules/agents/tasks/manager.py`, `modules/agents/memory/updater.py`, `modules/agents/safety.py`, 56 个 @register_tool |
| created_at | 2026-04-09 |
| effort | 240 |

### 问题描述

- 关键路径无测试：deep_agent (build/reset/连接管理)、tasks/manager (DAG 依赖解析)、memory/updater (LLM JSON 解析)、safety Shell 黑名单绕过向量
- 56 个 @register_tool 工具函数全无单元测试
- Makefile 无 `make test` target
- `test_agents_runtime.py` 使用旧 `skill.yaml` 格式

### 延期原因

测试是持续工程，需要整体规划测试策略和优先级。建议从安全相关模块（safety.py 黑名单测试）开始。

### 建议修复方案

1. 添加 `make test` target 运行 pytest
2. 优先为 `safety.py` 添加黑名单绕过测试（与 TD-003 Shell 黑名单修复配合）
3. 为 `deep_agent.py` 的 reset/cache 逻辑添加单元测试
4. 更新 `test_agents_runtime.py` 适配 SKILL.md 格式

### 关联

- Issue: #6
- 依赖: TD-20260409-003 (Shell 黑名单绕过修复后同步添加测试)

---

## TD-20260409-010

| 字段 | 值 |
|------|-----|
| title | Skill 子模块间私有函数依赖形成紧耦合三角 |
| status | open |
| severity | P2 |
| category | architecture |
| source | Issue #6 架构部分, 全面代码审查 Phase 3+4 |
| files | `modules/agents/skill_service.py`, `modules/agents/skill_market.py`, `modules/agents/skill_version.py` |
| created_at | 2026-04-09 |
| effort | 60 |

### 问题描述

`skill_market.py` 和 `skill_version.py` 直接导入 `skill_service.py` 的 `_copy_skill_tree`、`_upsert_skill` 等下划线私有函数，形成紧耦合三角。

### 延期原因

耦合重构需要整体规划，需要评估提取 `skill_common.py` 后的 API 边界。本次已修复了最严重的双源真相问题（Issue #2），耦合问题可在后续重构中处理。

### 建议修复方案

1. 创建 `skill_common.py`，提取 `_copy_skill_tree`、`_upsert_skill`、`_log_install` 等共享函数为公开 API
2. `skill_service.py`、`skill_market.py`、`skill_version.py` 改为从 `skill_common` 导入
3. 同时考虑将 `skill_service.py`（954 行）拆分为 `skill_parser.py` + `skill_repository.py` + `skill_recommender.py`

### 关联

- Issue: #6
- Issue: #8 (拆分 skill_service.py)

---

## TD-20260410-001

| 字段 | 值 |
|------|-----|
| title | YAML 编译器验证是死代码 — compile_steps_json 未导出，异常被吞 |
| status | open |
| severity | P1 |
| category | architecture |
| source | Codex Adversarial Review (Pipeline 全功能审查) |
| files | `modules/pipelines/services.py:95-145`, `modules/pipelines/compiler.py` |
| created_at | 2026-04-10 |
| effort | 60 |

### 问题描述

`_compile_steps()` 导入 `compile_steps_json`，但 `compiler.py` 不导出此符号，导入静默失败后回退到直接存储原始 YAML steps。`_validate_parsed()` 调用 `validate_pipeline(parsed)` 传入 `dict` 而非 `PipelineDefinition`，产生的 `AttributeError` 被吞掉，高级验证全部失效。实际效果：无效工作流在保存时被接受，运行时才部分执行后失败。

### 延期原因

修复涉及 compiler.py 导出重构 + services.py 调用链调整 + PipelineDefinition 类型对齐，需要完整设计避免破坏现有 Pipeline 的保存/加载流程。

### 建议修复方案

1. 在 `compiler.py` 中确认并导出 `compile_steps_json`（或修改 services.py 导入正确的名称）
2. `_validate_parsed()` 将 `dict` 转换为 `PipelineDefinition` 再调用 `validate_pipeline`
3. 移除 try/except 吞异常模式，验证失败时 fail closed
4. 添加测试：无效引用 → 期望被拒绝

### 关联

- 来源: Codex Pipeline 全功能 Adversarial Review

---

## TD-20260410-002

| 字段 | 值 |
|------|-----|
| title | max_concurrent_runs 有竞态条件 — read-then-insert 无锁 |
| status | open |
| severity | P2 |
| category | architecture |
| source | Codex Adversarial Review (Pipeline 全功能审查) |
| files | `modules/pipelines/executor.py:60-90` |
| created_at | 2026-04-10 |
| effort | 30 |

### 问题描述

`start_pipeline_run()` 先 COUNT 活跃运行数再 INSERT 新记录，两步之间无锁。并发触发可违反 `max_concurrent_runs` 限制。

### 延期原因

当前单用户场景并发概率低，SQLite 单写入者已提供一定序列化。完整修复需 per-pipeline Lock 或原子 SQL。

### 建议修复方案

per-pipeline `asyncio.Lock` 或原子 `INSERT ... WHERE (SELECT COUNT...) < max` SQL。

### 关联

- 来源: Codex Pipeline 全功能 Adversarial Review

---

## TD-20260409-011

| 字段 | 值 |
|------|-----|
| title | Skill 系统功能增强 — allowed-tools 权限收窄 + 推荐缓存 + frontmatter 预览 |
| status | open |
| severity | P3 |
| category | architecture |
| source | Issue #7, 全面代码审查 Phase 4 |
| files | `modules/agents/deep_agent.py`, `modules/agents/skill_service.py` |
| created_at | 2026-04-09 |
| effort | 120 |

### 问题描述

参考 Claude Code / DeerFlow 的设计：
1. Skill 激活时 agent 可使用全部 56 个工具，应按 `allowed-tools` 字段收窄
2. `recommend_skills()` 每次全量查询 + 分词，应缓存
3. 所有 enabled skills 的完整 SKILL.md 加载到提示词，应改为仅加载 frontmatter
4. SubAgent 应按 group 获取工具子集

### 延期原因

功能增强类需求，需要设计讨论确定优先级和实现方案。

### 建议修复方案

参见 Issue #7 中各子项的详细实现方案。优先级建议：1 (安全收益) > 3 (token 节省) > 2 (性能) > 4 (架构改善)。

### 关联

- Issue: #7

---

## TD-20260409-012

| 字段 | 值 |
|------|-----|
| title | 低优先级代码质量改进清单 |
| status | open |
| severity | P3 |
| category | code-quality |
| source | Issue #8, 全面代码审查 Phase 1-4 综合 |
| files | `modules/agents/skill_service.py`, `modules/agents/sandbox.py`, `modules/agents/safety.py`, `modules/agents/tasks/middleware.py`, `scripts_bridge/registry.py` |
| created_at | 2026-04-09 |
| effort | 180 |

### 问题描述

日常可顺手改进的项目（详见 Issue #8 checklist）：
- 代码结构：skill_service.py 拆分、parse_skill_md 提取、analyze_resource_trend 拆分
- 弃用 API：asyncio.get_event_loop() → get_running_loop()、f-string SQL
- 安全微调：pipe-to-shell 正则补充、SANDBOX_DIR mode=0o700、脚本完整性校验
- 文档：工具 API 参考、Skill 存储抽象

### 延期原因

Backlog 级别，日常开发中顺手改即可。

### 建议修复方案

参见 Issue #8 中的 checklist。建议在相关文件有其他改动时顺手处理。

### 关联

- Issue: #8

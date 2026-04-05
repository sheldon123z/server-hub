# ServerHub 技能系统设计文档

> 日期: 2026-04-05
> 状态: 已批准，待实施
> 灵感来源: DeerFlow Skills System + Claude Code Agent Skills Specification

## 1. 概述

### 1.1 目标

构建一个可插拔的运维技能系统，吸收 DeerFlow 的核心设计理念（三层渐进加载、技能组合、评测闭环）和 Claude Code 的标准格式，为 ServerHub AI 运维助手提供：

- **Agent 自动激活**：根据用户意图语义匹配技能，按需加载专业工作流
- **Web 管理面板**：可视化管理技能的安装/编辑/启禁/版本/评测
- **`/skill:` 命令触发**：用户在聊天输入框通过 `/skill:技能名` 主动激活
- **技能市场**：远程技能仓库的发现、安装、自动更新
- **多用户隔离**：系统/共享/私有三级技能可见性控制

### 1.2 设计原则

- **Claude Code 标准格式**：SKILL.md + YAML frontmatter，兼容 Agent Skills Specification (agentskills.io)
- **DeerFlow 目录惯例**：`references/` + `scripts/` + `assets/` 三层渐进加载
- **应用层主导（方案 A）**：`skill_service.py` 为单一真相源，`SkillsMiddleware` 从其获取 sources
- **单文件入口**：废弃 `skill.yaml`，SKILL.md 是唯一入口文件

### 1.3 现状

ServerHub 当前有两套技能机制并行：

| 层 | 机制 | 格式 |
|---|---|---|
| Deep Agents 框架层 | `SkillsMiddleware` | `SKILL.md` + YAML frontmatter |
| ServerHub 应用层 | `skill_service.py` | `skill.yaml` + `SKILL.md` |

本设计将两者统一为以应用层为主导、框架层为运行时消费者的单一架构。

---

## 2. 技能格式与目录结构

### 2.1 SKILL.md 格式规范

遵循 Claude Code Agent Skills Specification：

```markdown
---
name: incident-commander
description: >
  面向异常、告警和故障处理的指挥技能，优先组织诊断、风险评估与处置顺序。
  触发场景：系统告警(alert)、服务异常、监控波动、故障排查(troubleshoot)、
  需要快速判断优先级时使用。
allowed-tools: get_system_overview analyze_resource_trend search_fault_cases
metadata:
  version: "0.1.0"
  allowed-roles: admin user
  page-contexts: dashboard monitoring notifications
  capabilities: diagnosis triage incident-command
  compose: security-audit diagnosis
  owner: shared
---

# Incident Commander

## 何时使用
...

## 工作流
1. ...
2. ...

## 参考资料
详细分诊矩阵见 `references/triage-matrix.md`
```

#### 标准字段（Claude Code / Agent Skills Spec）

| 字段 | 必须 | 说明 |
|------|------|------|
| `name` | 是 | kebab-case 标识符，须与目录名一致，1-64 字符 |
| `description` | 是 | 做什么 + 何时触发，max 1024 字符 |
| `allowed-tools` | 否 | 空格分隔的工具白名单 |
| `license` | 否 | 许可证 |
| `compatibility` | 否 | 环境要求，max 500 字符 |
| `metadata` | 否 | 任意 key-value 扩展 |

#### ServerHub 扩展字段（通过 metadata 承载）

| metadata key | 说明 |
|-------------|------|
| `version` | 语义化版本号 |
| `allowed-roles` | 空格分隔的角色白名单（`admin user`）|
| `page-contexts` | 空格分隔的页面上下文（`dashboard monitoring`）|
| `capabilities` | 空格分隔的能力标签 |
| `compose` | 空格分隔的依赖技能名 |
| `owner` | 所有者（`system` / `shared` / 用户名）|

### 2.2 目录结构

```
data/skills/
├── system/                      # 系统内置技能（所有用户可见）
│   ├── deep-research/
│   │   └── SKILL.md
│   └── patrol/
│       └── SKILL.md
├── installed/                   # 通过市场/API 安装的共享技能
│   ├── incident-commander/
│   │   ├── SKILL.md             # 唯一入口文件
│   │   ├── references/          # 按需读取的参考文档
│   │   │   └── triage-matrix.md
│   │   ├── scripts/             # 确定性执行脚本
│   │   │   └── generate_report.py
│   │   ├── assets/              # 静态资源
│   │   └── evals/               # 评测用例
│   │       └── evals.json
│   └── fleet-investigator/
│       └── SKILL.md
├── users/                       # 用户私有技能
│   ├── zhengxiaodong/
│   │   └── my-workflow/
│   │       └── SKILL.md
│   └── wangtao/
│       └── experiment-helper/
│           └── SKILL.md
├── shared-scripts/              # 跨技能共享脚本库
│   ├── generate_html_report.py
│   └── chart_renderer.py
└── skill-versions/              # 版本快照
    └── incident-commander/
        ├── 0.1.0/
        └── 0.2.0/
```

### 2.3 三层渐进加载

| 层级 | 内容 | 加载时机 | 大小约束 |
|------|------|---------|---------|
| Level 1 | `name` + `description` | Agent 启动时，注入系统提示词 | ~100 词/技能 |
| Level 2 | SKILL.md 正文 | Agent `read_file()` 激活时 | <500 行 |
| Level 3 | `references/` + `scripts/` + `assets/` | 正文引用时按需读取 | 无限制 |

### 2.4 迁移策略

| 现有文件 | 动作 |
|---------|------|
| `data/skills/installed/*/skill.yaml` + `SKILL.md` | 合并为单个 SKILL.md（yaml 字段移入 frontmatter）|
| `data/skills/*/SKILL.md`（已有 frontmatter）| 保持不变 |
| `data/skills/*/SKILL.md`（无 frontmatter）| 补上 `name` + `description` frontmatter |

---

## 3. 三层触发系统

### 3.1 触发架构

```
用户消息进入
     │
     ├─① /skill:xxx ──────────► 精确匹配 ──► 加载 SKILL.md 全文注入对话
     │
     ├─② 页面上下文 ─────────► metadata.page-contexts 匹配 ──► 推荐气泡
     │
     └─③ 自然语言 ───────────► description 语义匹配 ──► Agent 自动激活
                                (SkillsMiddleware 原生能力)
```

### 3.2 触发层 1：`/skill:xxx` 精确命令

**前端交互**：
1. 用户输入 `/skill:` → 前端调用 `GET /api/agents/skills/list` 获取 enabled 技能列表
2. 继续输入 → 模糊过滤（匹配 `name` 和 `description`）
3. 选中技能 → 消息附加 `skill_id`：`{ "message": "...", "skill_id": "incident-commander" }`
4. 后端收到 `skill_id` → `load_skill_context(skill_id)` → SKILL.md 全文注入本轮系统提示词

与现有 `/` 内置指令使用独立前缀 `/skill:` 区分，不共享菜单。

### 3.3 触发层 2：页面上下文推荐

- 解析 `metadata.page-contexts` 字段
- 前端 AI 气泡打开时调用 `GET /api/agents/skills/recommendations?page_context=monitoring`
- 返回匹配技能卡片，点击等效 `/skill:xxx`

### 3.4 触发层 3：Agent 自动激活

Deep Agents `SkillsMiddleware` 原生能力，无需改动：
1. 启动时扫描技能目录，提取 `name` + `description` 注入系统提示词
2. Agent 根据语义匹配决定是否 `read_file(SKILL.md)`
3. 按正文工作流执行

### 3.5 桥接逻辑

`deep_agent.py` 中 `skills_paths` 从硬编码改为动态获取：

```python
async def _get_skill_sources(user: dict) -> list[str]:
    """按用户身份返回技能目录列表"""
    sources = [str(data_dir / "skills" / "system")]
    sources.append(str(data_dir / "skills" / "installed"))
    user_skills = data_dir / "skills" / "users" / user["username"]
    if user_skills.is_dir():
        sources.append(str(user_skills))
    return sources
```

### 3.6 description 触发优化

`recommend_skills()` 从精确 keywords 匹配改为 description 全文搜索 + 简单评分：

- description 中自然包含触发关键词（中英文），不再需要独立的 `triggers.keywords`
- 写作规范：第一句说做什么，第二句说何时触发，关键词覆盖中英文

---

## 4. 技能组合与链式调用

### 4.1 声明式依赖

技能在 `metadata.compose` 中声明依赖关系，实际串联逻辑写在 SKILL.md 正文中：

```markdown
---
name: full-inspection
metadata:
  compose: security-audit diagnosis patrol
---

# 全面巡检

## 工作流
### Step 1: 安全审计
读取 `../security-audit/SKILL.md` 并执行其工作流。

### Step 2: 系统诊断
读取 `../diagnosis/SKILL.md` 并执行其工作流。
...
```

### 4.2 脚本级复用

`shared-scripts/` 目录存放跨技能共享的确定性脚本，技能通过 `execute` 工具调用。

### 4.3 依赖关系管理

- 管理面板展示技能依赖图
- 卸载时校验：如果被其他技能依赖，给出警告
- 不做运行时自动级联注入、不做技能间 RPC、不做 DAG 引擎

---

## 5. Web 管理面板

### 5.1 UI 布局

Agent 页面「管理」标签中新增「技能」子标签：
- 操作栏：[+ 创建技能] [📦 导入技能包] [🔄 扫描发现]
- 技能列表：名称、描述、版本、owner 标签、启禁状态、工具数/引用数/依赖数
- 编辑器：左侧元数据表单 + 右侧 SKILL.md 编辑器（双向同步）+ 底部附属文件管理

### 5.2 技能生命周期

```
创建/导入 ──► 已安装(enabled) ◄──► 已禁用(disabled) ──► 已删除
```

安装来源：手动创建、本地导入(.zip/.tar.gz)、目录扫描、市场安装、API 安装。

### 5.3 保存后生效

技能变更后调用 `reset_agent_cache()`，下一轮对话自动加载最新配置，无需重启。

### 5.4 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/agents/admin/skills` | GET | 所有技能列表 |
| `GET /api/agents/skills/{id}` | GET | 技能详情（可含 SKILL.md 全文 + 附属文件列表）|
| `POST /api/agents/admin/skills/create` | POST | 创建技能 |
| `PUT /api/agents/admin/skills/{id}` | PUT | 更新 SKILL.md + 附属文件 |
| `GET /api/agents/admin/skills/{id}/files` | GET | 列出附属文件 |
| `PUT /api/agents/admin/skills/{id}/files/{path}` | PUT | 上传/更新附属文件 |
| `DELETE /api/agents/admin/skills/{id}/files/{path}` | DELETE | 删除附属文件 |
| `GET /api/agents/skills/list` | GET | enabled 技能的 name+description（给 `/skill:` 菜单）|
| `POST /api/agents/admin/skills/{id}/export` | POST | 导出为 .zip 包 |
| `POST /api/agents/admin/skills/install-from-repo` | POST | 从本地路径安装（已有）|
| `POST /api/agents/admin/skills/install-upload` | POST | 从上传包安装（已有）|
| `POST /api/agents/admin/skills/{id}/enable` | POST | 启用（已有）|
| `POST /api/agents/admin/skills/{id}/disable` | POST | 禁用（已有）|
| `DELETE /api/agents/admin/skills/{id}` | DELETE | 删除（已有）|

---

## 6. 评测闭环

### 6.1 评测工作流

```
定义测试集(2-5 场景) → 执行评测(有技能/无技能 A/B) → 查看结果(通过率+对比) → 改进技能 → 重新评测
```

### 6.2 测试集格式

`evals/evals.json`：

```json
{
  "skill_name": "incident-commander",
  "evals": [
    {
      "id": 1,
      "prompt": "Docker 容器 dify-worker 频繁重启，帮我排查",
      "expected_behavior": "应先查容器日志和资源使用，给出三级处置建议",
      "assertions": [
        {"name": "调用了容器日志工具", "check": "tool_used:get_container_logs"},
        {"name": "给出了处置优先级", "check": "output_contains:立即处置|继续观察|人工审批"}
      ]
    }
  ]
}
```

### 6.3 Assertion 检查类型

| check 语法 | 含义 |
|-----------|------|
| `tool_used:工具名` | Agent 调用了指定工具 |
| `output_contains:关键词\|关键词` | 输出包含任一关键词 |
| `output_not_contains:关键词` | 输出不包含 |
| `subagent_used:子智能体名` | 委派了指定子智能体 |
| `status:ok\|warning\|critical` | 巡检状态判定正确 |

### 6.4 评测引擎

`skill_eval.py`：
- `run_skill_eval(skill_id, mode="ab")` — 复用 `build_agent()` 工厂，with_skill 注入 SKILL.md，without_skill 不注入
- 结果包含：tool_calls、output_summary、assertions 通过情况、pass_rate、tokens_used、duration_ms
- 异步执行，通过现有异步任务机制后台运行

### 6.5 Description 触发率测试

`trigger_evals` 数组定义 should_trigger / should_not_trigger 用例，调用 `recommend_skills()` 检查目标技能是否在 top-3 中，输出 precision/recall。

### 6.6 评测 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/agents/admin/skills/{id}/evals` | GET | 获取测试集 |
| `PUT /api/agents/admin/skills/{id}/evals` | PUT | 保存测试集 |
| `POST /api/agents/admin/skills/{id}/evals/run` | POST | 执行评测（异步）|
| `GET /api/agents/admin/skills/{id}/evals/results` | GET | 评测结果列表 |
| `GET /api/agents/admin/skills/{id}/evals/results/{run_id}` | GET | 单次评测详情 |

---

## 7. 技能市场

### 7.1 远程 Registry

`registry.json` 索引清单，包含每个技能的 name、description、version、category、author、tags、download_url、checksum。

### 7.2 远程源类型

| 类型 | 拉取方式 | 适用场景 |
|------|---------|---------|
| `git` | `git clone --depth 1` / `git pull` | GitHub/GitLab 仓库 |
| `http` | `GET registry.json` + `GET package.zip` | 内网 HTTP 文件服务器 |
| `local` | 直接扫描目录 | 本地共享目录（NFS/Samba）|

### 7.3 市场 UI

管理面板「技能」标签新增「市场」子视图：搜索、分类筛选、安装/更新按钮、版本对比。

### 7.4 市场 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/agents/admin/skill-market` | GET | 远程索引（带本地安装状态对比）|
| `POST /api/agents/admin/skill-market/sync` | POST | 从远程拉取最新 registry |
| `POST /api/agents/admin/skill-market/install/{name}` | POST | 从市场安装（指定版本）|
| `GET /api/agents/admin/skill-market/sources` | GET | 列出远程源 |
| `PUT /api/agents/admin/skill-market/sources` | PUT | 添加/删除远程源 |

---

## 8. 版本管理与回滚

### 8.1 版本快照

每次安装/更新时自动保存版本快照到 `data/skill-versions/{skill_id}/{version}/`。

### 8.2 回滚机制

`rollback_skill(skill_id, target_version)` — 从快照目录复制到 `installed/`，更新数据库，`reset_agent_cache()`。

### 8.3 数据库

`agent_skill_versions` 表新增 `snapshot_path` 列存储快照目录。

### 8.4 版本 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/agents/admin/skills/{id}/versions` | GET | 列出版本快照 |
| `GET /api/agents/admin/skills/{id}/versions/{ver}` | GET | 查看特定版本 |
| `POST /api/agents/admin/skills/{id}/rollback` | POST | 回滚到指定版本 |

### 8.5 快照保留策略

默认保留最近 10 个版本，可在配置中调整。

---

## 9. 自动更新

### 9.1 更新策略

| 策略 | 行为 | 配置值 |
|------|------|-------|
| 手动（默认）| 管理面板展示可更新徽章 | `manual` |
| 通知 | Telegram 通知管理员 | `notify` |
| 自动 | 自动安装（保留旧版快照可回滚）| `auto` |

### 9.2 定时检查

复用巡检调度的 asyncio 循环，每 24 小时检查远程 registry，按策略处理。在 `main.py` lifespan 中注册为后台任务。

---

## 10. 多用户技能隔离

### 10.1 三级隔离模型

| 级别 | 目录 | 可见性 |
|------|------|-------|
| 系统 | `data/skills/system/` | 所有用户 |
| 共享 | `data/skills/installed/` | 按 `metadata.allowed-roles` 过滤 |
| 私有 | `data/skills/users/{username}/` | 仅 owner 本人（admin 可查看全部）|

### 10.2 数据库

`agent_skills` 表新增 `owner` 列：`system` / `shared` / `{username}`。

### 10.3 权限矩阵

| 用户角色 | 能力 |
|---------|------|
| admin | 创建系统/共享/私有技能，管理所有技能，安装市场技能 |
| user | 创建私有技能，查看自己的 + 共享的 + 系统的 |

---

## 11. 涉及文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `modules/agents/skill_service.py` | 重构 | 解析 SKILL.md frontmatter，新增 CRUD、多用户过滤 |
| `modules/agents/skill_market.py` | 新增 | 远程 registry 同步、市场安装、更新检查 |
| `modules/agents/skill_eval.py` | 新增 | 评测引擎、assertion 检查器、触发率测试 |
| `modules/agents/routes/skills.py` | 增强 | 新增 create/update/files/evals/market/versions/rollback 端点 |
| `modules/agents/routes/chat.py` | 小改 | 消息体增加可选 `skill_id` 字段 |
| `modules/agents/deep_agent.py` | 小改 | `skills_paths` 动态获取，按用户过滤 |
| `modules/agents/schemas.py` | 增强 | 新增 SkillCreate/SkillUpdate/EvalRun 等模型 |
| `database.py` | 小改 | `agent_skills` 新增 `owner` 列，`agent_skill_versions` 新增 `snapshot_path` 列 |
| `config.py` | 小改 | 新增 `skill_auto_update` 配置项 |
| `main.py` | 小改 | lifespan 注册技能更新检查后台任务 |
| `frontend/src/pages/agents/SkillsTab.tsx` | 新增 | 技能管理标签页 |
| `frontend/src/pages/agents/SkillEditor.tsx` | 新增 | 技能编辑器 |
| `frontend/src/pages/agents/SkillEvalPanel.tsx` | 新增 | 评测面板 |
| `frontend/src/pages/agents/SkillMarketView.tsx` | 新增 | 市场视图 |
| `frontend/src/hooks/useSkillCommand.ts` | 新增 | `/skill:` 命令检测和菜单 |
| `frontend/src/api/skills.ts` | 新增 | 技能 API 调用函数 |
| `scripts/migrate_skills.py` | 新增 | skill.yaml → SKILL.md frontmatter 迁移脚本 |

---

## 12. 实现阶段

### Phase 1: 格式统一 + 核心桥接

1. `skill_service.py` 重构：`parse_skill_md()` 替代 `_safe_read_manifest()`
2. 迁移脚本：`scripts/migrate_skills.py`
3. `deep_agent.py` 桥接：`skills_paths` 动态获取
4. `recommend_skills()` 改进：description 全文匹配

**验收**：现有技能以新格式正常加载，Agent 自动激活正常。

### Phase 2: `/skill:` 命令 + 管理面板 + 多用户隔离

5. `routes/chat.py`：支持 `skill_id` 参数
6. `routes/skills.py`：新增 create/update/files/export 端点
7. `owner` 列迁移 + `get_visible_skills()` 过滤
8. 前端 `useSkillCommand.ts` + `SkillsTab.tsx` + `SkillEditor.tsx`

**验收**：`/skill:xxx` 触发可用，管理面板 CRUD 正常，用户只看到自己有权的技能。

### Phase 3: 技能组合 + 评测闭环

9. `metadata.compose` 解析 + 依赖关系查询
10. `shared-scripts/` 共享脚本基础设施
11. `skill_eval.py` 评测引擎
12. 评测相关端点 + 前端 `SkillEvalPanel.tsx`
13. 触发率测试集成

**验收**：组合技能可串联执行，评测 A/B 对比正常。

### Phase 4: 技能市场 + 版本管理 + 自动更新

14. `skill_market.py`：远程 registry 同步、市场安装
15. 版本快照 + `rollback_skill()`
16. 自动更新循环注册到 lifespan
17. 市场 + 版本端点
18. 前端 `SkillMarketView.tsx` + 版本历史面板

**验收**：可从远程仓库安装技能，版本回滚正常，自动更新按策略工作。

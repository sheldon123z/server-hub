---
name: update-docs
description: 根据最近的 git commits 更新 ServerHub 技术文档体系。分析代码变更，自动更新 docs/ 目录中对应的 API 文档、Agent 工具说明、巡检任务、数据库 Schema 等。当用户说"更新文档"、"同步文档"、"文档需要更新"时触发。
---

# 更新 ServerHub 技术文档

当 ServerHub 代码发生变更后，使用此技能更新 `docs/` 目录中的技术文档，保持文档与代码同步。

## 工作流程

### 第一步：分析变更范围

运行以下命令确定需要更新的文件：

```bash
# 查看最近的 commits（默认看最近一次，可通过参数调整）
git log --oneline -5

# 查看变更了哪些文件
git diff --name-only HEAD~1  # 或指定 commit 范围
```

### 第二步：根据变更文件确定需要更新的文档

按以下映射关系确定需要更新的文档：

| 变更文件 | 需要更新的文档 |
|---------|-------------|
| `modules/*/routes.py` | `docs/api/{模块名}.md` |
| `modules/agents/tools.py` | `docs/agents/tools.md` + `docs/api/agents.md` |
| `modules/agents/subagents.py` | `docs/agents/subagents.md` |
| `modules/agents/patrol.py` | `docs/agents/patrol.md` |
| `modules/agents/alert_engine.py` | `docs/agents/alerts.md` |
| `modules/agents/diagnosis.py` | `docs/agents/diagnosis.md` |
| `modules/agents/safety.py` | `docs/agents/safety.md` |
| `data/compliance_baselines.json` | `docs/agents/compliance.md` |
| `database.py` | `docs/database.md` |
| `templates/*.html` | `docs/frontend.md` |
| `modules/新模块/` | 创建 `docs/api/{新模块}.md` + 更新 `docs/api/README.md` + `docs/README.md` |
| `config.py` | `docs/getting-started.md` |
| `main.py`（页面路由） | `docs/api/README.md` |

### 第三步：读取源代码并更新文档

1. 读取变更文件的**当前版本**（不是 diff，而是完整内容）
2. 读取对应文档的**当前版本**
3. 根据代码变更更新文档内容
4. 保持文档格式一致

### 第四步：更新文档索引

如果有新增模块或新增文档文件，更新：
- `docs/README.md` — 文档总索引
- `docs/api/README.md` — API 端点汇总表

## 文档编写规范

### API 端点文档格式

每个端点按以下格式记录：

```markdown
### METHOD /path

- **说明**: 端点功能描述
- **权限**: `admin` 或 `user`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 参数说明 |

**响应示例**:
\```json
{...}
\```
```

### Agent 工具文档格式

每个工具按以下格式记录：

```markdown
### 工具名称

- **风险等级**: safe / moderate / danger
- **说明**: 工具功能
- **参数**: 参数表格
- **返回**: 返回格式说明
- **使用场景**: 何时使用
```

### 巡检任务文档格式

```markdown
| ID | 名称 | 间隔 | 工具 | 说明 |
|---|---|---|---|---|
| task_id | 显示名称 | N分钟 | tool1,tool2 | 检查内容 |
```

## 语言和风格

- 全部使用**中文**
- 技术术语保留英文原文（如 API、JWT、HTMX）
- 代码示例中的键名/参数名保留英文
- 每篇文档聚焦单一主题，控制在 **800 行以内**
- 必须包含准确的**响应示例**（从代码中提取真实格式）

## 注意事项

- 不要凭记忆编写文档，必须**读取当前版本的源代码**确认准确性
- 如果源代码中的函数签名或返回格式与现有文档不一致，以**源代码为准**
- 新增工具必须同时检查 `safety.py` 中的 `TOOL_RISK_MAP` 获取风险等级
- 新增巡检任务必须检查 `patrol.py` 中的 `DEFAULT_PATROLS` 获取完整定义
- 新增数据库表必须检查 `database.py` 中的 `init_tables()` 获取 Schema

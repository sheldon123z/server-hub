---
name: code-review
description: 对当前分支的变更进行深度 code review — 检查权限守卫、SQL 安全、前端一致性、API 规范、Agent 工具注册完整性
disable-model-invocation: true
---

# Code Review

对当前分支相对 main 的所有变更进行系统性审查。

## 工作流程

### 1. 收集变更范围

```bash
# 获取变更文件列表
git diff main --name-only
git diff --staged --name-only
git diff --name-only
```

### 2. 分维度审查

对每个变更文件，按以下维度检查：

#### 权限守卫
- 新增 API 端点是否有 `Depends(require_role(...))` 或 `Depends(get_current_user)`
- 新增工具是否在 `TOOL_RISK_MAP` 中注册风险等级
- 新增工具是否在 `get_server_tools()` 的 `all_tools` 列表中
- 新增工具是否在 `build_interrupt_config()` 的 supervised 配置中（MODERATE/DANGER 级别）
- 前端新增操作按钮是否有 `{% if user.role == 'admin' %}` 守卫

#### SQL 安全
- 所有 SQL 查询使用 `?` 参数化
- 无 f-string 拼接 SQL（除 SET 子句的字段名，且字段名来自白名单）
- ALTER TABLE 用 try/except 兼容已存在列

#### API 规范
- 写操作返回 `{"ok": True, ...}`
- GET 直接返回数据
- 错误使用 `HTTPException(status_code=N, detail="...")`
- 路由前缀遵循 `/api/模块名` 模式

#### 前端一致性
- 新增页面继承 `base.html`
- Alpine.js 组件使用 `init()` 初始化
- 操作按钮对 user 角色隐藏（如适用）

#### Agent 集成完整性
- 新增 SubAgent 遵循 LangChain 官方规范（name/description/system_prompt/tools 四个必填字段）
- SubAgent 工具集最小化（≤7 个）
- SubAgent system_prompt 包含 500 词输出限制

### 3. 使用 security-reviewer subagent

启动 security-reviewer agent 并行执行安全审查：

```
使用 Agent 工具，subagent_type 选择 security-reviewer，
prompt 为 "审查以下变更文件的安全性: [文件列表]"
```

### 4. 输出报告

```markdown
## Code Review 报告

### 变更概要
- 分支: [branch]
- 变更文件: N 个
- 新增行: +N / 删除行: -N

### 问题清单

| 严重度 | 文件 | 问题 | 建议 |
|--------|------|------|------|
| 🔴 | path:line | ... | ... |
| 🟡 | path:line | ... | ... |

### 检查通过项
- ✅ 所有 API 端点有权限守卫
- ✅ SQL 查询参数化
- ...

### 总结
[一句话总结代码质量和安全状况]
```

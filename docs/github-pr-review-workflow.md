# GitHub PR 自动审查工作流

## 概述

本工作流是三智能体闭环系统的一部分。完整系统文档见 [.workflow/README.md](../.workflow/README.md)。

```
Discovery (发现者) → 创建 Issue → Fixer (修复者) → 创建 PR → Reviewer (审查者) → 合并
     ↑                                                              │
     └──────────────────── 反馈循环 ◄────────────────────────────────┘
```

本文档描述 **Reviewer (审查者)** 的工作流程。智能体定义: `.claude/agents/pr-reviewer.md`

---

## 1. 触发方式

两个定时任务驱动整个 PR 审查循环：

| 任务 | Cron ID | 频率 | 职责 |
|------|---------|------|------|
| PR 审查合并 | `be9a68bd` | 每 30 分钟 | 检查 open PR，审查并合并或搁置 |
| PR 日志总结 | `c37255f3` | 每 2 小时 (:07) | 汇总已合并 PR 到分类日志 |

---

## 2. PR 审查合并流程

每 30 分钟自动执行以下步骤：

### 2.1 同步本地

```bash
git fetch origin && git reset --hard origin/main
```

**原因**: 修复 Agent 在 worktree 中持续修复 Issue 并推送 PR，合并后本地必须同步到最新，否则后续 worktree 操作会冲突。使用 `reset --hard` 而非 `pull --rebase` 是因为本地 main 不应有任何未提交改动，直接对齐远程最可靠。

### 2.2 获取 Open PR

```bash
gh pr list --state open --limit 20 --json number,title,author,headRefName,additions,deletions,mergeable,mergeStateStatus,labels
```

### 2.3 四维审查

对每个 PR 执行四个维度的审查:

#### 维度 1: 风格规范 (CI 自动化)

| 检查项 | 方法 | 阻断? |
|--------|------|-------|
| Python: PEP 8 / ruff | CI: `ruff check + format` | 是 |
| TypeScript: 无 `any` | CI: `tsc --noEmit` | 是 |
| 提交格式 | `<type>: <中文描述>` | 是 |
| API 路由 | `/api/<module>` 前缀、kebab-case | 是 |

#### 维度 2: 功能验证

| 检查项 | 方法 |
|--------|------|
| PR 是否覆盖 Issue 全部修复项 | 对照 Issue 描述逐项 check |
| 散弹修复是否遗漏文件 | grep 确认同类问题不再存在 |

#### 维度 3: 回归检测

| 检查项 | 方法 |
|--------|------|
| CI 全绿 | Ruff + Frontend Build + Backend Tests |
| 导入无循环依赖 | 检查新增 import |
| 已知陷阱 | SPA catch-all 顺序、_ensure_column 时序 |

#### 维度 4: 架构一致性

| 检查项 | 标准 |
|--------|------|
| routes.py 只做 HTTP 层 | 业务逻辑在 services.py |
| SQL 参数化 | 使用 `?`，禁止 f-string |
| 认证声明 | `Depends(require_role/get_current_user)` |
| 响应格式 | POST/PUT/DELETE: `{"ok": true}` |

### 2.3.1 风险分级

| 条件 | 级别 | 处理 |
|------|------|------|
| <50 行, ≤3 文件, CI 全绿 | 快速通道 | 自动合并 |
| 50-200 行 | 标准审查 | 四维审查后合并 |
| >200 行且涉及关键文件 | needs-human | 不自动合并，写入人工确认队列 |
| 删除功能 / 架构重构 | needs-human | 不自动合并，写入人工确认队列 |

**关键文件**: `main.py`, `database.py`, `config.py`, `auth/`, `modules/agents/safety.py`

### 2.4 CI 检查策略

合并前必须等待所有关键 CI job 通过：

```
Ruff Lint + Format       → 必须 SUCCESS
Frontend Build           → 必须 SUCCESS
Backend Tests            → 必须 SUCCESS
Dependency Audit         → 允许 FAILURE（通常是已有依赖问题，非本 PR 引入）
```

如果 Backend Tests 长时间 pending（超过 5 分钟），记录状态但不无限等待，下一轮再检查。

### 2.5 合并操作

审查通过且 CI 全绿后：

```bash
gh pr merge <N> --squash --delete-branch
```

合并后清理：
1. 删除关联的 worktree：`git worktree remove .claude/worktrees/<name> --force`
2. 删除本地分支：`git branch -D <branch>`
3. 再次同步：`git fetch origin && git reset --hard origin/main`

### 2.6 搁置处理

不符合合并条件的 PR 记录到 `.workflow/pr-shelved.md` 和 `.workflow/state.md` 的搁置反馈队列：

| 搁置原因 | 处理方式 |
|---------|---------|
| 合并冲突 (CONFLICTING/DIRTY) | 记录冲突文件，建议 rebase |
| CI 失败且与本 PR 相关 | 记录失败 job，等待修复 |
| 不符合 CONTRIBUTING.md | 列出具体违规项和修复建议 |
| 重复/已被替代 | 关闭并说明原因 |

搁置文件格式：
```markdown
## PR #N — 标题
- **状态**: 搁置原因
- **分支**: `branch-name`
- **+A/-D**，N 个文件

### 问题清单
| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|

### 修复建议
1. 具体修复步骤
```

---

## 3. PR 日志总结流程

每 2 小时自动执行：

### 3.1 同步 + 提取

```bash
git fetch origin && git reset --hard origin/main
git log --oneline origin/main | grep -E '\(#[0-9]+\)|Merge pull request'
```

### 3.2 增量追加

对比 `.pr-review-log.md` 已有记录，只追加新合并的 PR。按类别归入：

| 类别 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| refactor | 重构 |
| perf | 性能优化 |
| security | 安全修复 |
| test | 测试相关 |
| docs | 文档 |
| chore | 工程基础设施 |

每条记录保持简短：PR 编号 + 标题 + 一句话说明。

---

## 4. 与 Issue 修复工作流的关系

两个工作流共享同一个仓库和 main 分支，形成闭环：

```
┌──────────────────────────────────────────────┐
│              Issue 修复工作流                  │
│  读取 issues → worktree 隔离 → 修复 → 创建 PR │
└──────────────────┬───────────────────────────┘
                   │ 创建 PR
                   ▼
┌──────────────────────────────────────────────┐
│              PR 审查工作流                     │
│  检查 open PR → 审查 → 合并/搁置 → 同步 main  │
└──────────────────┬───────────────────────────┘
                   │ 合并后 main 更新
                   ▼
           修复 Agent worktree rebase
                   │
                   ▼
              继续修复下一个 Issue
```

**关键约束**:
- 合并后必须立即 `git reset --hard origin/main`，因为修复 Agent 的 worktree 依赖最新代码
- worktree 清理必须在合并后立即执行，否则分支无法删除
- 搁置的 PR 可能在下一轮 Issue 修复中被间接解决（如 rebase 后重新审查）

---

## 5. 当前局限与改进方向

| 局限 | 说明 | 改进方向 |
|------|------|---------|
| 审查以风格为主 | 对照 CONTRIBUTING.md 做静态审查，不验证功能正确性 | 合并前对前端 PR 跑 `tsc --noEmit`，后端跑 `ruff check` |
| 无运行时测试 | 不执行 `make smoke-test` 或端到端测试 | 对关键 API 路径做 smoke test |
| CI 等待阻塞 | Backend Tests 有时超过 5 分钟，导致审查循环拉长 | 设置超时上限，未完成的 PR 下一轮再处理 |
| 无风险分级 | 1 行 typo 和 500 行重构同等对待 | 大 PR（>200 行或 >10 文件）不自动合并，记录后等人工确认 |
| 单点执行 | 审查和日志在同一 Claude 会话中运行 | 考虑拆分为独立 Agent |

---

## 6. 状态文件清单

所有状态文件集中在 `.workflow/` 目录:

| 文件 | 用途 | 更新者 |
|------|------|--------|
| `.workflow/state.md` | 三方协同状态 (队列、worktree、轮次) | 三方共同 |
| `.workflow/pr-shelved.md` | 搁置 PR 及可操作修复指南 | Reviewer |
| `.workflow/pr-merged-log.md` | 所有已合并 PR 的分类日志 | Reviewer |
| `.workflow/issue-plan.md` | Issue 分类、优先级、依赖图 | Discovery + Fixer |
| `.workflow/metrics.md` | 质量指标 (通过率、审查轮数) | Reviewer + Discovery |
| `.workflow/rules.md` | 共享规则 (人工维护) | 人工 |

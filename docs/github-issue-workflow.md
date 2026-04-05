# GitHub Issue 自动修复工作流

## 概述

本工作流是三智能体闭环系统的一部分。完整系统文档见 [.workflow/README.md](../.workflow/README.md)。

```
Discovery (发现者) → 创建 Issue → Fixer (修复者) → 创建 PR → Reviewer (审查者) → 合并
     ↑                                                              │
     └──────────────────── 反馈循环 ◄────────────────────────────────┘
```

本文档描述 **Fixer (修复者)** 的工作流程。智能体定义: `.claude/agents/issue-fixer.md`

---

## 1. 每轮循环入口

每次循环开始时，按顺序执行以下检查：

### 1.1 读取状态文件

| 文件 | 用途 |
|------|------|
| `.workflow/issue-plan.md` | Issue 归类与进度追踪（主文件） |
| `.workflow/state.md` | 三智能体共享协同状态 |
| `.workflow/pr-shelved.md` | 搁置 PR 及修复指南 |

### 1.2 优先处理搁置反馈

在开始新 Issue 修复前，**必须先检查** `.workflow/state.md` 的"搁置反馈队列"：

- **有搁置 PR** → 逐条 check 修复指南，在 worktree 中修复后更新 PR，登记到"修复完成队列"
- **无搁置** → 继续取新 Issue

每个 PR 最多 3 轮搁置-修复循环，第 3 次移入人工确认队列。

### 1.3 更新 Issue 归类

读取 `.workflow/issue-plan.md`，清理已完成的部分。如果文件内容与当前 GitHub Open Issues 不一致，重新归类并更新文件。

---

## 2. Issue 修复流程

### 2.1 优先级与依赖

修复顺序按 `.github-issues-plan.md` 中的优先级排序执行。开始修复前需评估 **Issue 间的依赖与阻塞关系**：

- 有依赖的 Issue 按顺序修复（如 #254 CI 基础设施 → #258 测试覆盖）
- 无依赖的 Issue 可并行修复
- 互相阻塞的 Issue 不能同时开工

### 2.2 Worktree 隔离

**所有 Issue 修复必须在独立的 git worktree 中进行**，互不干扰：

```bash
git worktree add .claude/worktrees/fix-<issue-id>-<desc> -b fix/<issue-id>-<desc>
```

命名规范：

- worktree 目录：`fix-<issue-id>-<简短描述>`
- 分支名：`fix/<issue-id>-<简短描述>`

### 2.3 修复 → 提交 → PR

1. 在 worktree 中完成代码修改
2. 遵循 `docs/CONTRIBUTING.md` 规范（编码风格、Git 提交格式等）
3. 通过 `ruff check` + `ruff format` 验证
4. 提交代码，创建 PR
5. 将 PR 信息记录到 `.pr-review-issues.md`

---

## 3. 关键约束

| 规则 | 说明 |
|------|------|
| **禁止合并 PR** | 只创建 PR，不合并。合并由人工审核后执行 |
| **Worktree 隔离** | 每个 Issue 在独立 worktree 中修复，避免代码冲突 |
| **遵循 CONTRIBUTING.md** | 编码风格、API 规范、Git 提交格式等 |
| **先清 PR 再修 Issue** | 每轮先检查未合并 PR，再开始新修复 |
| **注意依赖关系** | Issue 间有阻塞时按顺序执行，不并行 |
| **及时更新状态文件** | 修复完成/PR 创建后立即更新 `.github-issues-plan.md` |

---

## 4. 状态文件维护

所有状态文件集中在 `.workflow/` 目录:

### `.workflow/issue-plan.md`

- 记录所有 Open Issue 的分类、优先级、状态
- 已完成的 Issue 移入「已完成」区域
- 包含依赖关系图，指导修复顺序

### `.workflow/state.md`

- 搁置反馈队列 (Reviewer → Fixer)
- 修复完成队列 (Fixer → Reviewer)
- 活跃 worktree 列表
- 人工确认队列

### `.workflow/pr-shelved.md`

- 审查未通过的搁置 PR 及可操作修复指南
- 搁置后由 Fixer 消费修复

---

## 5. 循环示意

```
┌─────────────────────────────────────┐
│  读取 .github-issues-plan.md        │
│  读取 .pr-review-issues.md          │
└──────────────┬──────────────────────┘
               │
       ┌───────▼────────┐    有未合并 PR
       │ 有待合并 PR？   │──────────────┐
       └───────┬────────┘              │
               │ 无                     ▼
       ┌───────▼────────┐    /pr-comments 获取反馈
       │ 取下一个 Issue  │    修改并更新 PR
       └───────┬────────┘              │
               │                       │
       ┌───────▼────────┐              │
       │ Worktree 隔离   │              │
       │ 修复 → 提交     │              │
       │ 创建 PR         │              │
       │ 更新状态文件     │              │
       └───────┬────────┘              │
               │                       │
       ┌───────▼───────────────────────┘
       │  回到循环起点
       └────────────────┘
```

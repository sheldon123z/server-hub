#!/bin/bash
# roborev 评审发现问题时自动创建 GitHub Issue
# 触发条件: review.completed + verdict=F
# 环境变量由 roborev hook 通过命令行参数传入

JOB_ID="$1"
SHA="$2"
REPO="ChenShi-Tech/serverhub"

if [ -z "$JOB_ID" ] || [ -z "$SHA" ]; then
    echo "Usage: $0 <job_id> <sha>" >&2
    exit 1
fi

# 获取完整评审内容
REVIEW=$(roborev show --job "$JOB_ID" 2>/dev/null)
if [ -z "$REVIEW" ]; then
    echo "roborev-issue: 无法获取 job $JOB_ID 的评审内容" >&2
    exit 1
fi

SHORT_SHA="${SHA:0:7}"

# 根据评审内容中最高严重级别决定 Priority 标签
LABELS="code-quality"
if echo "$REVIEW" | grep -qi "Severity.*:.*High\|严重\|Critical"; then
    LABELS="$LABELS,P1-high"
elif echo "$REVIEW" | grep -qi "Severity.*:.*Medium\|中等"; then
    LABELS="$LABELS,P2-medium"
else
    LABELS="$LABELS,P3-low"
fi

# 如果评审内容包含安全相关词汇，追加 security 标签
if echo "$REVIEW" | grep -qi "inject\|injection\|xss\|csrf\|auth\|密钥\|secret\|token\|sql.*inject\|命令注入"; then
    LABELS="$LABELS,security"
fi

# 构建 Issue body（含评审摘要 + 操作指引）
BODY=$(cat <<EOF
## 自动评审发现问题

- **Commit**: \`$SHORT_SHA\`
- **Job ID**: $JOB_ID
- **Agent**: claude-code

## 评审内容

\`\`\`
$REVIEW
\`\`\`

## 操作建议

在 Claude Code 中运行以下命令自动修复：

\`\`\`
/roborev-fix $JOB_ID
\`\`\`

或手动运行：
\`\`\`bash
roborev fix $JOB_ID
\`\`\`
EOF
)

# 创建 Issue
ISSUE_URL=$(gh issue create \
    --repo "$REPO" \
    --title "[roborev] $SHORT_SHA: AI 代码评审发现问题" \
    --body "$BODY" \
    --label "$LABELS" \
    2>&1)

if echo "$ISSUE_URL" | grep -q "https://"; then
    echo "roborev-issue: Issue 已创建 → $ISSUE_URL"

    # ── 自动触发 Claude Code 修复（worktree 隔离，不影响用户工作） ──
    ISSUE_NUM=$(echo "$ISSUE_URL" | grep -oP '\d+$')
    if [ -n "$ISSUE_NUM" ] && command -v claude &>/dev/null; then
        MAIN_REPO="/home/zhengxiaodong/scripts/server-hub"
        BRANCH="fix/roborev-${ISSUE_NUM}"
        WT_DIR="${MAIN_REPO}/.claude/worktrees/roborev-${ISSUE_NUM}"
        LOG_FILE="${MAIN_REPO}/logs/roborev-autofix.log"

        echo "roborev-issue: 触发 Claude Code 自动修复 Issue #$ISSUE_NUM (worktree: $WT_DIR)" >> "$LOG_FILE"

        nohup bash -c "
            cd '$MAIN_REPO' || exit 1
            # 创建隔离 worktree
            git worktree add '$WT_DIR' -b '$BRANCH' origin/main 2>>'$LOG_FILE' || exit 1
            cd '$WT_DIR' || exit 1

            # Claude Code 在 worktree 中修复
            claude --dangerously-skip-permissions -p \
                '修复 GitHub Issue #$ISSUE_NUM 的 roborev 代码评审问题。
                 1. 用 gh issue view $ISSUE_NUM 查看评审内容
                 2. 逐项修复每个 Finding
                 3. 确保 ruff check . 通过
                 4. git add 修改的文件并 commit (message 必须以 [roborev] 开头，包含 Closes #$ISSUE_NUM)
                 5. git push origin $BRANCH 并用 gh pr create 创建 PR
                 6. 运行 roborev close $JOB_ID' \
                >>'$LOG_FILE' 2>&1

            # 清理 worktree
            cd '$MAIN_REPO'
            git worktree remove '$WT_DIR' --force 2>/dev/null
        " >> "$LOG_FILE" 2>&1 &
        echo "roborev-issue: 自动修复已在后台 worktree 启动 (PID: $!)"
    fi
else
    echo "roborev-issue: Issue 创建失败: $ISSUE_URL" >&2
    exit 1
fi

#!/bin/bash
# ──────────────────────────────────────────────────────────
# GitHub 远程状态清理 — 定时检查 open issues/PRs
#
# 功能:
#   1. 合并可直接合并的 roborev PR
#   2. 关闭有冲突的过时 PR
#   3. 关闭已在 main 中修复的 issue
#   4. 清理残留的远程分支
#
# 用法: cron 每小时执行一次
#   0 * * * * bash ~/scripts/server-hub/scripts/gh-cleanup.sh
# ──────────────────────────────────────────────────────────

set -uo pipefail

# ── 并发保护 (flock) ──
exec 200>/tmp/gh-cleanup.lock
flock -n 200 || exit 0

REPO="${SERVERHUB_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "ChenShi-Tech/serverhub")}"
LOG="/home/zhengxiaodong/scripts/server-hub/logs/gh-cleanup.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

MAIN_REPO="/home/zhengxiaodong/scripts/server-hub"
cd "$MAIN_REPO" || exit 1

# ── 冲突解决函数 ──
_resolve_conflict() {
    local pr_num="$1" branch="$2"
    local wt_dir="${MAIN_REPO}/.claude/worktrees/conflict-${pr_num}"

    # 在 worktree 中尝试 rebase
    git fetch origin main "$branch" 2>/dev/null
    git worktree add "$wt_dir" "$branch" 2>>"$LOG" || {
        log "CONFLICT-SKIP: PR #$pr_num — 无法创建 worktree"
        return
    }

    cd "$wt_dir" || return

    if git rebase origin/main 2>/dev/null; then
        # rebase 成功（简单冲突自动解决了）
        git push origin "$branch" --force-with-lease 2>>"$LOG" && \
            log "CONFLICT-RESOLVED: PR #$pr_num — rebase 成功，已推送" || \
            log "CONFLICT-PUSH-FAILED: PR #$pr_num"
    else
        # rebase 失败，用 Claude Code 解决冲突
        git rebase --abort 2>/dev/null

        if command -v claude &>/dev/null; then
            log "CONFLICT-CLAUDE: PR #$pr_num — 调用 Claude Code 解决冲突"
            timeout 300 claude --dangerously-skip-permissions -p \
                "你在 worktree 中处理 PR #$pr_num 的 git 冲突。
                 1. 运行 git rebase origin/main
                 2. 如果有冲突，读取冲突文件，理解两边意图，手动解决
                 3. 解决后 git add 并 git rebase --continue
                 4. 确保 ruff check . 通过
                 5. git push origin $branch --force-with-lease
                 不要修改任何与冲突无关的代码。" \
                >>"$LOG" 2>&1

            if [ $? -eq 0 ]; then
                log "CONFLICT-RESOLVED: PR #$pr_num — Claude Code 解决冲突成功"
            else
                log "CONFLICT-FAILED: PR #$pr_num — Claude Code 无法解决，保留 PR 等待人工处理"
            fi
        else
            log "CONFLICT-MANUAL: PR #$pr_num — 无 Claude CLI，需人工解决"
        fi
    fi

    # 清理 worktree
    cd "$MAIN_REPO"
    git worktree remove "$wt_dir" --force 2>/dev/null
}

# ── 1. 处理 open PRs (仅 roborev) ──
# 不自动合并！冲突 PR 尝试用 Claude Code 自动解决冲突后保留给人工审批。
OPEN_PRS=$(gh pr list --repo "$REPO" --state open --json number,title,mergeable,headRefName \
    --jq '.[] | select(.title | contains("[roborev]")) | [.number, .title, .mergeable, .headRefName] | @tsv' 2>/dev/null)

if [ -n "$OPEN_PRS" ]; then
    while IFS=$'\t' read -r num title mergeable branch; do
        if [ "$mergeable" = "CONFLICTING" ]; then
            log "CONFLICT: PR #$num ($title) — 尝试自动解决冲突"
            _resolve_conflict "$num" "$branch"
        else
            log "PENDING-REVIEW: PR #$num ($mergeable) — 等待人工审批"
        fi
    done <<< "$OPEN_PRS"
fi

# ── 2. 处理 open Issues (roborev 创建的) ──
OPEN_ISSUES=$(gh issue list --repo "$REPO" --state open --label code-quality --json number,title,createdAt \
    --jq '.[] | select(.title | contains("[roborev]")) | [.number, .title, .createdAt] | @tsv' 2>/dev/null)

NOW_EPOCH=$(date +%s)

if [ -n "$OPEN_ISSUES" ]; then
    while IFS=$'\t' read -r num title created_at; do
        # 用 issue 创建时间计算年龄
        CREATED_EPOCH=$(date -d "$created_at" +%s 2>/dev/null || echo "")
        if [ -n "$CREATED_EPOCH" ]; then
            AGE=$(( (NOW_EPOCH - CREATED_EPOCH) / 3600 ))
            if [ "$AGE" -gt 48 ]; then
                # 超过 48h 且无关联 open PR 才关闭
                LINKED_PRS=$(gh pr list --repo "$REPO" --state open --head "fix/roborev-$num" \
                    --json number --jq 'length' 2>/dev/null)
                if [ "${LINKED_PRS:-0}" = "0" ]; then
                    gh issue close "$num" --repo "$REPO" --comment "自动关闭：超过 48 小时且无关联 PR" 2>/dev/null
                    log "CLOSED-STALE: Issue #$num ($title, age=${AGE}h)"
                else
                    log "SKIPPED: Issue #$num (has linked PR, age=${AGE}h)"
                fi
            fi
        fi
    done <<< "$OPEN_ISSUES"
fi

# ── 3. 清理远程残留分支 ──
git branch -r --list 'origin/fix/roborev-*' 2>/dev/null | sed 's|^ *origin/||' | while read -r branch; do
    [ -z "$branch" ] && continue
    # 检查是否有对应的 open PR
    PR_COUNT=$(gh pr list --repo "$REPO" --head "$branch" --state open --json number --jq 'length' 2>/dev/null)
    if [ "$PR_COUNT" = "0" ]; then
        git push origin --delete "$branch" 2>/dev/null && log "DELETED-BRANCH: $branch"
    fi
done

# ── 汇总 ──
REMAINING_ISSUES=$(gh issue list --repo "$REPO" --state open --json number --jq 'length' 2>/dev/null)
REMAINING_PRS=$(gh pr list --repo "$REPO" --state open --json number --jq 'length' 2>/dev/null)
log "CHECK-DONE: issues=$REMAINING_ISSUES, PRs=$REMAINING_PRS"

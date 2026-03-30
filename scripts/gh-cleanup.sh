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

cd /home/zhengxiaodong/scripts/server-hub || exit 1

# ── 1. 处理 open PRs (仅 roborev) ──
# 注意：不自动合并！PR 需要人工审批后才能合并。
# 只关闭有冲突的 PR（修复内容已过时）。
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

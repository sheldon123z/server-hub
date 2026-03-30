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

REPO="ChenShi-Tech/serverhub"
LOG="/home/zhengxiaodong/scripts/server-hub/logs/gh-cleanup.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

cd /home/zhengxiaodong/scripts/server-hub || exit 1

# ── 1. 处理 open PRs ──
OPEN_PRS=$(gh pr list --repo "$REPO" --state open --json number,title,mergeable,headRefName --jq '.[] | "\(.number)|\(.title)|\(.mergeable)|\(.headRefName)"' 2>/dev/null)

if [ -n "$OPEN_PRS" ]; then
    while IFS='|' read -r num title mergeable branch; do
        # roborev 自动 PR
        if echo "$title" | grep -q "\[roborev\]"; then
            if [ "$mergeable" = "MERGEABLE" ]; then
                # 可合并 → 自动合并
                if gh pr merge "$num" --repo "$REPO" --merge --delete-branch 2>/dev/null; then
                    log "AUTO-MERGED: PR #$num ($title)"
                else
                    log "MERGE-FAILED: PR #$num ($title)"
                fi
            elif [ "$mergeable" = "CONFLICTING" ]; then
                # 有冲突 → 关闭
                gh pr close "$num" --repo "$REPO" --delete-branch --comment "自动关闭：与 main 有冲突，修复内容可能已在 main 中" 2>/dev/null
                log "CLOSED-CONFLICT: PR #$num ($title)"
            fi
            # UNKNOWN 状态跳过，等下次检查
        fi
    done <<< "$OPEN_PRS"
fi

# ── 2. 处理 open Issues (roborev 创建的) ──
OPEN_ISSUES=$(gh issue list --repo "$REPO" --state open --label code-quality --json number,title --jq '.[] | "\(.number)|\(.title)"' 2>/dev/null)

if [ -n "$OPEN_ISSUES" ]; then
    while IFS='|' read -r num title; do
        if echo "$title" | grep -q "\[roborev\]"; then
            # 检查对应的 commit SHA 是否在 main 中
            SHA=$(echo "$title" | grep -oP '[a-f0-9]{7}')
            if [ -n "$SHA" ]; then
                # 如果 commit 之后有更新（main 已前进），大概率已修复
                COMMIT_DATE=$(git log --format="%ct" "$SHA" 2>/dev/null | head -1)
                LATEST_DATE=$(git log --format="%ct" -1 2>/dev/null)
                if [ -n "$COMMIT_DATE" ] && [ -n "$LATEST_DATE" ]; then
                    AGE=$(( (LATEST_DATE - COMMIT_DATE) / 3600 ))
                    if [ "$AGE" -gt 24 ]; then
                        # 超过 24 小时的旧 issue，自动关闭
                        gh issue close "$num" --repo "$REPO" --comment "自动关闭：commit 已超过 24 小时，后续提交可能已修复" 2>/dev/null
                        log "CLOSED-STALE: Issue #$num ($title, age=${AGE}h)"
                    fi
                fi
            fi
        fi
    done <<< "$OPEN_ISSUES"
fi

# ── 3. 清理远程残留分支 ──
REMOTE_BRANCHES=$(git branch -r --list 'origin/fix/roborev-*' 2>/dev/null | sed 's|origin/||')
for branch in $REMOTE_BRANCHES; do
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

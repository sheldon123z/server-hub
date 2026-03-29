#!/bin/bash
# RoboRev PR 自动评审 — 轮询模式
# 每 5 分钟检查是否有新 PR 需要评审
# 用法: 加入 cron 或手动运行
# cron: */5 * * * * bash /home/zhengxiaodong/scripts/server-hub/scripts/roborev-pr-watcher.sh

set -euo pipefail

REPO="ChenShi-Tech/serverhub"
STATE_FILE="/tmp/.roborev-pr-reviewed"
LOG_FILE="/home/zhengxiaodong/scripts/server-hub/logs/roborev-pr-watcher.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

# 确保状态文件存在
touch "$STATE_FILE"

# 获取所有 open PR
PRS=$(gh pr list --repo "$REPO" --state open --json number,headRefName,updatedAt --jq '.[] | "\(.number) \(.headRefName) \(.updatedAt)"' 2>/dev/null)

if [ -z "$PRS" ]; then
    exit 0
fi

while IFS= read -r line; do
    PR_NUM=$(echo "$line" | awk '{print $1}')
    BRANCH=$(echo "$line" | awk '{print $2}')
    UPDATED=$(echo "$line" | awk '{print $3}')

    # 检查是否已评审过此版本
    REVIEW_KEY="${PR_NUM}:${UPDATED}"
    if grep -qF "$REVIEW_KEY" "$STATE_FILE" 2>/dev/null; then
        continue
    fi

    log "发现未评审 PR #$PR_NUM ($BRANCH), 开始 roborev 评审..."

    # 切到项目目录执行评审
    cd /home/zhengxiaodong/scripts/server-hub

    # 获取 PR 的 base branch
    BASE=$(gh pr view "$PR_NUM" --repo "$REPO" --json baseRefName -q .baseRefName 2>/dev/null || echo "main")

    # fetch PR 分支并评审
    git fetch origin "$BRANCH" 2>/dev/null || continue
    RESULT=$(roborev review --branch --wait --base "$BASE" 2>&1) || true

    # 将评审结果发表为 PR comment
    COMMENT_BODY="## 🤖 RoboRev AI 代码评审\n\n\`\`\`\n${RESULT}\n\`\`\`"
    gh pr comment "$PR_NUM" --repo "$REPO" --body "$(echo -e "$COMMENT_BODY")" 2>/dev/null || true

    # 标记为已评审
    echo "$REVIEW_KEY" >> "$STATE_FILE"
    log "PR #$PR_NUM 评审完成"

done <<< "$PRS"

# 清理 > 7 天的状态记录（防止文件无限增长）
if [ -f "$STATE_FILE" ]; then
    tail -200 "$STATE_FILE" > "${STATE_FILE}.tmp" && mv "${STATE_FILE}.tmp" "$STATE_FILE"
fi

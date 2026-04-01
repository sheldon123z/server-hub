#!/bin/bash
# ──────────────────────────────────────────────────
# 本地 main 分支快速同步（每 5 分钟）
# 保持本地 main 与远程一致，PR 合并后立即可用
# ──────────────────────────────────────────────────

exec 201>/tmp/git-sync.lock
flock -n 201 || exit 0

cd /home/zhengxiaodong/scripts/server-hub || exit 1

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
[ "$CURRENT_BRANCH" != "main" ] && exit 0

git fetch origin main 2>/dev/null || exit 0

LOCAL=$(git rev-parse main 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null)

if [ "$LOCAL" != "$REMOTE" ]; then
    BEHIND=$(git rev-list --count main..origin/main 2>/dev/null)
    if git pull --ff-only origin main 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] SYNCED: +${BEHIND} commits" >> logs/git-sync.log

        # 如果有前端变更，自动重建
        CHANGED=$(git diff --name-only "$LOCAL".."$REMOTE" -- \
            'frontend/src/' 'frontend/package.json' 'frontend/package-lock.json' \
            'frontend/vite.config.ts' 'frontend/tsconfig*.json' \
            'frontend/index.html' 'frontend/public/' 2>/dev/null | wc -l)
        if [ "$CHANGED" -gt 0 ]; then
            # 用子 shell 确保构建失败时仍回到原目录
            (cd frontend && npm run build) >> logs/git-sync.log 2>&1 && \
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] REBUILT: frontend ($CHANGED files changed)" >> logs/git-sync.log || \
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] BUILD-FAILED: frontend ($CHANGED files)" >> logs/git-sync.log
        fi

        # 如果有后端变更，重启服务
        BACKEND_CHANGED=$(git diff --name-only "$LOCAL".."$REMOTE" -- modules/ main.py config.py database.py 2>/dev/null | wc -l)
        if [ "$BACKEND_CHANGED" -gt 0 ]; then
            sudo systemctl restart server-hub 2>/dev/null
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] RESTARTED: server-hub ($BACKEND_CHANGED backend files)" >> logs/git-sync.log
        fi
    fi
fi

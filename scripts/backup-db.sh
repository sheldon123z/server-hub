#!/bin/bash
# SQLite 数据库备份脚本
# 备份 data/ 下 3 个数据库到 /mnt/data1/serverhub-backups/
# 保留 30 天，自动清理旧备份
# 建议 cron: 0 3 * * * bash /home/zhengxiaodong/scripts/server-hub/scripts/backup-db.sh

set -euo pipefail

# ─── 配置 ───
PROJECT_DIR="/home/zhengxiaodong/scripts/server-hub"
DATA_DIR="${PROJECT_DIR}/data"
BACKUP_DIR="/mnt/data1/serverhub-backups"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${PROJECT_DIR}/logs/db-backup.log"

DATABASES=(
    "server-hub.db"
    "agent-checkpoints.db"
    "agent-store.db"
)

# Telegram 通知（可选，失败时告警）
TELEGRAM_SCRIPT="/home/zhengxiaodong/scripts/notification/send-telegram-report.sh"

# ─── 函数 ───
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ─── 前置检查 ───
mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

if ! command -v sqlite3 &>/dev/null; then
    log "ERROR: sqlite3 未安装"
    exit 1
fi

# ─── 备份 ───
FAIL_COUNT=0
for db in "${DATABASES[@]}"; do
    src="${DATA_DIR}/${db}"
    if [[ ! -f "$src" ]]; then
        log "WARN: 数据库不存在，跳过: ${src}"
        continue
    fi

    dst="${BACKUP_DIR}/${db%.db}_${TIMESTAMP}.db"
    log "备份: ${db} → ${dst}"

    if sqlite3 "$src" ".backup '${dst}'"; then
        # 验证备份文件大小 > 0
        if [[ -s "$dst" ]]; then
            log "OK: ${db} 备份成功 ($(du -h "$dst" | cut -f1))"
        else
            log "ERROR: ${db} 备份文件为空"
            rm -f "$dst"
            ((FAIL_COUNT++))
        fi
    else
        log "ERROR: ${db} 备份失败 (sqlite3 退出码: $?)"
        rm -f "$dst"
        ((FAIL_COUNT++))
    fi
done

# ─── 清理旧备份 ───
CLEANED=$(find "$BACKUP_DIR" -name "*.db" -mtime +${RETENTION_DAYS} -print -delete | wc -l)
if [[ "$CLEANED" -gt 0 ]]; then
    log "清理: 删除 ${CLEANED} 个超过 ${RETENTION_DAYS} 天的旧备份"
fi

# ─── 汇总 ───
TOTAL=${#DATABASES[@]}
SUCCESS=$((TOTAL - FAIL_COUNT))
log "备份完成: ${SUCCESS}/${TOTAL} 成功，保留 ${RETENTION_DAYS} 天"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    log "ERROR: ${FAIL_COUNT} 个数据库备份失败"
    # 备份失败时发送 Telegram 告警
    if [[ -x "$TELEGRAM_SCRIPT" ]]; then
        echo "⚠️ ServerHub 数据库备份失败: ${FAIL_COUNT}/${TOTAL} 个库备份异常，请检查 ${LOG_FILE}" \
            | "$TELEGRAM_SCRIPT" --stdin
    fi
    exit 1
fi

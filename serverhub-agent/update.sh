#!/bin/bash
# ServerHub Agent 自更新脚本
# 从 Hub 下载最新 agent 源码并重启服务
#
# 用法: curl -sSL http://<hub-ip>:9900/static/agent/update.sh | sudo bash -s -- --hub http://<hub-ip>:9900

set -euo pipefail

AGENT_DIR="/opt/serverhub-agent"
HUB_URL=""
PY_FILES="collectors.py config.py main.py"

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hub) HUB_URL="$2"; shift 2 ;;
        --dir) AGENT_DIR="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [ -z "$HUB_URL" ]; then
    echo "错误: 必须指定 --hub 参数"
    echo "用法: sudo bash update.sh --hub http://192.168.110.219:9900"
    exit 1
fi

echo "=== ServerHub Agent 更新 ==="
echo "Hub: $HUB_URL"
echo "Agent 目录: $AGENT_DIR"

# 下载所有 .py 文件
for f in $PY_FILES; do
    echo "下载 $f ..."
    if curl -sSL -o "${AGENT_DIR}/${f}.new" "${HUB_URL}/static/agent/${f}" 2>/dev/null; then
        # 备份并替换
        if [ -f "${AGENT_DIR}/${f}" ]; then
            cp "${AGENT_DIR}/${f}" "${AGENT_DIR}/${f}.bak"
        fi
        mv "${AGENT_DIR}/${f}.new" "${AGENT_DIR}/${f}"
        echo "  ✓ $f 已更新"
    else
        echo "  ✗ $f 下载失败，跳过"
        rm -f "${AGENT_DIR}/${f}.new"
    fi
done

# 重启服务
echo "重启 serverhub-agent 服务..."
systemctl restart serverhub-agent
sleep 2

if systemctl is-active --quiet serverhub-agent; then
    echo "=== 更新完成，agent 运行中 ==="
else
    echo "=== 警告: agent 未正常启动，检查日志: journalctl -u serverhub-agent -n 20 ==="
    exit 1
fi

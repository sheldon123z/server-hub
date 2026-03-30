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

# 阶段 1: 下载所有文件到临时目录
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

for f in $PY_FILES; do
    echo "下载 $f ..."
    if ! curl -fsSL -o "${TMPDIR}/${f}" "${HUB_URL}/static/agent/${f}"; then
        echo "  ✗ $f 下载失败，中止更新"
        exit 1
    fi
    # 基本校验: 文件非空且是合法 Python
    if [ ! -s "${TMPDIR}/${f}" ]; then
        echo "  ✗ $f 为空文件，中止更新"
        exit 1
    fi
    echo "  ✓ $f 下载成功"
done

# 阶段 2: 全部下载成功后，备份并替换
for f in $PY_FILES; do
    if [ -f "${AGENT_DIR}/${f}" ]; then
        cp "${AGENT_DIR}/${f}" "${AGENT_DIR}/${f}.bak"
    fi
    mv "${TMPDIR}/${f}" "${AGENT_DIR}/${f}"
done
echo "所有文件已替换"

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

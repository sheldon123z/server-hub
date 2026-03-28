#!/bin/bash
# ServerHub Agent 一键安装脚本
# Usage: curl -sSL http://hub:9900/install-agent.sh | bash -s -- --token YOUR_TOKEN
#
# 选项:
#   --token TOKEN     Agent 认证令牌（必须）
#   --port PORT       Agent 监听端口（默认 9901）
#   --hub-url URL     Hub 地址（可选，用于 push 模式）
#   --install-dir DIR 安装目录（默认 /opt/serverhub-agent）

set -euo pipefail

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

AGENT_TOKEN=""
AGENT_PORT="9901"
HUB_URL=""
INSTALL_DIR="/opt/serverhub-agent"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)
            AGENT_TOKEN="$2"
            shift 2
            ;;
        --port)
            AGENT_PORT="$2"
            shift 2
            ;;
        --hub-url)
            HUB_URL="$2"
            shift 2
            ;;
        --install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$AGENT_TOKEN" ]]; then
    echo "ERROR: 必须指定 --token"
    echo "Usage: bash install.sh --token YOUR_TOKEN [--port 9901] [--hub-url http://hub:9900]"
    exit 1
fi

# ---------------------------------------------------------------------------
# 环境检查
# ---------------------------------------------------------------------------

echo "=== ServerHub Agent 安装程序 ==="
echo "安装目录: $INSTALL_DIR"
echo "Agent 端口: $AGENT_PORT"

# 检查 Python 3.9+
if ! command -v python3 &>/dev/null; then
    echo "ERROR: 需要 Python 3.9+，请先安装"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 9 ]]; then
    echo "ERROR: Python 版本 $PY_VER 过低，需要 3.9+"
    exit 1
fi
echo "Python 版本: $PY_VER"

# ---------------------------------------------------------------------------
# 安装文件
# ---------------------------------------------------------------------------

echo ""
echo "[1/5] 创建安装目录..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$(whoami):$(whoami)" "$INSTALL_DIR"

# 如果从远程执行（stdin pipe），需要从 hub 下载文件
# 如果本地执行，直接复制
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/main.py" ]]; then
    echo "[2/5] 复制 agent 文件..."
    cp "$SCRIPT_DIR/main.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/collectors.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
elif [[ -n "$HUB_URL" ]]; then
    echo "[2/5] 从 Hub 下载 agent 文件..."
    for f in main.py collectors.py config.py requirements.txt; do
        curl -fsSL "$HUB_URL/static/agent/$f" -o "$INSTALL_DIR/$f" || {
            echo "错误: 无法从 $HUB_URL 下载 $f"
            echo "请确保 Hub 已部署 agent 文件到 /static/agent/ 目录"
            exit 1
        }
    done
else
    echo "[2/5] 错误: 未找到本地文件且未设置 HUB_URL"
    echo "用法: bash install.sh --token TOKEN --hub http://hub:9900"
    echo "  或: 将 agent 文件放入 $(pwd) 后再运行"
    exit 1
fi

# ---------------------------------------------------------------------------
# 创建虚拟环境 & 安装依赖
# ---------------------------------------------------------------------------

echo "[3/5] 创建虚拟环境并安装依赖..."
cd "$INSTALL_DIR"

if [[ ! -d "venv" ]]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

# ---------------------------------------------------------------------------
# 创建环境文件
# ---------------------------------------------------------------------------

echo "[4/5] 写入配置..."
cat > "$INSTALL_DIR/.env" <<EOF
AGENT_TOKEN=${AGENT_TOKEN}
AGENT_PORT=${AGENT_PORT}
HUB_URL=${HUB_URL}
EOF

chmod 600 "$INSTALL_DIR/.env"

# ---------------------------------------------------------------------------
# 创建 systemd 服务
# ---------------------------------------------------------------------------

echo "[5/5] 创建 systemd 服务..."

SERVICE_FILE="/etc/systemd/system/serverhub-agent.service"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=ServerHub Agent — 服务器监控代理
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=serverhub-agent

# 安全加固
NoNewPrivileges=false
ProtectSystem=false
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable serverhub-agent
sudo systemctl restart serverhub-agent

# ---------------------------------------------------------------------------
# 验证
# ---------------------------------------------------------------------------

echo ""
echo "=== 安装完成 ==="
sleep 2

if systemctl is-active --quiet serverhub-agent; then
    echo "serverhub-agent 服务运行中"
    echo ""
    # 测试 health 端点
    if command -v curl &>/dev/null; then
        echo "健康检查:"
        curl -s "http://127.0.0.1:${AGENT_PORT}/health" | python3 -m json.tool 2>/dev/null || echo "(curl 测试失败，可能还在启动中)"
    fi
else
    echo "WARNING: 服务未正常启动，请检查日志:"
    echo "  sudo journalctl -u serverhub-agent -n 30 --no-pager"
fi

echo ""
echo "管理命令:"
echo "  sudo systemctl status serverhub-agent   # 查看状态"
echo "  sudo systemctl restart serverhub-agent   # 重启"
echo "  sudo journalctl -u serverhub-agent -f    # 查看日志"
echo ""
echo "在 Hub 端注册此服务器时使用:"
echo "  IP: $(hostname -I | awk '{print $1}')"
echo "  端口: ${AGENT_PORT}"
echo "  Token: (安装时指定的 token)"

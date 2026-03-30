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
# 辅助函数
# ---------------------------------------------------------------------------

UPGRADE_MODE=false

log_step() {
    echo ""
    echo "[$1] $2"
}

# 自动检测最高可用 Python 版本 (>=3.9)，设置 PYTHON 和 PY_VER
detect_python() {
    PYTHON=""
    PY_VER=""
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$candidate" &>/dev/null; then
            local ver
            ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            local minor
            minor=$(echo "$ver" | cut -d. -f2)
            if [[ "${minor:-0}" -ge 9 ]]; then
                PYTHON="$candidate"
                PY_VER="$ver"
                break
            fi
        fi
    done
}

# ---------------------------------------------------------------------------
# 环境检查
# ---------------------------------------------------------------------------

echo "=== ServerHub Agent 安装程序 ==="
echo "安装目录: $INSTALL_DIR"
echo "Agent 端口: $AGENT_PORT"

# ---------------------------------------------------------------------------
# 升级模式检测
# ---------------------------------------------------------------------------

if [[ -f "$INSTALL_DIR/main.py" ]]; then
    echo ""
    echo "检测到已有安装，将进行升级..."
    UPGRADE_MODE=true
    # 停止旧服务
    sudo systemctl stop serverhub-agent 2>/dev/null || true
    echo "  已停止旧服务"
fi

# ---------------------------------------------------------------------------
# [1/7] Python 环境检测与自动安装
# ---------------------------------------------------------------------------

log_step "1/7" "检测 Python 环境..."

detect_python

if [[ -z "$PYTHON" ]]; then
    echo "  未找到 Python 3.9+，尝试自动安装..."

    if command -v apt-get &>/dev/null; then
        # Debian/Ubuntu: 尝试 deadsnakes PPA
        echo "  检测到 Debian/Ubuntu 系统，通过 apt 安装..."
        sudo apt-get update -qq
        sudo apt-get install -y software-properties-common 2>/dev/null || true
        sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
        sudo apt-get update -qq
        # 按优先级尝试安装
        if sudo apt-get install -y python3.11 python3.11-venv python3.11-dev 2>/dev/null; then
            echo "  已通过 apt 安装 Python 3.11"
        elif sudo apt-get install -y python3.10 python3.10-venv python3.10-dev 2>/dev/null; then
            echo "  已通过 apt 安装 Python 3.10"
        elif sudo apt-get install -y python3.9 python3.9-venv python3.9-dev 2>/dev/null; then
            echo "  已通过 apt 安装 Python 3.9"
        else
            echo "  apt 安装失败，将尝试从源码编译..."
        fi
    elif command -v dnf &>/dev/null; then
        # Fedora / RHEL 9+
        echo "  检测到 Fedora/RHEL 系统，通过 dnf 安装..."
        sudo dnf install -y python3.11 python3.11-devel 2>/dev/null || \
        sudo dnf install -y python3.10 python3.10-devel 2>/dev/null || \
        echo "  dnf 安装失败，将尝试从源码编译..."
    elif command -v yum &>/dev/null; then
        # RHEL/CentOS 7/8
        echo "  检测到 CentOS/RHEL 系统，通过 yum 安装..."
        sudo yum install -y python3.11 2>/dev/null || \
        sudo yum install -y python39 python39-devel 2>/dev/null || \
        echo "  yum 安装失败，将尝试从源码编译..."
    fi

    # 重新检测
    detect_python

    # 如果仍然没有，从源码编译 Python 3.11 作为最后手段
    if [[ -z "$PYTHON" ]]; then
        echo "  包管理器安装失败，从源码编译 Python 3.11.11..."
        echo "  （编译过程可能需要 5-15 分钟）"

        # 安装编译依赖
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y build-essential zlib1g-dev libncurses5-dev \
                libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev \
                libsqlite3-dev wget libbz2-dev 2>/dev/null || true
        elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
            local pkg_mgr="yum"
            command -v dnf &>/dev/null && pkg_mgr="dnf"
            sudo "$pkg_mgr" groupinstall -y "Development Tools" 2>/dev/null || true
            sudo "$pkg_mgr" install -y openssl-devel bzip2-devel libffi-devel \
                zlib-devel readline-devel sqlite-devel wget 2>/dev/null || true
        fi

        BUILD_DIR=$(mktemp -d)
        cd "$BUILD_DIR"
        wget -q "https://www.python.org/ftp/python/3.11.11/Python-3.11.11.tgz" || {
            echo "ERROR: 无法下载 Python 源码，请检查网络连接或手动安装 Python 3.9+"
            rm -rf "$BUILD_DIR"
            exit 1
        }
        tar xzf Python-3.11.11.tgz
        cd Python-3.11.11
        echo "  正在 configure..."
        ./configure --enable-optimizations --prefix=/usr/local 2>/dev/null || {
            # 不带优化重试（更快但性能稍差）
            echo "  优化编译失败，尝试标准编译..."
            ./configure --prefix=/usr/local 2>/dev/null || {
                echo "ERROR: Python 源码编译 configure 失败"
                rm -rf "$BUILD_DIR"
                exit 1
            }
        }
        echo "  正在编译（使用 $(nproc) 核心）..."
        make -j"$(nproc)" 2>/dev/null || {
            echo "ERROR: Python 源码编译失败"
            rm -rf "$BUILD_DIR"
            exit 1
        }
        echo "  正在安装..."
        sudo make altinstall 2>/dev/null || {
            echo "ERROR: Python 安装失败"
            rm -rf "$BUILD_DIR"
            exit 1
        }
        # 清理编译文件
        rm -rf "$BUILD_DIR"
        echo "  Python 3.11.11 源码编译安装完成"

        # 再次检测
        detect_python
    fi

    if [[ -z "$PYTHON" ]]; then
        echo "ERROR: Python 自动安装失败，请手动安装 Python 3.9+ 后重试"
        echo "  当前 python3 版本: $(python3 --version 2>/dev/null || echo '未安装')"
        exit 1
    fi
fi

echo "  Python: $PYTHON ($PY_VER)"

# ---------------------------------------------------------------------------
# [2/7] 创建安装目录
# ---------------------------------------------------------------------------

log_step "2/7" "创建安装目录..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$(whoami):$(whoami)" "$INSTALL_DIR"

# ---------------------------------------------------------------------------
# [3/7] 复制/下载 agent 文件
# ---------------------------------------------------------------------------

# 如果从远程执行（stdin pipe），需要从 hub 下载文件
# 如果本地执行，直接复制
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "$SCRIPT_DIR/main.py" ]]; then
    log_step "3/7" "复制 agent 文件..."
    cp "$SCRIPT_DIR/main.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/collectors.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/config.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
elif [[ -n "$HUB_URL" ]]; then
    log_step "3/7" "从 Hub 下载 agent 文件..."
    for f in main.py collectors.py config.py requirements.txt; do
        curl -fsSL "$HUB_URL/static/agent/$f" -o "$INSTALL_DIR/$f" || {
            echo "错误: 无法从 $HUB_URL 下载 $f"
            echo "请确保 Hub 已部署 agent 文件到 /static/agent/ 目录"
            exit 1
        }
    done
else
    log_step "3/7" "错误: 未找到本地文件且未设置 HUB_URL"
    echo "用法: bash install.sh --token TOKEN --hub-url http://hub:9900"
    echo "  或: 将 agent 文件放入 $(pwd) 后再运行"
    exit 1
fi

# ---------------------------------------------------------------------------
# [4/7] 创建虚拟环境 & 安装依赖
# ---------------------------------------------------------------------------

log_step "4/7" "创建虚拟环境并安装依赖..."
cd "$INSTALL_DIR"

if [[ "$UPGRADE_MODE" == true ]] && [[ -d "venv" ]]; then
    echo "  升级模式: 复用已有虚拟环境"
else
    "$PYTHON" -m venv venv
fi

source venv/bin/activate

# 检测是否需要国内镜像（pypi.org 不可达则使用清华源）
PIP_EXTRA=""
if ! timeout 3 curl -s https://pypi.org > /dev/null 2>&1; then
    PIP_EXTRA="-i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn"
    echo "  检测到 PyPI 不可达，使用清华镜像"
fi

# shellcheck disable=SC2086
pip install --quiet --upgrade pip $PIP_EXTRA
# shellcheck disable=SC2086
pip install --quiet -r requirements.txt $PIP_EXTRA
deactivate

# ---------------------------------------------------------------------------
# [5/7] 创建环境文件
# ---------------------------------------------------------------------------

log_step "5/7" "写入配置..."

if [[ "$UPGRADE_MODE" == true ]] && [[ -f "$INSTALL_DIR/.env" ]]; then
    # 升级模式: 就地更新已有配置，保留用户自定义的额外变量
    for var_name in AGENT_TOKEN AGENT_PORT; do
        var_value="${!var_name}"
        if grep -q "^${var_name}=" "$INSTALL_DIR/.env"; then
            sed -i "s|^${var_name}=.*|${var_name}=${var_value}|" "$INSTALL_DIR/.env"
        else
            echo "${var_name}=${var_value}" >> "$INSTALL_DIR/.env"
        fi
    done
    if [[ -n "$HUB_URL" ]]; then
        if grep -q "^HUB_URL=" "$INSTALL_DIR/.env"; then
            sed -i "s|^HUB_URL=.*|HUB_URL=${HUB_URL}|" "$INSTALL_DIR/.env"
        else
            echo "HUB_URL=${HUB_URL}" >> "$INSTALL_DIR/.env"
        fi
    fi
    echo "  升级模式: 已更新 .env 配置"
else
    cat > "$INSTALL_DIR/.env" <<EOF
AGENT_TOKEN=${AGENT_TOKEN}
AGENT_PORT=${AGENT_PORT}
HUB_URL=${HUB_URL}
EOF
fi

chmod 600 "$INSTALL_DIR/.env"

# ---------------------------------------------------------------------------
# [6/7] 创建 systemd 服务
# ---------------------------------------------------------------------------

log_step "6/7" "创建 systemd 服务..."

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
# [7/7] 配置防火墙
# ---------------------------------------------------------------------------

log_step "7/7" "配置防火墙..."

if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -qi "active\|激活"; then
    sudo ufw allow "${AGENT_PORT}/tcp" comment "ServerHub Agent" 2>/dev/null && \
        echo "  已开放 UFW 端口 ${AGENT_PORT}/tcp" || \
        echo "  UFW 规则添加失败，请手动开放端口 ${AGENT_PORT}/tcp"
elif command -v firewall-cmd &>/dev/null && firewall-cmd --state 2>/dev/null | grep -q running; then
    sudo firewall-cmd --permanent --add-port="${AGENT_PORT}/tcp" 2>/dev/null && \
    sudo firewall-cmd --reload 2>/dev/null && \
        echo "  已开放 firewalld 端口 ${AGENT_PORT}/tcp" || \
        echo "  firewalld 规则添加失败，请手动开放端口 ${AGENT_PORT}/tcp"
elif command -v iptables &>/dev/null; then
    # 检查是否已存在规则，避免重复添加
    if ! sudo iptables -C INPUT -p tcp --dport "${AGENT_PORT}" -j ACCEPT 2>/dev/null; then
        sudo iptables -I INPUT -p tcp --dport "${AGENT_PORT}" -j ACCEPT 2>/dev/null && \
            echo "  已通过 iptables 开放端口 ${AGENT_PORT}/tcp" || \
            echo "  iptables 规则添加失败，请手动开放端口 ${AGENT_PORT}/tcp"
    else
        echo "  iptables 端口 ${AGENT_PORT}/tcp 已开放"
    fi
else
    echo "  未检测到活跃的防火墙，跳过"
fi

# ---------------------------------------------------------------------------
# 验证
# ---------------------------------------------------------------------------

echo ""
if [[ "$UPGRADE_MODE" == true ]]; then
    echo "=== 升级完成 ==="
else
    echo "=== 安装完成 ==="
fi
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

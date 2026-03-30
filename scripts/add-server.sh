#!/bin/bash
# ──────────────────────────────────────────────────────────
# ServerHub 一键添加远程服务器
#
# 在 Hub 服务器上执行，一条命令完成：
#   1. 在 Hub 注册服务器 → 获取 token
#   2. SSH 到远程服务器安装 Agent
#   3. 验证连接
#
# 用法:
#   bash scripts/add-server.sh 服务器名 IP地址 [SSH用户]
#
# 示例:
#   bash scripts/add-server.sh gpu-node-01 192.168.110.50
#   bash scripts/add-server.sh gpu-node-01 192.168.110.50 root
# ──────────────────────────────────────────────────────────

set -euo pipefail

# 前置依赖检查
if ! command -v jq &>/dev/null; then
    echo "❌ 需要 jq 工具来安全构建 JSON。请安装: sudo apt-get install -y jq"
    exit 1
fi

NAME=""
IP=""
SSH_USER=""
SSH_PASS=""
AGENT_PORT="9901"

# 支持两种用法：位置参数 或 --flag 参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)     NAME="$2"; shift 2 ;;
        --ip)       IP="$2"; shift 2 ;;
        --user)     SSH_USER="$2"; shift 2 ;;
        --pass)     SSH_PASS="$2"; shift 2 ;;
        --port)     AGENT_PORT="$2"; shift 2 ;;
        --help|-h)
            echo "用法: bash scripts/add-server.sh --name 名称 --ip IP --user 用户 --pass 密码"
            echo "  或: bash scripts/add-server.sh 名称 IP [用户] [密码]"
            exit 0 ;;
        *)
            # 位置参数兼容
            if [ -z "$NAME" ]; then NAME="$1"
            elif [ -z "$IP" ]; then IP="$1"
            elif [ -z "$SSH_USER" ]; then SSH_USER="$1"
            elif [ -z "$SSH_PASS" ]; then SSH_PASS="$1"
            fi
            shift ;;
    esac
done

[ -z "$SSH_USER" ] && SSH_USER="root"
HUB_URL="http://$(hostname -I | awk '{print $1}'):9900"
HUB_LOCAL="http://127.0.0.1:9900"
COOKIE_JAR=$(mktemp /tmp/serverhub-cookies.XXXXXX)
trap 'rm -f "$COOKIE_JAR"' EXIT

if [ -z "$NAME" ] || [ -z "$IP" ]; then
    echo "用法:"
    echo "  bash scripts/add-server.sh 名称 IP 用户 密码"
    echo "  bash scripts/add-server.sh --name gpu-01 --ip 10.0.0.1 --user root --pass 123456"
    echo ""
    echo "示例:"
    echo "  bash scripts/add-server.sh gpu-node-01 192.168.110.50 root mypassword"
    exit 1
fi

# 如果没给密码，交互式询问
if [ -z "$SSH_PASS" ]; then
    read -rsp "输入 $SSH_USER@$IP 的 SSH 密码 (回车跳过用密钥): " SSH_PASS
    echo ""
fi

echo "══════════════════════════════════════════"
echo "  ServerHub 添加服务器: $NAME ($IP)"
echo "══════════════════════════════════════════"
echo ""

# ── 1. 登录 Hub 获取认证 ──
echo "[1/4] 登录 Hub..."
source /home/zhengxiaodong/.api_keys 2>/dev/null || true

# 读取 admin 密码
ADMIN_PASS="${SERVERHUB_ADMIN_PASSWORD:-}"
if [ -z "$ADMIN_PASS" ]; then
    # 尝试从 .env 读取
    ADMIN_PASS=$(grep SERVERHUB_ADMIN_PASSWORD /home/zhengxiaodong/scripts/server-hub/.env 2>/dev/null | cut -d= -f2-)
fi
if [ -z "$ADMIN_PASS" ]; then
    read -rsp "输入 admin 密码: " ADMIN_PASS
    echo ""
fi

LOGIN=$(curl -s -c "$COOKIE_JAR" -X POST "$HUB_LOCAL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg u "admin" --arg p "$ADMIN_PASS" '{username:$u,password:$p}')" 2>/dev/null)

if ! echo "$LOGIN" | grep -q '"ok".*true'; then
    echo "❌ Hub 登录失败: $LOGIN"
    exit 1
fi
echo "  ✓ Hub 登录成功"

# ── 2. 注册服务器 → 获取 token ──
echo "[2/4] 注册服务器..."
REGISTER=$(curl -s -b "$COOKIE_JAR" -X POST "$HUB_LOCAL/api/servers/" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg n "$NAME" --arg ip "$IP" --argjson port "$AGENT_PORT" --arg u "$SSH_USER" \
        '{name:$n,ip_address:$ip,agent_port:$port,ssh_user:$u}')" 2>/dev/null)

if echo "$REGISTER" | grep -q '"ok".*true'; then
    AGENT_TOKEN=$(echo "$REGISTER" | python3 -c "import sys,json; print(json.load(sys.stdin)['agent_token'])")
    echo "  ✓ 服务器已注册 (token: ${AGENT_TOKEN:0:8}...)"
elif echo "$REGISTER" | grep -q "已存在"; then
    echo "  ⚠ 服务器 '$NAME' 已注册，跳过注册步骤"
    echo "  需要重新获取 token 请先在 Web 界面删除再重新添加"
    AGENT_TOKEN=""
else
    echo "❌ 注册失败: $REGISTER"
    exit 1
fi

# ── 3. SSH 安装 Agent ──
if [ -n "$AGENT_TOKEN" ]; then
    echo "[3/4] SSH 安装 Agent 到 $SSH_USER@$IP..."

    # 安全提醒: HUB_URL 使用 HTTP，请确保网络环境可信（内网）
    ESCAPED_TOKEN=$(printf '%q' "$AGENT_TOKEN")
    REMOTE_CMD="curl -sSL $HUB_URL/static/agent/install.sh | bash -s -- --token $ESCAPED_TOKEN --port $AGENT_PORT --hub-url $(printf '%q' "$HUB_URL")"

    if [ -n "$SSH_PASS" ]; then
        # 密码方式（需要 sshpass）
        if ! command -v sshpass &>/dev/null; then
            echo "  安装 sshpass..."
            sudo apt-get install -y sshpass &>/dev/null || sudo yum install -y sshpass &>/dev/null || {
                echo "❌ 无法安装 sshpass，请手动在远程服务器执行:"
                echo "  $REMOTE_CMD"
                exit 1
            }
        fi
        export SSHPASS="$SSH_PASS"
        if ! sshpass -e ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
            "$SSH_USER@$IP" "$REMOTE_CMD" 2>&1 | sed 's/^/  │ /'; then
            echo "  ❌ SSH 连接或 Agent 安装失败"
            exit 1
        fi
        unset SSHPASS
    else
        # 密钥方式
        if ! ssh -o ConnectTimeout=10 -o BatchMode=yes \
            "$SSH_USER@$IP" "$REMOTE_CMD" 2>&1 | sed 's/^/  │ /'; then
            echo "  ❌ SSH 连接或 Agent 安装失败"
            exit 1
        fi
    fi

    echo "  ✓ Agent 安装完成"
else
    echo "[3/4] ⚠ 跳过安装（无 token）"
fi

# ── 4. 验证连接 ──
if [ -z "$AGENT_TOKEN" ]; then
    echo "[4/4] ⚠ 跳过验证（服务器已存在，未获取新 token）"
else
    SERVER_ID=$(echo "$REGISTER" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    if [ -n "$SERVER_ID" ]; then
        echo "[4/4] 验证连接..."
        sleep 3
        TEST=$(curl -s -b "$COOKIE_JAR" -X POST "$HUB_LOCAL/api/servers/$SERVER_ID/test" 2>/dev/null)
        if echo "$TEST" | grep -q '"ok".*true\|"reachable".*true'; then
            echo "  ✓ 连接验证成功！"
        else
            echo "  ⚠ 连接测试: $TEST"
            echo "  Agent 可能还在启动中，稍后在 Web 界面查看状态"
        fi
    else
        echo "[4/4] ⚠ 跳过验证（未获取到服务器 ID）"
    fi
fi

# cookie 文件由 trap EXIT 自动清理

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ 服务器 $NAME ($IP) 添加完成"
echo ""
echo "  在 Web 界面查看: $HUB_URL"
echo "  切换顶部服务器选择器即可管理"
echo "══════════════════════════════════════════"

#!/bin/bash
# ──────────────────────────────────────────────────────────────
# ServerHub Smoke Test — 关键端点集成验证
#
# 用法:
#   bash scripts/smoke-test.sh              # 测试 localhost:9900
#   bash scripts/smoke-test.sh 192.168.1.1  # 测试指定地址
#   make smoke-test                         # 通过 Makefile
#
# 退出码: 0=全部通过, 1=有失败
# ──────────────────────────────────────────────────────────────

set -uo pipefail

HOST="${1:-localhost}"
PORT="${2:-9900}"
BASE="http://${HOST}:${PORT}"
COOKIE_JAR="/tmp/.serverhub-smoke-cookies"
FAIL=0
PASS=0
TOTAL=0

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

pass() { ((PASS++)); ((TOTAL++)); echo -e "  ${GREEN}✓${NC} $1"; }
fail() { ((FAIL++)); ((TOTAL++)); echo -e "  ${RED}✗${NC} $1 — $2"; }
skip() { ((TOTAL++)); echo -e "  ${YELLOW}○${NC} $1 — $2"; }

# ── 测试函数 ──
test_status() {
    local desc="$1" url="$2" expect_code="${3:-200}"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "${BASE}${url}" --max-time 10 2>/dev/null)
    if [ "$code" = "$expect_code" ]; then
        pass "$desc ($code)"
    else
        fail "$desc" "期望 ${expect_code}, 实际 ${code}"
    fi
}

test_json_array() {
    local desc="$1" url="$2"
    local body code
    body=$(curl -s -b "$COOKIE_JAR" "${BASE}${url}" --max-time 10 2>/dev/null)
    code=$?
    if [ $code -ne 0 ]; then fail "$desc" "curl 失败"; return; fi
    if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
        pass "$desc (array, $(echo "$body" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null) items)"
    else
        fail "$desc" "期望 JSON array, 实际: $(echo "$body" | head -c 80)"
    fi
}

test_json_object() {
    local desc="$1" url="$2" key="${3:-}"
    local body
    body=$(curl -s -b "$COOKIE_JAR" "${BASE}${url}" --max-time 10 2>/dev/null)
    if [ -z "$key" ]; then
        if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, dict)" 2>/dev/null; then
            pass "$desc (object)"
        else
            fail "$desc" "期望 JSON object, 实际: $(echo "$body" | head -c 80)"
        fi
    else
        if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$key' in d" 2>/dev/null; then
            pass "$desc (has '$key')"
        else
            fail "$desc" "缺少字段 '$key', 实际: $(echo "$body" | head -c 80)"
        fi
    fi
}

test_sse() {
    local desc="$1" url="$2" data="$3"
    local body
    body=$(curl -s -b "$COOKIE_JAR" -X POST "${BASE}${url}" \
        -H "Content-Type: application/json" -d "$data" \
        -N --max-time 15 2>/dev/null | head -c 500)
    if echo "$body" | grep -q "event:"; then
        pass "$desc (SSE stream)"
    else
        fail "$desc" "无 SSE 事件, 实际: $(echo "$body" | head -c 80)"
    fi
}

# ══════════════════════════════════════════════════════════════
echo "ServerHub Smoke Test"
echo "Target: ${BASE}"
echo "══════════════════════════════════════════════════════════"

# ── 1. 基础连接 ──
echo ""
echo "▸ 基础连接"
test_json_object "Health check" "/api/health" "status"
test_status "SPA fallback (/)" "/" 200
test_status "Static assets" "/assets/" 404  # 目录不直接可访问是正常的

# ── 2. 认证 ──
echo ""
echo "▸ 认证"

# 登录获取 cookie
LOGIN_RESP=$(curl -s -c "$COOKIE_JAR" -X POST "${BASE}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' --max-time 10 2>/dev/null)

if echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok')==True" 2>/dev/null; then
    pass "Login (admin)"
else
    fail "Login" "$(echo "$LOGIN_RESP" | head -c 80)"
    echo -e "\n${RED}认证失败，后续需要认证的测试将跳过${NC}"
fi

test_json_object "Get current user" "/api/auth/me" "username"
# 无 cookie 测试（用空 cookie jar）
nc_code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/api/auth/me" --max-time 5 2>/dev/null)
if [ "$nc_code" = "401" ]; then pass "未认证返回 401"; else fail "未认证检查" "期望 401, 实际 $nc_code"; fi

# ── 3. 侧边栏 ──
echo ""
echo "▸ 侧边栏"
test_json_array "Sidebar items" "/api/sidebar"

# ── 4. 监控模块 ──
echo ""
echo "▸ 监控"
test_json_object "Top processes" "/api/monitoring/top-processes?server_id=local" "by_cpu"
test_status "Metrics history" "/api/monitoring/history?server_id=local&hours=1&metric=cpu" 200

# ── 5. Docker ──
echo ""
echo "▸ Docker"
test_json_array "Container list" "/api/docker/containers?server_id=local"
test_json_array "Image list" "/api/docker/images?server_id=local"
test_json_array "Stacks" "/api/docker/stacks?server_id=local"

# ── 6. Systemd 服务 ──
echo ""
echo "▸ 服务管理"
test_json_array "Service list" "/api/services/?server_id=local"

# ── 7. 用户管理 ──
echo ""
echo "▸ 用户管理"
test_json_object "User quota status" "/api/users/quota-status?server_id=local"

# ── 8. 服务器管理 ──
echo ""
echo "▸ 服务器"
test_json_array "Server list (with slash)" "/api/servers/"
test_json_array "Server list (no slash)" "/api/servers"

# ── 9. 日志 ──
echo ""
echo "▸ 日志"
test_json_object "Log files" "/api/logs/files?server_id=local" "files"

# ── 10. Cron ──
echo ""
echo "▸ 定时任务"
test_status "Cron list" "/api/cron/?server_id=local" 200

# ── 11. Agent 系统 ──
echo ""
echo "▸ AI 智能体"
test_json_array "Conversations" "/api/agents/conversations"
test_json_object "SubAgents config" "/api/agents/admin/subagents" "subagents"
test_json_array "Patrol list" "/api/agents/patrols"
test_json_array "Approvals" "/api/agents/approvals"
test_sse "Agent chat (SSE)" "/api/agents/chat" '{"message":"ping","conversation_id":"smoke-test"}'

# ── 12. Playbooks ──
echo ""
echo "▸ 运维剧本"
test_json_array "Playbook list (with slash)" "/api/playbooks/"

# ── 13. 网络 ──
echo ""
echo "▸ 网络"
test_json_object "Network ports" "/api/network/ports?server_id=local"

# ── 14. 通知 ──
echo ""
echo "▸ 通知"
test_json_object "Notification channels" "/api/notifications/channels"

# ── 15. 资产 ──
echo ""
echo "▸ 资产"
test_json_array "Assets" "/api/assets/"

# ── 16. SPA 路由不拦截 API ──
echo ""
echo "▸ SPA 路由隔离"
test_status "API 404 不返回 HTML" "/api/nonexistent" 404
# 验证返回的是 JSON 不是 HTML
RESP=$(curl -s "${BASE}/api/nonexistent" --max-time 5 2>/dev/null)
if echo "$RESP" | grep -q "<!doctype"; then
    fail "API 404 格式" "返回了 HTML（SPA catch-all 拦截了 API 路由！）"
else
    pass "API 404 返回 JSON"
fi

# ══════════════════════════════════════════════════════════════
echo ""
echo "══════════════════════════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}全部通过: ${PASS}/${TOTAL}${NC}"
else
    echo -e "${RED}失败: ${FAIL}/${TOTAL}${NC} (通过: ${PASS})"
fi
echo "══════════════════════════════════════════════════════════"

# 清理
rm -f "$COOKIE_JAR"
exit $FAIL

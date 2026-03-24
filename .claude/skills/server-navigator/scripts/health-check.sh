#!/bin/bash
# 服务器健康检查脚本 - 快速生成系统状态摘要
# 用法: bash health-check.sh

echo "=== 系统健康检查 $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

echo "--- 内存 ---"
free -h | head -2
echo ""

echo "--- Swap ---"
swapon --show 2>/dev/null || echo "无 swap"
echo ""

echo "--- 磁盘 ---"
df -h / /mnt/sda /mnt/data3 2>/dev/null
echo ""

echo "--- GPU ---"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "GPU 不可用"
echo ""

echo "--- Docker 容器 ---"
docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | sort
echo ""

echo "--- 失败的服务 ---"
systemctl list-units --type=service --state=failed 2>/dev/null | grep -v "^$" || echo "无失败服务"
echo ""

echo "--- 当前登录用户 ---"
who 2>/dev/null
echo ""

echo "--- 系统负载 ---"
uptime
echo ""

echo "=== 检查完成 ==="

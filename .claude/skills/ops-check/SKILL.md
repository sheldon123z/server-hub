---
name: ops-check
description: 快速检查服务器运维状态 - Docker容器、内存、GPU、磁盘、用户进程，汇总为简洁中文报告并标出异常项
---

# 服务器运维状态检查

依次执行以下检查命令，收集服务器当前状态：

## 数据采集

运行以下命令（全部并行执行）：

1. **Docker 容器状态**
   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null
   ```

2. **内存与 Swap**
   ```bash
   free -h
   ```

3. **GPU 状态**
   ```bash
   nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader 2>/dev/null
   ```
   ```bash
   nvidia-smi --query-compute-apps=pid,used_gpu_memory,name --format=csv,noheader 2>/dev/null
   ```

4. **内存占用 Top 10 进程**
   ```bash
   ps aux --sort=-%mem | head -11
   ```

5. **磁盘使用**
   ```bash
   df -h | grep "^/dev/"
   ```

6. **系统负载**
   ```bash
   uptime
   ```

7. **登录用户**
   ```bash
   who
   ```

8. **非管理员用户资源占用汇总**
   ```bash
   for user in $(awk -F: '$3 >= 1000 {print $1}' /etc/passwd); do mem=$(ps -u "$user" --no-headers -o rss 2>/dev/null | awk '{sum+=$1} END {printf "%.1f", sum/1024/1024}'); procs=$(ps -u "$user" --no-headers 2>/dev/null | wc -l); [ "$(echo "$mem > 0.1" | bc -l 2>/dev/null)" = "1" ] && echo "$user: ${mem}GB, ${procs} procs"; done | sort -t: -k2 -rn
   ```

## 输出格式

将采集结果汇总为**简洁的中文报告**，按以下分类组织：

### 系统概览
- 负载、运行时间、登录用户数

### 内存状态
- 总量/已用/可用，Swap 使用情况
- **异常标记**：内存使用 >80% 或 Swap >60%

### GPU 状态
- 利用率、显存占用、温度
- 当前 GPU 进程及其所属用户
- **异常标记**：显存 >90% 或温度 >80C

### Docker 容器
- 列出所有容器及其状态
- **异常标记**：标记 Restarting、Exited、unhealthy 状态的容器

### 磁盘使用
- 各挂载点使用率
- **异常标记**：使用率 >85%

### 用户资源占用
- 按内存降序列出非管理员用户的资源使用
- 对照 ~/scripts/config/user-quotas.conf 中的配额，**标记超配额用户**

报告应简洁直观，正常项一行带过，异常项突出显示。

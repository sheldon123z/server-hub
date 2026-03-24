# 运维操作手册

> 当需要执行运维操作、排查故障时加载此文件。

## 目录

- [日常检查](#日常检查)
- [服务管理](#服务管理)
- [Docker 管理](#docker-管理)
- [用户管理](#用户管理)
- [网络与代理](#网络与代理)
- [存储管理](#存储管理)
- [GPU 管理](#gpu-管理)
- [故障处理流程](#故障处理流程)
- [变更记录规范](#变更记录规范)

## 日常检查

```bash
# 系统概览
bash ~/scripts/system_info.sh

# 快速健康检查
free -h                          # 内存和 swap
df -h / /mnt/sda /mnt/data3     # 磁盘
nvidia-smi                       # GPU
docker ps --format "table {{.Names}}\t{{.Status}}" | sort  # 容器
systemctl list-units --type=service --state=failed          # 失败服务

# 谁在登录
who
last -n 10
```

## 服务管理

### 通用操作

```bash
# 查看/重启/停止
sudo systemctl status <service>
sudo systemctl restart <service>
sudo systemctl stop <service>

# 查看日志
sudo journalctl -u <service> --since "1 hour ago"
sudo journalctl -u <service> -f    # 实时跟踪
```

### sudo 密码传递

在脚本或管道中传递 sudo 密码：
```bash
sudo -S <<< '密码' command
# 或
echo '密码' | sudo -S command
```

### 常用服务操作

```bash
# Nginx - 测试配置后重载
sudo nginx -t && sudo systemctl reload nginx

# Clash - 更新配置
sudo cp ~/config.yaml /opt/clash/config.yaml
sudo systemctl restart clash

# JupyterLab
sudo systemctl restart jupyterlab
sudo journalctl -u jupyterlab -f

# Ollama
ollama_update                    # 更新到最新版本
ollama list                      # 查看模型
ollama run <model>               # 运行模型
```

## Docker 管理

### 日常操作

```bash
# 容器状态
see_docker                       # 资源统计 (alias)
see_docker2                      # 创建时间 (alias)
docker ps -a                     # 全部容器

# Dify 管理
cd ~/projects/dify/docker
docker compose up -d             # 启动
docker compose down              # 停止
docker compose logs -f <service> # 日志
docker compose restart <service> # 重启单个

# Grid AutoPilot 基础设施
cd ~/exps/grid-autopilot
docker compose up -d
docker compose down
docker compose logs -f

# LobeChat 更新
rm_lobe && pull_lobe && run_lobe
```

### 清理操作

```bash
docker_rmi                       # 清理悬空镜像 (alias)
docker system prune -f           # 清理停止的容器和悬空镜像
docker volume ls -qf dangling=true  # 查看孤立卷
# docker volume prune -f         # 清理孤立卷（慎用，确认无用后再执行）
```

### 容器排查

```bash
# 查看重启原因
docker inspect <container> --format '{{.State.ExitCode}}'
docker logs <container> --tail 100

# 进入容器
docker exec -it <container> sh

# 查看资源使用
docker stats --no-stream
```

## 用户管理

### 学生用户管理

```bash
# 查看学生组成员
getent group students

# 调整资源限制（默认: 80GB 内存, 600 进程, 10h CPU, 6 核心）
sudo bash ~/scripts/adjust-student-limits.sh <内存GB> <进程数> <CPU时间> <核心数>

# 登录监控
sudo bash ~/scripts/login-monitor.sh --status
sudo bash ~/scripts/login-monitor.sh --log
sudo bash ~/scripts/login-monitor.sh --groups students --time 8 --interval 300

# 通知学生
sudo bash ~/scripts/notify-students.sh

# 强制登出用户
sudo pkill -u <username>
```

### 添加新学生用户

```bash
sudo adduser <username>
sudo usermod -aG students <username>
# 资源限制会自动应用（login-time-monitor 监控 students 组）
```

## 网络与代理

### Clash 代理

```bash
# Shell 中开关代理
proxy                            # 设置 HTTP_PROXY/HTTPS_PROXY
unproxy                          # 取消代理

# 测试代理
curl -x http://127.0.0.1:7890 https://www.google.com

# 更新代理配置
# 1. 编辑 ~/config.yaml
# 2. 复制到服务目录
sudo cp ~/config.yaml /opt/clash/config.yaml
# 3. 重启
sudo systemctl restart clash

# Clash Dashboard
# http://127.0.0.1:9090
```

### 百度网盘封禁管理

```bash
# 封禁（三层防御：DNS + iptables + 应用层）
sudo bash ~/block_baidupan.sh

# 解封
sudo bash ~/unblock_baidupan.sh

# 验证
getent hosts pan.baidu.com       # 应返回 0.0.0.0
getent hosts www.baidu.com       # 应返回正常 IP
sudo iptables -L BLOCK_BAIDUPAN -n  # 查看防火墙规则
```

## 存储管理

### 磁盘监控

```bash
df -h / /mnt/sda /mnt/data1 /mnt/data2 /mnt/data3

# 查找大文件
sudo du -sh /home/zhengxiaodong/exps/* | sort -rh | head -20
sudo du -sh /mnt/sda/* | sort -rh | head -20
```

### 存储使用指南

| 数据类型 | 推荐存储位置 |
|---------|-------------|
| 项目代码 | `~/exps/` (系统盘) |
| 大型数据集 | `/mnt/sda/` (16TB) |
| 冷存储/备份 | `/mnt/data1-3/` (3x6TB, 当前空闲) |
| Docker 卷 | 默认在系统盘 |
| 模型文件 | `~/exps/models/` 或 `/mnt/sda/` |

## GPU 管理

```bash
# 查看 GPU 状态
nvidia-smi
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv

# 查看 GPU 进程
nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv

# CUDA 版本
nvcc --version
ls /etc/alternatives/cuda*
```

## 故障处理流程

### Dify Worker 重启循环

```bash
cd ~/projects/dify/docker
# 1. 查看日志定位原因
docker compose logs docker-worker-1 --tail 200
# 2. 检查依赖服务
docker compose ps  # 确认 db, redis 等正常
# 3. 尝试重建
docker compose up -d --force-recreate docker-worker-1
# 4. 如果是内存问题
free -h  # 检查系统内存
```

### Swap 使用率过高

```bash
# 1. 确认 swap 使用
free -h && swapon --show
# 2. 找内存大户
ps aux --sort=-%mem | head -20
# 3. 考虑增加 swap（如果需要）
sudo fallocate -l 16G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2
```

### 容器无法启动

```bash
# 1. 查看退出码和日志
docker inspect <container> --format '{{.State.ExitCode}}'
docker logs <container> --tail 100
# 2. 检查端口冲突
sudo ss -tlnp | grep <port>
# 3. 检查磁盘空间
df -h /
# 4. 检查 Docker 存储
docker system df
```

### 服务无响应

```bash
# 1. 检查服务状态
sudo systemctl status <service>
# 2. 检查端口监听
sudo ss -tlnp | grep <port>
# 3. 检查日志
sudo journalctl -u <service> --since "30 min ago"
# 4. 重启
sudo systemctl restart <service>
```

## 变更记录规范

每次运维操作后，更新 `~/ops-docs/changelog.md`：

```markdown
## YYYY-MM-DD

- **类型**: 变更描述
  - 详细说明（可选）
  - 影响范围（可选）
```

类型标签：
- **初始化** / **安装** — 新增组件
- **配置** — 修改配置
- **升级** — 版本更新
- **修复** — 故障修复
- **安全** — 安全相关
- **清理** — 清理操作
- **文档** — 文档更新

同时根据变更类型更新对应文件：
- 服务变更 → `~/ops-docs/services.md`
- 容器变更 → `~/ops-docs/docker-stacks.md`
- 端口变更 → `~/ops-docs/ports.md`
- 发现/解决问题 → `~/ops-docs/issues.md`

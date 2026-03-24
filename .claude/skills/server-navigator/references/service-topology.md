# 服务拓扑 - 详细参考

> 当处理服务相关问题、网络配置、容器管理时加载此文件。

## 目录

- [Systemd 服务详情](#systemd-服务详情)
- [Docker 容器组详情](#docker-容器组详情)
- [端口完整映射](#端口完整映射)
- [服务依赖拓扑](#服务依赖拓扑)
- [用户管理](#用户管理)

## Systemd 服务详情

### 自定义服务 (在 /etc/systemd/system/)

**clash.service** — Clash 代理网关
```ini
ExecStart=/opt/clash/clash_linux -f /opt/clash/config.yaml
# 混合端口 7890，允许 LAN 连接
# external-controller: 127.0.0.1:9090
```

**jupyterlab.service** — JupyterLab
```ini
User=zhengxiaodong
WorkingDirectory=/home/zhengxiaodong
ExecStart=/.../jupyter-ai/bin/jupyter-lab --ip=0.0.0.0 --port=8888 --no-browser
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
# 依赖 clash 代理运行
```

**ollama.service** — Ollama LLM 推理
```ini
ExecStart=/usr/local/bin/ollama serve
User=ollama, Group=ollama
# 端口 11434
# 更新: curl -fsSL https://ollama.com/install.sh | sh
```

**login-time-monitor.service** — 学生登录时间监控
```ini
ExecStart=/usr/local/bin/monitor-login-time.sh
# 配置文件: /etc/login-monitor/config
# 日志: /var/log/login-monitor.log
# 默认: 10 小时限制, 600 秒检查间隔, students 组
```

**sunny.service** — 内网穿透
```ini
ExecStart=/mnt/sda/system_softwares/sunny/sunny --server=ss5.tunnelfrp.com:4443 --key=225813440442
User=zhengxiaodong
Environment="http_proxy="   # 显式清空代理，不走 Clash
```

### 关键系统服务

| 服务 | 配置路径 | 备注 |
|------|---------|------|
| nginx | `/etc/nginx/` | 站点: academic.bir-nanyang.cn |
| haproxy | `/etc/haproxy/haproxy.cfg` | 默认 HTTP 模式 |
| fail2ban | `/etc/fail2ban/` | SSH 防暴力 |
| webmin | `/etc/webmin/miniserv.conf` | 端口 10000 HTTPS |
| mysql | `/etc/mysql/` | MySQL Community Server |
| smbd | `/etc/samba/smb.conf` | Samba 文件共享 |
| xrdp | `/etc/xrdp/` | 远程桌面 |
| docker | `/etc/docker/daemon.json` | 容器运行时 |

## Docker 容器组详情

### Dify AI 平台

**路径**: `~/projects/dify/docker/docker-compose.yaml`

```
docker-nginx-1        → 8080:80, 8443:443  (Web 网关)
docker-api-1          → 5001 (内部)         (API 服务)
docker-worker-1       → (无端口)            (Celery Worker, ⚠️ 重启循环)
docker-worker_beat-1  → 5001 (内部)         (Celery Beat)
docker-web-1          → 3000 (内部)         (前端)
docker-db_postgres-1  → 5432 (内部)         (PostgreSQL)
docker-weaviate-1     → (内部)              (向量数据库)
docker-sandbox-1      → (内部)              (代码沙箱)
docker-plugin_daemon-1→ 5003               (插件守护进程)
docker-ssrf_proxy-1   → 3128 (内部)         (SSRF 代理)
```

**排查 worker 重启**:
```bash
cd ~/projects/dify/docker
docker compose logs docker-worker-1 --tail 200
docker compose restart docker-worker-1
```

### Grid AutoPilot 基础设施

**路径**: `~/exps/grid-autopilot/docker-compose.yml`

```
grid-autopilot-postgres   → 5432:5432  (PostgreSQL 15, DB: grid_autopilot, User: grid_user)
grid-autopilot-timescale  → 5433:5432  (TimescaleDB, PG15)
grid-autopilot-redis      → 16379:6379 (Redis 7, 需密码)
grid-autopilot-neo4j      → 7474:7474, 7687:7687 (Neo4j 5 Community)
grid-autopilot-milvus     → 19530:19530, 19091:9091 (Milvus v2.3.0)
grid-autopilot-minio      → 9000:9000, 9001:9001 (MinIO)
grid-autopilot-kafka      → 9092:9092 (Confluent Kafka 7.5.0)
grid-autopilot-zookeeper  → 2181:2181 (ZooKeeper)
grid-autopilot-etcd       → (内部) (etcd v3.5.5, Milvus 依赖)
```

**需要环境变量**: `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET_KEY`

### LobeChat

```
lobe-database → 3210:3210 (lobehub/lobe-chat-database)
# Env 文件: ~/scripts/lobe.env
# 管理别名: rm_lobe / pull_lobe / run_lobe
```

## 端口完整映射

### 宿主机直接监听

| 端口 | 服务 | 协议 | 备注 |
|------|------|------|------|
| 22 | SSH | TCP | OpenSSH |
| 80 | Nginx | TCP | HTTP (重定向 HTTPS) |
| 443 | Nginx | TCP | HTTPS |
| 631 | CUPS | TCP | 仅 localhost |
| 3306 | MySQL | TCP | MySQL |
| 7890 | Clash | TCP | HTTP/SOCKS5 混合代理 |
| 8888 | JupyterLab | TCP | 所有接口 |
| 10000 | Webmin | TCP | HTTPS |
| 11434 | Ollama | TCP | LLM API |

### Docker 映射

| 宿主端口 | 容器端口 | 容器 | 服务 |
|---------|---------|------|------|
| 2181 | 2181 | zookeeper | ZooKeeper |
| 3210 | 3210 | lobe-database | LobeChat |
| 5003 | 5003 | plugin_daemon | Dify 插件 |
| 5432 | 5432 | ga-postgres | PostgreSQL |
| 5433 | 5432 | ga-timescale | TimescaleDB |
| 7474 | 7474 | ga-neo4j | Neo4j Browser |
| 7687 | 7687 | ga-neo4j | Neo4j Bolt |
| 8080 | 80 | dify-nginx | Dify HTTP |
| 8443 | 443 | dify-nginx | Dify HTTPS |
| 9000 | 9000 | ga-minio | MinIO API |
| 9001 | 9001 | ga-minio | MinIO Console |
| 9092 | 9092 | ga-kafka | Kafka |
| 16379 | 6379 | ga-redis | Redis |
| 19091 | 9091 | ga-milvus | Milvus 管理 |
| 19530 | 19530 | ga-milvus | Milvus gRPC |

### 端口冲突注意

- **5432**: Grid AutoPilot PostgreSQL 占用了标准端口，Dify PostgreSQL 仅内部可达
- **8080**: 被 Dify Nginx 占用

## 服务依赖拓扑

```
Internet
  │
  ├─ Nginx (80/443) ─── academic.bir-nanyang.cn
  │
  ├─ Clash (7890) ──┬── JupyterLab (8888, 通过代理)
  │                 └── Ollama (11434, 下载模型时)
  │
  ├─ Docker Engine
  │   ├── Dify 容器组 (8080/8443)
  │   │   └── nginx → api/worker/web → postgres/weaviate/sandbox
  │   │
  │   ├── Grid AutoPilot 容器组
  │   │   ├── postgres (5432) + timescale (5433)
  │   │   ├── redis (16379)
  │   │   ├── neo4j (7474/7687)
  │   │   ├── milvus (19530) ← etcd + minio
  │   │   └── kafka (9092) ← zookeeper (2181)
  │   │
  │   └── LobeChat (3210)
  │
  ├─ Sunny (内网穿透) → tunnelfrp.com
  │
  └── login-time-monitor → 监控 students 组
```

## 用户管理

### 用户列表

| 用户 | UID | 角色 | 限制 |
|------|-----|------|------|
| zhengxiaodong | 1000 | 管理员 | 无 |
| wangtao | 1001 | 学生 | 80GB 内存 / 600 进程 / 6 CPU / 10h 登录 |

### 学生资源限制管理

```bash
# 查看当前限制
sudo bash ~/scripts/adjust-student-limits.sh

# 自定义限制
sudo bash ~/scripts/adjust-student-limits.sh <内存GB> <进程数> <CPU时间h> <CPU核心数>
# 默认: 80 600 10 6

# 登录监控
sudo bash ~/scripts/login-monitor.sh --status   # 查看状态
sudo bash ~/scripts/login-monitor.sh --log       # 查看日志
sudo bash ~/scripts/login-monitor.sh --restart   # 重启
```

### 登录监控配置 (`/etc/login-monitor/config`)

```bash
LOGIN_HOURS_LIMIT=10         # 小时
CHECK_INTERVAL=600           # 秒
MONITORED_GROUPS="students"  # 监控的用户组
```

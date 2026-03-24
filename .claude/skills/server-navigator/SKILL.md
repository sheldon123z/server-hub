---
name: server-navigator
description: >
  服务器系统维护导航技能。提供主机 system-NF5468M6 的完整系统地图、目录索引和服务拓扑，
  让智能体在执行任务时能快速定位目录、配置文件、服务和工具。
  触发条件：(1) 任何涉及服务器维护、系统管理的任务，
  (2) 需要查找文件、目录、配置、服务位置时，
  (3) Docker 容器管理、端口查询、用户管理，
  (4) 运维脚本执行、Conda 环境切换，
  (5) 关键词匹配：运维、维护、服务器、容器、端口、服务、目录、配置、部署、监控。
---

# Server Navigator - 系统维护导航

## 渐进式加载策略

根据任务复杂度分层加载信息，减少上下文消耗：

1. **本文件** — 快速索引表，覆盖 80% 的查询需求
2. **[references/directory-map.md](references/directory-map.md)** — 完整目录树和项目说明，当需要深入查找文件时加载
3. **[references/service-topology.md](references/service-topology.md)** — 服务依赖、Docker 详情、端口映射，当处理服务/网络问题时加载
4. **[references/ops-playbook.md](references/ops-playbook.md)** — 运维操作手册和故障处理流程，当执行运维操作时加载

## 快速定位表

### 核心路径

| 要找什么 | 位置 |
|---------|------|
| 运维文档中心 | `~/ops-docs/` |
| 运维脚本 | `~/scripts/` |
| API 密钥 | `~/.api_keys`（敏感，勿读取） |
| 核心研究项目 | `~/exps/grid-autopilot/`（有独立 CLAUDE.md） |
| 前端项目 | `~/exps/grid-autopilot-frontend/` |
| Dify 平台 | `~/projects/dify/docker/` |
| Clash 代理配置 | `~/config.yaml` + `/opt/clash/config.yaml` |
| Conda 环境 | `~/miniconda3/envs/` |
| Nginx 站点 | `/etc/nginx/sites-enabled/` |
| JupyterLab 服务 | systemd: `jupyterlab.service`，conda env: `jupyter-ai` |
| 系统级自定义服务 | `/etc/systemd/system/` (clash, jupyterlab, ollama, login-time-monitor, sunny) |

### 端口速查

| 端口 | 服务 | 端口 | 服务 |
|------|------|------|------|
| 22 | SSH | 8080/8443 | Dify |
| 80/443 | Nginx | 8888 | JupyterLab |
| 3210 | LobeChat | 9000/9001 | MinIO |
| 5432 | Grid PostgreSQL | 9092 | Kafka |
| 5433 | TimescaleDB | 10000 | Webmin (HTTPS) |
| 7474/7687 | Neo4j | 11434 | Ollama |
| 7890 | Clash 代理 | 16379 | Redis |
| 19530 | Milvus | | |

### 别名速查

```
proxy / unproxy          — 开关 HTTP 代理
see_docker / see_docker2 — 查看容器状态
rm_lobe / pull_lobe / run_lobe — 更新 LobeChat
docker_start_all         — 启动所有容器
docker_rmi               — 清理悬空镜像
ollama_update            — 更新 Ollama
claudes                  — Claude Code (skip permissions)
```

### Conda 环境速查

| 环境 | 用途 | 环境 | 用途 |
|------|------|------|------|
| `ele` | 当前默认激活 | `sglang`/`vllm` | LLM 推理 |
| `jupyter-ai` | JupyterLab | `HARL`/`Gym_base` | 强化学习 |
| `ev`/`mev` | 电动汽车实验 | `deepseek-ocr` | OCR |
| `tslib` | 时间序列 | `openhands` | AI agent |

### Docker 容器组

| 组 | Compose 路径 | 管理命令 |
|----|-------------|---------|
| Dify | `~/projects/dify/docker/` | `cd ~/projects/dify/docker && docker compose up -d` |
| Grid AutoPilot | `~/exps/grid-autopilot/` | `cd ~/exps/grid-autopilot && docker compose up -d` |
| LobeChat | 单容器 | `rm_lobe && pull_lobe && run_lobe` |

### 已知问题

查阅 `~/ops-docs/issues.md` 获取最新列表。当前关键问题：
- Dify `docker-worker-1` 重启循环
- Swap 使用率 99% (7.9/8.0GB)

### 运维操作后更新

每次运维变更后，更新 `~/ops-docs/` 下对应文件：
- 服务变更 → `services.md` | 容器变更 → `docker-stacks.md`
- 端口变更 → `ports.md` | 问题 → `issues.md`
- 所有变更 → `changelog.md`

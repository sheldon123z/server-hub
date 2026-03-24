# ServerHub 快速上手

本文档帮助你在 5 分钟内完成 ServerHub 的安装、配置和启动。

---

## 目录

1. [环境要求](#1-环境要求)
2. [安装步骤](#2-安装步骤)
3. [配置说明](#3-配置说明)
4. [启动服务](#4-启动服务)
5. [生产部署](#5-生产部署)
6. [首次使用](#6-首次使用)
7. [常见问题](#7-常见问题)

---

## 1. 环境要求

### 必需

| 要求 | 版本/说明 |
|------|---------|
| Python | **3.11**（必须，deepagents 框架不兼容 3.10） |
| conda | 任意版本（用于创建隔离环境） |
| Linux | 任意发行版（需要 systemd，已在 Ubuntu 23.04 验证） |
| 操作系统权限 | 建议以有 sudo 权限的用户运行 |

### 可选

| 要求 | 说明 |
|------|------|
| NVIDIA GPU | 用于 GPU 监控功能，需安装 `pynvml` |
| Docker | 用于 Docker 容器管理功能 |
| Telegram Bot | 用于告警通知推送 |
| LLM API Key | 用于 AI 智能体功能（支持 8 家服务商，或用本地 Ollama） |

---

## 2. 安装步骤

### 步骤一：克隆仓库

```bash
git clone <repository-url> ~/scripts/server-hub
cd ~/scripts/server-hub
```

### 步骤二：创建 conda 环境

```bash
# 创建 Python 3.11 环境
conda create -n serverhub python=3.11 -y

# 激活环境
conda activate serverhub
```

### 步骤三：安装依赖

```bash
pip install -r requirements.txt
```

如果网络较慢，可以使用国内镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 步骤四：初始化数据目录

```bash
mkdir -p data
```

数据目录 `data/` 已加入 `.gitignore`，数据库文件会在首次启动时自动创建。

---

## 3. 配置说明

### 3.1 环境变量（SERVERHUB_*）

应用配置通过 `SERVERHUB_*` 前缀的环境变量或 `.env` 文件控制：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SERVERHUB_SECRET_KEY` | `change-me-to-a-random-string` | JWT 签名密钥，**生产环境必须修改** |
| `SERVERHUB_ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `SERVERHUB_ADMIN_PASSWORD` | `admin123` | 初始管理员密码，**生产环境必须修改** |
| `SERVERHUB_AGENT_MODEL` | `openrouter:deepseek/deepseek-chat` | AI 对话默认模型 |
| `SERVERHUB_PATROL_MODEL` | `openrouter:deepseek/deepseek-chat` | 巡检任务使用的模型 |

创建 `.env` 文件（推荐方式）：

```bash
cat > .env << 'EOF'
SERVERHUB_SECRET_KEY=your-random-secret-key-here
SERVERHUB_ADMIN_USERNAME=admin
SERVERHUB_ADMIN_PASSWORD=your-secure-password

# AI 模型配置（选择一个服务商即可）
SERVERHUB_AGENT_MODEL=openrouter:deepseek/deepseek-chat
SERVERHUB_PATROL_MODEL=openrouter:deepseek/deepseek-chat
EOF
```

生成安全的随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3.2 LLM API Key 配置

根据你使用的 LLM 服务商，设置对应的环境变量。在 `.env` 文件中追加（或 `export` 到 shell）：

| 服务商 | 模型 ID 前缀 | 环境变量 |
|--------|------------|---------|
| OpenRouter（推荐，支持百余模型） | `openrouter:` | `OPENROUTER_API_KEY` |
| DeepSeek 直连 | `deepseek:` | `DEEPSEEK_API_KEY` |
| OpenAI 直连 | `openai:` | `OPENAI_API_KEY` |
| 火山引擎（豆包） | `volcengine:` | `VOLCENGINE_API_KEY` |
| 智谱 AI | `zhipu:` | `ZHIPU_API_KEY` |
| Kimi（月之暗面） | `moonshot:` | `MOONSHOT_API_KEY` |
| MiniMax | `minimax:` | `MINIMAX_API_KEY` |
| Ollama（本地，免费） | `ollama:` | 无需配置 |

**最简配置**（使用 OpenRouter，一个 Key 接入所有模型）：

```bash
# 添加到 .env
OPENROUTER_API_KEY=sk-or-v1-...
SERVERHUB_AGENT_MODEL=openrouter:deepseek/deepseek-chat
```

**使用本地 Ollama**（零成本，需先安装并下载模型）：

```bash
# 确保 ollama 服务在运行
ollama pull qwen3:8b

# .env 配置
SERVERHUB_AGENT_MODEL=ollama:qwen3:8b
```

### 3.3 Telegram 通知配置（可选）

告警通知通过系统脚本发送，配置在 `~/.telegram_config`：

```bash
cat > ~/.telegram_config << 'EOF'
BOT_TOKEN=your-bot-token
CHAT_ID=your-chat-id
EOF
chmod 600 ~/.telegram_config
```

如果不配置，告警功能仍可用，只是无法推送 Telegram 消息。

### 3.4 服务器特定配置

`config.py` 中有一些与服务器环境相关的硬编码配置，按实际情况修改：

```python
# config.py
settings.quota_file = "/path/to/user-quotas.conf"   # 用户配额文件
settings.admin_linux_users = {"your_admin_user"}     # Linux 管理员用户名（监控时跳过）
settings.managed_services = ["nginx", "docker", ...] # 需要管理的 systemd 服务
settings.compose_stacks = {                          # Docker compose 堆栈
    "myapp": {
        "path": "/path/to/compose/dir",
        "display_name": "My App",
    }
}
```

---

## 4. 启动服务

### 开发模式（推荐调试时使用）

```bash
conda activate serverhub

# 方式一：直接启动（自动重载）
python main.py

# 方式二：uvicorn 启动（等效）
uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1
```

**注意**：`--workers 1` 是强制要求，SQLite 不支持多进程写入，且 Agent checkpoint 需要单进程内存一致性。

启动成功后，终端会显示：

```
[ServerHub] 已加载 15 个模块
[ServerHub] 指标采集已启动
[ServerHub] AI 巡检调度器已启动
INFO:     Uvicorn running on http://0.0.0.0:9900 (Press CTRL+C to quit)
```

访问 `http://localhost:9900` 进入登录页面。

---

## 5. 生产部署

### 使用 systemd 管理服务

项目提供了 `server-hub.service` systemd 服务文件，适合生产环境使用。

**步骤一：检查服务文件路径**

打开 `server-hub.service`，确认以下路径与实际一致：

```ini
[Service]
User=zhengxiaodong              # 修改为实际用户
WorkingDirectory=/home/zhengxiaodong/scripts/server-hub   # 项目路径
ExecStart=/home/zhengxiaodong/miniconda3/envs/serverhub/bin/python main.py
```

**步骤二：安装服务**

```bash
sudo cp server-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now server-hub
```

**步骤三：验证运行状态**

```bash
sudo systemctl status server-hub

# 查看日志
journalctl -u server-hub -f
```

### Nginx 反向代理（可选）

如果需要通过域名访问或启用 HTTPS，可以配置 Nginx 反向代理：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example.com;

    # SSL 证书配置（省略）

    location / {
        proxy_pass http://127.0.0.1:9900;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";   # WebSocket 支持（终端）
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;  # SSE 长连接需要较长超时
    }
}
```

**重要**：SSE 对话流和 WebSocket 终端都需要长连接，`proxy_read_timeout` 建议设置为 3600 秒。

### 常用管理命令

```bash
# 启动
sudo systemctl start server-hub

# 停止
sudo systemctl stop server-hub

# 重启（代码更新后）
sudo systemctl restart server-hub

# 查看实时日志
journalctl -u server-hub -f --since "5 min ago"

# 查看状态
sudo systemctl status server-hub
```

---

## 6. 首次使用

### 默认账户

首次启动时，系统自动创建管理员账户：

| 字段 | 默认值 |
|------|--------|
| 用户名 | `admin`（或 `SERVERHUB_ADMIN_USERNAME` 的值） |
| 密码 | `admin123`（或 `SERVERHUB_ADMIN_PASSWORD` 的值） |

**请立即修改默认密码**：进入「面板用户」模块 → 点击管理员账户 → 修改密码。

### 基本使用流程

1. **访问系统**：打开浏览器访问 `http://服务器IP:9900`

2. **登录**：使用管理员账号登录

3. **仪表盘**：首页展示服务器实时状态（CPU/内存/GPU/磁盘）

4. **配置 AI 模型**：
   - 进入「AI 智能体」页面
   - 点击顶部设置图标
   - 选择服务商和模型
   - 确保已在 `.env` 中配置对应的 API Key

5. **体验 AI 对话**：
   - 在聊天框输入 `你好，请介绍一下当前服务器状态`
   - Agent 会自动调用工具获取系统信息并回复

6. **配置巡检任务**：
   - 在 AI 智能体页面切换到「巡检」标签
   - 查看 8 个内置巡检任务的状态和历史记录
   - 点击任务右侧「立即运行」可手动触发

7. **创建普通用户**：
   - 进入「面板用户」模块
   - 点击「新增用户」，角色选择 `user`
   - 普通用户只能查看仪表盘和监控，不能执行管理操作

### 快捷指令

在 AI 对话框中输入 `/` 可调出 10 个内置快捷指令：

| 指令 | 功能 |
|------|------|
| `/status` | 查看系统状态概览 |
| `/docker` | 列出所有 Docker 容器 |
| `/services` | 检查 systemd 服务状态 |
| `/memory` | 查看内存使用情况 |
| `/gpu` | 查看 GPU 状态 |
| `/disk` | 查看磁盘使用情况 |
| `/users` | 查看用户资源使用 |
| `/logs` | 最近系统日志 |
| `/patrol` | 立即执行综合巡检 |
| `/report` | 生成系统报告 |

---

## 7. 常见问题

### Q: 启动报错 "deepagents 不兼容"

确保使用 Python 3.11：

```bash
conda activate serverhub
python --version   # 应显示 Python 3.11.x
```

### Q: AI 对话提示 "模型调用失败"

检查 API Key 是否正确配置：

```bash
# 检查环境变量
echo $OPENROUTER_API_KEY

# 或查看 .env 文件是否存在
cat .env | grep API_KEY
```

在 AI 页面设置中可以看到哪些服务商已配置（绿色）、哪些未配置（灰色）。

### Q: WebTerminal 连接失败

WebTerminal 使用 WebSocket，确保：
1. 若使用 Nginx 代理，已配置 `Upgrade` 和 `Connection` 头（见上方 Nginx 配置）
2. 浏览器支持 WebSocket（现代浏览器均支持）

### Q: 巡检任务不执行

检查 AI 巡检调度器是否正常启动：

```bash
journalctl -u server-hub | grep "巡检调度器"
# 应看到：[ServerHub] AI 巡检调度器已启动
```

也可在 AI 页面的「巡检」标签中手动点击「立即运行」测试。

### Q: 如何重置管理员密码

如果忘记密码，可以修改 `.env` 中的 `SERVERHUB_ADMIN_PASSWORD` 后重启服务，系统会重新创建管理员账户（已存在则更新密码）。

### Q: 数据如何备份

备份 `data/` 目录下的所有 `.db` 文件即可：

```bash
cp -r data/ /backup/server-hub-$(date +%Y%m%d)/
```

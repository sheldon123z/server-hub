# ServerHub 开发环境指南

## 最小运行环境

### 后端

```bash
conda activate serverhub  # Python 3.11 (必须，deepagents 不兼容 3.10)
pip install -r requirements.txt
python main.py
# 服务默认监听 http://0.0.0.0:9900
```

### 前端

```bash
cd frontend
npm install
npm run dev    # Vite dev server at http://localhost:5173
npm run build  # 构建生产产物到 frontend/dist/
```

开发模式需设置 `SERVERHUB_DEV=1` 环境变量以启用 CORS。

### 测试

```bash
pytest tests/ -v
```

> **注意**: 完整测试需要 `deepagents` 包。若未安装，agent 相关测试会跳过，
> 但其余模块（auth、monitoring、users 等）仍可正常测试。

### 生产部署

```bash
sudo cp server-hub.service /etc/systemd/system/
sudo systemctl enable --now server-hub
```

**workers 必须为 1** — SQLite 不支持多进程写入。

### 健康检查

服务启动后可访问 `GET /api/health` (无需认证) 查看各子系统状态：

```bash
curl http://localhost:9900/api/health
```

详细文档见 [docs/getting-started.md](docs/getting-started.md)。

# 目录地图 - 完整索引

> 当需要深入查找特定文件、项目或数据目录时加载此文件。

## 家目录 (`/home/zhengxiaodong/`) 总览

### 核心工作区

```
~/exps/                          # 实验和项目代码（主要工作区）
├── grid-autopilot/              # ★ 核心项目：电网自主巡航系统后端
│   ├── CLAUDE.md                # 项目专属指导（23 微服务架构详情）
│   ├── docker-compose.yml       # 基础设施容器组
│   ├── services/                # 微服务代码
│   │   ├── gmcp/               # 电网多模态认知 (8 服务, 8001-8008)
│   │   ├── isdp/               # 智能调度决策 (8 服务, 8101-8112)
│   │   └── fcds/               # 故障协同处置 (6 服务, 8201-8204,8113-8114)
│   ├── shared/                  # 共享代码 (models/utils/proto/schemas)
│   ├── infrastructure/          # K8s/Docker/Helm 配置
│   ├── configs/                 # 配置文件
│   ├── tests/                   # 测试代码
│   └── Makefile                 # make dev/test/lint/docker-build
├── grid-autopilot-frontend/     # ★ 核心项目前端 (React 18 + TS + Vite)
├── PowerZoo/                    # 电力系统数据集/模型库
├── PowerZoo_CodeStandards/      # PowerZoo 代码规范
├── Rural-Low-Voltage-Detection/ # 农村低压检测
├── Rural-Voltage-Thesis/        # 农村电压论文
├── SHOM/                        # SHOM 项目
├── MARL_LFC/                    # 多智能体强化学习负荷频率控制
├── MARLlib/                     # MARL 库
├── Time-Series-Library/         # 时间序列库
├── Traffic-Prediction-Control/  # 交通预测控制
├── Multi-EVCS/                  # 多电动汽车充电站
├── RL_based_EVCS/               # 基于 RL 的 EVCS
├── aicustom_service_system/     # AI 客服系统
├── SuperClaude/                 # SuperClaude 框架
├── openclaw/                    # OpenClaw
├── OpenHands-CLI/               # OpenHands CLI
├── OpenHandsDev/                # OpenHands 开发
├── DeepSeek-OCR/                # DeepSeek OCR
├── DeepVVC-agent/               # DeepVVC Agent
├── LMC/                         # LMC 项目
├── promptpex/                   # Prompt 测试
├── next-ai-draw-io/             # AI Draw.io
├── gen_pandapower_pv/           # PandaPower PV 生成
├── serena/                      # Serena 代码助手
├── mcp_servers/                 # MCP 服务器
├── llama.cpp/                   # 本地 LLM 推理编译
├── claude-config/               # Claude 配置
├── 1_MTS/                       # 多时间序列实验
├── 2_LLM/                       # LLM 实验
├── 3_RL/                        # 强化学习实验
├── 4_Power_grid/                # 电网实验
├── 5_Notebooks/                 # Jupyter Notebooks
├── 6_Paper_Result/              # 论文结果
├── models/                      # 模型文件
├── papers/                      # 论文 PDF
├── Power_Datasets/              # 电力数据集
├── node_systems/                # Node.js 系统
└── skills/                      # 技能文件
```

### 第三方项目和工具

```
~/projects/                      # 第三方项目
├── dify/                        # ★ Dify AI 平台
│   └── docker/                  # Docker Compose 部署
│       └── docker-compose.yaml
├── LLaMA-Factory/               # LLM 微调工具
├── llama.cpp/                   # LLM 推理 (另一份)
├── gpt_academic/                # GPT 学术优化
├── memos/                       # 备忘录
├── deer-flow/                   # DeerFlow
├── prompt-optimizer/            # Prompt 优化器
├── PaperAssistant/              # 论文助手
├── opendatalab/                 # 开放数据实验室
├── SummaryMaster/               # 摘要大师
├── ollama/                      # Ollama 源码
├── trilium/                     # Trilium 笔记
├── openui/                      # Open UI
├── langchain/                   # LangChain
├── extensions/                  # 浏览器扩展
├── pdfs/                        # PDF 文件
├── stable_diffusion_ui/         # Stable Diffusion UI
└── yolo/                        # YOLO 目标检测
```

### 运维和系统管理

```
~/scripts/                       # 运维脚本
├── login-monitor.sh             # 登录时间监控（含 systemd 安装功能）
├── login-monitor.md             # 监控脚本使用说明
├── adjust-student-limits.sh     # 学生资源限制（内存/进程/CPU）
├── idle_user_monitor.sh         # 空闲用户监控
├── notify-students.sh           # 通知学生
├── auto-notify-logout.sh        # 自动通知并登出
├── maintenance_guid.sh          # 所有脚本使用指南
├── system_info.sh               # 系统信息查看
├── auto_update_lobe.sh          # LobeChat 自动更新
├── setup-repos.sh               # 仓库初始化
├── update_vpn.sh                # VPN 更新
├── print_alias_info.sh          # 别名信息
├── lobe.env                     # LobeChat 环境变量
├── .env_keys                    # 额外环境变量
├── dify_default.conf            # Dify Nginx 配置参考
└── config.yaml / KyCloud.yaml   # 旧配置文件

~/ops-docs/                      # 运维文档中心（动态维护）
├── README.md                    # 文档索引
├── services.md                  # 系统服务状态
├── docker-stacks.md             # Docker 容器组详情
├── ports.md                     # 端口映射表
├── cron-jobs.md                 # 定时任务
├── issues.md                    # 已知问题
└── changelog.md                 # 变更日志
```

### 数据存储

```
~/data/                          # 电力市场交易数据
├── 年度交易数据/ (.csv/.zip)
├── 月度交易数据/
├── 月内交易数据/
├── 发电种类/
├── EV/
├── market.csv / market_mapped.csv
└── *.ipynb (数据处理笔记本)

~/data_grid2op/                  # Grid2Op 电网仿真数据
~/huggingface/                   # HuggingFace 缓存
~/articles/                      # 文章
~/files/                         # 杂项文件
~/shared/                        # 共享文件
```

### 配置和环境

```
~/.bashrc                        # Shell 配置（别名、PATH、API keys source）
~/.api_keys                      # API 密钥（敏感，由 .bashrc source）
~/.gitconfig                     # Git 配置
~/config.yaml                    # Clash 代理主配置
~/nginx.conf                     # Nginx 配置参考（实际在 /etc/nginx/）
~/miniconda3/                    # Conda 安装目录
│   └── envs/                    # 所有 conda 环境
~/.nvm/                          # Node.js 版本管理
~/.cargo/                        # Rust 工具链
~/.claude/                       # Claude Code 配置和技能
~/dockerfiles/                   # Dockerfile 模板
│   ├── dockerfile_harl
│   ├── dockerfile_pytorch
│   └── linux_pytorch
```

## 系统级关键目录

```
/etc/systemd/system/             # 自定义 systemd 服务
├── clash.service                # Clash 代理
├── jupyterlab.service           # JupyterLab
├── ollama.service               # Ollama LLM
├── login-time-monitor.service   # 登录监控
└── sunny.service                # 内网穿透

/etc/nginx/                      # Nginx 配置
├── nginx.conf
├── sites-enabled/
│   ├── default
│   └── academic.bir-nanyang.cn.conf
└── ssl/                         # SSL 证书

/etc/login-monitor/config        # 登录监控配置
/etc/haproxy/haproxy.cfg         # HAProxy 配置
/etc/fail2ban/                   # Fail2Ban 配置
/etc/mysql/                      # MySQL 配置
/etc/samba/smb.conf              # Samba 共享
/opt/clash/                      # Clash 二进制和配置
/usr/local/bin/monitor-login-time.sh  # 监控脚本部署位置

/mnt/sda/                        # 16.4TB 大容量存储 (75% 已用)
├── system_softwares/
│   └── sunny/sunny              # Sunny 内网穿透二进制
└── ...

/mnt/data1/                      # 6TB 数据盘 1（空闲）
/mnt/data2/                      # 6TB 数据盘 2（空闲）
/mnt/data3/                      # 6.2TB 数据盘 3（~/data3 软链接）
```

## 快速搜索提示

```bash
# 在 exps 目录下找项目
ls ~/exps/ | grep -i <关键词>

# 找 conda 环境
conda env list | grep <名称>

# 找 Docker 容器
docker ps --format "{{.Names}}" | grep <关键词>

# 找配置文件
find /etc/systemd/system -name "*.service" -exec grep -l <关键词> {} \;

# 找运维脚本
ls ~/scripts/*.sh
```

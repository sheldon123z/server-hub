# 巡检系统

巡检系统定义在 `modules/agents/patrol.py`，由 8 个内置任务、11 个巡检模板和 asyncio 调度器组成。

---

## 调度机制

### 工作原理

```
start_patrol_scheduler()
    │
    ├── seed_default_patrols()    # 初始化默认任务、模板、告警规则
    │
    └── asyncio.create_task(_patrol_loop())
              │
              │  每 60s 循环一次
              ▼
        查询所有 enabled=1 的任务
        对每个任务判断是否到期（now - last_run >= interval）
        asyncio.create_task(execute_patrol(task))   # 并发执行，互不阻塞
```

### 防重复机制

`_running_patrols: set[str]` 集合记录正在运行的任务 ID。同一任务的下一次调度触发时，若上次未完成则跳过（记录 `skipped` 状态）。

### 巡检执行流程

```
execute_patrol(task)
    │
    ├── build_agent(safety_mode="autonomous", purpose="patrol")
    │       # 使用 autonomous 模式（无需人工审批）
    │       # purpose="patrol" 使用 patrol 模型 + 100 次调用限制
    │
    ├── agent.ainvoke(PATROL_PROMPT.format(task_name, task_description))
    │
    ├── parse_patrol_report(report)    # 提取结构化 JSON
    │
    ├── 保存结果到 agent_patrol_tasks（last_run, last_status, last_report）
    ├── 保存历史到 agent_patrol_history（含 report_json, duration_seconds）
    │
    ├── 如果 status in (warning, critical)  → 发送 Telegram 通知
    │
    ├── 如果 report_json 有效  → evaluate_rules(extract_metrics_from_report(report_json))
    │       # 触发告警规则引擎
    │
    └── 如果 status == "critical"  → asyncio.create_task(trigger_diagnosis(...))
            # 自动触发故障诊断（异步，不阻塞巡检流程）
```

---

## 默认巡检任务（8 个）

| ID | 显示名 | 间隔 | 使用工具 | 说明 |
|----|--------|------|---------|------|
| memory_check | 内存巡检 | 30 分钟 | get_system_overview, get_user_resources, get_user_quotas | 系统内存使用率（>85% 告警）+ 用户超配额检查 |
| docker_health | Docker 容器健康 | 15 分钟 | list_docker_containers | 检查 restarting/exited 状态的容器 |
| gpu_monitor | GPU 监控 | 60 分钟 | get_system_overview | GPU 温度（>80°C 警告 / >85°C 紧急）+ 显存（>95% 告警）|
| service_status | 服务状态巡检 | 30 分钟 | list_systemd_services | 所有 systemd 服务是否正常 |
| disk_usage | 磁盘空间巡检 | 360 分钟 | get_system_overview, get_disk_info | 所有挂载点（>90% 告警）|
| daily_report | 每日综合报告 | 1440 分钟 | get_system_overview, get_disk_info, get_user_resources, list_docker_containers, list_systemd_services | 全面状态报告 + send_notification |
| security_compliance | 安全合规检查 | 1440 分钟 | check_compliance | CIS 基线全量检查 |
| resource_trend | 资源趋势周报 | 10080 分钟 | analyze_resource_trend, get_system_overview | 过去一周资源趋势 + 预测 |

---

## 巡检模板（11 个）

模板支持参数化，用 `{variable}` 占位符，用户填写变量值后创建实际任务。

| ID | 名称 | 分类 | 变量 |
|----|------|------|------|
| tpl_memory | 内存巡检 | performance | warning_threshold（默认 85）|
| tpl_docker | Docker 容器健康 | availability | 无 |
| tpl_gpu | GPU 监控 | performance | temp_warning(80), temp_critical(85), mem_threshold(95) |
| tpl_service | 服务状态巡检 | availability | 无 |
| tpl_disk | 磁盘空间巡检 | performance | threshold（默认 90）|
| tpl_daily_report | 每日综合报告 | general | 无 |
| tpl_security_compliance | 安全合规检查 | security | 无 |
| tpl_user_audit | 用户资源审计 | security | 无 |
| tpl_docker_deep | Docker 深度检查 | availability | 无 |
| tpl_network_security | 网络安全检查 | security | 无 |
| tpl_resource_trend | 资源趋势分析 | performance | hours（默认 168）|

### 模板分类

| 分类 | 含义 |
|------|------|
| performance | 性能相关（CPU、内存、GPU、磁盘、趋势）|
| availability | 可用性相关（Docker、服务）|
| security | 安全相关（合规、用户、网络）|
| general | 综合类 |

### 从模板创建任务的流程

1. 前端调用 `GET /api/agents/patrol-templates` 获取模板列表
2. 用户选择模板，填写变量值
3. 前端调用 `POST /api/agents/patrol-templates/{id}/instantiate`，传入变量值
4. 后端替换 `{variable}` 占位符，生成实际 prompt
5. 新任务插入 `agent_patrol_tasks` 表

---

## 巡检报告格式

每次巡检结束后，报告分两部分：

### Markdown 可读部分

```markdown
## {task_name}
**状态**: 正常 / 告警 / 严重

### 检查结果
- 各项检查结果

### 异常项
- 发现的问题（无则写"无异常"）

### 建议
- 修复建议
```

### 结构化 JSON 部分（在报告末尾，用 ```json 包裹）

```json
{
  "summary": "一句话概括巡检结果",
  "status": "ok | warning | critical",
  "check_items": [
    {
      "name": "检查项名称",
      "status": "pass | warn | fail",
      "severity": "info | low | medium | high | critical",
      "current_value": "当前值",
      "threshold": "阈值",
      "detail": "详细描述",
      "recommendation": "修复建议（无则留空）"
    }
  ],
  "metrics_snapshot": {
    "memory_percent": 78.5,
    "gpu_temperature": 72
  }
}
```

### 状态判定

`parse_patrol_report()` 解析 JSON 中的 `status` 字段：

| status | 含义 | 后续动作 |
|--------|------|---------|
| ok | 一切正常 | 仅记录 |
| warning | 存在需要关注的问题 | 发送 Telegram + 触发告警规则引擎 |
| critical | 严重问题，需要立即处理 | 发送 Telegram + 触发告警规则引擎 + 自动启动故障诊断 |

JSON 解析失败时，`determine_status_from_text()` 用关键词匹配降级处理（搜索 "正常" / "告警" / "严重" 等词）。

---

## metrics_snapshot 与告警规则引擎

巡检报告的 `metrics_snapshot` 字段是扁平化的指标键值对，由 `extract_metrics_from_report()` 提取后传入 `evaluate_rules()`。

支持的 metrics_snapshot 键与告警规则的 metric 字段对应：

| metrics_snapshot 键 | 告警规则 metric | 单位 |
|---------------------|----------------|------|
| memory_percent | memory_percent | % |
| swap_percent | swap_percent | % |
| disk_root_percent | disk_root_percent | % |
| gpu_temperature | gpu_temperature | °C |
| gpu_memory_percent | gpu_memory_percent | % |
| cpu_percent | cpu_percent | % |
| load_1m | load_1m | 数值 |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/agents/patrols | 获取所有巡检任务列表 |
| PUT | /api/agents/patrols/{id} | 更新任务配置（prompt/interval/enabled）|
| POST | /api/agents/patrols/{id}/run | 立即执行一次巡检 |
| GET | /api/agents/patrols/{id}/history | 获取巡检历史（最近 20 条）|
| GET | /api/agents/patrol-templates | 获取所有模板 |
| POST | /api/agents/patrol-templates/{id}/instantiate | 从模板创建任务 |

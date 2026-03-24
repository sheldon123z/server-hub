# 故障诊断

故障诊断模块定义在 `modules/agents/diagnosis.py`，当巡检结果为 `critical` 时自动触发，执行根因分析并生成结构化诊断报告。

---

## 触发条件

巡检执行流程（`execute_patrol`）中，当巡检结果 `status == "critical"` 时：

```python
if status == "critical":
    asyncio.create_task(trigger_diagnosis(
        source=f"patrol:{task_id}",
        severity="critical",
        alert_context=f"巡检任务 [{display_name}] 发现严重问题:\n{context}",
    ))
```

使用 `asyncio.create_task()` 异步启动，不阻塞当前巡检流程的返回。

---

## 诊断工作流

```
trigger_diagnosis(source, severity, alert_context)
    │
    ├── 生成唯一报告 ID（uuid4）
    │
    ├── build_agent(safety_mode="autonomous", purpose="patrol")
    │       # 使用 autonomous 模式（自动执行，无需人工审批）
    │
    ├── 构建 DIAGNOSIS_PROMPT（含告警信息）
    │
    ├── agent.ainvoke(prompt)
    │       诊断 Agent 执行步骤：
    │       1. 调用工具收集当前系统状态（get_system_overview 等）
    │       2. task(subagent_type="log-analyzer") 分析相关服务日志
    │       3. 分析证据，确定根因
    │       4. 输出结构化 JSON 报告（用 ```json 包裹）
    │
    ├── _parse_diagnosis_report(report_text)
    │       提取最后一个包含 "root_cause" 的 JSON 块
    │
    ├── 保存到 fault_reports 表
    │       若 JSON 解析成功 → 存结构化字段
    │       若 JSON 解析失败 → 存原始文本（root_cause 字段）
    │
    ├── 自动录入 fault_cases 案例库（若有有效 root_cause）
    │       从 source + alert_context 推断分类
    │       同步更新 FTS5 索引
    │
    └── 发送 Telegram 摘要通知
```

---

## 诊断提示词（DIAGNOSIS_PROMPT）

```
你是 ServerHub 故障诊断专家。系统检测到以下严重告警，请进行根因分析。

## 告警信息
- 来源: {source}
- 严重级别: {severity}
- 告警内容: {alert_context}

## 诊断步骤
1. 首先调用相关工具收集当前系统状态
2. 使用 task() 委派 log-analyzer 分析相关服务日志
3. 根据收集到的证据，分析根本原因
4. 给出紧急处置建议和长期修复方案

## 输出格式
在分析完成后，输出如下 JSON（用 ```json 包裹）：
{
  "affected_components": ["受影响的组件列表"],
  "symptoms": ["观察到的症状列表"],
  "root_cause": "根本原因分析",
  "evidence": ["支持根因判断的证据，如日志片段"],
  "immediate_actions": ["紧急处置步骤"],
  "long_term_solutions": ["长期修复方案"]
}
```

---

## 结构化报告格式

诊断完成后，`fault_reports` 表存储以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 唯一报告 ID（uuid4）|
| detected_at | TIMESTAMP | 诊断时间 |
| source | TEXT | 来源（如 `patrol:memory_check`）|
| severity | TEXT | 严重级别（critical / warning）|
| affected_components | TEXT | JSON 数组：受影响组件列表 |
| symptoms | TEXT | JSON 数组：观察到的症状 |
| root_cause | TEXT | 根本原因分析（核心字段）|
| evidence | TEXT | JSON 数组：证据列表（日志片段等）|
| immediate_actions | TEXT | JSON 数组：紧急处置步骤 |
| long_term_solutions | TEXT | JSON 数组：长期修复方案 |
| similar_cases | TEXT | 相似案例（预留字段）|
| status | TEXT | open / resolved |
| resolved_at | TIMESTAMP | 解决时间 |

---

## 自动录入案例库

诊断完成后，若 `parsed["root_cause"]` 非空，自动将诊断结果录入 `fault_cases` 案例库：

### 分类推断规则

从 `source + alert_context` 的关键词推断分类：

| 分类 | 关键词 |
|------|-------|
| memory | 内存, memory, swap |
| docker | docker, 容器, container |
| gpu | gpu, 显存, 温度 |
| service | 服务, service, systemd |
| network | 网络, 端口, port, firewall |
| security | 安全, ssh, 权限 |
| general | 默认（无匹配关键词）|

### 案例字段映射

| fault_cases 字段 | 来源 |
|-----------------|------|
| title | `[自动] {root_cause前60字符}` |
| category | 推断分类 |
| symptoms | `"; ".join(symptoms)` |
| root_cause | `root_cause` |
| solution | `immediate_actions + long_term_solutions` 拼接 |
| tags | `"{severity},{category}"` |
| source | `"auto"` |
| source_id | 诊断报告 ID |

同步更新 FTS5 虚拟表 `fault_cases_fts`，支持全文搜索。

---

## 故障诊断 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/agents/fault-reports | 获取故障报告列表 |
| GET | /api/agents/fault-reports/{id} | 获取单个报告详情 |
| PUT | /api/agents/fault-reports/{id}/resolve | 标记为已解决 |

---

## 使用注意事项

1. **诊断耗时**：诊断 Agent 需要调用多个工具（含日志分析委派），单次诊断可能耗时 1-3 分钟
2. **资源占用**：诊断 Agent 独立运行，会消耗 LLM API 调用配额（patrol 模型，最多 100 轮）
3. **不触发审批**：使用 `autonomous` 模式，不会中断等待审批
4. **重复诊断**：同一巡检任务在短时间内多次触发 critical 时，可能产生多个诊断报告
5. **Telegram 通知**：诊断完成后自动发送包含根因和处置建议的摘要

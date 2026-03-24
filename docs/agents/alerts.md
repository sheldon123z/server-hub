# 告警系统

告警系统定义在 `modules/agents/alert_engine.py`，分两类：阈值告警和基线偏离告警。

---

## 阈值告警（7 条默认规则）

每次巡检结束后，从结构化报告的 `metrics_snapshot` 提取指标，与规则表中的阈值对比。

| 规则 ID | 名称 | 指标 | warning 阈值 | critical 阈值 | 冷却时间 |
|---------|------|------|-------------|--------------|---------|
| mem_high | 系统内存使用率过高 | memory_percent | > 85% | > 95% | 60 分钟 |
| swap_high | Swap 使用率过高 | swap_percent | > 60% | > 85% | 60 分钟 |
| disk_root_high | 系统盘使用率过高 | disk_root_percent | > 85% | > 95% | 360 分钟 |
| gpu_temp_high | GPU 温度过高 | gpu_temperature | > 80°C | > 85°C | 30 分钟 |
| gpu_mem_high | GPU 显存使用率过高 | gpu_memory_percent | > 90% | > 98% | 60 分钟 |
| cpu_high | CPU 使用率持续过高 | cpu_percent | > 90% | > 98% | 30 分钟 |
| load_high | 系统负载过高 | load_1m | > 120 | > 150 | 30 分钟 |

### 评估逻辑

```python
# evaluate_rules(metrics) 的核心逻辑
for rule in enabled_rules:
    value = metrics.get(rule["metric"])
    if value is None:
        continue
    # 先判断 critical（高优先），再判断 warning
    if value > rule["critical_threshold"]:
        severity = "critical"
    elif value > rule["warning_threshold"]:
        severity = "warning"
    else:
        continue
    # 检查冷却期
    if await _should_alert(rule["id"], rule["cooldown_minutes"]):
        await fire_alert(rule, severity, value)
```

### 支持的比较运算符

| 运算符 | 含义 |
|--------|------|
| `>` | 大于（默认）|
| `>=` | 大于等于 |
| `<` | 小于 |
| `<=` | 小于等于 |
| `==` | 等于 |

---

## 基线偏离告警（3 条默认规则）

基于 7 天历史数据建立统计基线（均值 μ、标准差 σ），当当前值偏离 μ±3σ 且连续 3 次出现时触发。

| 规则 ID | 名称 | 指标 | 窗口 | 倍数 | 冷却时间 |
|---------|------|------|------|------|---------|
| baseline_cpu | CPU 使用率偏离基线 | cpu_percent | 168 小时 | 3.0 σ | 120 分钟 |
| baseline_memory | 内存使用率偏离基线 | memory_percent | 168 小时 | 3.0 σ | 120 分钟 |
| baseline_gpu | GPU 利用率偏离基线 | gpu_util | 168 小时 | 3.0 σ | 120 分钟 |

### 基线计算

```python
# 计算 μ 和 σ（需要至少 50 个历史数据点）
values = [从 metrics 表查询最近 window_hours 小时的数据]
mean = sum(values) / len(values)
stddev = sqrt(sum((v - mean)^2 for v in values) / len(values))

# 偏离判定
upper = mean + multiplier * stddev
lower = mean - multiplier * stddev
is_deviation = current > upper or current < lower
```

**缓存机制**：基线每小时重新计算一次（`_CACHE_TTL_SECONDS = 3600`），减少数据库查询压力。

**数据量要求**：历史数据点少于 50 条时，不执行基线检测（返回 None）。

**标准差过小保护**：当 `stddev < 0.1` 时跳过检测（指标几乎恒定，无偏离意义）。

### 连续偏离计数

```python
# _deviation_counts: dict[str, int]  全局计数器
if is_deviation:
    _deviation_counts[metric] += 1
else:
    _deviation_counts[metric] = 0  # 重置

if _deviation_counts[metric] >= 3:  # 连续 3 次才告警
    if await _should_alert(rule_id, cooldown):
        await fire_alert(...)
    _deviation_counts[metric] = 0  # 告警后重置
```

### 调用时机

`check_baseline_deviation(snapshot)` 由 `scheduler.py` 中的指标采集循环（每 60s 一次）调用，传入实时采集的系统快照（`collect_all()` 的返回值）。

---

## Cooldown 去重机制

防止相同告警在短时间内重复触发，避免告警风暴。

### 实现原理

```sql
-- 查询冷却期内是否已有记录
SELECT COUNT(*) FROM alert_history
WHERE rule_id = ? AND created_at > datetime('now', '-{cooldown_minutes} minutes')
```

使用数据库侧的 `datetime('now', '-N minutes')` 进行 UTC 时间比较，避免应用层时区不一致问题。

### 执行顺序

`fire_alert()` 的执行顺序是先写数据库再发通知，确保即使通知发送失败，下次评估时也能查到该条记录，防止告警重复触发：

```python
async def fire_alert(rule, severity, value):
    # 1. 先写数据库（确保 cooldown 查询能命中）
    await db.execute("INSERT INTO alert_history ...")
    await db.commit()

    # 2. 再发通知（失败不影响 cooldown）
    await send_telegram(f"告警: {rule['name']} ...")
    await db.execute("UPDATE alert_history SET notified = 1 ...")
```

---

## 告警触发流程

```
巡检结束
    │
    ▼
parse_patrol_report(report) → report_json
    │
    ▼
extract_metrics_from_report(report_json)
    → flat_metrics = {"memory_percent": 92.3, "gpu_temperature": 83, ...}
    │
    ▼
evaluate_rules(flat_metrics)
    │
    ├── 遍历所有 enabled=1 的阈值规则
    │       ├── 提取对应指标值
    │       ├── 判定 severity（critical > warning）
    │       └── 检查 cooldown → fire_alert()
    │                               ├── INSERT alert_history
    │                               └── send_telegram()
    │
    └── 基线规则跳过（由 check_baseline_deviation 独立处理）
```

---

## 告警管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/agents/alert-rules | 获取所有告警规则 |
| POST | /api/agents/alert-rules | 创建自定义告警规则 |
| PUT | /api/agents/alert-rules/{id} | 更新告警规则 |
| DELETE | /api/agents/alert-rules/{id} | 删除告警规则 |
| GET | /api/agents/alert-history | 获取告警历史（最近 50 条）|

---

## 自定义告警规则

可通过 API 添加自定义规则，存入 `alert_rules` 表。规则字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 唯一标识（自动生成）|
| name | TEXT | 规则名称 |
| metric | TEXT | 指标键名 |
| operator | TEXT | 比较运算符（`>`/`>=`/`<`/`<=`/`==`）|
| warning_threshold | REAL | warning 阈值 |
| critical_threshold | REAL | critical 阈值 |
| cooldown_minutes | INTEGER | 冷却时间（分钟）|
| notify | INTEGER | 是否发送通知（1/0）|
| enabled | INTEGER | 是否启用（1/0）|
| rule_type | TEXT | threshold（阈值）/ baseline（基线）|

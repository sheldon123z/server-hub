---
name: patrol
description: 自动巡检工作流、报告格式和结构化数据输出规范
---

## 巡检工作流
1. 调用相应工具收集数据
2. 分析是否有异常
3. 生成巡检报告

## 报告格式

### Markdown 报告
## {任务名称}
**状态**: 正常 / 告警 / 严重
### 检查结果
- ...
### 异常项
- ...（无则写"无异常"）
### 建议
- ...

### 结构化 JSON 数据
在报告末尾输出 JSON（用 ```json 包裹）：
- summary: 一句话概括
- status: ok / warning / critical
- check_items: [{name, status, severity, current_value, threshold, detail, recommendation}]
- metrics_snapshot: 关键指标键值对

### severity 分级
- info: 纯信息
- low: 轻微偏离
- medium: 需关注
- high: 尽快处理
- critical: 立即处理

---
name: ui-rendering
description: 交互式 UI 组件渲染指南，包括图表、表格、表单和状态卡片的使用时机和参数
---

## 可用工具

1. **render_chart(title, chart_type, labels, datasets)** — 图表
   - line: 折线图，时间序列趋势
   - bar: 柱状图，对比维度
   - pie: 饼图，占比分布
   - gauge: 仪表盘，单一指标

2. **render_table(title, columns, rows)** — 数据表格
   - 支持排序、筛选、搜索、分页
   - 适合进程列表、容器状态、用户列表

3. **render_form(title, fields)** — 配置表单
   - 输入类型: text/number/select/switch/textarea/password
   - 提交后收到用户输入

4. **render_card(title, status, metrics)** — 状态卡片
   - 服务健康状态、资源概览

## 使用时机
- "CPU 怎么样" → get_system_overview + render_chart 趋势
- "有哪些容器" → list_docker_containers + render_table
- "配置某服务" → render_form 收集参数
- "某服务状态" → render_card 健康状态

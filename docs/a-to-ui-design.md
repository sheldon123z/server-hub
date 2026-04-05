# A to UI 技术方案设计文档

> 生成日期: 2026-04-01
> 项目: ServerHub 前端对话页面 Agent UI 渲染
> 状态: 讨论中，待审查

---

## 一、背景与目标

### 1.1 问题陈述

当前的 ServerHub 对话页面只能显示纯文本消息和工具调用结果。当 Agent 需要展示结构化数据（如监控图表、进程列表、配置表单）时，用户必须在文本中手动解析信息，体验不佳。

### 1.2 目标

实现 **A to UI** (Agent to UI)：让 Agent 能够返回可被前端直接渲染的 UI 组件，包括：
- 交互式图表（折线图、柱状图、饼图）
- 数据表格（支持排序、筛选）
- 配置表单（用户可填写并提交）
- 状态卡片（资源监控概览）
- 日志查看器

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           A to UI 架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐  │
│   │   Agent     │────>│   后端      │────>│   SSE 事件流            │  │
│   │  (Deep)     │     │  (FastAPI)  │     │  ui.render / ui.action │  │
│   └─────────────┘     └─────────────┘     └───────────┬─────────────┘  │
│                                                       │                 │
│                                                       v                 │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────┐  │
│   │   前端      │<────│  组件注册   │<────│   React 组件库          │  │
│   │  (React)    │     │   中心      │     │  Chart/Table/Form/Card  │  │
│   └─────────────┘     └─────────────┘     └─────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 消息流程

```
1. Agent 调用 render_* 工具
2. 后端检测到 _ui 标记，转换为 ui.render 事件
3. 前端接收事件，通过组件注册中心获取渲染器
4. 渲染对应 UI 组件
5. 用户交互 → POST /api/agents/ui/action
6. 后端转发给 Agent 处理 → Agent 返回响应
7. 前端通过 ui.update 事件更新组件
```

---

## 三、Schema 定义

### 3.1 基础结构

```typescript
interface BaseComponent {
  id: string              // 唯一标识
  type: ComponentType     // 组件类型
  title?: string          // 可选标题
  version: '1.0'          // Schema 版本
}

type ComponentType = 
  | 'chart' 
  | 'table' 
  | 'form' 
  | 'card' 
  | 'metric' 
  | 'log-viewer'
  | 'process-tree'
  | 'custom'
```

### 3.2 图表组件 Schema

```typescript
interface ChartComponent extends BaseComponent {
  type: 'chart'
  chartType: 'line' | 'bar' | 'pie' | 'gauge' | 'heatmap'
  data: {
    labels: string[]
    datasets: Dataset[]
    options?: ChartOptions
  }
  interactions?: {
    zoom?: boolean
    download?: boolean
    tooltip?: boolean
  }
}

interface Dataset {
  label: string
  data: number[]
  color?: string
  unit?: string
}
```

### 3.3 表格组件 Schema

```typescript
interface TableComponent extends BaseComponent {
  type: 'table'
  schema: ColumnSchema[]
  data: Record<string, unknown>[]
  features: {
    sortable: boolean
    filterable: boolean
    paginated: boolean
    pageSize?: number
    searchable?: boolean
  }
}

interface ColumnSchema {
  key: string
  label: string
  type: 'text' | 'number' | 'status' | 'action' | 'timestamp'
  width?: string
  align?: 'left' | 'center' | 'right'
  render?: 'default' | 'badge' | 'progress' | 'link'
}
```

### 3.4 表单组件 Schema

```typescript
interface FormComponent extends BaseComponent {
  type: 'form'
  fields: FieldSchema[]
  initialValues?: Record<string, unknown>
  layout?: 'vertical' | 'horizontal'
  actions: FormAction[]
}

interface FieldSchema {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'switch' | 'textarea' | 'password'
  placeholder?: string
  validation?: {
    required?: boolean
    min?: number
    max?: number
    pattern?: string
  }
  options?: { label: string; value: string }[]
  disabled?: boolean
}

interface FormAction {
  id: string
  label: string
  variant: 'primary' | 'secondary' | 'danger'
  action_type: 'submit' | 'reset' | 'agent'
}
```

---

## 四、交互事件设计

### 4.1 事件类型

| 方向 | 事件名 | 说明 |
|------|--------|------|
| 后端→前端 | `ui.render` | 渲染新组件 |
| 后端→前端 | `ui.update` | 更新现有组件 |
| 后端→前端 | `ui.remove` | 删除组件 |
| 前端→后端 | `POST /api/agents/ui/action` | 用户交互 |

### 4.2 前端 → 后端：交互事件

```typescript
interface UIInteractionEvent {
  component_id: string
  component_type: string
  action_id: string
  action_type: 'callback' | 'navigate' | 'api' | 'agent'
  payload: Record<string, unknown>
  conversation_id: string
  run_id: string
}
```

### 4.3 后端 → 前端：更新事件

```typescript
interface UIUpdateEvent {
  event: 'ui.update'
  data: {
    component_id: string
    update_type: 'replace' | 'append' | 'clear'
    data: Record<string, unknown>
    errors?: ValidationError[]
  }
}
```

---

## 五、组件注册机制

### 5.1 注册中心设计

```typescript
interface ComponentRegistry {
  register<T extends BaseComponent>(
    type: string,
    renderer: React.ComponentType<RendererProps<T>>,
    schema?: ZodSchema<T>
  ): void
  
  getRenderer(type: string): React.ComponentType<any> | null
  validate(type: string, data: unknown): ValidationResult
  list(): ComponentTypeInfo[]
}
```

### 5.2 预置组件

| 组件 | 类型 | 用途 |
|------|------|------|
| ChartRenderer | chart | 折线图、柱状图、饼图 |
| DataTable | table | 数据表格 |
| ConfigForm | form | 配置表单 |
| StatusCard | card | 状态卡片 |
| MetricGrid | metric | 指标网格 |
| LogViewer | log-viewer | 日志查看器 |

---

## 六、实施计划

### Phase 1：基础设施（1-2天）

- [ ] 扩展 `ChatMessage` 类型定义，新增 `ui_component` 角色
- [ ] 新增 `UIComponentMessage` 接口
- [ ] 扩展 `useSSEChat` 事件处理，新增 `ui.render` / `ui.update` / `ui.remove`
- [ ] 创建组件注册中心 (`useComponentRegistry`)

### Phase 2：基础组件（2-3天）

- [ ] 复用 `echarts-for-react` 实现 `ChartRenderer`
- [ ] 实现 `DataTable` 组件（排序、筛选、分页）
- [ ] 实现 `StatusCard` 组件
- [ ] 实现 `ConfigForm` 组件

### Phase 3：工具封装（2天）

- [ ] 在 Agent 侧创建 `render_chart`, `render_table`, `render_form` 工具
- [ ] 实现 `modules/agents/tools/ui_tools.py`
- [ ] 更新系统提示词，引导 Agent 何时使用

### Phase 4：交互闭环（2-3天）

- [ ] 新增 `POST /api/agents/ui/action` 路由
- [ ] 前端实现交互事件处理
- [ ] 支持 `ui.update` 事件实现组件动态更新
- [ ] 错误处理与边界情况

### Phase 5：增强功能（2天）

- [ ] 动画效果（流式渲染时的骨架屏）
- [ ] 响应式适配
- [ ] 组件文档与示例

---

## 七、关键设计决策

### 7.1 为什么选择方案 A（协议扩展）+ 方案 B（工具驱动）？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 协议扩展 | 灵活、向后兼容 | 需要定义新协议 |
| 工具驱动 | 语义清晰、可控 | Agent 需要学习新工具 |
| Markdown 扩展 | 简单 | 不适合复杂交互 |

**决策**：采用协议扩展为主，工具驱动为辅。Agent 可以通过：
1. 显式调用 `render_*` 工具（推荐）
2. 在文本中返回 UI 标记（兼容）

### 7.2 Schema 演进策略

- 每个组件带 `version: '1.0'` 字段
- 不兼容变更递增版本号
- 前端校验版本，拒绝未知版本

### 7.3 安全策略

- 组件渲染使用白名单（仅注册过的组件）
- 数据使用 Zod 运行时校验
- 交互事件需要携带 conversation_id 验证
- 敏感操作（如删除）需要二次确认

---

## 八、开放讨论点

### 8.1 待讨论

1. **组件数据 Schema**：当前定义是否满足需求？是否需要添加其他字段？

2. **交互事件传回**：
   - 表单提交后，Agent 是同步响应还是异步？
   - 是否需要支持"流式更新"（类似打字机效果）？
   - 错误处理如何设计？

3. **自定义组件注册**：
   - 是否需要支持 Agent 动态注册新组件？
   - 组件版本如何管理？
   - 是否需要组件市场/模板系统？

### 8.2 后续工作

- [ ] 审查本设计文档
- [ ] 确定技术选型
- [ ] 拆分任务到具体 PR
- [ ] 开始 Phase 1 实现

---

## 九、相关文件

- `frontend/src/pages/agents/MessageBubble.tsx` - 消息渲染
- `frontend/src/pages/agents/ChatPanel.tsx` - 聊天面板
- `frontend/src/hooks/useSSEChat.ts` - SSE 事件处理
- `frontend/src/types/agent.ts` - 类型定义
- `modules/agents/routes/chat.py` - 后端 SSE 路由
- `modules/agents/tools/` - Agent 工具目录

---

## 十、详细实现代码

### 10.1 前端组件渲染器

#### 10.1.1 图表组件渲染器

```tsx
// frontend/src/components/agent/renderers/ChartRenderer.tsx
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'
import { cn } from '@/lib/utils'

interface ChartData {
  type: 'line' | 'bar' | 'pie' | 'gauge' | 'heatmap'
  title: string
  data: number[]
  labels: string[]
  options?: Record<string, unknown>
}

interface ChartRendererProps {
  data: ChartData
  actions?: UIAction[]
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
}

export function ChartRenderer({ data, actions, onAction }: ChartRendererProps) {
  const option = useMemo(() => ({
    title: { text: data.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    grid: { left: '10%', right: '10%', bottom: '15%' },
    xAxis: { 
      type: 'category', 
      data: data.labels,
      axisLabel: { fontSize: 10 }
    },
    yAxis: { 
      type: 'value',
      axisLabel: { fontSize: 10 }
    },
    series: [{ 
      type: data.type, 
      data: data.data,
      smooth: data.type === 'line',
      areaStyle: data.type === 'line' ? { opacity: 0.3 } : undefined,
      itemStyle: { borderRadius: data.type === 'bar' ? [4, 4, 0, 0] : 0 }
    }],
    ...data.options
  }), [data])

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <ReactECharts 
        option={option} 
        style={{ height: 280 }} 
        opts={{ renderer: 'canvas' }}
      />
      {actions && actions.length > 0 && (
        <div className="mt-3 flex gap-2 justify-end">
          {actions.map(action => (
            <button
              key={action.id}
              onClick={() => onAction(action.id)}
              className="px-3 py-1.5 text-xs rounded-md bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
```

#### 10.1.2 数据表格组件渲染器

```tsx
// frontend/src/components/agent/renderers/DataTable.tsx
import { useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { ChevronUp, ChevronDown, Search, X } from 'lucide-react'

interface TableData {
  columns: { key: string; label: string; type?: string; align?: string }[]
  rows: Record<string, unknown>[]
  sortable?: boolean
  filterable?: boolean
  searchable?: boolean
  pageSize?: number
}

interface DataTableProps {
  data: TableData
  actions?: UIAction[]
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
}

export function DataTable({ data, actions, onAction }: DataTableProps) {
  const [sortColumn, setSortColumn] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filterColumn, setFilterColumn] = useState<string | null>(null)
  const [filterValue, setFilterValue] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(0)
  const pageSize = data.pageSize ?? 10

  const filteredRows = useMemo(() => {
    let rows = [...data.rows]
    
    // 搜索
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      rows = rows.filter(row => 
        Object.values(row).some(v => String(v).toLowerCase().includes(term))
      )
    }
    
    // 筛选
    if (filterColumn && filterValue) {
      rows = rows.filter(row => 
        String(row[filterColumn]).toLowerCase().includes(filterValue.toLowerCase())
      )
    }
    
    // 排序
    if (sortColumn) {
      rows.sort((a, b) => {
        const aVal = a[sortColumn], bVal = b[sortColumn]
        const cmp = String(aVal ?? '').localeCompare(String(bVal ?? ''))
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    
    return rows
  }, [data.rows, searchTerm, filterColumn, filterValue, sortColumn, sortDir])

  const paginatedRows = useMemo(() => {
    return filteredRows.slice(page * pageSize, (page + 1) * pageSize)
  }, [filteredRows, page, pageSize])

  const totalPages = Math.ceil(filteredRows.length / pageSize)

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* 工具栏 */}
      {(data.searchable || data.filterable) && (
        <div className="flex gap-2 p-3 border-b border-border bg-bg2">
          {data.searchable && (
            <div className="relative flex-1">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-text3" />
              <input
                type="text"
                placeholder="搜索..."
                value={searchTerm}
                onChange={e => { setSearchTerm(e.target.value); setPage(0) }}
                className="w-full pl-8 pr-3 py-1.5 text-sm border border-border rounded bg-bg"
              />
            </div>
          )}
          {data.filterable && data.columns.length > 0 && (
            <select
              value={filterColumn || ''}
              onChange={e => { setFilterColumn(e.target.value || null); setPage(0) }}
              className="px-2 py-1.5 text-sm border border-border rounded bg-bg"
            >
              <option value="">筛选列...</option>
              {data.columns.map(col => (
                <option key={col.key} value={col.key}>{col.label}</option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* 表格 */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg2">
            <tr>
              {data.columns.map(col => (
                <th 
                  key={col.key}
                  className={cn(
                    "px-3 py-2 text-left text-xs font-medium text-text3",
                    data.sortable && "cursor-pointer hover:bg-bg3",
                    col.align === 'right' && "text-right",
                    col.align === 'center' && "text-center"
                  )}
                  onClick={() => data.sortable && handleSort(col.key)}
                >
                  <div className={cn("flex items-center gap-1", 
                    col.align === 'right' && "justify-end",
                    col.align === 'center' && "justify-center"
                  )}>
                    {col.label}
                    {data.sortable && sortColumn === col.key && (
                      sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedRows.map((row, i) => (
              <tr key={i} className="border-t border-border hover:bg-bg2/50">
                {data.columns.map(col => (
                  <td key={col.key} className={cn("px-3 py-2 text-xs",
                    col.align === 'right' && "text-right",
                    col.align === 'center' && "text-center"
                  )}>
                    {col.type === 'status' ? (
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-xs",
                        row[col.key] === 'running' && "bg-green/20 text-green",
                        row[col.key] === 'stopped' && "bg-red/20 text-red",
                        row[col.key] === 'pending' && "bg-yellow/20 text-yellow"
                      )}>
                        {String(row[col.key])}
                      </span>
                    ) : (
                      String(row[col.key] ?? '-')
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between p-3 border-t border-border bg-bg2">
          <div className="text-xs text-text3">
            第 {page + 1} / {totalPages} 页，共 {filteredRows.length} 条
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-2 py-1 text-xs border border-border rounded hover:bg-bg3 disabled:opacity-50"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 text-xs border border-border rounded hover:bg-bg3 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      {/* 操作按钮 */}
      {actions && actions.length > 0 && (
        <div className="flex gap-2 p-3 border-t border-border justify-end">
          {actions.map(action => (
            <button
              key={action.id}
              onClick={() => onAction(action.id)}
              className="px-3 py-1.5 text-xs rounded-md bg-accent/10 text-accent hover:bg-accent/20"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )

  function handleSort(key: string) {
    if (sortColumn === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(key)
      setSortDir('asc')
    }
  }
}
```

### 10.2 后端 Agent 工具

```python
# modules/agents/tools/ui_tools.py
"""Agent UI 渲染工具集"""

from __future__ import annotations

import uuid
from typing import TypedDict, Literal, List, Optional
from langchain_core.tools import tool


class UIAction(TypedDict):
    id: str
    label: str
    action_type: Literal["callback", "navigate", "api", "agent"]
    payload: Optional[dict]


class Dataset(TypedDict):
    label: str
    data: List[float]
    color: Optional[str]
    unit: Optional[str]


class ChartData(TypedDict):
    labels: List[str]
    datasets: List[Dataset]


@tool
def render_chart(
    title: str,
    chart_type: Literal["line", "bar", "pie", "gauge", "heatmap"],
    data: ChartData,
    actions: Optional[List[UIAction]] = None,
    description: Optional[str] = None
) -> dict:
    """
    渲染一个图表组件到聊天界面。

    适用场景:
    - 展示系统指标趋势 (CPU、内存、网络流量)
    - 对比多个维度的数据
    - 显示占比分布 (如磁盘使用率)
    - 展示实时监控数据

    Args:
        title: 图表标题
        chart_type: 图表类型
          - line: 折线图，适合展示趋势
          - bar: 柱状图，适合对比
          - pie: 饼图，适合占比
          - gauge: 仪表盘，适合单一指标
          - heatmap: 热力图，适合密度分布
        data: 图表数据，包含 labels 和 datasets
        actions: 可选的操作按钮列表
        description: 可选的描述文字

    Returns:
        UI 组件规范，前端将渲染为交互式图表

    Example:
        render_chart(
            title="CPU 使用率 (24小时)",
            chart_type="line",
            data={
                "labels": ["00:00", "06:00", "12:00", "18:00"],
                "datasets": [{
                    "label": "CPU %",
                    "data": [45, 52, 78, 35],
                    "unit": "%"
                }]
            },
            actions=[{"id": "refresh", "label": "刷新", "action_type": "agent"}]
        )
    """
    return {
        "_ui": True,
        "id": f"chart_{uuid.uuid4().hex[:8]}",
        "type": "chart",
        "version": "1.0",
        "title": title,
        "chartType": chart_type,
        "data": data,
        "actions": actions or [],
        "description": description
    }


@tool
def render_table(
    title: str,
    columns: List[dict],
    rows: List[dict],
    sortable: bool = True,
    filterable: bool = True,
    searchable: bool = True,
    page_size: int = 10,
    actions: Optional[List[UIAction]] = None,
    description: Optional[str] = None
) -> dict:
    """
    渲染一个数据表格组件。

    适用场景:
    - 展示进程列表
    - 展示 Docker 容器
    - 展示用户列表
    - 展示服务状态

    Args:
        title: 表格标题
        columns: 列定义列表，每项包含:
          - key: 数据字段名
          - label: 显示标题
          - type: 类型 (text/number/status/action/timestamp)
          - align: 对齐方式
        rows: 数据行列表
        sortable: 是否可排序
        filterable: 是否可按列筛选
        searchable: 是否可全局搜索
        page_size: 每页条数
        actions: 操作按钮

    Returns:
        UI 组件规范，前端将渲染为交互式表格
    """
    return {
        "_ui": True,
        "id": f"table_{uuid.uuid4().hex[:8]}",
        "type": "table",
        "version": "1.0",
        "title": title,
        "schema": columns,
        "data": rows,
        "features": {
            "sortable": sortable,
            "filterable": filterable,
            "searchable": searchable,
            "paginated": True,
            "pageSize": page_size
        },
        "actions": actions or [],
        "description": description
    }


@tool
def render_form(
    title: str,
    fields: List[dict],
    initial_values: Optional[dict] = None,
    actions: Optional[List[UIAction]] = None,
    description: Optional[str] = None
) -> dict:
    """
    渲染一个配置表单组件。

    适用场景:
    - 用户提交配置
    - 创建新资源
    - 编辑设置

    Args:
        title: 表单标题
        fields: 字段定义，每项包含:
          - name: 字段名
          - label: 显示标签
          - type: 类型 (text/number/select/switch/textarea/password)
          - placeholder: 占位符
          - validation: 验证规则 (required/min/max/pattern)
          - options: 选项列表 (用于 select)
          - disabled: 是否禁用
        initial_values: 初始值
        actions: 表单按钮
          - 提交按钮 action_type 应为 "agent"，会触发 Agent 处理
        description: 描述文字

    Returns:
        UI 组件规范，前端将渲染为可交互表单
    """
    return {
        "_ui": True,
        "id": f"form_{uuid.uuid4().hex[:8]}",
        "type": "form",
        "version": "1.0",
        "title": title,
        "fields": fields,
        "initialValues": initial_values or {},
        "actions": actions or [
            {
                "id": "submit",
                "label": "提交",
                "action_type": "agent",
                "variant": "primary"
            }
        ],
        "description": description
    }


@tool
def render_card(
    title: str,
    status: Literal["healthy", "warning", "error", "unknown"],
    metrics: List[dict],
    details: Optional[str] = None,
    actions: Optional[List[UIAction]] = None
) -> dict:
    """
    渲染一个状态卡片组件。

    适用场景:
    - 展示单个服务器状态
    - 展示服务健康状态
    - 展示资源概览

    Args:
        title: 卡片标题
        status: 状态 (healthy/warning/error/unknown)
        metrics: 指标列表，每项包含:
          - label: 标签
          - value: 值
          - unit: 单位
          - trend: 趋势 (up/down/stable)
        details: 详情文字
        actions: 操作按钮

    Returns:
        UI 组件规范，前端将渲染为状态卡片
    """
    status_colors = {
        "healthy": "bg-green/20 border-green/40 text-green",
        "warning": "bg-yellow/20 border-yellow/40 text-yellow",
        "error": "bg-red/20 border-red/40 text-red",
        "unknown": "bg-gray/20 border-gray/40 text-gray"
    }
    
    return {
        "_ui": True,
        "id": f"card_{uuid.uuid4().hex[:8]}",
        "type": "card",
        "version": "1.0",
        "title": title,
        "status": status,
        "statusClass": status_colors.get(status, status_colors["unknown"]),
        "metrics": metrics,
        "details": details,
        "actions": actions or []
    }
```

### 10.3 Schema 验证

```typescript
// frontend/src/lib/ui-schema-validation.ts
import { z } from 'zod'

// 基础组件 Schema
const BaseComponentSchema = z.object({
  id: z.string(),
  type: z.string(),
  title: z.string().optional(),
  version: z.literal('1.0'),
})

// 图表 Schema
const DatasetSchema = z.object({
  label: z.string(),
  data: z.array(z.number()),
  color: z.string().optional(),
  unit: z.string().optional(),
})

const ChartDataSchema = z.object({
  labels: z.array(z.string()),
  datasets: z.array(DatasetSchema),
})

const ChartComponentSchema = BaseComponentSchema.extend({
  type: z.literal('chart'),
  chartType: z.enum(['line', 'bar', 'pie', 'gauge', 'heatmap']),
  data: ChartDataSchema,
  actions: z.array(z.object({
    id: z.string(),
    label: z.string(),
    action_type: z.enum(['callback', 'navigate', 'api', 'agent']),
    payload: z.record(z.unknown()).optional(),
  })).optional(),
})

// 表格 Schema
const ColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum(['text', 'number', 'status', 'action', 'timestamp']).optional(),
  align: z.enum(['left', 'center', 'right']).optional(),
  render: z.enum(['default', 'badge', 'progress', 'link']).optional(),
})

const TableFeaturesSchema = z.object({
  sortable: z.boolean().optional(),
  filterable: z.boolean().optional(),
  searchable: z.boolean().optional(),
  paginated: z.boolean().optional(),
  pageSize: z.number().optional(),
})

const TableComponentSchema = BaseComponentSchema.extend({
  type: z.literal('table'),
  schema: z.array(ColumnSchema),
  data: z.array(z.record(z.unknown())),
  features: TableFeaturesSchema.optional(),
  actions: z.array(z.object({
    id: z.string(),
    label: z.string(),
    action_type: z.enum(['callback', 'navigate', 'api', 'agent']),
  })).optional(),
})

// 表单 Schema
const FieldSchema = z.object({
  name: z.string(),
  label: z.string(),
  type: z.enum(['text', 'number', 'select', 'switch', 'textarea', 'password']),
  placeholder: z.string().optional(),
  validation: z.object({
    required: z.boolean().optional(),
    min: z.number().optional(),
    max: z.number().optional(),
    pattern: z.string().optional(),
  }).optional(),
  options: z.array(z.object({
    label: z.string(),
    value: z.string(),
  })).optional(),
  disabled: z.boolean().optional(),
})

const FormActionSchema = z.object({
  id: z.string(),
  label: z.string(),
  variant: z.enum(['primary', 'secondary', 'danger']).optional(),
  action_type: z.enum(['submit', 'reset', 'agent']),
})

const FormComponentSchema = BaseComponentSchema.extend({
  type: z.literal('form'),
  fields: z.array(FieldSchema),
  initialValues: z.record(z.unknown()).optional(),
  actions: z.array(FormActionSchema).optional(),
})

// 联合验证
export const UIComponentSchema = z.discriminatedUnion('type', [
  ChartComponentSchema,
  TableComponentSchema,
  FormComponentSchema,
])

export type UIComponent = z.infer<typeof UIComponentSchema>

// 验证函数
export function validateUIComponent(data: unknown): {
  valid: boolean
  data?: UIComponent
  error?: z.ZodError
} {
  const result = UIComponentSchema.safeParse(data)
  if (!result.success) {
    return { valid: false, error: result.error }
  }
  return { valid: true, data: result.data }
}
```

### 10.4 组件注册中心

```typescript
// frontend/src/stores/componentRegistry.ts
import { create } from 'zustand'
import type { UIComponent } from '@/lib/ui-schema-validation'

interface RendererProps {
  component: UIComponent
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
  loadingActions?: Set<string>
}

interface ComponentRegistryState {
  renderers: Map<string, React.ComponentType<RendererProps>>
  schemas: Map<string, z.ZodSchema>
  register: <T extends UIComponent>(
    type: string,
    renderer: React.ComponentType<RendererProps>,
    schema?: z.ZodSchema<T>
  ) => void
  getRenderer: (type: string) => React.ComponentType<RendererProps> | null
  validate: (type: string, data: unknown) => { valid: boolean; errors?: any }
}

export const useComponentRegistry = create<ComponentRegistryState>((set, get) => ({
  renderers: new Map(),
  schemas: new Map(),
  
  register(type, renderer, schema) {
    set(state => {
      const newRenderers = new Map(state.renderers)
      const newSchemas = new Map(state.schemas)
      newRenderers.set(type, renderer as React.ComponentType<RendererProps>)
      if (schema) newSchemas.set(type, schema)
      return { renderers: newRenderers, schemas: newSchemas }
    })
  },
  
  getRenderer(type) {
    return get().renderers.get(type) ?? null
  },
  
  validate(type, data) {
    const schema = get().schemas.get(type)
    if (!schema) return { valid: true }
    const result = schema.safeParse(data)
    return { 
      valid: result.success, 
      errors: result.success ? undefined : result.error.format() 
    }
  }
}))

// 预置组件注册
export function registerBuiltInComponents() {
  const registry = useComponentRegistry.getState()
  
  // 延迟导入以避免循环依赖
  import('./renderers/ChartRenderer').then(({ ChartRenderer }) => {
    registry.register('chart', ChartRenderer)
  })
  import('./renderers/DataTable').then(({ DataTable }) => {
    registry.register('table', DataTable)
  })
  import('./renderers/ConfigForm').then(({ ConfigForm }) => {
    registry.register('form', ConfigForm)
  })
  import('./renderers/StatusCard').then(({ StatusCard }) => {
    registry.register('card', StatusCard)
  })
}
```

### 10.5 错误边界

```tsx
// frontend/src/components/agent/UIComponentErrorBoundary.tsx
import React from 'react'

interface Props {
  componentId: string
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class UIComponentErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('UI Component Error:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      
      return (
        <div className="p-4 border border-red-300 bg-red-50 rounded-lg">
          <div className="text-red font-medium">组件渲染失败</div>
          <div className="text-sm text-red/70 mt-1">
            ID: {this.props.componentId}
          </div>
          {this.state.error && (
            <div className="mt-2 text-xs text-red/60 font-mono">
              {this.state.error.message}
            </div>
          )}
          <button 
            onClick={this.handleRetry}
            className="mt-2 text-sm underline text-red hover:text-red/80"
          >
            重试
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
```

---

## 十一、Prompt 工程指导

### 11.1 系统提示词扩展

```python
# modules/agents/prompts.py 添加

UI_RENDERING_GUIDE = """
## UI 渲染能力

你可以通过调用专门的工具来渲染交互式 UI 组件，而不是仅返回文本。

### 可用组件

1. **图表 (render_chart)** - 用于展示数据趋势和对比
   - 折线图: 展示时间序列趋势
   - 柱状图: 对比不同类别
   - 饼图: 展示占比分布
   - 仪表盘: 展示单一指标

2. **表格 (render_table)** - 用于展示列表数据
   - 支持排序、筛选、搜索
   - 适合展示进程、容器、用户等列表

3. **表单 (render_form)** - 用于收集用户输入
   - 支持多种输入类型
   - 提交后你将收到用户的输入内容

4. **状态卡片 (render_card)** - 用于展示状态概览
   - 适合展示单个资源的状态

### 使用时机

- 用户询问"服务器 CPU 怎么样" → 使用 render_chart 展示趋势图
- 用户询问"当前运行的进程" → 使用 render_table 展示进程列表
- 用户需要创建/配置资源 → 使用 render_form 收集信息
- 用户询问单个服务状态 → 使用 render_card 展示状态

### 注意事项

- 图表数据应该是真实的监控数据
- 表格行数过多时考虑分页
- 表单提交后等待用户输入，不要自行填充

### 示例

用户: 帮我看看内存使用情况
[调用 get_system_metrics 工具获取内存数据]
[调用 render_chart 工具渲染内存使用趋势]

用户: 有哪些 Docker 容器在运行
[调用 list_docker_containers 工具]
[调用 render_table 工具渲染容器列表]
"""
```

---

## 十二、相关文件清单

### 12.1 需要创建的新文件

| 文件路径 | 说明 |
|----------|------|
| `frontend/src/components/agent/renderers/ChartRenderer.tsx` | 图表渲染器 |
| `frontend/src/components/agent/renderers/DataTable.tsx` | 表格渲染器 |
| `frontend/src/components/agent/renderers/ConfigForm.tsx` | 表单渲染器 |
| `frontend/src/components/agent/renderers/StatusCard.tsx` | 状态卡片渲染器 |
| `frontend/src/components/agent/UICard.tsx` | 统一 UI 卡片入口 |
| `frontend/src/components/agent/UIComponentErrorBoundary.tsx` | 错误边界 |
| `frontend/src/lib/ui-schema-validation.ts` | Schema 验证 |
| `frontend/src/stores/componentRegistry.ts` | 组件注册中心 |
| `modules/agents/tools/ui_tools.py` | Agent UI 工具 |
| `modules/agents/routes/ui.py` | UI 交互路由 |

### 12.2 需要修改的现有文件

| 文件路径 | 修改内容 |
|----------|----------|
| `frontend/src/types/agent.ts` | 新增 UIComponentMessage 类型 |
| `frontend/src/hooks/useSSEChat.ts` | 新增 ui.render 等事件处理 |
| `frontend/src/pages/agents/MessageBubble.tsx` | 新增 ui_component 渲染分支 |
| `frontend/src/stores/chatStore.ts` | 新增 UI 组件状态管理 |
| `modules/agents/deep_agent.py` | 注册 ui_tools 工具 |
| `modules/agents/prompts.py` | 添加 UI 渲染指南 |

---

## 十三、审查意见（2026-04-01）

### 总体评价

文档覆盖面广，从架构到代码示例均有涉及。但对照项目实际代码后，发现 **5 个关键问题** 和 **3 个遗漏**。

---

### 关键问题（需修复）

#### P0 — `_ui` 标记在现有 SSE 管道中不会被识别

**问题**：当前 `modules/agents/routes/chat.py` 的 `_process_ai_message()` 只处理两种情况：`tool_calls` 和 `msg.content`（纯文本）。`render_chart` 等工具的返回值 `{"_ui": True, ...}` 会作为 `ToolMessage.content` 被序列化为字符串，然后走 `tool_result` 事件发给前端 — **前端不会收到 `ui.render` 事件**。

文档中的消息流程（§2.2）描述了"后端检测到 `_ui` 标记，转换为 `ui.render` 事件"，但 `_process_tool_message()` 里根本没有这个检测逻辑。

**修复建议**：在 `_process_tool_message()` 中添加 `_ui` 检测逻辑：

```python
async def _process_tool_message(msg: ToolMessage, run_id: str, conversation_id: str, username: str) -> list[dict]:
    """处理工具调用结果消息"""
    
    # 尝试解析 JSON 内容
    try:
        content_data = json.loads(msg.content) if msg.content else {}
    except json.JSONDecodeError:
        content_data = {}
    
    # 检测 UI 组件
    if content_data.get("_ui"):
        payload = {
            "run_id": run_id,
            "component_type": content_data.get("type"),
            "data": content_data,
            "id": getattr(msg, "id", None) or "",
        }
        events.append({"event": "ui.render", "data": json.dumps(payload)})
        # 同时发送一条文字消息作为 fallback
        if content_data.get("title"):
            events.append({
                "event": "message.final",
                "data": json.dumps({
                    "run_id": run_id,
                    "content": f"[{content_data['title']}]",
                    "role": "assistant",
                })
            })
        return events
    
    # 原有逻辑...
```

---

#### P0 — `ChatMessage` 类型与 `pushMsg()` 不兼容

**问题**：`frontend/src/stores/chatStore.ts` 的 `pushMsg()` 硬编码了 `ChatMessage` 的字段构造（第 99-109 行），只认 `role/content/tool/args/approval_id/description/actions/_serverId`。新增的 `componentType`、`data`、`actions`（UIAction 类型）这些字段会被直接丢弃。

**修复建议**：扩展 `ChatMessage` 类型并修改 `pushMsg()`：

```typescript
// frontend/src/types/agent.ts 扩展
export interface UIComponentMessage extends ChatMessage {
  role: 'ui_component'
  componentType: string
  data: Record<string, unknown>
  uiActions?: UIAction[]
}

// chatStore.ts pushMsg 扩展
pushMsg: (msg: Partial<ChatMessage>) => {
  const newMsg: ChatMessage = {
    _id,
    role: msg.role ?? 'assistant',
    content: msg.content ?? '',
    tool: msg.tool,
    args: msg.args,
    approval_id: msg.approval_id,
    description: msg.description,
    actions: Array.isArray(msg.actions) ? msg.actions : undefined,
    _serverId: msg._serverId,
    // 新增字段透传
    componentType: (msg as any).componentType,
    data: (msg as any).data,
    uiActions: (msg as any).uiActions,
  }
  // ...
}
```

---

#### P1 — 前后端 `data` 字段结构不一致

**问题**：后端 `render_chart` 的 `ChartData` 用 `labels + datasets`（多数据集），但前端 `ChartRenderer` 的 props 用 `data: number[] + labels: string[]`（单数据集）。同样，`render_table` 返回 `schema + data`，但前端 `DataTable` 期望 `columns + rows`。

**修复建议**：统一使用前端格式，后端适配：

```python
# 后端 render_chart 返回值修改为
return {
    "_ui": True,
    "id": f"chart_{uuid.uuid4().hex[:8]}",
    "type": "chart",
    "version": "1.0",
    "title": title,
    "chartType": chart_type,
    # 使用前端期望的格式
    "data": {
        "type": chart_type,
        "title": title,
        "labels": data["labels"],
        "data": data["datasets"][0]["data"],  # 取第一个数据集
    },
    # ...
}
```

或反向适配前端代码支持 `datasets` 格式。

---

#### P1 — Schema 定义（§3）与代码示例（§10）多处矛盾

| 位置 | 问题 |
|------|------|
| §3.2 `ChartComponent.data` | 用 `labels + datasets` |
| §10.1.1 `ChartData` | 用 `labels + data + type` |
| §3.3 `TableComponent` | 用 `schema + data` |
| §10.1.2 `DataTable` | 用 `columns + rows` |
| §4.2 `UIAction` | 4 种类型 (`callback/navigate/api/agent`) |
| §10.2 `FormAction` | 多了 `submit/reset` |

**修复建议**：在 §3 中增加统一定义：

```typescript
// 统一 UIAction 定义
interface UIAction {
  id: string
  label: string
  variant?: 'primary' | 'secondary' | 'danger'
  action_type: 'callback' | 'navigate' | 'api' | 'agent' | 'submit' | 'reset'
}

// 表格数据统一命名
interface TableComponentData {
  columns: ColumnSchema[]  // 而非 schema
  rows: Record<string, unknown>[]  // 而非 data
}
```

---

#### P2 — 样式 token 与项目不兼容

**问题**：`UIComponentErrorBoundary.tsx`（§10.5）使用了原生 Tailwind 颜色（`bg-red-50`、`text-red`），但项目用的是自定义 CSS 变量（`bg-card`、`text-text`、`border-border`）。

**修复建议**：全部改为项目 token：

```tsx
// 错误边界样式修改
return (
  <div className="p-4 border border-red/30 bg-red/10 rounded-lg">
    <div className="text-red font-medium">组件渲染失败</div>
    <div className="text-sm text-red/70 mt-1">
      ID: {this.props.componentId}
    </div>
    // ...
  </div>
)
```

---

### 遗漏点（需补充）

#### 1. 工具注册路径未说明

`deep_agent.py` 通过 `get_server_tools()` 加载工具（调用 `modules/agents/tools/` 下各子模块）。文档说"注册 ui_tools 工具"但没有说明具体的注册方式。

**补充说明**：

```python
# modules/agents/tools/__init__.py 或 tools/loader.py 中添加
def get_server_tools() -> list[BaseTool]:
    # ... 现有工具 ...
    
    # 新增 UI 工具
    from modules.agents.tools.ui_tools import (
        render_chart,
        render_table,
        render_form,
        render_card,
    )
    
    return [*tools, render_chart, render_table, render_form, render_card]
```

---

#### 2. SSE 处理流程缺失

完整的 UI 工具处理流程未在文档中体现。

**补充流程图**：

```
Agent 调用 render_chart 
    ↓
AIMessage.tool_calls 产生 tool_call
    ↓
框架执行工具 → ToolMessage.content = {"_ui": true, ...}
    ↓
_process_tool_message() 检测到 _ui 标记
    ↓
发送 ui.render 事件（发给前端）
    ↓
同时发送 message.final 让用户看到文字说明（如"[图表已渲染]"）
    ↓
前端接收 ui.render → 渲染组件
```

---

#### 3. 共享类型文件缺失

前端和后端各自定义了 `UIAction`，但没有共享类型文件。

**建议**：创建 `shared/types/ui.ts` 放置统一定义，前端和后端各生成对应类型。

---

### 审查结论

| 类别 | 数量 | 状态 |
|------|------|------|
| P0 关键问题 | 2 | 🔴 需修复 |
| P1 重要问题 | 2 | 🟡 建议修复 |
| P2 次要问题 | 1 | 🟡 建议修复 |
| 遗漏点 | 3 | 🟡 需补充 |

**建议**：修复上述 P0/P1 问题后，设计文档方可进入实施阶段。

---

*审查完成于 2026-04-01*
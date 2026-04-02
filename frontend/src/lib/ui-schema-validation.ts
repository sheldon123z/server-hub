/**
 * UI 组件 Schema 验证
 *
 * 使用 Zod 校验后端推送的 UI 组件数据，支持 chart/table/form/card 四种类型。
 * 字段名与后端 ui_tools.py 输出 + 前端渲染器 interface 保持一致。
 * 通过 discriminated union 按 type 字段分发。
 */
import { z } from 'zod'

// ── Chart 类型 ──
// 后端 render_chart 返回: chartType, data: {labels, datasets}
// 前端 ChartRenderer interface: chartType, data: {labels, datasets}

const ChartDatasetSchema = z.object({
  label: z.string(),
  data: z.array(z.number()),
  color: z.string().optional(),
  unit: z.string().optional(),
})

const ChartSchema = z.object({
  _ui: z.literal(true).optional(),
  id: z.string(),
  type: z.literal('chart'),
  version: z.string().optional(),
  title: z.string().optional(),
  chartType: z.enum(['line', 'bar', 'pie', 'gauge', 'heatmap']),
  data: z.object({
    labels: z.array(z.string()),
    datasets: z.array(ChartDatasetSchema),
  }),
  actions: z.array(z.unknown()).optional(),
  description: z.string().nullable().optional(),
})

// ── Table 类型 ──
// 后端 render_table 返回: schema (columns 定义), data (rows)
// 前端 DataTable interface: schema: ColumnSchema[], data: Record[]

const TableSchemaColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum(['text', 'number', 'status', 'action', 'timestamp']).optional(),
  align: z.enum(['left', 'center', 'right']).optional(),
  render: z.enum(['default', 'badge', 'progress', 'link']).optional(),
})

const TableSchema = z.object({
  _ui: z.literal(true).optional(),
  id: z.string(),
  type: z.literal('table'),
  version: z.string().optional(),
  title: z.string().optional(),
  schema: z.array(TableSchemaColumnSchema),
  data: z.array(z.record(z.string(), z.unknown())),
  features: z
    .object({
      sortable: z.boolean().optional(),
      filterable: z.boolean().optional(),
      searchable: z.boolean().optional(),
      paginated: z.boolean().optional(),
      pageSize: z.number().optional(),
    })
    .optional(),
  actions: z.array(z.unknown()).optional(),
  description: z.string().nullable().optional(),
})

// ── Form 类型 ──
// 后端 render_form 返回: fields, initialValues (camelCase)
// 前端 ConfigForm interface: fields: FormField[], initialValues?: Record

const FormFieldSchema = z.object({
  name: z.string(),
  label: z.string(),
  type: z.enum(['text', 'number', 'select', 'switch', 'textarea', 'password']),
  placeholder: z.string().optional(),
  validation: z
    .object({
      required: z.boolean().optional(),
      min: z.number().optional(),
      max: z.number().optional(),
      pattern: z.string().optional(),
    })
    .optional(),
  options: z
    .array(
      z.object({
        label: z.string(),
        value: z.unknown(),
      }),
    )
    .optional(),
  disabled: z.boolean().optional(),
})

const FormActionSchema = z.object({
  id: z.string(),
  label: z.string(),
  variant: z.enum(['primary', 'secondary', 'danger']).optional(),
  action_type: z.enum(['submit', 'reset', 'agent']),
})

const FormSchema = z.object({
  _ui: z.literal(true).optional(),
  id: z.string(),
  type: z.literal('form'),
  version: z.string().optional(),
  title: z.string().optional(),
  fields: z.array(FormFieldSchema),
  initialValues: z.record(z.string(), z.unknown()).optional(),
  actions: z.array(FormActionSchema).optional(),
  description: z.string().nullable().optional(),
})

// ── Card 类型 ──
// 后端 render_card 返回: title, status, metrics (含 unit/trend), details
// 前端 StatusCard interface: title, status, metrics: Metric[], details?

const MetricSchema = z.object({
  label: z.string(),
  value: z.union([z.string(), z.number()]),
  unit: z.string().optional(),
  trend: z.enum(['up', 'down', 'stable']).optional(),
})

const CardSchema = z.object({
  _ui: z.literal(true).optional(),
  id: z.string(),
  type: z.literal('card'),
  version: z.string().optional(),
  title: z.string(),
  status: z.enum(['healthy', 'warning', 'error', 'unknown']),
  metrics: z.array(MetricSchema),
  details: z.string().nullable().optional(),
  actions: z.array(z.unknown()).optional(),
})

// ── Discriminated Union (第一个参数是判别字段名) ──

export const UIComponentSchema = z.discriminatedUnion('type', [ChartSchema, TableSchema, FormSchema, CardSchema])

export type UIComponent = z.infer<typeof UIComponentSchema>

export function validateUIComponent(data: unknown): {
  valid: boolean
  data?: UIComponent
  error?: z.ZodError
} {
  const result = UIComponentSchema.safeParse(data)
  if (result.success) {
    return { valid: true, data: result.data }
  }
  return { valid: false, error: result.error }
}

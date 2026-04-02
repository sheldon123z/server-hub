/**
 * UI 组件 Schema 验证
 *
 * 使用 Zod 校验后端推送的 UI 组件数据，支持 chart/table/form/card 四种类型。
 * 每种类型有独立的 Schema 定义，通过 discriminated union 按 type 字段分发。
 */
import { z } from 'zod'

// ── Chart 类型 ──

const ChartDataSeriesSchema = z.object({
  name: z.string(),
  data: z.array(z.union([z.number(), z.string(), z.null()])),
})

const ChartSchema = z.object({
  type: z.literal('chart'),
  chart_type: z.enum(['line', 'bar', 'pie', 'scatter', 'heatmap', 'gauge', 'radar']).optional(),
  x_axis: z.array(z.union([z.string(), z.number()])).optional(),
  series: z.array(ChartDataSeriesSchema).optional(),
  option: z.record(z.string(), z.unknown()).optional(),
})

// ── Table 类型 ──

const TableColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  width: z.union([z.string(), z.number()]).optional(),
  align: z.enum(['left', 'center', 'right']).optional(),
  sortable: z.boolean().optional(),
})

const TableSchema = z.object({
  type: z.literal('table'),
  columns: z.array(TableColumnSchema),
  rows: z.array(z.record(z.string(), z.unknown())),
  pagination: z
    .object({
      page: z.number(),
      page_size: z.number(),
      total: z.number(),
    })
    .optional(),
})

// ── Form 类型 ──

const FormFieldSchema = z.object({
  name: z.string(),
  label: z.string(),
  field_type: z.enum(['text', 'number', 'select', 'checkbox', 'textarea', 'password', 'slider']),
  default: z.unknown().optional(),
  options: z
    .array(
      z.object({
        label: z.string(),
        value: z.unknown(),
      }),
    )
    .optional(),
  required: z.boolean().optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  placeholder: z.string().optional(),
})

const FormSchema = z.object({
  type: z.literal('form'),
  fields: z.array(FormFieldSchema),
  values: z.record(z.string(), z.unknown()).optional(),
  submit_label: z.string().optional(),
})

// ── Card 类型 ──

const CardSchema = z.object({
  type: z.literal('card'),
  content: z.string().optional(),
  items: z
    .array(
      z.object({
        label: z.string(),
        value: z.unknown(),
        icon: z.string().optional(),
        color: z.string().optional(),
      }),
    )
    .optional(),
  status: z.enum(['healthy', 'warning', 'error', 'info', 'unknown']).optional(),
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

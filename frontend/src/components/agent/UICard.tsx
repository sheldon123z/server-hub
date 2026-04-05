/**
 * UICard — unified entry point that dispatches to the correct renderer
 * based on component.type. Uses lazy loading for code splitting.
 */

import { lazy, Suspense } from 'react'
import { cn } from '@/lib/utils'
import type { UIComponentType } from '@/types/agent'

/* ── Lazy-loaded renderers ──────────────────────── */

const ChartRenderer = lazy(() =>
  import('./renderers/ChartRenderer').then((m) => ({ default: m.ChartRenderer })),
)
const DataTable = lazy(() =>
  import('./renderers/DataTable').then((m) => ({ default: m.DataTable })),
)
const ConfigForm = lazy(() =>
  import('./renderers/ConfigForm').then((m) => ({ default: m.ConfigForm })),
)
const StatusCard = lazy(() =>
  import('./renderers/StatusCard').then((m) => ({ default: m.StatusCard })),
)

/* ── Types ─────────────────────────────────────── */

export type { UIComponentType }

export interface UIComponentData {
  id: string
  type: UIComponentType
  title?: string
  // chart
  chartType?: 'line' | 'bar' | 'pie' | 'gauge' | 'heatmap'
  data?: {
    labels?: string[]
    datasets?: Array<{
      label: string
      data: number[]
      color?: string
      unit?: string
    }>
  }
  interactions?: { zoom?: boolean; download?: boolean; tooltip?: boolean }
  // table
  schema?: Array<{
    key: string
    label: string
    type?: 'text' | 'number' | 'status' | 'action' | 'timestamp'
    align?: 'left' | 'center' | 'right'
    render?: 'default' | 'badge' | 'progress' | 'link'
  }>
  // form
  fields?: Array<{
    name: string
    label: string
    type: 'text' | 'number' | 'select' | 'switch' | 'textarea' | 'password'
    placeholder?: string
    validation?: { required?: boolean; min?: number; max?: number; pattern?: string }
    options?: Array<{ label: string; value: string }>
    disabled?: boolean
  }>
  initialValues?: Record<string, unknown>
  actions?: Array<{
    id: string
    label: string
    variant?: 'primary' | 'secondary' | 'danger'
    action_type: 'submit' | 'reset' | 'agent'
  }>
  // card
  status?: 'healthy' | 'warning' | 'error' | 'unknown'
  metrics?: Array<{
    label: string
    value: string | number
    unit?: string
    trend?: 'up' | 'down' | 'stable'
  }>
  details?: string
  // table features
  features?: {
    sortable?: boolean
    filterable?: boolean
    searchable?: boolean
    paginated?: boolean
    pageSize?: number
  }
  // table data (rows)
  rows?: Array<Record<string, unknown>>
}

export interface UIAction {
  id: string
  label: string
  variant?: 'primary' | 'secondary' | 'danger'
  action_type: 'submit' | 'reset' | 'agent'
}

interface UICardProps {
  component: UIComponentData
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
  loadingActions?: Set<string>
}

/* ── Loading skeleton ───────────────────────────── */

function LoadingSkeleton() {
  return (
    <div className="border border-border bg-card rounded-lg p-4 animate-pulse">
      <div className="h-4 w-1/3 bg-bg3 rounded mb-3" />
      <div className="space-y-2">
        <div className="h-3 w-full bg-bg3 rounded" />
        <div className="h-3 w-5/6 bg-bg3 rounded" />
        <div className="h-3 w-2/3 bg-bg3 rounded" />
      </div>
    </div>
  )
}

/* ── Error card for unknown types ───────────────── */

function UnknownTypeCard({ type }: { type: string }) {
  return (
    <div className="border border-red/30 bg-red/5 rounded-lg p-3 text-sm text-red">
      不支持的组件类型: {type}
    </div>
  )
}

/* ── Main component ─────────────────────────────── */

export function UICard({ component, onAction, loadingActions }: UICardProps) {
  const renderer = (() => {
    switch (component.type) {
      case 'chart':
        return (
          <ChartRenderer
            component={component as Parameters<typeof ChartRenderer>[0]['component']}
          />
        )
      case 'table': {
        // Normalize table data: support both `data` and `rows` keys
        const tableData = component.rows ?? (component.data as unknown as Array<Record<string, unknown>> | undefined) ?? []
        return (
          <DataTable
            component={{
              ...component,
              type: 'table' as const,
              schema: component.schema ?? [],
              data: Array.isArray(tableData) ? tableData : [],
              features: component.features,
            }}
          />
        )
      }
      case 'form':
        return (
          <ConfigForm
            component={{
              ...component,
              type: 'form' as const,
              fields: component.fields ?? [],
              initialValues: component.initialValues,
              actions: component.actions,
            }}
            onAction={onAction}
            loadingActions={loadingActions}
          />
        )
      case 'card':
        return (
          <StatusCard
            component={{
              ...component,
              type: 'card' as const,
              title: component.title ?? '',
              status: component.status ?? 'unknown',
              metrics: component.metrics ?? [],
              details: component.details,
            }}
          />
        )
      default:
        return <UnknownTypeCard type={component.type} />
    }
  })()

  return (
    <div className="my-1">
      {component.title && component.type !== 'card' && component.type !== 'form' && (
        <div className="text-xs text-text3 mb-1.5 font-medium">{component.title}</div>
      )}
      <Suspense fallback={<LoadingSkeleton />}>
        {renderer}
      </Suspense>
    </div>
  )
}

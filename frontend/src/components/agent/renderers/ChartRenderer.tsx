/**
 * ChartRenderer — renders echarts charts (line, bar, pie, gauge) inside agent messages.
 * Uses the project's registered "serverhub-dark" theme.
 */

import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { cn } from '@/lib/utils'

const THEME_NAME = 'serverhub-dark'
const DEFAULT_COLORS = ['#38bdf8', '#4ade80', '#fbbf24', '#f87171', '#a78bfa', '#fb923c']

interface ChartDataset {
  label: string
  data: number[]
  color?: string
  unit?: string
}

interface ChartComponent {
  id: string
  type: 'chart'
  chartType: 'line' | 'bar' | 'pie' | 'gauge' | 'heatmap'
  title?: string
  data: {
    labels: string[]
    datasets: ChartDataset[]
  }
  interactions?: { zoom?: boolean; download?: boolean; tooltip?: boolean }
}

interface ChartRendererProps {
  component: ChartComponent
}

/* ── Option builders ──────────────────────────────── */

function buildLineOption(
  labels: string[],
  datasets: ChartDataset[],
  title?: string,
  zoom?: boolean,
) {
  return {
    title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 14 } } : undefined,
    tooltip: { trigger: 'axis' as const },
    legend: { textStyle: { color: '#94a3b8' } },
    grid: { left: 50, right: 20, top: title ? 40 : 20, bottom: zoom ? 60 : 30 },
    xAxis: { type: 'category' as const, data: labels, boundaryGap: false },
    yAxis: { type: 'value' as const },
    dataZoom: zoom
      ? [{ type: 'inside' as const }, { type: 'slider' as const }]
      : undefined,
    series: datasets.map((ds, i) => ({
      name: ds.label,
      type: 'line' as const,
      data: ds.data,
      smooth: true,
      itemStyle: { color: ds.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length] },
      areaStyle: { opacity: 0.3 },
    })),
  }
}

function buildBarOption(
  labels: string[],
  datasets: ChartDataset[],
  title?: string,
) {
  return {
    title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 14 } } : undefined,
    tooltip: { trigger: 'axis' as const },
    legend: { textStyle: { color: '#94a3b8' } },
    grid: { left: 50, right: 20, top: title ? 40 : 20, bottom: 30 },
    xAxis: { type: 'category' as const, data: labels },
    yAxis: { type: 'value' as const },
    series: datasets.map((ds, i) => ({
      name: ds.label,
      type: 'bar' as const,
      data: ds.data,
      itemStyle: {
        color: ds.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length],
        borderRadius: [4, 4, 0, 0],
      },
    })),
  }
}

function buildPieOption(
  _labels: string[],
  datasets: ChartDataset[],
  title?: string,
) {
  // Pie charts use only the first dataset
  const ds = datasets[0]
  if (!ds) {
    return { title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 14 } } : undefined }
  }

  const pieData = ds.data.map((val, i) => ({
    name: _labels[i] ?? `项${i + 1}`,
    value: val,
    itemStyle: { color: DEFAULT_COLORS[i % DEFAULT_COLORS.length] },
  }))

  return {
    title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 14 } } : undefined,
    tooltip: { trigger: 'item' as const },
    legend: { textStyle: { color: '#94a3b8' }, orient: 'vertical' as const, right: 10, top: 'center' },
    series: [{
      type: 'pie' as const,
      radius: ['40%', '70%'],
      data: pieData,
      label: { color: '#94a3b8' },
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' },
      },
    }],
  }
}

function buildGaugeOption(
  _labels: string[],
  datasets: ChartDataset[],
  title?: string,
) {
  const ds = datasets[0]
  const value = ds?.data?.[0] ?? 0
  const unit = ds?.unit ?? ''
  const name = ds?.label ?? ''

  return {
    title: title ? { text: title, textStyle: { color: '#e2e8f0', fontSize: 14 } } : undefined,
    series: [{
      type: 'gauge' as const,
      detail: {
        valueAnimation: true,
        formatter: `{value}${unit}`,
        color: '#e2e8f0',
        fontSize: 18,
      },
      data: [{ value, name }],
      axisLine: { lineStyle: { color: [[0.3, '#4ade80'], [0.7, '#fbbf24'], [1, '#f87171']] } },
      axisTick: { lineStyle: { color: '#64748b' } },
      splitLine: { lineStyle: { color: '#334155' } },
      axisLabel: { color: '#64748b' },
      pointer: { itemStyle: { color: '#38bdf8' } },
    }],
  }
}

/* ── Component ─────────────────────────────────── */

export function ChartRenderer({ component }: ChartRendererProps) {
  const { chartType, title, data, interactions } = component
  const { labels, datasets } = data

  const option = useMemo(() => {
    switch (chartType) {
      case 'line':
        return buildLineOption(labels, datasets, title, interactions?.zoom)
      case 'bar':
        return buildBarOption(labels, datasets, title)
      case 'pie':
        return buildPieOption(labels, datasets, title)
      case 'gauge':
        return buildGaugeOption(labels, datasets, title)
      case 'heatmap':
        return null
      default:
        return null
    }
  }, [chartType, labels, datasets, title, interactions?.zoom])

  if (chartType === 'heatmap' || option === null) {
    return (
      <div className={cn(
        'border border-border bg-bg2 rounded-lg p-4 text-sm text-text3 text-center',
      )}>
        {chartType === 'heatmap' ? '热力图暂不支持' : `不支持的图表类型: ${chartType}`}
      </div>
    )
  }

  return (
    <div className="border border-border bg-card rounded-lg p-3">
      <ReactECharts
        option={option}
        theme={THEME_NAME}
        style={{ height: 300, width: '100%' }}
        opts={{ renderer: 'canvas' }}
        notMerge
        lazyUpdate
      />
    </div>
  )
}

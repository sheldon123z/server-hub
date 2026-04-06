/**
 * Pipeline 编排页面 — 三栏布局
 *
 * 左栏: Pipeline 列表 + 新建按钮
 * 中栏: 详情面板 (编辑 / 预览 / 历史 三个 Tab)
 * 右栏: 运行监控面板
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { cn, formatDate, getErrorMessage } from '@/lib/utils'
import {
  pipelinesApi,
  type Pipeline,
  type PipelineRun,
  type PipelineParam,
  type StepLog,
  type StepDefinition,
  type RunStatus,
  type StepStatus,
} from '@/api/pipelines'

/* ═══════════════════════════════════════════════════════
   常量 & 辅助
   ═══════════════════════════════════════════════════════ */

const RUN_STATUS_STYLES: Record<RunStatus, string> = {
  pending: 'bg-yellow/20 text-yellow',
  running: 'bg-accent-dim text-accent',
  paused: 'bg-purple/20 text-purple',
  completed: 'bg-green/20 text-green',
  failed: 'bg-red/20 text-red',
  cancelled: 'bg-bg2 text-text3',
}

const STEP_STATUS_ICON: Record<StepStatus, string> = {
  pending: 'ti-clock',
  running: 'ti-loader animate-spin',
  completed: 'ti-circle-check',
  failed: 'ti-circle-x',
  skipped: 'ti-arrow-forward',
}

const STEP_STATUS_COLOR: Record<StepStatus, string> = {
  pending: 'text-text3',
  running: 'text-accent',
  completed: 'text-green',
  failed: 'text-red',
  skipped: 'text-text3',
}

const STEP_TYPE_ICON: Record<string, string> = {
  shell: 'ti-terminal-2',
  ssh: 'ti-network',
  playbook: 'ti-script',
  agent: 'ti-robot',
  approval: 'ti-user-check',
  condition: 'ti-git-branch',
  parallel: 'ti-arrows-split',
  notify: 'ti-bell',
  http: 'ti-world',
  delay: 'ti-hourglass',
}

function parseJsonSafe<T>(raw: string | null | undefined, fallback: T): T {
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

/* ─── 内置模板 ─── */

const TEMPLATES = [
  {
    id: 'server-init',
    name: '服务器初始化',
    icon: 'ti-server',
    yaml: `name: server-init
display_name: 服务器初始化流水线
description: 新机器上架全流程
version: 1
timeout: 3600

trigger:
  type: manual

params:
  - name: target_server
    type: string
    required: true
    description: 目标服务器 ID

steps:
  - id: check
    type: ssh
    name: 连通性检查
    host: "{{params.target_server}}"
    command: "echo ok"
    timeout: 30
  - id: setup
    type: playbook
    name: 系统基础配置
    playbook_id: "system-init-template"
  - id: install
    type: parallel
    name: 并行安装服务
    branches:
      - id: install-docker
        type: shell
        command: "curl -fsSL https://get.docker.com | sh"
      - id: install-nginx
        type: shell
        command: "apt-get install -y nginx"
  - id: verify
    type: agent
    name: AI 健康验证
    prompt: "检查服务状态，确认所有组件正常运行"
  - id: approve
    type: approval
    name: 管理员确认
    assignee: admin
    timeout: 3600
  - id: notify
    type: notify
    name: 完成通知
    channel: telegram
    message: "服务器初始化完成"
`,
  },
  {
    id: 'fault-heal',
    name: '故障自愈',
    icon: 'ti-heartbeat',
    yaml: `name: fault-heal
display_name: 故障自愈流水线
description: 告警触发 → AI 诊断 → 审批 → 自动修复 → 验证
version: 1
timeout: 1800

trigger:
  type: alert

params:
  - name: alert_id
    type: string
    required: true
    description: 触发告警 ID

steps:
  - id: diagnose
    type: agent
    name: AI 诊断根因
    prompt: "分析告警 {{params.alert_id}} 的根因并推荐修复方案"
    output_format: json
  - id: approve
    type: approval
    name: 确认修复方案
    assignee: admin
    timeout: 3600
  - id: fix
    type: playbook
    name: 执行修复
    playbook_id: "auto-fix"
  - id: wait
    type: delay
    name: 等待恢复
    seconds: 30
  - id: verify
    type: agent
    name: AI 验证恢复
    prompt: "检查告警是否已恢复"
  - id: notify
    type: notify
    name: 结果通知
    channel: telegram
    message: "故障自愈完成"
`,
  },
  {
    id: 'daily-patrol',
    name: '日常巡检',
    icon: 'ti-clipboard-check',
    yaml: `name: daily-patrol
display_name: 日常巡检流水线
description: 每日定时并行检查 → AI 汇总 → 条件通知
version: 1
timeout: 1800

trigger:
  type: cron
  cron: "0 8 * * *"

steps:
  - id: checks
    type: parallel
    name: 并行检查
    branches:
      - id: resource
        type: shell
        name: 资源检查
        command: "df -h && free -h && uptime"
      - id: security
        type: playbook
        name: 安全扫描
        playbook_id: "security-scan"
      - id: logs
        type: agent
        name: 日志分析
        prompt: "分析最近 24 小时的系统日志，找出异常"
  - id: summarize
    type: agent
    name: AI 汇总报告
    prompt: "汇总所有检查结果，生成巡检报告"
  - id: notify
    type: notify
    name: 发送报告
    channel: telegram
    message: "日常巡检完成"
`,
  },
  {
    id: 'security-scan',
    name: '安全扫描',
    icon: 'ti-shield-check',
    yaml: `name: security-scan
display_name: 安全扫描流水线
description: 合规检查 → 端口扫描 → SSH 审计 → AI 报告
version: 1
timeout: 3600

trigger:
  type: manual

steps:
  - id: compliance
    type: playbook
    name: 合规检查
    playbook_id: "compliance-check"
  - id: ports
    type: shell
    name: 端口扫描
    command: "ss -tlnp"
  - id: ssh-audit
    type: ssh
    name: SSH 审计
    host: localhost
    command: "grep -c 'Failed password' /var/log/auth.log || echo 0"
  - id: report
    type: agent
    name: AI 安全报告
    prompt: "根据扫描结果生成安全评估报告"
    output_format: json
  - id: severity
    type: condition
    name: 严重性判断
    expression: "{{steps.report.output.severity}} >= 'high'"
    on_true: approve
    on_false: notify
  - id: approve
    type: approval
    name: 高风险审批
    assignee: admin
    timeout: 3600
  - id: notify
    type: notify
    name: 通知
    channel: telegram
    message: "安全扫描完成"
`,
  },
]

/* ═══════════════════════════════════════════════════════
   SSE Hook for Pipeline Run Streaming
   ═══════════════════════════════════════════════════════ */

interface SSEStepEvent {
  step_id: string
  step_name?: string
  step_type?: string
  status?: StepStatus
  duration_ms?: number
  error?: string
  output_preview?: string
  assignee?: string
  timeout?: number
}

function usePipelineSSE(runId: string | null) {
  const [stepEvents, setStepEvents] = useState<Map<string, SSEStepEvent>>(new Map())
  const [connected, setConnected] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!runId) {
      setStepEvents(new Map())
      setConnected(false)
      return
    }

    const controller = new AbortController()
    controllerRef.current = controller

    const connect = async () => {
      try {
        const response = await fetch(`/api/pipelines/runs/${runId}/stream`, {
          credentials: 'include',
          signal: controller.signal,
        })
        if (!response.ok || !response.body) return

        setConnected(true)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) {
              currentEvent = ''
              continue
            }
            if (trimmed.startsWith('event:')) {
              currentEvent = trimmed.slice(6).trim()
              continue
            }
            if (!trimmed.startsWith('data:')) continue

            const dataStr = trimmed.slice(5).trim()
            if (!dataStr) continue
            try {
              const data = JSON.parse(dataStr) as SSEStepEvent & { run_id?: string; status?: string; total_duration?: number }
              if (currentEvent === 'step_start' || currentEvent === 'step_complete' || currentEvent === 'step_failed' || currentEvent === 'step_output' || currentEvent === 'approval_required') {
                setStepEvents((prev) => {
                  const next = new Map(prev)
                  const existing = next.get(data.step_id) ?? {}
                  next.set(data.step_id, { ...existing, ...data })
                  return next
                })
              }
              if (currentEvent === 'pipeline_complete') {
                setConnected(false)
              }
            } catch {
              // ignore invalid JSON
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
      } finally {
        setConnected(false)
      }
    }

    connect()

    return () => {
      controller.abort()
      controllerRef.current = null
    }
  }, [runId])

  return { stepEvents, connected }
}

/* ═══════════════════════════════════════════════════════
   Mermaid 渲染组件
   ═══════════════════════════════════════════════════════ */

function MermaidChart({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [rendered, setRendered] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function render() {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          themeVariables: {
            darkMode: true,
            background: '#1a1a2e',
            primaryColor: '#3b82f6',
            primaryTextColor: '#e2e8f0',
            lineColor: '#475569',
            secondaryColor: '#1e293b',
            tertiaryColor: '#0f172a',
          },
        })
        const id = 'mermaid-' + Math.random().toString(36).slice(2)
        const { svg } = await mermaid.render(id, code)
        if (!cancelled) {
          setRendered(svg)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '渲染失败')
          setRendered('')
        }
      }
    }

    if (code.trim()) {
      render()
    }

    return () => {
      cancelled = true
    }
  }, [code])

  if (error) {
    return (
      <div className="rounded-lg border border-red/30 bg-red/10 p-4 text-sm text-red">
        <i className="ti ti-alert-triangle mr-2" />
        Mermaid 渲染错误: {error}
      </div>
    )
  }

  if (!rendered) {
    return (
      <div className="flex items-center justify-center py-12 text-text3">
        <i className="ti ti-loader animate-spin mr-2" />
        渲染中...
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="overflow-auto rounded-lg bg-bg p-4 [&_svg]:mx-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: rendered }}
    />
  )
}

/* ═══════════════════════════════════════════════════════
   主页面
   ═══════════════════════════════════════════════════════ */

type DetailTab = 'edit' | 'preview' | 'history'

export default function PipelinesPage() {
  const queryClient = useQueryClient()

  // 状态
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<DetailTab>('edit')
  const [searchText, setSearchText] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editorContent, setEditorContent] = useState('')
  const [editorDirty, setEditorDirty] = useState(false)
  const [showRunModal, setShowRunModal] = useState(false)
  const [runParams, setRunParams] = useState<Record<string, string>>({})
  const [watchRunId, setWatchRunId] = useState<string | null>(null)

  // 验证 debounce
  const [validationResult, setValidationResult] = useState<{ valid: boolean; errors?: string[] } | null>(null)
  const validateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /* ─── Queries ─── */

  const { data: pipelinesRaw } = useQuery({
    queryKey: ['pipelines'],
    queryFn: () => pipelinesApi.list().then((r) => r.data),
    refetchInterval: 30_000,
  })
  const pipelines = useMemo(() => (Array.isArray(pipelinesRaw) ? pipelinesRaw : []), [pipelinesRaw])

  const selectedPipeline = useMemo(
    () => pipelines.find((p) => p.id === selectedId) ?? null,
    [pipelines, selectedId],
  )

  const { data: mermaidRaw } = useQuery({
    queryKey: ['pipeline-mermaid', selectedId],
    queryFn: () => (selectedId ? pipelinesApi.getMermaid(selectedId).then((r) => r.data) : null),
    enabled: !!selectedId && detailTab === 'preview',
  })

  const { data: runsRaw } = useQuery({
    queryKey: ['pipeline-runs', selectedId],
    queryFn: () =>
      selectedId
        ? pipelinesApi.listRuns({ pipeline_id: selectedId, limit: 50 }).then((r) => r.data)
        : [],
    enabled: !!selectedId,
    refetchInterval: 10_000,
  })
  const runs = useMemo(() => (Array.isArray(runsRaw) ? runsRaw : []), [runsRaw])

  const { data: watchRunRaw } = useQuery({
    queryKey: ['pipeline-run', watchRunId],
    queryFn: () => (watchRunId ? pipelinesApi.getRun(watchRunId).then((r) => r.data) : null),
    enabled: !!watchRunId,
    refetchInterval: 5_000,
  })
  const watchRun = watchRunRaw ?? null

  const { data: runLogsRaw } = useQuery({
    queryKey: ['pipeline-run-logs', watchRunId],
    queryFn: () => (watchRunId ? pipelinesApi.getRunLogs(watchRunId).then((r) => r.data) : []),
    enabled: !!watchRunId,
    refetchInterval: 5_000,
  })
  const runLogs = useMemo(() => (Array.isArray(runLogsRaw) ? runLogsRaw : []), [runLogsRaw])

  // SSE streaming
  const activeRunId = useMemo(() => {
    if (watchRun?.status === 'running' || watchRun?.status === 'paused') return watchRunId
    return null
  }, [watchRun, watchRunId])
  const { stepEvents, connected: sseConnected } = usePipelineSSE(activeRunId)

  /* ─── Mutations ─── */

  const createMutation = useMutation({
    mutationFn: (yaml: string) => pipelinesApi.create(yaml).then((r) => r.data),
    onSuccess: (data) => {
      toast.success('Pipeline 创建成功')
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setSelectedId(data.id)
      setShowCreateModal(false)
    },
    onError: (e) => toast.error(getErrorMessage(e, '创建失败')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, yaml }: { id: string; yaml: string }) =>
      pipelinesApi.update(id, yaml).then((r) => r.data),
    onSuccess: () => {
      toast.success('已保存')
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setEditorDirty(false)
    },
    onError: (e) => toast.error(getErrorMessage(e, '保存失败')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => pipelinesApi.delete(id),
    onSuccess: () => {
      toast.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['pipelines'] })
      setSelectedId(null)
    },
    onError: (e) => toast.error(getErrorMessage(e, '删除失败')),
  })

  const runMutation = useMutation({
    mutationFn: ({ id, params }: { id: string; params: Record<string, unknown> }) =>
      pipelinesApi.run(id, params).then((r) => r.data),
    onSuccess: (data) => {
      toast.success('Pipeline 已触发')
      setWatchRunId(data.run_id)
      setShowRunModal(false)
      queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] })
    },
    onError: (e) => toast.error(getErrorMessage(e, '触发失败')),
  })

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => pipelinesApi.cancelRun(runId),
    onSuccess: () => {
      toast.success('已取消')
      queryClient.invalidateQueries({ queryKey: ['pipeline-runs'] })
      queryClient.invalidateQueries({ queryKey: ['pipeline-run', watchRunId] })
    },
    onError: (e) => toast.error(getErrorMessage(e, '取消失败')),
  })

  const approveMutation = useMutation({
    mutationFn: (runId: string) => pipelinesApi.approveRun(runId),
    onSuccess: () => {
      toast.success('已批准')
      queryClient.invalidateQueries({ queryKey: ['pipeline-run', watchRunId] })
    },
    onError: (e) => toast.error(getErrorMessage(e, '审批失败')),
  })

  const rejectMutation = useMutation({
    mutationFn: (runId: string) => pipelinesApi.rejectRun(runId),
    onSuccess: () => {
      toast.success('已拒绝')
      queryClient.invalidateQueries({ queryKey: ['pipeline-run', watchRunId] })
    },
    onError: (e) => toast.error(getErrorMessage(e, '拒绝失败')),
  })

  /* ─── Effects ─── */

  // Sync editor content when pipeline changes
  useEffect(() => {
    if (selectedPipeline) {
      setEditorContent(selectedPipeline.yaml_content)
      setEditorDirty(false)
      setValidationResult(null)
    }
  }, [selectedPipeline])

  // Debounced validation
  const triggerValidation = useCallback(
    (yaml: string) => {
      if (validateTimerRef.current) clearTimeout(validateTimerRef.current)
      validateTimerRef.current = setTimeout(async () => {
        try {
          const res = await pipelinesApi.validate(yaml)
          setValidationResult(res.data)
        } catch {
          setValidationResult({ valid: false, errors: ['验证请求失败'] })
        }
      }, 500)
    },
    [],
  )

  // Filtered pipelines
  const filteredPipelines = useMemo(() => {
    if (!searchText.trim()) return pipelines
    const q = searchText.toLowerCase()
    return pipelines.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q) ||
        p.description?.toLowerCase().includes(q),
    )
  }, [pipelines, searchText])

  // Merge SSE step events with polled logs for the run panel
  const mergedSteps = useMemo(() => {
    const steps = parseJsonSafe<StepDefinition[]>(selectedPipeline?.steps_json, [])
    return steps.map((step) => {
      const log = runLogs.find((l) => l.step_id === step.id)
      const sse = stepEvents.get(step.id)
      const status: StepStatus = (sse?.status as StepStatus) ?? (log?.status as StepStatus) ?? 'pending'
      return {
        ...step,
        status,
        duration_ms: sse?.duration_ms ?? log?.duration_ms ?? null,
        error: sse?.error ?? log?.error ?? null,
        output_preview: sse?.output_preview ?? null,
        assignee: sse?.assignee ?? null,
      }
    })
  }, [selectedPipeline?.steps_json, runLogs, stepEvents])

  /* ═══════════════════════════════════════════════════════
     Render
     ═══════════════════════════════════════════════════════ */

  return (
    <div className="flex h-[calc(100vh-3.5rem)] gap-0 overflow-hidden">
      {/* ─── 左栏: Pipeline 列表 ─── */}
      <div className="flex w-[200px] shrink-0 flex-col border-r border-border bg-bg">
        <div className="border-b border-border p-3">
          <div className="relative">
            <i className="ti ti-search absolute left-2.5 top-2.5 text-sm text-text3" />
            <input
              type="text"
              placeholder="搜索..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full rounded-lg border border-border bg-bg2 py-2 pl-8 pr-3 text-sm text-text placeholder:text-text3 focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {filteredPipelines.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setSelectedId(p.id)
                setDetailTab('edit')
              }}
              className={cn(
                'mb-1 flex w-full flex-col items-start rounded-lg px-3 py-2.5 text-left transition-colors',
                p.id === selectedId
                  ? 'bg-accent-dim text-accent'
                  : 'text-text2 hover:bg-bg2 hover:text-text',
              )}
            >
              <div className="flex w-full items-center gap-2">
                <span
                  className={cn(
                    'h-2 w-2 shrink-0 rounded-full',
                    p.enabled ? 'bg-green' : 'bg-text3',
                  )}
                />
                <span className="truncate text-sm font-medium">
                  {p.display_name || p.name}
                </span>
              </div>
              <span className="mt-0.5 text-xs text-text3">v{p.version}</span>
            </button>
          ))}
          {filteredPipelines.length === 0 && (
            <div className="py-8 text-center text-sm text-text3">
              {searchText ? '无匹配结果' : '暂无 Pipeline'}
            </div>
          )}
        </div>

        <div className="border-t border-border p-3">
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90"
          >
            <i className="ti ti-plus text-base" />
            新建 Pipeline
          </button>
        </div>
      </div>

      {/* ─── 中栏: 详情面板 ─── */}
      <div className="flex min-w-0 flex-1 flex-col bg-bg">
        {selectedPipeline ? (
          <>
            {/* Tab 栏 */}
            <div className="flex items-center gap-1 border-b border-border px-4 py-2">
              <h2 className="mr-4 truncate text-base font-semibold text-text">
                {selectedPipeline.display_name || selectedPipeline.name}
              </h2>
              {(['edit', 'preview', 'history'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setDetailTab(t)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-sm transition-colors',
                    detailTab === t
                      ? 'bg-accent-dim text-accent'
                      : 'text-text2 hover:bg-bg2 hover:text-text',
                  )}
                >
                  {t === 'edit' ? '编辑' : t === 'preview' ? '预览' : '历史'}
                </button>
              ))}
              <div className="flex-1" />
              <button
                type="button"
                onClick={() => {
                  if (confirm('确定删除此 Pipeline？')) {
                    deleteMutation.mutate(selectedPipeline.id)
                  }
                }}
                className="rounded-lg px-2 py-1.5 text-sm text-red transition-colors hover:bg-red/10"
              >
                <i className="ti ti-trash" />
              </button>
            </div>

            {/* Tab 内容 */}
            <div className="flex-1 overflow-y-auto">
              {detailTab === 'edit' && (
                <EditTab
                  content={editorContent}
                  dirty={editorDirty}
                  validation={validationResult}
                  saving={updateMutation.isPending}
                  onChange={(val) => {
                    setEditorContent(val)
                    setEditorDirty(true)
                    triggerValidation(val)
                  }}
                  onSave={() =>
                    updateMutation.mutate({ id: selectedPipeline.id, yaml: editorContent })
                  }
                />
              )}
              {detailTab === 'preview' && (
                <PreviewTab
                  pipeline={selectedPipeline}
                  mermaidCode={mermaidRaw?.mermaid ?? null}
                  onRun={() => {
                    setRunParams({})
                    setShowRunModal(true)
                  }}
                />
              )}
              {detailTab === 'history' && (
                <HistoryTab
                  runs={runs}
                  onSelectRun={(runId) => setWatchRunId(runId)}
                  activeRunId={watchRunId}
                />
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center text-text3">
              <i className="ti ti-git-merge mb-3 block text-4xl" />
              <p className="text-sm">选择一个 Pipeline 或创建新的</p>
            </div>
          </div>
        )}
      </div>

      {/* ─── 右栏: 运行监控 ─── */}
      <div className="flex w-[350px] shrink-0 flex-col border-l border-border bg-bg">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <i className="ti ti-player-play text-base text-accent" />
          <span className="text-sm font-semibold text-text">运行监控</span>
          {sseConnected && (
            <span className="ml-auto flex items-center gap-1 text-xs text-green">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green" />
              实时
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {watchRun ? (
            <RunPanel
              run={watchRun}
              steps={mergedSteps}
              onCancel={() => cancelMutation.mutate(watchRun.id)}
              onApprove={() => approveMutation.mutate(watchRun.id)}
              onReject={() => rejectMutation.mutate(watchRun.id)}
              cancelPending={cancelMutation.isPending}
              approvePending={approveMutation.isPending}
              rejectPending={rejectMutation.isPending}
            />
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-text3">
              <i className="ti ti-eye-off mb-3 text-3xl" />
              <p className="text-sm">暂无运行中的实例</p>
              <p className="mt-1 text-xs">触发 Pipeline 后在此查看实时进度</p>
            </div>
          )}
        </div>
      </div>

      {/* ─── Modals ─── */}
      {showCreateModal && (
        <CreateModal
          onClose={() => setShowCreateModal(false)}
          onCreate={(yaml) => createMutation.mutate(yaml)}
          creating={createMutation.isPending}
        />
      )}

      {showRunModal && selectedPipeline && (
        <RunModal
          pipeline={selectedPipeline}
          params={runParams}
          onParamChange={(k, v) => setRunParams((prev) => ({ ...prev, [k]: v }))}
          onRun={() =>
            runMutation.mutate({ id: selectedPipeline.id, params: runParams })
          }
          onClose={() => setShowRunModal(false)}
          running={runMutation.isPending}
        />
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 编辑 Tab
   ═══════════════════════════════════════════════════════ */

function EditTab({
  content,
  dirty,
  validation,
  saving,
  onChange,
  onSave,
}: {
  content: string
  dirty: boolean
  validation: { valid: boolean; errors?: string[] } | null
  saving: boolean
  onChange: (val: string) => void
  onSave: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        {validation && (
          <span
            className={cn(
              'flex items-center gap-1 text-xs',
              validation.valid ? 'text-green' : 'text-red',
            )}
          >
            <i className={cn('ti', validation.valid ? 'ti-circle-check' : 'ti-circle-x')} />
            {validation.valid ? 'YAML 有效' : `${validation.errors?.length ?? 0} 个错误`}
          </span>
        )}
        <div className="flex-1" />
        <button
          type="button"
          disabled
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text3 opacity-50"
          title="即将推出"
        >
          <i className="ti ti-sparkles mr-1" />
          AI 生成
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty || saving}
          className={cn(
            'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
            dirty
              ? 'bg-accent text-white hover:bg-accent/90'
              : 'bg-bg2 text-text3',
          )}
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>

      {/* Editor area */}
      <div className="flex-1 overflow-auto p-0">
        <textarea
          value={content}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="h-full w-full resize-none border-none bg-[#0d1117] p-4 font-mono text-sm leading-relaxed text-[#c9d1d9] focus:outline-none"
          placeholder="# 在此编写 Pipeline YAML..."
        />
      </div>

      {/* Validation errors */}
      {validation && !validation.valid && validation.errors && (
        <div className="border-t border-red/30 bg-red/5 px-4 py-2">
          <div className="space-y-1">
            {validation.errors.map((err, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-red">
                <i className="ti ti-alert-circle mt-0.5 shrink-0" />
                <span>{err}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 预览 Tab
   ═══════════════════════════════════════════════════════ */

function PreviewTab({
  pipeline,
  mermaidCode,
  onRun,
}: {
  pipeline: Pipeline
  mermaidCode: string | null
  onRun: () => void
}) {
  const params = parseJsonSafe<PipelineParam[]>(pipeline.params_json, [])
  const trigger = parseJsonSafe<Record<string, unknown>>(pipeline.trigger_json, {})

  return (
    <div className="space-y-6 p-4">
      {/* Info */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-text3">版本</span>
          <p className="text-text">v{pipeline.version}</p>
        </div>
        <div>
          <span className="text-text3">触发方式</span>
          <p className="text-text">{(trigger.type as string) ?? 'manual'}</p>
        </div>
        <div>
          <span className="text-text3">超时</span>
          <p className="text-text">{pipeline.timeout}s</p>
        </div>
        <div>
          <span className="text-text3">最大并发</span>
          <p className="text-text">{pipeline.max_concurrent_runs}</p>
        </div>
      </div>

      {/* Mermaid */}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-text">流程图</h3>
        {mermaidCode ? (
          <MermaidChart code={mermaidCode} />
        ) : (
          <div className="rounded-lg border border-border bg-bg2 p-8 text-center text-sm text-text3">
            加载流程图...
          </div>
        )}
      </div>

      {/* Params table */}
      {params.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-text">参数定义</h3>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg2">
                  <th className="px-3 py-2 text-left font-medium text-text3">名称</th>
                  <th className="px-3 py-2 text-left font-medium text-text3">类型</th>
                  <th className="px-3 py-2 text-left font-medium text-text3">必填</th>
                  <th className="px-3 py-2 text-left font-medium text-text3">描述</th>
                </tr>
              </thead>
              <tbody>
                {params.map((p) => (
                  <tr key={p.name} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-mono text-accent">{p.name}</td>
                    <td className="px-3 py-2 text-text2">{p.type}</td>
                    <td className="px-3 py-2">{p.required ? '是' : '否'}</td>
                    <td className="px-3 py-2 text-text3">{p.description ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Run button */}
      <button
        type="button"
        onClick={onRun}
        className="flex items-center gap-2 rounded-lg bg-green px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green/90"
      >
        <i className="ti ti-player-play" />
        运行此 Pipeline
      </button>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 历史 Tab
   ═══════════════════════════════════════════════════════ */

function HistoryTab({
  runs,
  onSelectRun,
  activeRunId,
}: {
  runs: PipelineRun[]
  onSelectRun: (runId: string) => void
  activeRunId: string | null
}) {
  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text3">
        <i className="ti ti-history mb-3 text-3xl" />
        <p className="text-sm">暂无运行历史</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-bg2">
            <th className="px-4 py-2.5 text-left font-medium text-text3">状态</th>
            <th className="px-4 py-2.5 text-left font-medium text-text3">触发</th>
            <th className="px-4 py-2.5 text-left font-medium text-text3">开始时间</th>
            <th className="px-4 py-2.5 text-left font-medium text-text3">耗时</th>
            <th className="px-4 py-2.5 text-left font-medium text-text3">操作人</th>
            <th className="px-4 py-2.5 text-left font-medium text-text3">操作</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const durationMs =
              run.started_at && run.completed_at
                ? new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
                : null
            return (
              <tr
                key={run.id}
                className={cn(
                  'border-b border-border transition-colors',
                  run.id === activeRunId ? 'bg-accent-dim/30' : 'hover:bg-bg2',
                )}
              >
                <td className="px-4 py-2.5">
                  <span
                    className={cn(
                      'inline-block rounded-full px-2 py-0.5 text-xs font-medium',
                      RUN_STATUS_STYLES[run.status],
                    )}
                  >
                    {run.status}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-text2">{run.trigger_type}</td>
                <td className="px-4 py-2.5 text-text2">{formatDate(run.started_at)}</td>
                <td className="px-4 py-2.5 text-text2">{formatDuration(durationMs)}</td>
                <td className="px-4 py-2.5 text-text2">{run.started_by}</td>
                <td className="px-4 py-2.5">
                  <button
                    type="button"
                    onClick={() => onSelectRun(run.id)}
                    className="text-xs text-accent hover:underline"
                  >
                    {run.id === activeRunId ? '查看中' : '查看'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 运行面板 (右栏)
   ═══════════════════════════════════════════════════════ */

interface MergedStep {
  id: string
  type: string
  name: string
  status: StepStatus
  duration_ms: number | null
  error: string | null
  output_preview: string | null
  assignee: string | null
}

function RunPanel({
  run,
  steps,
  onCancel,
  onApprove,
  onReject,
  cancelPending,
  approvePending,
  rejectPending,
}: {
  run: PipelineRun
  steps: MergedStep[]
  onCancel: () => void
  onApprove: () => void
  onReject: () => void
  cancelPending: boolean
  approvePending: boolean
  rejectPending: boolean
}) {
  const isActive = run.status === 'running' || run.status === 'paused'

  return (
    <div className="space-y-3 p-4">
      {/* Run header */}
      <div className="flex items-center justify-between">
        <span
          className={cn(
            'rounded-full px-2.5 py-0.5 text-xs font-medium',
            RUN_STATUS_STYLES[run.status],
          )}
        >
          {run.status}
        </span>
        {isActive && (
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelPending}
            className="rounded-lg px-2.5 py-1 text-xs text-red transition-colors hover:bg-red/10"
          >
            {cancelPending ? '取消中...' : '取消运行'}
          </button>
        )}
      </div>

      <div className="text-xs text-text3">
        <span>触发: {run.trigger_type}</span>
        <span className="mx-2">|</span>
        <span>操作人: {run.started_by}</span>
      </div>

      {run.error && (
        <div className="rounded-lg border border-red/30 bg-red/10 p-3 text-xs text-red">
          <i className="ti ti-alert-circle mr-1" />
          {run.error}
        </div>
      )}

      {run.summary && (
        <div className="rounded-lg border border-border bg-bg2 p-3 text-xs text-text2">
          <i className="ti ti-file-text mr-1" />
          {run.summary}
        </div>
      )}

      {/* Step list */}
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-text3">步骤进度</h4>
        {steps.map((step) => {
          const icon = STEP_TYPE_ICON[step.type] ?? 'ti-point'
          const statusIcon = STEP_STATUS_ICON[step.status]
          const statusColor = STEP_STATUS_COLOR[step.status]
          const isApprovalWaiting = step.type === 'approval' && step.status === 'running'
          const isFailed = step.status === 'failed'

          return (
            <div
              key={step.id}
              className={cn(
                'rounded-lg border p-2.5 transition-colors',
                step.status === 'running'
                  ? 'border-accent/40 bg-accent-dim/20'
                  : step.status === 'failed'
                    ? 'border-red/30 bg-red/5'
                    : 'border-border bg-bg2',
              )}
            >
              <div className="flex items-center gap-2">
                <i className={cn('ti text-sm', icon, 'text-text3')} />
                <span className="flex-1 truncate text-xs font-medium text-text">
                  {step.name}
                </span>
                <i className={cn('ti text-sm', statusIcon, statusColor)} />
                {step.duration_ms != null && (
                  <span className="text-[10px] tabular-nums text-text3">
                    {formatDuration(step.duration_ms)}
                  </span>
                )}
              </div>

              {step.error && (
                <p className="mt-1.5 text-[11px] text-red">{step.error}</p>
              )}

              {step.output_preview && (
                <p className="mt-1 truncate text-[11px] text-text3">{step.output_preview}</p>
              )}

              {/* Approval buttons */}
              {isApprovalWaiting && (
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={onApprove}
                    disabled={approvePending}
                    className="rounded-md bg-green px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-green/90"
                  >
                    {approvePending ? '...' : '通过'}
                  </button>
                  <button
                    type="button"
                    onClick={onReject}
                    disabled={rejectPending}
                    className="rounded-md bg-red px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-red/90"
                  >
                    {rejectPending ? '...' : '拒绝'}
                  </button>
                </div>
              )}

              {/* Retry from this step (placeholder) */}
              {isFailed && (
                <button
                  type="button"
                  className="mt-2 text-[11px] text-accent hover:underline"
                  onClick={() => toast('从此步重试功能即将推出')}
                >
                  从此步重试
                </button>
              )}
            </div>
          )
        })}

        {steps.length === 0 && (
          <p className="py-4 text-center text-xs text-text3">无步骤信息</p>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 新建 Modal
   ═══════════════════════════════════════════════════════ */

function CreateModal({
  onClose,
  onCreate,
  creating,
}: {
  onClose: () => void
  onCreate: (yaml: string) => void
  creating: boolean
}) {
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [customYaml, setCustomYaml] = useState('')

  const handleCreate = () => {
    if (selectedTemplate) {
      const tpl = TEMPLATES.find((t) => t.id === selectedTemplate)
      if (tpl) {
        onCreate(tpl.yaml)
        return
      }
    }
    if (customYaml.trim()) {
      onCreate(customYaml)
      return
    }
    toast.error('请选择模板或输入 YAML')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-2xl rounded-xl border border-border bg-bg shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-base font-semibold text-text">新建 Pipeline</h3>
          <button type="button" onClick={onClose} className="text-text3 hover:text-text">
            <i className="ti ti-x text-lg" />
          </button>
        </div>

        <div className="p-6">
          <p className="mb-4 text-sm text-text3">选择模板或从空白开始</p>

          <div className="grid grid-cols-3 gap-3">
            {TEMPLATES.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                onClick={() => {
                  setSelectedTemplate(tpl.id)
                  setCustomYaml('')
                }}
                className={cn(
                  'flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors',
                  selectedTemplate === tpl.id
                    ? 'border-accent bg-accent-dim text-accent'
                    : 'border-border bg-bg2 text-text2 hover:border-text3',
                )}
              >
                <i className={cn('ti text-2xl', tpl.icon)} />
                <span className="text-sm font-medium">{tpl.name}</span>
              </button>
            ))}

            {/* Blank template */}
            <button
              type="button"
              onClick={() => {
                setSelectedTemplate(null)
                setCustomYaml(`name: my-pipeline
display_name: 我的流水线
description: 描述
version: 1
timeout: 3600

trigger:
  type: manual

params: []

steps:
  - id: step-1
    type: shell
    name: 第一步
    command: echo "hello"
`)
              }}
              className={cn(
                'flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors',
                !selectedTemplate && customYaml
                  ? 'border-accent bg-accent-dim text-accent'
                  : 'border-border bg-bg2 text-text2 hover:border-text3',
              )}
            >
              <i className="ti ti-plus text-2xl" />
              <span className="text-sm font-medium">空白 Pipeline</span>
            </button>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text2 transition-colors hover:bg-bg2"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating || (!selectedTemplate && !customYaml.trim())}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50"
          >
            {creating ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════
   子组件: 运行参数 Modal
   ═══════════════════════════════════════════════════════ */

function RunModal({
  pipeline,
  params,
  onParamChange,
  onRun,
  onClose,
  running,
}: {
  pipeline: Pipeline
  params: Record<string, string>
  onParamChange: (key: string, value: string) => void
  onRun: () => void
  onClose: () => void
  running: boolean
}) {
  const paramDefs = parseJsonSafe<PipelineParam[]>(pipeline.params_json, [])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-md rounded-xl border border-border bg-bg shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-base font-semibold text-text">
            运行: {pipeline.display_name || pipeline.name}
          </h3>
          <button type="button" onClick={onClose} className="text-text3 hover:text-text">
            <i className="ti ti-x text-lg" />
          </button>
        </div>

        <div className="space-y-4 p-6">
          {paramDefs.length === 0 ? (
            <p className="text-sm text-text3">此 Pipeline 无需参数</p>
          ) : (
            paramDefs.map((def) => (
              <div key={def.name}>
                <label className="mb-1 block text-sm font-medium text-text">
                  {def.name}
                  {def.required && <span className="ml-0.5 text-red">*</span>}
                </label>
                {def.description && (
                  <p className="mb-1 text-xs text-text3">{def.description}</p>
                )}
                <input
                  type={def.type === 'secret' ? 'password' : 'text'}
                  value={params[def.name] ?? (def.default != null ? String(def.default) : '')}
                  onChange={(e) => onParamChange(def.name, e.target.value)}
                  placeholder={def.type}
                  className="w-full rounded-lg border border-border bg-bg2 px-3 py-2 text-sm text-text placeholder:text-text3 focus:border-accent focus:outline-none"
                />
              </div>
            ))
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text2 transition-colors hover:bg-bg2"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onRun}
            disabled={running}
            className="rounded-lg bg-green px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green/90 disabled:opacity-50"
          >
            {running ? '启动中...' : '开始运行'}
          </button>
        </div>
      </div>
    </div>
  )
}

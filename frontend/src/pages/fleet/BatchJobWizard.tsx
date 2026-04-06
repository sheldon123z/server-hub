/**
 * BatchJobWizard — 批量操作创建向导（3 步）
 * Step 1: 选择服务器
 * Step 2: 选择操作（模板从后端动态加载，失败时 fallback 到硬编码预设）
 * Step 3: 执行策略 + 确认
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import { fetchBatchTemplates, type BatchTemplate } from '@/api/batch'
import toast from 'react-hot-toast'
import { cn, getErrorMessage } from '@/lib/utils'
import ServerSelector from './ServerSelector'

// ---------------------------------------------------------------------------
// 规范化的展示型 Preset（统一后端模板 + 硬编码 fallback）
// ---------------------------------------------------------------------------
interface Preset {
  id: string
  name: string
  description: string
  type: 'command' | 'service_action' | 'docker_action' | 'script' | 'playbook'
  defaultPayload: Record<string, string>
  defaultStrategy: Strategy
  defaultBatchSize: number
  icon: string
  isCustom?: boolean
  requiresServiceName?: boolean
  isBuiltin?: boolean
}

/** 从后端 BatchTemplate 转换为展示型 Preset */
function templateToPreset(t: BatchTemplate): Preset {
  const icon = iconForType(t.type)
  const isServiceAction = t.type === 'service_action'
  return {
    id: t.id,
    name: t.name,
    description: t.description ?? '',
    type: t.type,
    defaultPayload: t.payload as Record<string, string>,
    defaultStrategy: t.strategy,
    defaultBatchSize: t.rolling_batch_size,
    icon,
    requiresServiceName: isServiceAction,
    isBuiltin: t.is_builtin,
  }
}

function iconForType(type: string): string {
  switch (type) {
    case 'command': return 'ti-terminal-2'
    case 'service_action': return 'ti-refresh'
    case 'docker_action': return 'ti-brand-docker'
    case 'script': return 'ti-shield-check'
    case 'playbook': return 'ti-list-check'
    default: return 'ti-server-2'
  }
}

/** 硬编码 fallback（后端不可用时使用） */
const FALLBACK_PRESETS: Preset[] = [
  {
    id: 'sys_info',
    name: '批量系统信息',
    description: '采集 CPU、内存、磁盘信息',
    type: 'command',
    defaultPayload: { command: 'uname -a && free -h && df -h' },
    defaultStrategy: 'parallel',
    defaultBatchSize: 1,
    icon: 'ti-server-2',
    isBuiltin: true,
  },
  {
    id: 'docker_prune',
    name: '批量 Docker 清理',
    description: '清理未使用容器、镜像和卷',
    type: 'docker_action',
    defaultPayload: { action: 'prune' },
    defaultStrategy: 'parallel',
    defaultBatchSize: 1,
    icon: 'ti-brand-docker',
    isBuiltin: true,
  },
  {
    id: 'security_check',
    name: '批量安全检查',
    description: '运行安全审计脚本',
    type: 'script',
    defaultPayload: { script: 'security_check' },
    defaultStrategy: 'parallel',
    defaultBatchSize: 1,
    icon: 'ti-shield-check',
    isBuiltin: true,
  },
  {
    id: 'service_restart',
    name: '批量服务重启',
    description: '滚动重启指定 systemd 服务',
    type: 'service_action',
    defaultPayload: { action: 'restart', service: '' },
    defaultStrategy: 'rolling',
    defaultBatchSize: 1,
    icon: 'ti-refresh',
    requiresServiceName: true,
    isBuiltin: true,
  },
  {
    id: 'custom',
    name: '自定义命令',
    description: '执行任意 Shell 命令',
    type: 'command',
    defaultPayload: { command: '' },
    defaultStrategy: 'parallel',
    defaultBatchSize: 1,
    icon: 'ti-terminal-2',
    isCustom: true,
  },
]

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------
type Strategy = 'parallel' | 'serial' | 'rolling'
type Step = 1 | 2 | 3

interface CreateJobPayload {
  name: string
  type: string
  payload: Record<string, string>
  server_ids: string[]
  strategy: Strategy
  rolling_batch_size: number
  stop_on_failure: boolean
}

interface BatchJobWizardProps {
  initialPresetId?: string
  onClose: () => void
  onCreated: (jobId: string) => void
}

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------
export default function BatchJobWizard({
  initialPresetId = '',
  onClose,
  onCreated,
}: BatchJobWizardProps) {
  const queryClient = useQueryClient()

  const [step, setStep] = useState<Step>(1)
  const [selectedServers, setSelectedServers] = useState<string[]>([])
  const [presetId, setPresetId] = useState<string>(initialPresetId)
  const [customCommand, setCustomCommand] = useState('')
  const [serviceName, setServiceName] = useState('')
  const [strategy, setStrategy] = useState<Strategy>('parallel')
  const [rollingBatchSize, setRollingBatchSize] = useState(1)
  const [stopOnFailure, setStopOnFailure] = useState(false)
  const [jobName, setJobName] = useState('')

  // 从后端动态加载模板，失败时 fallback 到硬编码预设
  const {
    data: remoteTemplates,
    isLoading: templatesLoading,
    isError: templatesFailed,
  } = useQuery({
    queryKey: ['batch-templates'],
    queryFn: fetchBatchTemplates,
    staleTime: 5 * 60 * 1000, // 5 分钟缓存
    retry: 1,
  })

  // 始终在列表末尾追加"自定义命令"选项
  const CUSTOM_PRESET: Preset = {
    id: 'custom',
    name: '自定义命令',
    description: '执行任意 Shell 命令',
    type: 'command',
    defaultPayload: { command: '' },
    defaultStrategy: 'parallel',
    defaultBatchSize: 1,
    icon: 'ti-terminal-2',
    isCustom: true,
  }

  const presets: Preset[] = templatesFailed || (!templatesLoading && !remoteTemplates)
    ? FALLBACK_PRESETS
    : remoteTemplates
      ? [...remoteTemplates.map(templateToPreset), CUSTOM_PRESET]
      : []

  const preset = presets.find((p) => p.id === presetId)

  const createMut = useMutation({
    mutationFn: (data: CreateJobPayload) =>
      client.post('/api/servers/batch/execute', data),
    onSuccess: (res) => {
      toast.success('批量任务已创建')
      queryClient.invalidateQueries({ queryKey: ['batch-history'] })
      const jobId: string = (res.data as Record<string, string>).job_id ?? (res.data as Record<string, string>).id
      onCreated(jobId)
    },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '创建失败')),
  })

  // ---------------------------------------------------------------------------
  // 步骤导航
  // ---------------------------------------------------------------------------
  const nextStep = () => setStep((s) => (s < 3 ? ((s + 1) as Step) : s))
  const prevStep = () => setStep((s) => (s > 1 ? ((s - 1) as Step) : s))

  const canNext1 = selectedServers.length > 0
  const canNext2 =
    !!presetId &&
    (preset?.isCustom === true ? customCommand.trim().length > 0 : true) &&
    (preset?.requiresServiceName === true ? serviceName.trim().length > 0 : true)

  // ---------------------------------------------------------------------------
  // 提交
  // ---------------------------------------------------------------------------
  const handleCreate = () => {
    if (!preset) return
    const payload: Record<string, string> = { ...preset.defaultPayload }
    if (preset.isCustom) payload.command = customCommand
    if (preset.requiresServiceName) payload.service = serviceName

    const name =
      jobName.trim() ||
      `${preset.name} — ${new Date().toLocaleString('zh-CN', { hour12: false })}`

    createMut.mutate({
      name,
      type: preset.type,
      payload,
      server_ids: selectedServers,
      strategy,
      rolling_batch_size: rollingBatchSize,
      stop_on_failure: stopOnFailure,
    })
  }

  const strategyLabel: Record<Strategy, string> = {
    parallel: '并行',
    serial: '串行',
    rolling: `滚动 (每批 ${rollingBatchSize})`,
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-bg border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between p-5 border-b border-border shrink-0">
          <div>
            <h2 className="text-base font-semibold text-text">创建批量操作</h2>
            <p className="text-xs text-text3 mt-0.5">
              步骤 {step}/3 —{' '}
              {step === 1 ? '选择服务器' : step === 2 ? '选择操作' : '确认策略'}
            </p>
          </div>
          <button onClick={onClose} className="text-text3 hover:text-text p-1">
            <i className="ti ti-x text-lg" />
          </button>
        </div>

        {/* ── Step indicators ── */}
        <div className="flex items-center px-5 pt-4 shrink-0">
          {([1, 2, 3] as Step[]).map((s) => (
            <div key={s} className="flex items-center flex-1 last:flex-none last:flex-initial">
              <div
                className={cn(
                  'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0',
                  step === s
                    ? 'bg-accent text-[#0f172a]'
                    : step > s
                      ? 'bg-green text-white'
                      : 'bg-bg2 text-text3',
                )}
              >
                {step > s ? <i className="ti ti-check text-xs" /> : s}
              </div>
              {s < 3 && (
                <div
                  className={cn('flex-1 h-0.5 mx-2', step > s ? 'bg-green' : 'bg-border')}
                />
              )}
            </div>
          ))}
        </div>

        {/* ── Content ── */}
        <div className="flex-1 overflow-y-auto p-5">
          {/* Step 1: 选择服务器 */}
          {step === 1 && (
            <ServerSelector selected={selectedServers} onChange={setSelectedServers} />
          )}

          {/* Step 2: 选择操作 */}
          {step === 2 && (
            <div className="space-y-4">
              {/* 加载骨架屏 */}
              {templatesLoading && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-[72px] rounded-lg border border-border bg-bg2 animate-pulse"
                    />
                  ))}
                </div>
              )}

              {/* 加载失败提示 */}
              {templatesFailed && (
                <div className="flex items-center gap-2 text-xs text-yellow-400 bg-yellow-400/10 border border-yellow-400/20 rounded-md px-3 py-2">
                  <i className="ti ti-alert-triangle text-sm" />
                  <span>无法从服务器加载模板，已使用内置预设</span>
                </div>
              )}

              {/* 模板列表 */}
              {!templatesLoading && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {presets.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setPresetId(p.id)
                        setStrategy(p.defaultStrategy)
                        setRollingBatchSize(p.defaultBatchSize)
                      }}
                      className={cn(
                        'flex items-start gap-3 p-4 rounded-lg border text-left transition-all',
                        presetId === p.id
                          ? 'border-accent bg-accent-dim'
                          : 'border-border bg-bg2 hover:border-border-light',
                      )}
                    >
                      <i
                        className={cn(
                          p.icon,
                          'ti text-xl mt-0.5 shrink-0',
                          presetId === p.id ? 'text-accent' : 'text-text3',
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium text-text truncate">{p.name}</span>
                          {!p.isCustom && (
                            <span
                              className={cn(
                                'shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium',
                                p.isBuiltin
                                  ? 'bg-blue-500/15 text-blue-400'
                                  : 'bg-purple-500/15 text-purple-400',
                              )}
                            >
                              {p.isBuiltin ? '内置' : '自定义'}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-text3 mt-0.5 line-clamp-2">{p.description}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}


              {/* 自定义命令输入 */}
              {preset?.isCustom && (
                <div>
                  <label className="text-xs text-text3 block mb-1">Shell 命令</label>
                  <textarea
                    value={customCommand}
                    onChange={(e) => setCustomCommand(e.target.value)}
                    rows={3}
                    placeholder="e.g. uptime && free -h"
                    className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text font-mono placeholder:text-text3 focus:outline-none focus:border-accent resize-none"
                  />
                </div>
              )}

              {/* 服务名称输入 */}
              {preset?.requiresServiceName && (
                <div>
                  <label className="text-xs text-text3 block mb-1">服务名称</label>
                  <input
                    value={serviceName}
                    onChange={(e) => setServiceName(e.target.value)}
                    placeholder="e.g. nginx"
                    className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
                  />
                </div>
              )}
            </div>
          )}

          {/* Step 3: 策略 + 确认 */}
          {step === 3 && (
            <div className="space-y-5">
              {/* 任务名称 */}
              <div>
                <label className="text-xs text-text3 block mb-1">任务名称（可选）</label>
                <input
                  value={jobName}
                  onChange={(e) => setJobName(e.target.value)}
                  placeholder={`${preset?.name ?? '批量任务'} — 将自动生成时间戳`}
                  className="w-full bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
                />
              </div>

              {/* 执行策略 */}
              <div>
                <label className="text-xs text-text3 block mb-2">执行策略</label>
                <div className="grid grid-cols-3 gap-2">
                  {(['parallel', 'serial', 'rolling'] as Strategy[]).map((s) => (
                    <button
                      key={s}
                      onClick={() => setStrategy(s)}
                      className={cn(
                        'p-3 rounded-lg border text-left transition-all',
                        strategy === s
                          ? 'border-accent bg-accent-dim'
                          : 'border-border bg-bg2 hover:border-border-light',
                      )}
                    >
                      <div className="text-sm font-medium text-text mb-1">
                        {s === 'parallel' ? '并行' : s === 'serial' ? '串行' : '滚动'}
                      </div>
                      <div className="text-[10px] text-text3">
                        {s === 'parallel'
                          ? '全部同时执行'
                          : s === 'serial'
                            ? '逐台顺序执行'
                            : '分批滚动执行'}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 滚动批次大小 */}
              {strategy === 'rolling' && (
                <div>
                  <label className="text-xs text-text3 block mb-1">每批服务器数</label>
                  <input
                    type="number"
                    min={1}
                    max={selectedServers.length}
                    value={rollingBatchSize}
                    onChange={(e) =>
                      setRollingBatchSize(Math.max(1, Number(e.target.value)))
                    }
                    className="w-24 bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
                  />
                </div>
              )}

              {/* 选项 */}
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={stopOnFailure}
                  onChange={(e) => setStopOnFailure(e.target.checked)}
                  className="rounded border-border bg-bg text-accent"
                />
                <span className="text-text2">失败时停止后续服务器</span>
              </label>

              {/* 摘要 */}
              <div className="bg-bg2 border border-border rounded-lg p-4 text-xs space-y-2">
                <div className="text-[10px] text-text3 uppercase tracking-wider mb-3">
                  执行摘要
                </div>
                <SummaryRow label="操作" value={preset?.name ?? '-'} />
                <SummaryRow label="服务器" value={`${selectedServers.length} 台`} />
                <SummaryRow label="策略" value={strategyLabel[strategy]} />
                {preset?.isCustom && (
                  <SummaryRow label="命令" value={customCommand} mono />
                )}
                {preset?.requiresServiceName && (
                  <SummaryRow label="服务" value={serviceName} mono />
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between p-5 border-t border-border shrink-0">
          <button
            onClick={step === 1 ? onClose : prevStep}
            className="px-4 py-2 text-sm text-text2 border border-border rounded-md hover:text-text"
          >
            {step === 1 ? '取消' : '上一步'}
          </button>

          {step < 3 ? (
            <button
              onClick={nextStep}
              disabled={step === 1 ? !canNext1 : !canNext2}
              className="px-4 py-2 text-sm bg-accent text-[#0f172a] rounded-md font-medium disabled:opacity-40"
            >
              下一步
            </button>
          ) : (
            <button
              onClick={handleCreate}
              disabled={createMut.isPending}
              className="px-4 py-2 text-sm bg-accent text-[#0f172a] rounded-md font-medium disabled:opacity-40"
            >
              {createMut.isPending ? '创建中...' : '开始执行'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 摘要行
// ---------------------------------------------------------------------------
function SummaryRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-text3 shrink-0">{label}</span>
      <span
        className={cn(
          'text-text text-right truncate max-w-[260px]',
          mono && 'font-mono text-accent text-[11px]',
        )}
        title={value}
      >
        {value}
      </span>
    </div>
  )
}

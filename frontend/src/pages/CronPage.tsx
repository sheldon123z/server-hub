import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { useServerStore } from '@/stores/serverStore'

/* ---------- types ---------- */

/** 定时任务条目 */
interface CronJob {
  /** Cron 表达式（如 "每5分钟" 的标准格式） */
  schedule: string
  /** 要执行的命令 */
  command: string
  /** 是否启用 */
  enabled: boolean
  /** 备注 */
  comment: string
  /** 人类可读的调度描述 */
  description?: string
}

/** Cron 任务列表响应 */
interface CronListResponse {
  /** 任务列表 */
  jobs: CronJob[]
  /** 所属用户 */
  user: string
}

/** Cron 表达式验证结果 */
interface ValidateResult {
  /** 表达式是否有效 */
  valid: boolean
  /** 人类可读描述 (如 "每5分钟") */
  description: string
  /** 未来 5 次执行时间 */
  next_runs: string[]
}

/** Cron 执行历史记录 */
interface HistoryEntry {
  /** 执行时间 */
  timestamp: string
  /** 执行用户 */
  user: string
  /** 执行的命令 */
  command: string
}

/* ---------- constants ---------- */

const SCHEDULE_PRESETS = [
  { label: '每分钟', value: '* * * * *' },
  { label: '每5分钟', value: '*/5 * * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '每天零点', value: '0 0 * * *' },
  { label: '每周日3点', value: '0 3 * * 0' },
  { label: '每月1号', value: '0 0 1 * *' },
] as const

/* ---------- sub-components ---------- */

/** Cron 任务统计概览卡片 */
function StatCards({ userJobs, rootJobs }: { userJobs: CronJob[]; rootJobs: CronJob[] }) {
  const userCount = userJobs.length
  const rootCount = rootJobs.length
  const enabledCount = [...userJobs, ...rootJobs].filter((j) => j.enabled).length
  const disabledCount = userCount + rootCount - enabledCount

  const cards = [
    { label: '用户任务', value: userCount, color: 'text-accent' },
    { label: 'Root 任务', value: rootCount, color: 'text-yellow' },
    { label: '已启用', value: enabledCount, color: 'text-green' },
    { label: '已禁用', value: disabledCount, color: 'text-text3' },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      {cards.map((c) => (
        <div key={c.label} className="bg-card border border-border rounded-lg p-4">
          <div className="text-text3 text-xs uppercase mb-1">{c.label}</div>
          <div className={cn('text-2xl font-bold', c.color)}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}

/** Cron 表达式预设选择下拉菜单 */
function SchedulePresetsDropdown({ onSelect }: { onSelect: (v: string) => void }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-text3 hover:text-text border border-border rounded-md px-2 py-2 text-sm hover:border-accent transition-colors"
        title="常用表达式"
      >
        ...
      </button>
      {open && (
        <div className="absolute left-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 py-1 w-44">
          {SCHEDULE_PRESETS.map((p) => (
            <button
              key={p.value}
              className="w-full text-left px-3 py-2 text-sm text-text hover:bg-bg2/50 flex justify-between items-center"
              onClick={() => {
                onSelect(p.value)
                setOpen(false)
              }}
            >
              <span className="text-text2">{p.label}</span>
              <span className="text-text3 font-mono text-xs">{p.value}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function TabBar({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-4 border-b border-border mb-4">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            'pb-2 px-1 text-sm font-medium transition-colors',
            active === t.key ? 'border-b-2 border-accent text-accent' : 'border-b-2 border-transparent text-text3 hover:text-text',
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/** Cron 表达式验证器，输入表达式后显示描述和未来执行时间 */
function ExpressionValidator() {
  const [expr, setExpr] = useState('')
  const mutation = useMutation({
    mutationFn: () => client.post('/api/cron/validate', { expression: expr }).then((r) => r.data as ValidateResult),
  })

  return (
    <div className="bg-card border border-border rounded-lg p-4 mb-4">
      <h3 className="text-sm font-medium mb-3">Cron 表达式验证</h3>
      <div className="flex gap-2 items-start">
        <input
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder="* * * * * (分 时 日 月 周)"
          className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1 font-mono"
        />
        <button
          onClick={() => mutation.mutate()}
          disabled={!expr.trim() || mutation.isPending}
          className="bg-accent text-[#0f172a] px-3 py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          验证
        </button>
      </div>
      {mutation.data && (
        <div className="mt-3 text-sm">
          {mutation.data.valid ? (
            <>
              <p className="text-green mb-1">{mutation.data.description}</p>
              <p className="text-text3 text-xs mb-1">未来 5 次执行:</p>
              <ul className="text-text2 text-xs space-y-0.5">
                {mutation.data.next_runs.map((r, i) => (
                  <li key={i} className="font-mono">{r}</li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-red">表达式无效</p>
          )}
        </div>
      )}
    </div>
  )
}

/** 新增定时任务表单 */
function AddJobForm({ cronUser }: { cronUser: string }) {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [schedule, setSchedule] = useState('')
  const [command, setCommand] = useState('')
  const [comment, setComment] = useState('')
  const [open, setOpen] = useState(false)

  const addMut = useMutation({
    mutationFn: () => client.post('/api/cron/jobs', { cron_user: cronUser, schedule, command, comment }, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => {
      toast.success('任务已添加')
      qc.invalidateQueries({ queryKey: ['cron', cronUser, serverId] })
      setSchedule('')
      setCommand('')
      setComment('')
      setOpen(false)
    },
    onError: () => toast.error('添加失败'),
  })

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 mb-4">
        + 新增任务
      </button>
    )
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4 mb-4">
      <h3 className="text-sm font-medium mb-3">新增定时任务</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div className="flex gap-1 items-center">
          <input value={schedule} onChange={(e) => setSchedule(e.target.value)} placeholder="Cron 表达式" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none font-mono flex-1" />
          <SchedulePresetsDropdown onSelect={setSchedule} />
        </div>
        <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="命令" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="备注 (可选)" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={() => addMut.mutate()} disabled={!schedule || !command || addMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">
          添加
        </button>
        <button onClick={() => setOpen(false)} className="text-text3 px-3 py-1.5 rounded-md text-sm hover:text-text">
          取消
        </button>
      </div>
    </div>
  )
}

/** 定时任务列表表格，支持编辑调度/启禁/删除 */
function JobTable({ cronUser }: { cronUser: string }) {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [editingJob, setEditingJob] = useState<CronJob | null>(null)
  const [newSchedule, setNewSchedule] = useState('')

  const { data, isLoading } = useQuery<CronListResponse>({
    queryKey: ['cron', cronUser, serverId],
    queryFn: () => client.get(cronUser === 'root' ? '/api/cron/root' : '/api/cron/', { params: { server_id: serverId } }).then((r) => r.data),
  })

  const toggleMut = useMutation({
    mutationFn: (job: CronJob) => client.put('/api/cron/jobs/toggle', { cron_user: cronUser, schedule: job.schedule, command: job.command, enabled: !job.enabled }, { params: { server_id: serverId } }),
    onSuccess: () => { toast.success('状态已更新'); qc.invalidateQueries({ queryKey: ['cron', cronUser, serverId] }) },
    onError: () => toast.error('操作失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (job: CronJob) => client.delete('/api/cron/jobs', { data: { cron_user: cronUser, schedule: job.schedule, command: job.command }, params: { server_id: serverId } }),
    onSuccess: () => { toast.success('任务已删除'); qc.invalidateQueries({ queryKey: ['cron', cronUser, serverId] }) },
    onError: () => toast.error('删除失败'),
  })

  const editMut = useMutation({
    mutationFn: () => client.put('/api/cron/schedule', { cron_user: cronUser, old_schedule: editingJob!.schedule, command: editingJob!.command, new_schedule: newSchedule }, { params: { server_id: serverId } }),
    onSuccess: () => { toast.success('已更新'); setEditingJob(null); qc.invalidateQueries({ queryKey: ['cron', cronUser, serverId] }) },
    onError: () => toast.error('更新失败'),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const jobs = data?.jobs ?? []
  if (jobs.length === 0) return <p className="text-text3 text-sm">暂无任务</p>

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border">
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">Schedule</th>
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">命令</th>
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">状态</th>
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">备注</th>
          <th className="text-text3 text-left text-xs uppercase py-2">操作</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job, i) => (
          <tr key={i} className="border-b border-border">
            <td className="py-2 pr-2 font-mono text-accent whitespace-nowrap">
              {editingJob === job ? (
                <div className="flex gap-1 items-center">
                  <input value={newSchedule} onChange={(e) => setNewSchedule(e.target.value)} className="bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none font-mono w-32" />
                  <button onClick={() => editMut.mutate()} className="text-green text-xs hover:underline">保存</button>
                  <button onClick={() => setEditingJob(null)} className="text-text3 text-xs hover:underline">取消</button>
                </div>
              ) : (
                <span className="flex items-center gap-2">
                  {job.schedule}
                  {job.description && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-accent-dim text-accent font-sans whitespace-nowrap">
                      {job.description}
                    </span>
                  )}
                </span>
              )}
            </td>
            <td className="py-2 pr-2 text-text2 max-w-xs truncate" title={job.command}>{job.command}</td>
            <td className="py-2 pr-2">
              <span className={cn('px-2 py-0.5 rounded text-xs font-medium', job.enabled ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3')}>
                {job.enabled ? '启用' : '禁用'}
              </span>
            </td>
            <td className="py-2 pr-2 text-text3">{job.comment || '-'}</td>
            <td className="py-2">
              <div className="flex gap-2">
                <button
                  onClick={() => { setEditingJob(job); setNewSchedule(job.schedule) }}
                  className="text-accent text-xs hover:underline"
                >
                  编辑
                </button>
                <button onClick={() => toggleMut.mutate(job)} className="text-yellow text-xs hover:underline">
                  {job.enabled ? '禁用' : '启用'}
                </button>
                <button onClick={() => { if (confirm('确认删除该任务?')) deleteMut.mutate(job) }} className="text-red text-xs hover:underline">
                  删除
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Cron 任务执行历史记录 */
function HistorySection({ cronUser }: { cronUser: string }) {
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data, isLoading } = useQuery<{ entries: HistoryEntry[]; count: number }>({
    queryKey: ['cron-history', cronUser, serverId],
    queryFn: () => client.get('/api/cron/history', { params: { pattern: '', hours: 24, server_id: serverId } }).then((r) => r.data),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const entries = data?.entries ?? []
  if (entries.length === 0) return <p className="text-text3 text-sm">暂无执行记录</p>

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border">
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">时间</th>
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">用户</th>
          <th className="text-text3 text-left text-xs uppercase py-2 pr-2">命令</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={i} className="border-b border-border">
            <td className="py-2 pr-2 text-text2 whitespace-nowrap">{e.timestamp}</td>
            <td className="py-2 pr-2 font-mono text-accent text-xs">{e.user}</td>
            <td className="py-2 pr-2 text-text2 max-w-xs truncate" title={e.command}>{e.command}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/* ---------- main page ---------- */

/**
 * 定时任务管理页面
 * 提供用户/Root 双视图、任务 CRUD、表达式验证、执行历史和备份功能
 * API 前缀: /api/cron
 */
export default function CronPage() {
  const currentUser = useAuthStore((s) => s.user)
  const currentUsername = currentUser?.username ?? 'zhengxiaodong'
  const serverId = useServerStore((s) => s.selectedServerId)
  const [activeTab, setActiveTab] = useState('user')
  const [section, setSection] = useState<'jobs' | 'history'>('jobs')

  const backupMut = useMutation({
    mutationFn: (cronUser: string) => client.post('/api/cron/backup', null, { params: { cron_user: cronUser, server_id: serverId } }).then((r) => r.data),
    onSuccess: (d: { path: string }) => toast.success(`备份已保存: ${d.path}`),
    onError: () => toast.error('备份失败'),
  })

  // Fetch both user and root jobs for stat cards
  const { data: userJobsData } = useQuery<CronListResponse>({
    queryKey: ['cron', '', serverId],
    queryFn: () => client.get('/api/cron/', { params: { server_id: serverId } }).then((r) => r.data),
  })
  const { data: rootJobsData } = useQuery<CronListResponse>({
    queryKey: ['cron', 'root', serverId],
    queryFn: () => client.get('/api/cron/root', { params: { server_id: serverId } }).then((r) => r.data),
  })

  const cronUser = activeTab === 'root' ? 'root' : ''

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">定时任务</h2>
        <button
          onClick={() => backupMut.mutate(cronUser || currentUsername)}
          disabled={backupMut.isPending}
          className="text-text3 text-sm hover:text-text border border-border rounded-md px-3 py-1.5 hover:border-accent transition-colors"
        >
          备份 Crontab
        </button>
      </div>

      <StatCards userJobs={userJobsData?.jobs ?? []} rootJobs={rootJobsData?.jobs ?? []} />

      <TabBar
        tabs={[
          { key: 'user', label: '用户任务' },
          { key: 'root', label: 'Root 任务' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      <ExpressionValidator />

      <div className="flex gap-3 mb-4">
        <button
          onClick={() => setSection('jobs')}
          className={cn('text-sm px-3 py-1 rounded-md', section === 'jobs' ? 'bg-accent-dim text-accent' : 'text-text3 hover:text-text')}
        >
          任务列表
        </button>
        <button
          onClick={() => setSection('history')}
          className={cn('text-sm px-3 py-1 rounded-md', section === 'history' ? 'bg-accent-dim text-accent' : 'text-text3 hover:text-text')}
        >
          执行历史
        </button>
      </div>

      {section === 'jobs' ? (
        <>
          <AddJobForm cronUser={cronUser || currentUsername} />
          <div className="bg-card border border-border rounded-lg p-4">
            <JobTable cronUser={cronUser || currentUsername} />
          </div>
        </>
      ) : (
        <div className="bg-card border border-border rounded-lg p-4">
          <HistorySection cronUser={cronUser || currentUsername} />
        </div>
      )}
    </div>
  )
}

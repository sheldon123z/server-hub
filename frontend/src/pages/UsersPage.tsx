import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn, ensureArray, ensureRecord, formatDate, toNumber, toString, getErrorMessage } from '@/lib/utils'
import { useServerStore } from '@/stores/serverStore'

/* ---------- types ---------- */

interface UserStat {
  name: string
  uid: number
  mem_gb: number
  mem_percent: number
  proc_count: number
  cpu_percent: number
  groups: string | string[]
  home_dir: string
}

interface UserInfo {
  name: string
  uid: number
  groups: string | string[]
  home_dir: string
  shell: string
  last_login: string
}

interface Session {
  user: string
  tty: string
  from: string
  login_at: string
  idle: string
}

interface ProcessInfo {
  pid: number
  command: string
  cpu: number
  mem: number
  started: string
}

interface LoginEntry {
  date: string
  ip: string
  duration: string
}

interface QuotaEntry {
  key: string
  mem_gb: number
  proc_limit: number
  comment: string
}

interface EnforcementConfig {
  enabled: boolean
  level1_warning: boolean
  level2_kill_new: boolean
  level3_kill_all: boolean
  [k: string]: unknown
}

interface Violation {
  id: number
  username: string
  type: string
  mem_gb: number
  quota_mem_gb: number
  usage_pct: number
  action: string
  time: string
}

/* ---------- stat summary cards ---------- */

interface QuotaStatus {
  username: string
  mem_gb: number
  quota_mem_gb: number
  over_quota: boolean
}

function normalizeUserStats(value: unknown): UserStat[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.users
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    name: toString(item.name),
    uid: toNumber(item.uid),
    mem_gb: toNumber(item.mem_gb),
    mem_percent: toNumber(item.mem_percent ?? item.mem_usage_pct),
    proc_count: toNumber(item.proc_count),
    cpu_percent: toNumber(item.cpu_percent),
    groups: Array.isArray(item.groups) ? item.groups.map((g) => toString(g)).filter(Boolean) : toString(item.groups),
    home_dir: toString(item.home_dir ?? item.home),
  }))
}

function normalizeSessions(value: unknown): Session[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.sessions
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    user: toString(item.user ?? item.username),
    tty: toString(item.tty ?? item.terminal),
    from: toString(item.from ?? item.source),
    login_at: toString(item.login_at ?? item.login_time),
    idle: toString(item.idle),
  }))
}

function normalizeQuotaStatus(value: unknown): QuotaStatus[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.users
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    username: toString(item.username ?? item.name),
    mem_gb: toNumber(item.mem_gb),
    quota_mem_gb: toNumber(item.quota_mem_gb ?? ensureRecord(item.quota).mem_gb),
    over_quota: Boolean(item.over_quota ?? item.status === 'critical'),
  }))
}

function normalizeProcesses(value: unknown): ProcessInfo[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.processes
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    pid: toNumber(item.pid),
    command: toString(item.command ?? item.cmdline ?? item.name),
    cpu: toNumber(item.cpu ?? item.cpu_percent),
    mem: toNumber(item.mem ?? item.mem_mb),
    started: toString(item.started ?? item.elapsed),
  }))
}

function normalizeLoginEntries(value: unknown): LoginEntry[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.entries
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    date: toString(item.date ?? item.time ?? item.raw),
    ip: toString(item.ip ?? item.source),
    duration: toString(item.duration ?? item.raw),
  }))
}

function normalizeUserInfoList(value: unknown): UserInfo[] {
  const record = ensureRecord(value)
  const items = Array.isArray(value) ? value : record.users
  return ensureArray<Record<string, unknown>>(items).map((item) => ({
    name: toString(item.name),
    uid: toNumber(item.uid),
    groups: Array.isArray(item.groups) ? item.groups.map((g) => toString(g)).filter(Boolean) : toString(item.groups),
    home_dir: toString(item.home_dir ?? item.home),
    shell: toString(item.shell),
    last_login: toString(item.last_login),
  }))
}

function normalizeQuotas(value: unknown): QuotaEntry[] {
  return ensureArray<Record<string, unknown>>(value).map((item) => ({
    key: toString(item.key),
    mem_gb: toNumber(item.mem_gb),
    proc_limit: toNumber(item.proc_limit),
    comment: toString(item.comment),
  }))
}

function normalizeViolations(value: unknown): Violation[] {
  return ensureArray<Record<string, unknown>>(value).map((item) => ({
    id: toNumber(item.id),
    username: toString(item.username),
    type: toString(item.type),
    mem_gb: toNumber(item.mem_gb),
    quota_mem_gb: toNumber(item.quota_mem_gb),
    usage_pct: toNumber(item.usage_pct),
    action: toString(item.action),
    time: toString(item.time),
  }))
}

function StatSummaryCards() {
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data: stats } = useQuery<UserStat[]>({
    queryKey: ['user-stats', serverId],
    queryFn: () => client.get('/api/users/', { params: { server_id: serverId } }).then((r) => normalizeUserStats(r.data)),
    refetchInterval: 15000,
  })

  const { data: sessData } = useQuery<Session[]>({
    queryKey: ['user-sessions', serverId],
    queryFn: () => client.get('/api/users/sessions', { params: { server_id: serverId } }).then((r) => normalizeSessions(r.data)),
    refetchInterval: 30000,
  })

  const { data: quotaStatus } = useQuery<QuotaStatus[]>({
    queryKey: ['quota-status', serverId],
    queryFn: () => client.get('/api/users/quota-status', { params: { server_id: serverId } }).then((r) => normalizeQuotaStatus(r.data)).catch(() => []),
    refetchInterval: 30000,
  })

  const users = ensureArray<UserStat>(stats)
  const sessions = ensureArray<Session>(sessData)
  const quotaArr = ensureArray<QuotaStatus>(quotaStatus)
  const overQuota = quotaArr.filter((q: QuotaStatus) => q.over_quota).length
  const totalMem = users.reduce((sum, u) => sum + (u.mem_gb ?? 0), 0)

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
      <div className="bg-card border border-border rounded-lg px-4 py-3">
        <div className="text-[10px] text-text3 uppercase tracking-wider">用户总数</div>
        <div className="text-xl font-bold text-text mt-1">{users.length}</div>
      </div>
      <div className="bg-card border border-border rounded-lg px-4 py-3">
        <div className="text-[10px] text-text3 uppercase tracking-wider">活跃会话</div>
        <div className="text-xl font-bold text-accent mt-1">{sessions.length}</div>
      </div>
      <div className="bg-card border border-border rounded-lg px-4 py-3">
        <div className="text-[10px] text-text3 uppercase tracking-wider">超配额用户</div>
        <div className={cn('text-xl font-bold mt-1', overQuota > 0 ? 'text-red' : 'text-green')}>{overQuota}</div>
      </div>
      <div className="bg-card border border-border rounded-lg px-4 py-3">
        <div className="text-[10px] text-text3 uppercase tracking-wider">总内存占用</div>
        <div className="text-xl font-bold text-text mt-1">{totalMem.toFixed(1)} GB</div>
      </div>
    </div>
  )
}

/* ---------- tab bar ---------- */

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

/* ---------- Resource Monitor tab ---------- */

function UsageBar({ percent, label }: { percent: number; label: string }) {
  const color = percent >= 85 ? 'bg-red' : percent >= 60 ? 'bg-yellow' : 'bg-green'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-text3">{label}</span>
        <span className="text-text2">{percent.toFixed(1)}%</span>
      </div>
      <div className="w-full h-1.5 bg-bg rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
    </div>
  )
}

function UserCard({ user, onExpand }: { user: UserStat; onExpand: () => void }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4 cursor-pointer hover:border-accent/50 transition-colors" onClick={onExpand}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-medium text-text">{user.name}</span>
        <span className="text-text3 text-xs">UID {user.uid}</span>
      </div>
      <UsageBar percent={user.mem_percent ?? 0} label={`内存 ${(user.mem_gb ?? 0).toFixed(1)} GB`} />
      <div className="mt-2 flex justify-between text-xs text-text3">
        <span>进程: {user.proc_count ?? 0}</span>
        <span>CPU: {(user.cpu_percent ?? 0).toFixed(1)}%</span>
      </div>
    </div>
  )
}

function ProcessList({ username }: { username: string }) {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data, isLoading } = useQuery<ProcessInfo[]>({
    queryKey: ['user-processes', username, serverId],
    queryFn: () => client.get(`/api/users/${username}/processes`, { params: { sort: 'mem', server_id: serverId } }).then((r) => normalizeProcesses(r.data)),
  })

  const killMut = useMutation({
    mutationFn: (pid: number) => client.post(`/api/users/${username}/kill/${pid}`, null, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: (d: { message: string }) => { toast.success(d.message); qc.invalidateQueries({ queryKey: ['user-processes', username, serverId] }) },
    onError: () => toast.error('终止进程失败'),
  })

  const killAllMut = useMutation({
    mutationFn: () => client.post(`/api/users/${username}/kill`, null, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: (d: { message: string }) => { toast.success(d.message); qc.invalidateQueries({ queryKey: ['user-processes', username, serverId] }); qc.invalidateQueries({ queryKey: ['user-stats', serverId] }) },
    onError: () => toast.error('操作失败'),
  })

  if (isLoading) return <p className="text-text3 text-sm py-2">加载中...</p>

  const procs = ensureArray<ProcessInfo>(data)

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-text2">进程列表 ({procs.length})</span>
        {procs.length > 0 && (
          <button onClick={() => { if (confirm(`确认终止 ${username} 的所有进程?`)) killAllMut.mutate() }} className="bg-red/20 text-red px-3 py-1 rounded-md text-xs hover:bg-red/30">
            终止全部
          </button>
        )}
      </div>
      {procs.length === 0 ? (
        <p className="text-text3 text-xs">无运行进程</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="text-text3 text-left py-1">PID</th>
              <th className="text-text3 text-left py-1">命令</th>
              <th className="text-text3 text-left py-1">CPU%</th>
              <th className="text-text3 text-left py-1">MEM%</th>
              <th className="text-text3 text-left py-1">操作</th>
            </tr>
          </thead>
          <tbody>
            {procs.map((p) => (
              <tr key={p.pid} className="border-b border-border">
                <td className="py-1 text-text2 font-mono">{p.pid}</td>
                <td className="py-1 text-text2 max-w-xs truncate" title={p.command}>{p.command}</td>
                <td className="py-1 text-text2">{p.cpu.toFixed(1)}</td>
                <td className="py-1 text-text2">{p.mem.toFixed(1)}</td>
                <td className="py-1">
                  <button onClick={(e) => { e.stopPropagation(); killMut.mutate(p.pid) }} className="text-red hover:underline">kill</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function ResourceMonitorTab() {
  const [expandedUser, setExpandedUser] = useState<string | null>(null)
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data: stats, isLoading: statsLoading } = useQuery<UserStat[]>({
    queryKey: ['user-stats', serverId],
    queryFn: () => client.get('/api/users/', { params: { server_id: serverId } }).then((r) => normalizeUserStats(r.data)),
    refetchInterval: 15000,
  })

  const { data: sessData } = useQuery<Session[]>({
    queryKey: ['user-sessions', serverId],
    queryFn: () => client.get('/api/users/sessions', { params: { server_id: serverId } }).then((r) => normalizeSessions(r.data)),
    refetchInterval: 30000,
  })

  if (statsLoading) return <p className="text-text3 text-sm">加载中...</p>

  const users = ensureArray<UserStat>(stats)
  const sessions = ensureArray<Session>(sessData)

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {users.map((u) => (
          <div key={u.name}>
            <UserCard user={u} onExpand={() => setExpandedUser(expandedUser === u.name ? null : u.name)} />
            {expandedUser === u.name && (
              <div className="bg-bg2 border border-border border-t-0 rounded-b-lg p-3">
                <ProcessList username={u.name} />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">活跃会话 ({sessions.length})</h3>
        {sessions.length === 0 ? (
          <p className="text-text3 text-sm">无活跃会话</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase py-2">用户</th>
                <th className="text-text3 text-left text-xs uppercase py-2">TTY</th>
                <th className="text-text3 text-left text-xs uppercase py-2">来源</th>
                <th className="text-text3 text-left text-xs uppercase py-2">登录时间</th>
                <th className="text-text3 text-left text-xs uppercase py-2">空闲</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => (
                <tr key={i} className="border-b border-border">
                  <td className="py-2 text-text">{s.user}</td>
                  <td className="py-2 text-text2 font-mono text-xs">{s.tty}</td>
                  <td className="py-2 text-text2">{s.from || '-'}</td>
                  <td className="py-2 text-text2">{s.login_at}</td>
                  <td className="py-2 text-text3">{s.idle}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

/* ---------- User Management tab ---------- */

function CreateUserForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [form, setForm] = useState({ username: '', password: '', groups: '', shell: '/bin/bash' })

  const createMut = useMutation({
    mutationFn: () => client.post('/api/users/create', { ...form, groups: form.groups }, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('用户已创建'); qc.invalidateQueries({ queryKey: ['all-users', serverId] }); onDone() },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '创建失败')),
  })

  return (
    <div className="bg-card border border-border rounded-lg p-4 mb-4">
      <h3 className="text-sm font-medium mb-3">创建用户</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="用户名" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="密码" type="password" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input value={form.groups} onChange={(e) => setForm({ ...form, groups: e.target.value })} placeholder="用户组 (逗号分隔)" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input value={form.shell} onChange={(e) => setForm({ ...form, shell: e.target.value })} placeholder="Shell" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={() => createMut.mutate()} disabled={!form.username || !form.password || createMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">
          创建
        </button>
        <button onClick={onDone} className="text-text3 px-3 py-1.5 rounded-md text-sm hover:text-text">取消</button>
      </div>
    </div>
  )
}

function LoginHistory({ username }: { username: string }) {
  const serverId = useServerStore((s) => s.selectedServerId)

  const { data, isLoading } = useQuery<LoginEntry[]>({
    queryKey: ['login-history', username, serverId],
    queryFn: () => client.get(`/api/users/${username}/history`, { params: { count: 30, server_id: serverId } }).then((r) => normalizeLoginEntries(r.data)),
  })

  if (isLoading) return <p className="text-text3 text-xs py-2">加载中...</p>

  const entries = ensureArray<LoginEntry>(data)
  if (entries.length === 0) return <p className="text-text3 text-xs">无登录记录</p>

  return (
    <table className="w-full text-xs mt-2">
      <thead>
        <tr className="border-b border-border">
          <th className="text-text3 text-left py-1">日期</th>
          <th className="text-text3 text-left py-1">IP</th>
          <th className="text-text3 text-left py-1">时长</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={i} className="border-b border-border">
            <td className="py-1 text-text2">{e.date}</td>
            <td className="py-1 text-text2 font-mono">{e.ip || '-'}</td>
            <td className="py-1 text-text3">{e.duration}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function UserManagementTab() {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [showCreate, setShowCreate] = useState(false)
  const [selectedUser, setSelectedUser] = useState<string | null>(null)
  const [editingUser, setEditingUser] = useState<UserInfo | null>(null)
  const [editForm, setEditForm] = useState({ groups: '', shell: '' })
  const [pwUser, setPwUser] = useState<string | null>(null)
  const [newPw, setNewPw] = useState('')

  const { data, isLoading } = useQuery<UserInfo[]>({
    queryKey: ['all-users', serverId],
    queryFn: () => client.get('/api/users/all', { params: { server_id: serverId } }).then((r) => normalizeUserInfoList(r.data)),
  })

  const deleteMut = useMutation({
    mutationFn: (username: string) => client.delete(`/api/users/${username}`, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('用户已删除'); qc.invalidateQueries({ queryKey: ['all-users', serverId] }) },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '删除失败')),
  })

  const updateMut = useMutation({
    mutationFn: () => client.put(`/api/users/${editingUser!.name}`, { groups: editForm.groups, shell: editForm.shell }, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('已更新'); setEditingUser(null); qc.invalidateQueries({ queryKey: ['all-users', serverId] }) },
    onError: () => toast.error('更新失败'),
  })

  const pwMut = useMutation({
    mutationFn: () => client.post(`/api/users/${pwUser!}/password`, { password: newPw }, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('密码已重置'); setPwUser(null); setNewPw('') },
    onError: () => toast.error('重置失败'),
  })

  if (isLoading) return <p className="text-text3 text-sm">加载中...</p>

  const users = ensureArray<UserInfo>(data)

  return (
    <>
      {!showCreate ? (
        <button onClick={() => setShowCreate(true)} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 mb-4">
          + 创建用户
        </button>
      ) : (
        <CreateUserForm onDone={() => setShowCreate(false)} />
      )}

      {/* Password reset modal */}
      {pwUser && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-medium mb-2">重置 {pwUser} 的密码</h3>
          <div className="flex gap-2">
            <input value={newPw} onChange={(e) => setNewPw(e.target.value)} type="password" placeholder="新密码" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1" />
            <button onClick={() => pwMut.mutate()} disabled={!newPw || pwMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">确认</button>
            <button onClick={() => { setPwUser(null); setNewPw('') }} className="text-text3 px-3 py-1.5 text-sm hover:text-text">取消</button>
          </div>
        </div>
      )}

      <div className="bg-card border border-border rounded-lg p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-text3 text-left text-xs uppercase py-2">用户名</th>
              <th className="text-text3 text-left text-xs uppercase py-2">UID</th>
              <th className="text-text3 text-left text-xs uppercase py-2">用户组</th>
              <th className="text-text3 text-left text-xs uppercase py-2">Shell</th>
              <th className="text-text3 text-left text-xs uppercase py-2">最后登录</th>
              <th className="text-text3 text-left text-xs uppercase py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.name} className="border-b border-border">
                <td className="py-2 text-text font-medium">
                  <button onClick={() => setSelectedUser(selectedUser === u.name ? null : u.name)} className="hover:text-accent">
                    {u.name}
                  </button>
                </td>
                <td className="py-2 text-text2">{u.uid}</td>
                <td className="py-2">
                  {editingUser?.name === u.name ? (
                    <input value={editForm.groups} onChange={(e) => setEditForm({ ...editForm, groups: e.target.value })} className="bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none w-32" />
                  ) : (
                    <div className="flex gap-1 flex-wrap">
                      {(Array.isArray(u.groups) ? u.groups : typeof u.groups === 'string' ? u.groups.split(',').filter(Boolean) : []).map((g: string) => (
                        <span key={g} className="px-2 py-0.5 rounded text-xs font-medium bg-accent-dim text-accent">{g.trim()}</span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="py-2 text-text2 font-mono text-xs">
                  {editingUser?.name === u.name ? (
                    <input value={editForm.shell} onChange={(e) => setEditForm({ ...editForm, shell: e.target.value })} className="bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none w-28" />
                  ) : (
                    u.shell
                  )}
                </td>
                <td className="py-2 text-text3 text-xs">{u.last_login || '-'}</td>
                <td className="py-2">
                  {editingUser?.name === u.name ? (
                    <div className="flex gap-2">
                      <button onClick={() => updateMut.mutate()} className="text-green text-xs hover:underline">保存</button>
                      <button onClick={() => setEditingUser(null)} className="text-text3 text-xs hover:underline">取消</button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <button onClick={() => { setEditingUser(u); setEditForm({ groups: Array.isArray(u.groups) ? u.groups.join(', ') : String(u.groups ?? ''), shell: u.shell }) }} className="text-accent text-xs hover:underline">编辑</button>
                      <button onClick={() => setPwUser(u.name)} className="text-yellow text-xs hover:underline">重置密码</button>
                      <button onClick={() => { if (confirm(`确认删除用户 ${u.name}?`)) deleteMut.mutate(u.name) }} className="text-red text-xs hover:underline">删除</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Login history panel */}
      {selectedUser && (
        <div className="bg-card border border-border rounded-lg p-4 mt-4">
          <h3 className="text-sm font-medium mb-2">{selectedUser} 的登录历史</h3>
          <LoginHistory username={selectedUser} />
        </div>
      )}
    </>
  )
}

/* ---------- Quota Management tab ---------- */

function QuotaManagementTab() {
  const qc = useQueryClient()
  const serverId = useServerStore((s) => s.selectedServerId)
  const [newQuota, setNewQuota] = useState({ key: '', mem_gb: 80, proc_limit: 600, comment: '' })
  const [showAdd, setShowAdd] = useState(false)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValues, setEditValues] = useState<{ mem_gb: number; proc_limit: number; comment: string }>({ mem_gb: 0, proc_limit: 0, comment: '' })

  const { data: quotas, isLoading: quotasLoading } = useQuery<QuotaEntry[]>({
    queryKey: ['quotas', serverId],
    queryFn: () => client.get('/api/users/quotas', { params: { server_id: serverId } }).then((r) => normalizeQuotas(r.data)),
  })

  const { data: enforcement } = useQuery<EnforcementConfig>({
    queryKey: ['enforcement', serverId],
    queryFn: () => client.get('/api/users/enforcement', { params: { server_id: serverId } }).then((r) => r.data),
  })

  const { data: violations } = useQuery<Violation[]>({
    queryKey: ['violations', serverId],
    queryFn: () => client.get('/api/users/violations', { params: { limit: 30, server_id: serverId } }).then((r) => normalizeViolations(r.data)),
  })

  const updateQuotasMut = useMutation({
    mutationFn: (q: QuotaEntry[]) => client.put('/api/users/quotas', q, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('配额已更新'); setEditingKey(null); qc.invalidateQueries({ queryKey: ['quotas', serverId] }) },
    onError: () => toast.error('更新失败'),
  })

  const addQuotaMut = useMutation({
    mutationFn: () => client.post('/api/users/quotas', newQuota, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('已添加'); setShowAdd(false); setNewQuota({ key: '', mem_gb: 80, proc_limit: 600, comment: '' }); qc.invalidateQueries({ queryKey: ['quotas', serverId] }) },
    onError: () => toast.error('添加失败'),
  })

  const deleteQuotaMut = useMutation({
    mutationFn: (key: string) => client.delete(`/api/users/quotas/${key}`, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('已删除'); qc.invalidateQueries({ queryKey: ['quotas', serverId] }) },
    onError: () => toast.error('删除失败'),
  })

  const updateEnforcementMut = useMutation({
    mutationFn: (cfg: EnforcementConfig) => client.put('/api/users/enforcement', cfg, { params: { server_id: serverId } }).then((r) => r.data),
    onSuccess: () => { toast.success('执行策略已更新'); qc.invalidateQueries({ queryKey: ['enforcement', serverId] }) },
    onError: () => toast.error('更新失败'),
  })

  const startEdit = (q: QuotaEntry) => {
    setEditingKey(q.key)
    setEditValues({ mem_gb: q.mem_gb, proc_limit: q.proc_limit, comment: q.comment })
  }

  const saveEdit = () => {
    if (!editingKey) return
    const quotaList = ensureArray<QuotaEntry>(quotas)
    const updated = quotaList.map((q) =>
      q.key === editingKey ? { ...q, mem_gb: editValues.mem_gb, proc_limit: editValues.proc_limit, comment: editValues.comment } : q,
    )
    updateQuotasMut.mutate(updated)
  }

  if (quotasLoading) return <p className="text-text3 text-sm">加载中...</p>

  const quotaList = ensureArray<QuotaEntry>(quotas)
  const violationList = ensureArray<Violation>(violations)

  const inputCls = 'bg-bg border border-border rounded px-2 py-1 text-xs text-text focus:border-accent focus:outline-none'

  return (
    <>
      {/* Quotas table */}
      <div className="bg-card border border-border rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">配额规则</h3>
          <button onClick={() => setShowAdd(true)} className="bg-accent text-[#0f172a] px-3 py-1 rounded-md text-xs font-medium hover:opacity-90">+ 添加</button>
        </div>

        {showAdd && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-3 p-3 bg-bg rounded-lg">
            <input value={newQuota.key} onChange={(e) => setNewQuota({ ...newQuota, key: e.target.value })} placeholder="用户名 / @组名 / default" className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            <input type="number" value={newQuota.mem_gb} onChange={(e) => setNewQuota({ ...newQuota, mem_gb: +e.target.value })} placeholder="内存 (GB)" className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            <input type="number" value={newQuota.proc_limit} onChange={(e) => setNewQuota({ ...newQuota, proc_limit: +e.target.value })} placeholder="进程上限" className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
            <div className="flex gap-2">
              <input value={newQuota.comment} onChange={(e) => setNewQuota({ ...newQuota, comment: e.target.value })} placeholder="备注" className="bg-bg2 border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none flex-1" />
              <button onClick={() => addQuotaMut.mutate()} disabled={!newQuota.key || addQuotaMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50 whitespace-nowrap">确认</button>
              <button onClick={() => setShowAdd(false)} className="text-text3 px-2 py-1.5 text-xs hover:text-text">取消</button>
            </div>
          </div>
        )}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-text3 text-left text-xs uppercase py-2">Key</th>
              <th className="text-text3 text-left text-xs uppercase py-2">内存 (GB)</th>
              <th className="text-text3 text-left text-xs uppercase py-2">进程上限</th>
              <th className="text-text3 text-left text-xs uppercase py-2">备注</th>
              <th className="text-text3 text-left text-xs uppercase py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {quotaList.map((q) => (
              <tr key={q.key} className="border-b border-border">
                <td className="py-2 text-accent font-mono text-xs">{q.key}</td>
                <td className="py-2 text-text2">
                  {editingKey === q.key ? (
                    <input type="number" value={editValues.mem_gb} onChange={(e) => setEditValues({ ...editValues, mem_gb: +e.target.value })} className={cn(inputCls, 'w-20')} />
                  ) : q.mem_gb}
                </td>
                <td className="py-2 text-text2">
                  {editingKey === q.key ? (
                    <input type="number" value={editValues.proc_limit} onChange={(e) => setEditValues({ ...editValues, proc_limit: +e.target.value })} className={cn(inputCls, 'w-20')} />
                  ) : q.proc_limit}
                </td>
                <td className="py-2 text-text3">
                  {editingKey === q.key ? (
                    <input value={editValues.comment} onChange={(e) => setEditValues({ ...editValues, comment: e.target.value })} className={cn(inputCls, 'w-32')} />
                  ) : (q.comment || '-')}
                </td>
                <td className="py-2">
                  {editingKey === q.key ? (
                    <div className="flex gap-2">
                      <button onClick={saveEdit} disabled={updateQuotasMut.isPending} className="text-green text-xs hover:underline disabled:opacity-50">保存</button>
                      <button onClick={() => setEditingKey(null)} className="text-text3 text-xs hover:underline">取消</button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <button onClick={() => startEdit(q)} className="text-accent text-xs hover:underline">编辑</button>
                      <button onClick={() => { if (confirm(`删除配额 ${q.key}?`)) deleteQuotaMut.mutate(q.key) }} className="text-red text-xs hover:underline">删除</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Enforcement config */}
      {enforcement && (
        <div className="bg-card border border-border rounded-lg p-4 mb-4">
          <h3 className="text-sm font-medium mb-3">超配额处置策略</h3>
          <div className="space-y-2">
            {[
              { key: 'enabled' as const, label: '启用自动处置' },
              { key: 'level1_warning' as const, label: '一级: 超配额警告' },
              { key: 'level2_kill_new' as const, label: '二级: 终止新进程' },
              { key: 'level3_kill_all' as const, label: '三级: 终止全部进程' },
            ].map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!enforcement[key]}
                  onChange={() => updateEnforcementMut.mutate({ ...enforcement, [key]: !enforcement[key] })}
                  className="rounded border-border"
                />
                <span className="text-text2">{label}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Violations history */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">违规记录 ({violationList.length})</h3>
        {violationList.length === 0 ? (
          <p className="text-text3 text-sm">暂无记录</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-text3 text-left text-xs uppercase py-2">时间</th>
                <th className="text-text3 text-left text-xs uppercase py-2">用户</th>
                <th className="text-text3 text-left text-xs uppercase py-2">类型</th>
                <th className="text-text3 text-left text-xs uppercase py-2">详情</th>
                <th className="text-text3 text-left text-xs uppercase py-2">处置</th>
              </tr>
            </thead>
            <tbody>
              {violationList.map((v) => (
                <tr key={v.id} className="border-b border-border">
                  <td className="py-2 text-text2 text-xs">{formatDate(v.time)}</td>
                  <td className="py-2 text-text font-medium">{v.username}</td>
                  <td className="py-2">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', v.type === 'critical' ? 'bg-red/20 text-red' : v.type === 'warning' ? 'bg-yellow/20 text-yellow' : 'bg-accent-dim text-accent')}>
                      {v.type}
                    </span>
                  </td>
                  <td className="py-2 text-text3 text-xs">{v.mem_gb.toFixed(1)}GB / {v.quota_mem_gb}GB ({v.usage_pct}%)</td>
                  <td className="py-2 text-text2 text-xs">{v.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

/* ---------- main page ---------- */

export default function UsersPage() {
  const [activeTab, setActiveTab] = useState('monitor')

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">用户管理</h2>

      <StatSummaryCards />

      <TabBar
        tabs={[
          { key: 'monitor', label: '资源监控' },
          { key: 'manage', label: '用户管理' },
          { key: 'quotas', label: '配额管理' },
        ]}
        active={activeTab}
        onChange={setActiveTab}
      />

      {activeTab === 'monitor' && <ResourceMonitorTab />}
      {activeTab === 'manage' && <UserManagementTab />}
      {activeTab === 'quotas' && <QuotaManagementTab />}
    </div>
  )
}

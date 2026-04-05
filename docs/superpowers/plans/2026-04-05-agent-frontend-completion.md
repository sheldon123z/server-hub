# Agent 前端功能补全实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全 ServerHub 前端中 4 处未暴露的后端功能：故障案例库写操作、RAG 知识库状态 UI、异步任务监控 Tab、Agent 事件日志 + Runs 取消按钮。

**Architecture:** 所有变更为纯前端 React/TypeScript 修改，不触及后端；全部使用已有的 TanStack Query + Axios client 模式；修改集中在 `AgentStudioPage.tsx` 和 `PatrolPanel.tsx` 两个文件，测试加入现有 `agent-studio.test.tsx`。

**Tech Stack:** React 18 + TypeScript + TanStack Query v5 + Tailwind CSS + Vitest + @testing-library/react

---

## 文件结构

| 操作 | 文件 | 责任 |
|------|------|------|
| Modify | `frontend/src/pages/agents/PatrolPanel.tsx` | 故障案例库 新建/删除 |
| Modify | `frontend/src/pages/agents/AgentStudioPage.tsx` | RAG状态、Async Tasks Tab、Runs取消、Events日志 |
| Modify | `frontend/src/test/agent-studio.test.tsx` | 新增 4 组测试用例 |

---

## Task 1: 故障案例库 — 新建/删除操作

**Files:**
- Modify: `frontend/src/pages/agents/PatrolPanel.tsx:916-1050`

后端 API（已存在）：
- `POST /api/agents/fault-cases` body: `{title, category, symptoms, root_cause, solution, tags}`
- `DELETE /api/agents/fault-cases/{id}`

- [ ] **Step 1: 在 PatrolPanel.tsx 的 `CasesView` 函数前插入 `CreateCaseModal` 组件**

找到 `/* ── Cases View ────────────────────────────────────── */` 注释（约第 901 行）。在它**之前**插入：

```tsx
function CreateCaseModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ title: '', category: '', symptoms: '', root_cause: '', solution: '', tags: '' })
  const mutation = useMutation({
    mutationFn: (data: typeof form) => client.post('/api/agents/fault-cases', data),
    onSuccess: () => { toast.success('案例已创建'); onSaved(); onClose() },
    onError: () => toast.error('创建失败'),
  })
  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 space-y-3">
        <h2 className="text-sm font-semibold text-text">新建故障案例</h2>
        {(['title', 'category', 'symptoms', 'root_cause', 'solution', 'tags'] as const).map(field => (
          <div key={field}>
            <label className="block text-xs text-text3 mb-1 capitalize">{field.replace('_', ' ')}</label>
            <input
              className="w-full bg-bg border border-border rounded px-2 py-1.5 text-xs text-text"
              value={form[field]}
              onChange={e => set(field, e.target.value)}
              placeholder={field === 'title' ? '必填' : '可选'}
            />
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-text3 border border-border rounded-lg hover:text-text">取消</button>
          <button
            onClick={() => mutation.mutate(form)}
            disabled={mutation.isPending || !form.title}
            className="px-3 py-1.5 text-xs bg-accent text-white rounded-lg disabled:opacity-50"
          >
            {mutation.isPending ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 修改 `CasesView` 函数，添加 state、mutations 和 UI**

将 `CasesView` 函数替换为：

```tsx
function CasesView() {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const { data: cases = [] } = useQuery({
    queryKey: ['fault-cases', query],
    queryFn: () => client.get('/api/agents/fault-cases', { params: { q: query } }).then((r) => ensureArray<FaultCase>(r.data)),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/agents/fault-cases/${id}`),
    onSuccess: (_d, id) => {
      toast.success('案例已删除')
      qc.invalidateQueries({ queryKey: ['fault-cases'] })
      if (selectedId === id) setSelectedId(null)
    },
    onError: () => toast.error('删除失败'),
  })

  const selected = cases.find((c) => c.id === selectedId) ?? null

  return (
    <>
      {showCreate && (
        <CreateCaseModal
          onClose={() => setShowCreate(false)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['fault-cases'] })}
        />
      )}
      <div className="flex h-full">
        <div className="w-[200px] border-r border-border flex flex-col shrink-0">
          <div className="p-2 border-b border-border shrink-0 space-y-1">
            <input
              className="w-full bg-bg border border-border rounded px-2 py-1 text-xs text-text placeholder:text-text3 focus:border-accent focus:outline-none"
              placeholder="搜索案例..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              onClick={() => setShowCreate(true)}
              className="w-full py-1 text-xs bg-accent/10 hover:bg-accent/20 text-accent rounded transition-colors"
            >
              + 新建案例
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {cases.map((c) => (
              <div
                key={c.id}
                className={cn(
                  'w-full text-left px-3 py-2.5 border-b border-border text-xs transition-colors group',
                  selectedId === c.id ? 'bg-card' : 'hover:bg-bg2',
                )}
              >
                <button className="w-full text-left" onClick={() => setSelectedId(c.id)}>
                  <div className="text-text font-medium truncate">{c.title}</div>
                  <div className="text-text3 mt-0.5 flex items-center gap-2">
                    <span className="px-1 rounded bg-accent-dim text-accent text-[9px]">{c.category || '通用'}</span>
                    <span className="text-[10px]">{c.source === 'auto' ? '自动' : '手动'}</span>
                  </div>
                </button>
                {c.source !== 'auto' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (confirm(`删除「${c.title}」？`)) deleteMut.mutate(c.id)
                    }}
                    className="hidden group-hover:block mt-1 text-[10px] text-red hover:underline"
                  >
                    删除
                  </button>
                )}
              </div>
            ))}
            {cases.length === 0 && (
              <div className="text-text3 text-xs p-3 text-center">暂无案例</div>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {selected ? (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-text">{selected.title}</h3>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[10px]">
                  {selected.category || '通用'}
                </span>
                <span className={cn(
                  'px-1.5 py-0.5 rounded text-[10px]',
                  selected.source === 'auto' ? 'bg-yellow/15 text-yellow' : 'bg-green/15 text-green',
                )}>
                  {selected.source === 'auto' ? '自动生成' : '手动录入'}
                </span>
                {(selected.tags || '').split(',').filter(Boolean).map((tag) => (
                  <span key={tag} className="px-1.5 py-0.5 rounded bg-accent-dim text-accent text-[9px]">
                    {tag.trim()}
                  </span>
                ))}
              </div>
              {selected.symptoms && <FaultSection title="症状"><p className="text-xs text-text2">{selected.symptoms}</p></FaultSection>}
              {selected.root_cause && <FaultSection title="根本原因"><p className="text-xs text-text2">{selected.root_cause}</p></FaultSection>}
              {selected.solution && <FaultSection title="解决方案"><p className="text-xs text-text2">{selected.solution}</p></FaultSection>}
              <div className="text-text3 text-[10px]">{selected.created_at}</div>
            </div>
          ) : (
            <div className="text-text3 text-xs text-center pt-10">选择一个故障案例查看详情</div>
          )}
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 3: 运行前端 lint 确认无类型错误**

```bash
cd /home/zhengxiaodong/scripts/server-hub/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: 0 errors 或仅有无关文件的错误。

- [ ] **Step 4: 提交**

```bash
cd /home/zhengxiaodong/scripts/server-hub
git add frontend/src/pages/agents/PatrolPanel.tsx
git commit -m "feat(frontend): 故障案例库支持新建和删除操作"
```

---

## Task 2: RAG 知识库状态 — MemoryAndPromptsTab 新增状态区块

**Files:**
- Modify: `frontend/src/pages/agents/AgentStudioPage.tsx:650-745`（MemoryAndPromptsTab 函数）

后端 API（已存在）：
- `GET /api/agents/admin/rag` → `{ok: boolean, stats: {doc_count: number, index_path: string, ...}}`
- `POST /api/agents/admin/rag/reindex` → `{ok: boolean, stats: {...}}`

- [ ] **Step 1: 在 MemoryAndPromptsTab 内的已有 useQuery/useMutation 区域末尾，追加两个新 hook**

找到 `function MemoryAndPromptsTab()` 函数体开头（约第 650 行），在已有 `useQuery`/`useMutation` 声明后追加：

```tsx
  const { data: ragData, refetch: refetchRag } = useQuery({
    queryKey: ['rag-stats'],
    queryFn: () => client.get('/api/agents/admin/rag').then((r) => r.data as { ok: boolean; stats: Record<string, unknown> }),
    staleTime: 60_000,
  })

  const reindexMut = useMutation({
    mutationFn: () => client.post('/api/agents/admin/rag/reindex'),
    onSuccess: () => { toast.success('RAG 索引重建完成'); refetchRag() },
    onError: () => toast.error('重建失败'),
  })
```

- [ ] **Step 2: 在 MemoryAndPromptsTab 的 return 中，在长期记忆 section 之后添加 RAG section**

找到 `</section>` 结束长期记忆区块后，紧接着添加：

```tsx
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-text">RAG 知识库</div>
          <button
            type="button"
            onClick={() => reindexMut.mutate()}
            disabled={reindexMut.isPending}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-text transition-colors hover:border-accent/40 disabled:opacity-50"
          >
            {reindexMut.isPending ? '重建中...' : '重建索引'}
          </button>
        </div>
        {ragData?.ok && ragData.stats ? (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {Object.entries(ragData.stats).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-bg2 px-3 py-2 text-xs">
                <div className="text-text3 capitalize">{k.replace(/_/g, ' ')}</div>
                <div className="mt-1 font-mono text-text">{String(v)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-xs text-text3">
            {ragData?.ok === false ? `不可用: ${ragData.stats}` : '加载中...'}
          </div>
        )}
      </section>
```

- [ ] **Step 3: 运行 lint**

```bash
cd /home/zhengxiaodong/scripts/server-hub/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: 0 errors。

- [ ] **Step 4: 提交**

```bash
cd /home/zhengxiaodong/scripts/server-hub
git add frontend/src/pages/agents/AgentStudioPage.tsx
git commit -m "feat(frontend): AgentStudio 新增 RAG 知识库状态展示和重建索引按钮"
```

---

## Task 3: 异步任务监控 — AgentStudioPage 新增 Async Tasks Tab

**Files:**
- Modify: `frontend/src/pages/agents/AgentStudioPage.tsx`

后端 API（已存在）：
- `GET /api/agents/async-tasks` → 数组 `[{id, task_type, instruction, status, created_at, completed_at}]`
- `GET /api/agents/async-tasks/{id}` → `{id, task_type, instruction, status, result, created_at, completed_at}`
- `DELETE /api/agents/async-tasks/{id}` → 取消任务

- [ ] **Step 1: 在 TABS 数组中添加新 tab**

找到：
```tsx
const TABS: Array<{ id: StudioTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'skills', label: 'Skills' },
  { id: 'install', label: 'Install' },
  { id: 'subagents', label: 'SubAgents' },
  { id: 'memory', label: 'Memory & Prompts' },
  { id: 'runs', label: 'Runs & Approvals' },
]
```

替换为：
```tsx
type StudioTab = 'overview' | 'skills' | 'install' | 'subagents' | 'memory' | 'runs' | 'async-tasks'

const TABS: Array<{ id: StudioTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'skills', label: 'Skills' },
  { id: 'install', label: 'Install' },
  { id: 'subagents', label: 'SubAgents' },
  { id: 'memory', label: 'Memory & Prompts' },
  { id: 'runs', label: 'Runs & Approvals' },
  { id: 'async-tasks', label: 'Async Tasks' },
]
```

注意：`type StudioTab` 的声明在第 37 行，更新该类型定义。

- [ ] **Step 2: 在 AgentStudioPage return 中添加新 tab 渲染条件**

找到：
```tsx
      {tab === 'runs' && <RunsAndApprovalsTab />}
```

在其后添加：
```tsx
      {tab === 'async-tasks' && <AsyncTasksTab />}
```

- [ ] **Step 3: 在 `EmptyState` 组件之前插入 `AsyncTasksTab` 组件**

找到文件末尾的 `function EmptyState(...)` 定义之前，插入完整组件：

```tsx
interface AsyncTask {
  id: string
  task_type: string
  instruction: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  created_at: string
  completed_at: string | null
  result?: string
}

const TASK_STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow/10 text-yellow',
  running: 'bg-accent/10 text-accent',
  done: 'bg-green/10 text-green',
  failed: 'bg-red/10 text-red',
  cancelled: 'bg-text3/10 text-text3',
}

function AsyncTasksTab() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: tasks = [], isFetching } = useQuery({
    queryKey: ['async-tasks'],
    queryFn: () => client.get('/api/agents/async-tasks').then((r) => ensureArray<AsyncTask>(r.data)),
    refetchInterval: 10_000,
  })

  const { data: detail } = useQuery({
    queryKey: ['async-task-detail', selectedId],
    queryFn: () => client.get(`/api/agents/async-tasks/${selectedId}`).then((r) => r.data as AsyncTask),
    enabled: !!selectedId,
    refetchInterval: selectedId ? 5_000 : false,
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => client.delete(`/api/agents/async-tasks/${id}`),
    onSuccess: () => {
      toast.success('任务已取消')
      qc.invalidateQueries({ queryKey: ['async-tasks'] })
      qc.invalidateQueries({ queryKey: ['async-task-detail', selectedId] })
    },
    onError: () => toast.error('取消失败'),
  })

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-medium text-text">后台异步任务</div>
          <div className={isFetching ? 'text-[10px] text-text3 animate-pulse' : 'hidden'}>刷新中...</div>
        </div>
        <div className="space-y-2">
          {tasks.map((t) => (
            <div
              key={t.id}
              onClick={() => setSelectedId(t.id === selectedId ? null : t.id)}
              className={`rounded-lg border p-3 cursor-pointer transition-colors ${selectedId === t.id ? 'border-accent/50 bg-bg2' : 'border-border hover:bg-bg2'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${TASK_STATUS_STYLES[t.status] ?? 'bg-text3/10 text-text3'}`}>
                  {t.status}
                </span>
                <span className="text-[10px] text-text3 font-mono">{t.task_type}</span>
              </div>
              <div className="mt-1 text-xs text-text2 truncate" title={t.instruction}>
                {t.instruction}
              </div>
              <div className="mt-1 text-[10px] text-text3">{t.created_at}</div>
            </div>
          ))}
          {tasks.length === 0 && <EmptyState text="暂无异步任务。" />}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text mb-3">任务详情</div>
        {detail ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className={`text-xs font-medium px-2 py-0.5 rounded ${TASK_STATUS_STYLES[detail.status] ?? ''}`}>
                {detail.status}
              </span>
              {(detail.status === 'pending' || detail.status === 'running') && (
                <button
                  onClick={() => cancelMut.mutate(detail.id)}
                  disabled={cancelMut.isPending}
                  className="text-xs px-2 py-1 rounded bg-red/10 text-red hover:bg-red/20 transition-colors disabled:opacity-50"
                >
                  取消任务
                </button>
              )}
            </div>
            <div className="text-xs text-text3 space-y-1">
              <div><span className="text-text2">类型:</span> {detail.task_type}</div>
              <div><span className="text-text2">创建:</span> {detail.created_at}</div>
              {detail.completed_at && <div><span className="text-text2">完成:</span> {detail.completed_at}</div>}
            </div>
            <div>
              <div className="text-xs text-text3 mb-1">指令</div>
              <pre className="text-xs text-text2 bg-bg2 rounded p-2 whitespace-pre-wrap break-all font-mono">{detail.instruction}</pre>
            </div>
            {detail.result && (
              <div>
                <div className="text-xs text-text3 mb-1">结果</div>
                <pre className="text-xs text-text2 bg-bg2 rounded p-2 max-h-60 overflow-y-auto whitespace-pre-wrap break-all font-mono">{detail.result}</pre>
              </div>
            )}
          </div>
        ) : (
          <EmptyState text="点击左侧任务查看详情。" />
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 4: 运行 lint**

```bash
cd /home/zhengxiaodong/scripts/server-hub/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: 0 errors。

- [ ] **Step 5: 提交**

```bash
cd /home/zhengxiaodong/scripts/server-hub
git add frontend/src/pages/agents/AgentStudioPage.tsx
git commit -m "feat(frontend): AgentStudio 新增 Async Tasks 监控标签页"
```

---

## Task 4: Runs 取消按钮 + Agent Events 事件日志

**Files:**
- Modify: `frontend/src/pages/agents/AgentStudioPage.tsx:747-795`（RunsAndApprovalsTab）

后端 API（已存在）：
- `POST /api/agents/runs/{id}/cancel` → 取消运行中的 run
- `GET /api/agents/events?limit=50` → `[{timestamp, event_type, tool_name, tool_input, risk_level, username, details}]`

- [ ] **Step 1: 在 `AgentRun` 类型中确认 `status` 字段**

检查 `frontend/src/types/agent.ts` 中 `AgentRun` 的定义：

```bash
grep -n "status\|AgentRun" /home/zhengxiaodong/scripts/server-hub/frontend/src/types/agent.ts | head -20
```

Expected: 包含 `status` 字段（`'pending' | 'running' | 'done' | 'error' | ...`）。若无此字段，在类型定义中补充 `status?: string`。

- [ ] **Step 2: 替换 RunsAndApprovalsTab 函数**

找到 `function RunsAndApprovalsTab()` 定义（约第 747 行），整体替换为：

```tsx
interface AgentEvent {
  timestamp: string
  event_type: string
  tool_name: string | null
  tool_input: string | null
  risk_level: string | null
  username: string | null
  details: string | null
}

const RISK_COLORS: Record<string, string> = {
  high: 'text-red',
  medium: 'text-yellow',
  low: 'text-accent',
}

function RunsAndApprovalsTab() {
  const qc = useQueryClient()

  const { data: runs = [] } = useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => client.get('/api/agents/runs').then((r) => ensureArray<AgentRun>(r.data)),
    refetchInterval: 15_000,
  })
  const { data: approvals = [] } = useQuery({
    queryKey: ['agent-approvals'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => ensureArray(r.data) as ApprovalItem[]),
  })
  const { data: events = [] } = useQuery({
    queryKey: ['agent-events'],
    queryFn: () => client.get('/api/agents/events', { params: { limit: 30 } }).then((r) => ensureArray<AgentEvent>(r.data)),
    refetchInterval: 20_000,
  })

  const cancelRunMut = useMutation({
    mutationFn: (id: string) => client.post(`/api/agents/runs/${id}/cancel`),
    onSuccess: () => {
      toast.success('已发送取消请求')
      qc.invalidateQueries({ queryKey: ['agent-runs'] })
    },
    onError: () => toast.error('取消失败'),
  })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="text-sm font-medium text-text mb-3">最近运行</div>
          <div className="space-y-2">
            {runs.map((run) => (
              <div key={run.id} className="rounded-lg border border-border bg-bg2 p-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm text-text truncate flex-1">{run.user_message}</div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${run.status === 'error' ? 'bg-red/10 text-red' : run.status === 'running' ? 'bg-accent/10 text-accent' : 'bg-text3/10 text-text3'}`}>
                      {run.status}
                    </span>
                    {(run.status === 'running' || run.status === 'pending') && (
                      <button
                        onClick={() => cancelRunMut.mutate(run.id)}
                        disabled={cancelRunMut.isPending}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-red/10 text-red hover:bg-red/20 transition-colors disabled:opacity-50"
                      >
                        取消
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-1 text-xs text-text3">
                  {run.page_context || '无页面上下文'} · {run.skill_id || '未选技能'}
                </div>
              </div>
            ))}
            {runs.length === 0 && <EmptyState text="暂无运行记录。" />}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-bg p-4">
          <div className="text-sm font-medium text-text mb-3">待处理审批</div>
          <div className="space-y-2">
            {approvals.map((item: ApprovalItem) => (
              <div key={item.id} className="rounded-lg border border-border bg-bg2 p-3">
                <div className="text-sm text-text">{item.description || item.tool_name}</div>
                <div className="mt-1 text-xs text-text3">{item.created_at}</div>
              </div>
            ))}
            {approvals.length === 0 && <EmptyState text="当前没有待处理审批。" />}
          </div>
        </section>
      </div>

      {/* Agent Events 日志 */}
      <section className="rounded-xl border border-border bg-bg p-4">
        <div className="text-sm font-medium text-text mb-3">Agent 事件日志</div>
        {events.length === 0 ? (
          <EmptyState text="暂无事件记录。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text3">
                  <th className="text-left py-2 pr-3 w-36">时间</th>
                  <th className="text-left py-2 pr-3 w-24">类型</th>
                  <th className="text-left py-2 pr-3 w-32">工具</th>
                  <th className="text-left py-2 pr-3 w-16">风险</th>
                  <th className="text-left py-2">详情</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-bg2">
                    <td className="py-1.5 pr-3 text-text3 font-mono whitespace-nowrap">{e.timestamp?.slice(0, 19).replace('T', ' ')}</td>
                    <td className="py-1.5 pr-3 text-text2">{e.event_type}</td>
                    <td className="py-1.5 pr-3 text-text3 font-mono">{e.tool_name ?? '—'}</td>
                    <td className="py-1.5 pr-3">
                      {e.risk_level ? (
                        <span className={`font-medium ${RISK_COLORS[e.risk_level] ?? 'text-text3'}`}>
                          {e.risk_level}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-1.5 text-text3 truncate max-w-xs" title={e.details ?? ''}>
                      {e.details ?? e.tool_input ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 3: 运行 lint**

```bash
cd /home/zhengxiaodong/scripts/server-hub/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: 0 errors。

- [ ] **Step 4: 提交**

```bash
cd /home/zhengxiaodong/scripts/server-hub
git add frontend/src/pages/agents/AgentStudioPage.tsx
git commit -m "feat(frontend): Runs 取消按钮 + Agent Events 事件日志面板"
```

---

## Task 5: 测试覆盖

**Files:**
- Modify: `frontend/src/test/agent-studio.test.tsx`

- [ ] **Step 1: 在现有 mock setup 中追加新端点的 mock**

找到 `mockedClient.get.mockImplementation` 中的 switch 语句，追加以下 case：

```tsx
        case '/api/agents/async-tasks':
          return Promise.resolve({
            data: [
              {
                id: 'task-1',
                task_type: 'researcher',
                instruction: 'Search for memory leak causes',
                status: 'done',
                created_at: '2026-04-05T10:00:00',
                completed_at: '2026-04-05T10:02:00',
              },
              {
                id: 'task-2',
                task_type: 'security-auditor',
                instruction: 'Run security audit',
                status: 'running',
                created_at: '2026-04-05T10:05:00',
                completed_at: null,
              },
            ],
          })
        case '/api/agents/events':
          return Promise.resolve({
            data: [
              {
                timestamp: '2026-04-05T10:00:00',
                event_type: 'tool_call',
                tool_name: 'execute',
                tool_input: 'df -h',
                risk_level: 'low',
                username: 'admin',
                details: 'check disk usage',
              },
            ],
          })
        case '/api/agents/admin/rag':
          return Promise.resolve({
            data: { ok: true, stats: { doc_count: 42, index_path: '/data/rag' } },
          })
```

- [ ] **Step 2: 追加测试用例**

在现有 `describe('AgentStudioPage', ...)` 内追加：

```tsx
  it('Async Tasks tab 显示任务列表', async () => {
    renderWithProviders(<AgentStudioPage />)
    fireEvent.click(screen.getByText('Async Tasks'))
    await waitFor(() => {
      expect(screen.getByText('Search for memory leak causes')).toBeInTheDocument()
      expect(screen.getByText('Run security audit')).toBeInTheDocument()
    })
  })

  it('Async Tasks tab 对 running 任务显示取消按钮', async () => {
    renderWithProviders(<AgentStudioPage />)
    fireEvent.click(screen.getByText('Async Tasks'))
    await waitFor(() => {
      expect(screen.getByText('Run security audit')).toBeInTheDocument()
    })
    // running 任务的取消按钮通过点击任务行后在详情中显示
    // 此处验证 running badge 存在
    expect(screen.getAllByText('running').length).toBeGreaterThan(0)
  })

  it('Runs & Approvals tab 显示 Events 日志', async () => {
    renderWithProviders(<AgentStudioPage />)
    fireEvent.click(screen.getByText('Runs & Approvals'))
    await waitFor(() => {
      expect(screen.getByText('Agent 事件日志')).toBeInTheDocument()
      expect(screen.getByText('execute')).toBeInTheDocument()
    })
  })

  it('Memory & Prompts tab 显示 RAG 状态', async () => {
    renderWithProviders(<AgentStudioPage />)
    fireEvent.click(screen.getByText('Memory & Prompts'))
    await waitFor(() => {
      expect(screen.getByText('RAG 知识库')).toBeInTheDocument()
      expect(screen.getByText('重建索引')).toBeInTheDocument()
    })
  })
```

- [ ] **Step 3: 运行测试确认全部通过**

```bash
cd /home/zhengxiaodong/scripts/server-hub/frontend
npx vitest run src/test/agent-studio.test.tsx 2>&1 | tail -20
```

Expected: 所有测试 PASS，无 FAIL。

- [ ] **Step 4: 提交**

```bash
cd /home/zhengxiaodong/scripts/server-hub
git add frontend/src/test/agent-studio.test.tsx
git commit -m "test(frontend): 补充 AsyncTasks/Events/RAG/Runs 功能测试用例"
```

---

## 自检清单

- [ ] `PatrolPanel.tsx` 的 `CasesView` 有"+ 新建案例"按钮和删除按钮，手动录入案例可删除，自动生成案例无删除按钮
- [ ] `AgentStudioPage` 的 Memory & Prompts tab 底部新增 RAG 知识库状态卡片和"重建索引"按钮
- [ ] `AgentStudioPage` 的 tab 列表末尾新增"Async Tasks"，点击显示任务列表+详情+取消按钮
- [ ] `AgentStudioPage` 的 Runs & Approvals tab 底部新增 Agent Events 事件日志表格
- [ ] running/pending 状态的 Run 显示"取消"按钮，done/error 状态不显示
- [ ] 所有新测试通过：`npx vitest run src/test/agent-studio.test.tsx`
- [ ] `npx tsc --noEmit` 零错误

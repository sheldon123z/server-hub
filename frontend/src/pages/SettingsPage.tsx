import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'

/* ---------- types ---------- */

interface ProviderInfo {
  id: string
  name: string
  display_name: string
  base_url: string
  has_key: boolean
  models: string[]
}

interface AgentSettings {
  default_model: string
  patrol_model: string
  shell_timeout: number
  providers: ProviderInfo[]
}

/* ---------- sub-components ---------- */

function ModelSelect({
  value,
  onChange,
  providers,
  label,
}: {
  value: string
  onChange: (v: string) => void
  providers: ProviderInfo[]
  label: string
}) {
  return (
    <div>
      <label className="text-text3 text-xs uppercase block mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-full max-w-md"
      >
        <option value="">未选择</option>
        {providers
          .filter((p) => p.has_key && p.models.length > 0)
          .map((p) => (
            <optgroup key={p.id} label={p.display_name}>
              {p.models.map((m: any) => {
                const modelId = typeof m === 'string' ? m : m.id ?? m.name ?? ''
                const modelName = typeof m === 'string' ? m : m.name ?? m.id ?? ''
                return (
                  <option key={`${p.id}:${modelId}`} value={`${p.id}:${modelId}`}>
                    {modelName}
                  </option>
                )
              })}
            </optgroup>
          ))}
      </select>
    </div>
  )
}

function ProviderCard({ provider }: { provider: ProviderInfo }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [showApiKeyForm, setShowApiKeyForm] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')

  const refreshMut = useMutation({
    mutationFn: () => client.post(`/api/agents/settings/refresh-models/${provider.id}`).then((r) => r.data),
    onSuccess: (d: { count: number }) => {
      toast.success(`已刷新，共 ${d.count} 个模型`)
      qc.invalidateQueries({ queryKey: ['agent-settings'] })
    },
    onError: () => toast.error('刷新失败'),
  })

  const apiKeyMut = useMutation({
    mutationFn: (api_key: string) =>
      client.put(`/api/agents/settings/api-key/${provider.id}`, { api_key }).then((r) => r.data),
    onSuccess: () => {
      toast.success('API Key 已保存')
      setShowApiKeyForm(false)
      setApiKeyInput('')
      qc.invalidateQueries({ queryKey: ['agent-settings'] })
    },
    onError: () => toast.error('保存失败'),
  })

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-text">{provider.display_name}</span>
          <span className={cn('px-2 py-0.5 rounded text-xs font-medium', provider.has_key ? 'bg-green/20 text-green' : 'bg-text3/20 text-text3')}>
            {provider.has_key ? '已配置' : '未配置'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setShowApiKeyForm(!showApiKeyForm)
              setApiKeyInput('')
            }}
            className="text-accent text-xs hover:underline"
          >
            设置 API Key
          </button>
          <button
            onClick={() => refreshMut.mutate()}
            disabled={!provider.has_key || refreshMut.isPending}
            className="text-accent text-xs hover:underline disabled:opacity-50 disabled:no-underline"
          >
            {refreshMut.isPending ? '刷新中...' : '刷新模型列表'}
          </button>
        </div>
      </div>

      {/* Inline API Key form */}
      {showApiKeyForm && (
        <div className="mb-3 p-3 bg-bg rounded-md border border-border">
          <label className="text-text3 text-xs block mb-1.5">API Key</label>
          <div className="flex gap-2">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="输入 API Key..."
              className="flex-1 bg-card border border-border rounded-md px-3 py-1.5 text-sm text-text focus:border-accent focus:outline-none font-mono"
            />
            <button
              onClick={() => apiKeyMut.mutate(apiKeyInput)}
              disabled={!apiKeyInput.trim() || apiKeyMut.isPending}
              className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-xs font-medium disabled:opacity-50"
            >
              {apiKeyMut.isPending ? '保存中...' : '保存'}
            </button>
            <button
              onClick={() => {
                setShowApiKeyForm(false)
                setApiKeyInput('')
              }}
              className="px-3 py-1.5 rounded-md text-xs border border-border text-text2 hover:bg-bg2"
            >
              取消
            </button>
          </div>
        </div>
      )}

      <div className="text-text3 text-xs mb-2 font-mono">{provider.base_url}</div>

      <div className="flex items-center justify-between">
        <span className="text-text2 text-xs">{provider.models.length} 个可用模型</span>
        {provider.models.length > 0 && (
          <button onClick={() => setExpanded(!expanded)} className="text-text3 text-xs hover:text-text">
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>

      {expanded && provider.models.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border">
          <div className="flex flex-wrap gap-1.5">
            {provider.models.map((m: any, i: number) => {
              const name = typeof m === 'string' ? m : m.name ?? m.id ?? ''
              return (
                <span key={`${name}-${i}`} className="px-2 py-0.5 rounded text-xs bg-bg text-text2 font-mono">
                  {name}
                </span>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------- main page ---------- */

export default function SettingsPage() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<AgentSettings>({
    queryKey: ['agent-settings'],
    queryFn: () => client.get('/api/agents/settings').then((r) => r.data),
  })

  const [form, setForm] = useState({
    default_model: '',
    patrol_model: '',
    shell_timeout: 30,
  })

  const [dirty, setDirty] = useState(false)

  // Sync form when data loads
  useEffect(() => {
    if (data) {
      setForm({
        default_model: data.default_model,
        patrol_model: data.patrol_model,
        shell_timeout: data.shell_timeout,
      })
      setDirty(false)
    }
  }, [data])

  const saveMut = useMutation({
    mutationFn: () => client.put('/api/agents/settings', form).then((r) => r.data),
    onSuccess: () => {
      toast.success('设置已保存')
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['agent-settings'] })
    },
    onError: () => toast.error('保存失败'),
  })

  const updateField = <K extends keyof typeof form>(key: K, val: (typeof form)[K]) => {
    setForm((f) => ({ ...f, [key]: val }))
    setDirty(true)
  }

  if (isLoading) {
    return (
      <div>
        <h2 className="text-lg font-semibold mb-4">系统设置</h2>
        <p className="text-text3 text-sm">加载中...</p>
      </div>
    )
  }

  const providers = data?.providers ?? []

  return (
    <div>
      <h2 className="text-lg font-semibold mb-6">系统设置</h2>

      {/* AI Model Config Section */}
      <section className="mb-8">
        <h3 className="text-sm font-medium text-text2 uppercase tracking-wider mb-4">AI 模型配置</h3>
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="space-y-4">
            <ModelSelect
              label="默认对话模型"
              value={form.default_model}
              onChange={(v) => updateField('default_model', v)}
              providers={providers}
            />

            <ModelSelect
              label="巡检模型"
              value={form.patrol_model}
              onChange={(v) => updateField('patrol_model', v)}
              providers={providers}
            />

            <div>
              <label className="text-text3 text-xs uppercase block mb-1">Shell 超时 (秒)</label>
              <input
                type="number"
                value={form.shell_timeout}
                onChange={(e) => updateField('shell_timeout', parseInt(e.target.value) || 0)}
                min={5}
                max={600}
                className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-32"
              />
              <p className="text-text3 text-xs mt-1">Agent 执行 Shell 命令的最大等待时间</p>
            </div>

            <button
              onClick={() => saveMut.mutate()}
              disabled={!dirty || saveMut.isPending}
              className={cn(
                'px-4 py-2 rounded-md text-sm font-medium transition-colors',
                dirty
                  ? 'bg-accent text-[#0f172a] hover:opacity-90'
                  : 'bg-border text-text3 cursor-not-allowed',
              )}
            >
              {saveMut.isPending ? '保存中...' : '保存设置'}
            </button>
          </div>
        </div>
      </section>

      {/* Providers Section */}
      <section>
        <h3 className="text-sm font-medium text-text2 uppercase tracking-wider mb-4">模型供应商</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {providers.map((p) => (
            <ProviderCard key={p.id} provider={p} />
          ))}
        </div>
        {providers.length === 0 && <p className="text-text3 text-sm">未检测到供应商配置</p>}
      </section>
    </div>
  )
}

/**
 * 权限矩阵编辑器
 * 二维表格: 行=资源, 列=操作(read/write/execute/admin)
 * 支持勾选/取消和 Scope 编辑, 保存时调用 PUT /api/rbac/roles/{id}/permissions
 */

import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'

/* ---------- constants ---------- */

/** 所有受管资源 */
const RESOURCES = [
  { key: 'docker', label: 'Docker 容器' },
  { key: 'services', label: '系统服务' },
  { key: 'users', label: '用户管理' },
  { key: 'cron', label: '定时任务' },
  { key: 'servers', label: '服务器管理' },
  { key: 'files', label: '文件管理' },
  { key: 'agents', label: 'AI 智能体' },
  { key: 'alerts', label: '告警规则' },
  { key: 'system', label: '系统配置' },
]

/** 支持的操作类型 */
const ACTIONS = [
  { key: 'read', label: '读取', color: 'text-blue-400' },
  { key: 'write', label: '写入', color: 'text-yellow-400' },
  { key: 'execute', label: '执行', color: 'text-green-400' },
  { key: 'admin', label: '管理', color: 'text-red-400' },
] as const

type ActionKey = (typeof ACTIONS)[number]['key']

/* ---------- types ---------- */

export interface PermEntry {
  id?: number
  role_id: string
  resource: string
  action: string
  scope: string
}

interface MatrixCell {
  enabled: boolean
  scope: string
}

type MatrixState = Record<string, Record<ActionKey, MatrixCell>>

/* ---------- helpers ---------- */

function buildMatrix(permissions: PermEntry[]): MatrixState {
  const matrix: MatrixState = {}
  for (const r of RESOURCES) {
    matrix[r.key] = {} as Record<ActionKey, MatrixCell>
    for (const a of ACTIONS) {
      matrix[r.key][a.key] = { enabled: false, scope: '*' }
    }
  }
  for (const p of permissions) {
    if (matrix[p.resource]?.[p.action as ActionKey] !== undefined) {
      matrix[p.resource][p.action as ActionKey] = { enabled: true, scope: p.scope || '*' }
    }
  }
  return matrix
}

function matrixToPermissions(roleId: string, matrix: MatrixState): PermEntry[] {
  const result: PermEntry[] = []
  for (const resource of Object.keys(matrix)) {
    for (const action of Object.keys(matrix[resource]) as ActionKey[]) {
      const cell = matrix[resource][action]
      if (cell.enabled) {
        result.push({ role_id: roleId, resource, action, scope: cell.scope || '*' })
      }
    }
  }
  return result
}

/* ---------- scope input ---------- */

function ScopeInput({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const [editing, setEditing] = useState(false)

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-[10px] font-mono text-text3 hover:text-accent underline-offset-2 hover:underline truncate max-w-[80px]"
        title={value}
      >
        {value}
      </button>
    )
  }

  return (
    <input
      autoFocus
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={() => setEditing(false)}
      onKeyDown={(e) => e.key === 'Enter' && setEditing(false)}
      className="text-[10px] font-mono bg-bg border border-accent rounded px-1 py-0.5 text-text w-[80px] focus:outline-none"
      placeholder="* / server:x"
    />
  )
}

/* ---------- main component ---------- */

interface PermissionMatrixProps {
  /** 角色 ID */
  roleId: string
  /** 当前权限列表 */
  permissions: PermEntry[]
  /** 是否只读（内置角色） */
  readonly?: boolean
}

export default function PermissionMatrix({ roleId, permissions, readonly = false }: PermissionMatrixProps) {
  const qc = useQueryClient()
  const [matrix, setMatrix] = useState<MatrixState>(() => buildMatrix(permissions))
  const [dirty, setDirty] = useState(false)

  // 外部 permissions 变化时重置
  useEffect(() => {
    setMatrix(buildMatrix(permissions))
    setDirty(false)
  }, [permissions])

  const saveMut = useMutation({
    mutationFn: (perms: PermEntry[]) =>
      client
        .put(`/api/rbac/roles/${roleId}`, {
          permissions: perms.map(({ resource, action, scope }) => ({ resource, action, scope })),
        })
        .then((r) => r.data),
    onSuccess: () => {
      toast.success('权限已保存')
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['rbac-roles'] })
    },
    onError: () => toast.error('保存权限失败'),
  })

  function toggleCell(resource: string, action: ActionKey) {
    if (readonly) return
    setMatrix((prev) => ({
      ...prev,
      [resource]: {
        ...prev[resource],
        [action]: {
          ...prev[resource][action],
          enabled: !prev[resource][action].enabled,
        },
      },
    }))
    setDirty(true)
  }

  function updateScope(resource: string, action: ActionKey, scope: string) {
    if (readonly) return
    setMatrix((prev) => ({
      ...prev,
      [resource]: {
        ...prev[resource],
        [action]: { ...prev[resource][action], scope },
      },
    }))
    setDirty(true)
  }

  function handleSelectAll(action: ActionKey) {
    if (readonly) return
    const allEnabled = RESOURCES.every((r) => matrix[r.key][action].enabled)
    setMatrix((prev) => {
      const next = { ...prev }
      for (const r of RESOURCES) {
        next[r.key] = { ...next[r.key], [action]: { ...next[r.key][action], enabled: !allEnabled } }
      }
      return next
    })
    setDirty(true)
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-3 py-2 text-text3 text-xs font-medium w-[140px]">资源</th>
              {ACTIONS.map((a) => (
                <th key={a.key} className="px-3 py-2 text-center w-[110px]">
                  <button
                    onClick={() => handleSelectAll(a.key)}
                    disabled={readonly}
                    className={cn('text-xs font-medium', a.color, 'hover:underline disabled:cursor-default')}
                    title="点击全选/全取消"
                  >
                    {a.label}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {RESOURCES.map((r) => (
              <tr key={r.key} className="border-b border-border/50 hover:bg-bg2/30">
                <td className="px-3 py-2 text-text2 text-xs font-medium">{r.label}</td>
                {ACTIONS.map((a) => {
                  const cell = matrix[r.key][a.key]
                  return (
                    <td key={a.key} className="px-3 py-2 text-center">
                      <div className="flex flex-col items-center gap-1">
                        <input
                          type="checkbox"
                          checked={cell.enabled}
                          onChange={() => toggleCell(r.key, a.key)}
                          disabled={readonly}
                          className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed"
                        />
                        {cell.enabled && (
                          <ScopeInput
                            value={cell.scope}
                            onChange={(v) => updateScope(r.key, a.key, v)}
                          />
                        )}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!readonly && (
        <div className="mt-3 flex justify-end">
          <button
            onClick={() => saveMut.mutate(matrixToPermissions(roleId, matrix))}
            disabled={!dirty || saveMut.isPending}
            className={cn(
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
              dirty
                ? 'bg-accent text-[#0f172a] hover:opacity-90'
                : 'bg-border text-text3 cursor-not-allowed',
            )}
          >
            {saveMut.isPending ? '保存中...' : '保存权限'}
          </button>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { ensureArray, ensureRecord, formatDate, toNumber, toString } from '@/lib/utils'

interface AuditItem {
  timestamp: string
  username: string
  action: string
  target: string
  ip: string
  success: boolean
}

interface AuditResponse {
  total: number
  page: number
  limit: number
  items: AuditItem[]
}

const methodColor: Record<string, string> = {
  GET: 'text-text2',
  POST: 'text-green',
  PUT: 'text-yellow',
  DELETE: 'text-red',
}

function normalizeAuditResponse(value: unknown): AuditResponse {
  const record = ensureRecord(value)
  const items = ensureArray<Record<string, unknown>>(record.items).map((item) => ({
    timestamp: toString(item.timestamp ?? item.created_at),
    username: toString(item.username),
    action: toString(item.action ?? item.method),
    target: toString(item.target ?? item.path),
    ip: toString(item.ip ?? item.ip_address),
    success: Boolean(item.success ?? (toNumber(item.status_code) < 400)),
  }))
  return {
    total: toNumber(record.total, items.length),
    page: toNumber(record.page, 1),
    limit: toNumber(record.limit, 50),
    items,
  }
}

export default function AuditPage() {
  const [page, setPage] = useState(1)
  const [limit] = useState(50)
  const [username, setUsername] = useState('')

  const { data, isLoading } = useQuery<AuditResponse>({
    queryKey: ['audit', page, limit, username],
    queryFn: () =>
      client
        .get('/api/audit/', { params: { page, limit, username: username || undefined } })
        .then((r) => normalizeAuditResponse(r.data)),
  })

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const items = ensureArray<AuditItem>(data?.items)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text">审计日志</h2>
        <input
          type="text"
          placeholder="按用户名筛选..."
          value={username}
          onChange={(e) => {
            setUsername(e.target.value)
            setPage(1)
          }}
          className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none w-48"
        />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text3 text-left">
              <th className="px-4 py-3 font-medium">时间</th>
              <th className="px-4 py-3 font-medium">用户</th>
              <th className="px-4 py-3 font-medium">方法</th>
              <th className="px-4 py-3 font-medium">路径</th>
              <th className="px-4 py-3 font-medium">状态码</th>
              <th className="px-4 py-3 font-medium">IP</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text3">
                  加载中...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text3">
                  暂无记录
                </td>
              </tr>
            ) : (
              items.map((item, index) => (
                <tr key={`${item.timestamp}-${item.username}-${index}`} className="border-b border-border hover:bg-bg2/50">
                  <td className="px-4 py-2.5 text-text3 whitespace-nowrap">
                    {formatDate(item.timestamp)}
                  </td>
                  <td className="px-4 py-2.5 text-text">{item.username}</td>
                  <td className={`px-4 py-2.5 font-mono font-medium ${methodColor[item.action] || 'text-text2'}`}>
                    {item.action}
                  </td>
                  <td className="px-4 py-2.5 text-text2 font-mono text-xs max-w-xs truncate">
                    {item.target}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={item.success ? 'text-green' : 'text-red'}>
                      {item.success ? '成功' : '失败'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-text3 font-mono text-xs">{item.ip}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-text3">
            共 {data?.total ?? 0} 条，第 {page}/{totalPages} 页
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 rounded-md text-sm border border-border text-text2 hover:bg-bg2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              上一页
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 rounded-md text-sm border border-border text-text2 hover:bg-bg2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

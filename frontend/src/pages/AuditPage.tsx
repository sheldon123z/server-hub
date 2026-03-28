import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { formatDate } from '@/lib/utils'

interface AuditItem {
  id: number
  username: string
  method: string
  path: string
  status_code: number
  ip_address: string
  created_at: string
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

export default function AuditPage() {
  const [page, setPage] = useState(1)
  const [limit] = useState(50)
  const [username, setUsername] = useState('')

  const { data, isLoading } = useQuery<AuditResponse>({
    queryKey: ['audit', page, limit, username],
    queryFn: () =>
      client
        .get('/api/audit/', { params: { page, limit, username: username || undefined } })
        .then((r) => r.data),
  })

  const totalPages = data ? Math.ceil(data.total / limit) : 0

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
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-text3">
                  暂无记录
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                <tr key={item.id} className="border-b border-border hover:bg-bg2/50">
                  <td className="px-4 py-2.5 text-text3 whitespace-nowrap">
                    {formatDate(item.created_at)}
                  </td>
                  <td className="px-4 py-2.5 text-text">{item.username}</td>
                  <td className={`px-4 py-2.5 font-mono font-medium ${methodColor[item.method] || 'text-text2'}`}>
                    {item.method}
                  </td>
                  <td className="px-4 py-2.5 text-text2 font-mono text-xs max-w-xs truncate">
                    {item.path}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={
                        item.status_code >= 400
                          ? 'text-red'
                          : item.status_code >= 300
                            ? 'text-yellow'
                            : 'text-green'
                      }
                    >
                      {item.status_code}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-text3 font-mono text-xs">{item.ip_address}</td>
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

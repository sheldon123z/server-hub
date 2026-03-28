import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'

export function AdminPanel() {
  const { data: skills } = useQuery({
    queryKey: ['studio-skills-summary'],
    queryFn: () => client.get('/api/agents/admin/skills').then((r) => r.data),
  })

  const { data: runs } = useQuery({
    queryKey: ['studio-runs-summary'],
    queryFn: () => client.get('/api/agents/runs').then((r) => r.data),
  })

  const { data: approvals } = useQuery({
    queryKey: ['studio-approvals-summary'],
    queryFn: () => client.get('/api/agents/approvals').then((r) => r.data),
  })

  const skillCount = skills?.skills?.length ?? 0
  const failedRuns = Array.isArray(runs) ? runs.filter((item) => item.status === 'error').length : 0
  const pendingApprovals = Array.isArray(approvals) ? approvals.length : 0

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="rounded-xl border border-border bg-bg2 p-4">
        <div className="text-sm font-medium text-text">Agent Studio</div>
        <p className="mt-1 text-xs leading-5 text-text3">
          运行时、技能、Prompt、记忆和审批管理已经迁移到独立 Studio。当前页面保留为轻量聊天入口。
        </p>
        <Link
          to="/agents/studio"
          className="mt-4 inline-flex rounded-lg bg-accent px-3 py-2 text-sm font-medium text-[#0f172a] transition-colors hover:bg-accent/80"
        >
          打开 Agent Studio
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-border bg-bg p-4">
          <div className="text-xs text-text3">已安装技能</div>
          <div className="mt-2 text-2xl font-semibold text-text">{skillCount}</div>
        </div>
        <div className="rounded-xl border border-border bg-bg p-4">
          <div className="text-xs text-text3">最近失败运行</div>
          <div className="mt-2 text-2xl font-semibold text-text">{failedRuns}</div>
        </div>
        <div className="rounded-xl border border-border bg-bg p-4">
          <div className="text-xs text-text3">待处理审批</div>
          <div className="mt-2 text-2xl font-semibold text-text">{pendingApprovals}</div>
        </div>
      </div>
    </div>
  )
}

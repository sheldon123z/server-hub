/**
 * 创建团队弹窗组件
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import client from '@/api/client'
import toast from 'react-hot-toast'
import { getErrorMessage } from '@/lib/utils'
import type { TeamTopology, SafetyMode, TeamCreateRequest } from '@/types/team'

export function CreateTeamModal({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<TeamCreateRequest>({
    name: '',
    description: '',
    topology: 'supervisor',
    safety_mode: 'supervised',
    max_steps: 50,
    timeout_seconds: 300,
  })

  const createMut = useMutation({
    mutationFn: () => client.post('/api/agents/teams', form).then((r) => r.data),
    onSuccess: () => { toast.success('团队已创建'); qc.invalidateQueries({ queryKey: ['teams'] }); onDone() },
    onError: (err: unknown) => toast.error(getErrorMessage(err, '创建失败')),
  })

  return (
    <div className="bg-card border border-border rounded-lg p-4 mb-4">
      <h3 className="text-sm font-medium mb-3">创建团队</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="团队名称" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <select value={form.topology} onChange={(e) => setForm({ ...form, topology: e.target.value as TeamTopology })} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
          <option value="supervisor">组长调度</option>
          <option value="swarm">自主协作</option>
          <option value="pipeline">流水线</option>
        </select>
        <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="描述" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <select value={form.safety_mode} onChange={(e) => setForm({ ...form, safety_mode: e.target.value as SafetyMode })} className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none">
          <option value="supervised">受监督 (需审批)</option>
          <option value="autonomous">自主模式</option>
        </select>
        <input type="number" value={form.max_steps} onChange={(e) => setForm({ ...form, max_steps: +e.target.value })} placeholder="最大步数" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
        <input type="number" value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: +e.target.value })} placeholder="超时(秒)" className="bg-bg border border-border rounded-md px-3 py-2 text-sm text-text focus:border-accent focus:outline-none" />
      </div>
      <div className="flex gap-2">
        <button onClick={() => createMut.mutate()} disabled={!form.name || createMut.isPending} className="bg-accent text-[#0f172a] px-3 py-1.5 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">创建</button>
        <button onClick={onDone} className="text-text3 px-3 py-1.5 rounded-md text-sm hover:text-text">取消</button>
      </div>
    </div>
  )
}

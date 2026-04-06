/**
 * Batch operations API — template listing
 */
import client from './client'

export interface BatchTemplate {
  id: string
  name: string
  description: string | null
  type: 'command' | 'service_action' | 'docker_action' | 'script' | 'playbook'
  payload: Record<string, string>
  strategy: 'parallel' | 'serial' | 'rolling'
  rolling_batch_size: number
  stop_on_failure: boolean
  is_builtin: boolean
  created_at: string
}

export async function fetchBatchTemplates(): Promise<BatchTemplate[]> {
  const res = await client.get<BatchTemplate[]>('/api/servers/batch/templates')
  return res.data
}

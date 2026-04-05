/**
 * SkillEvalPanel - Evaluation panel shown at the bottom of SkillEditor.
 * Provides test set editing, eval execution, and A/B comparison results.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { cn } from '@/lib/utils'
import {
  getEvals,
  saveEvals,
  runEval,
  getEvalResults,
  type EvalSet,
  type EvalCase,
  type EvalRunResult,
  type EvalCaseResult,
} from '@/api/skills'

interface SkillEvalPanelProps {
  skillId: string
}

export function SkillEvalPanel({ skillId }: SkillEvalPanelProps) {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<'edit' | 'results'>('edit')
  const [jsonText, setJsonText] = useState<string | null>(null)
  const [jsonError, setJsonError] = useState<string | null>(null)

  // Fetch eval set
  const { data: evalSet } = useQuery({
    queryKey: ['skill-evals', skillId],
    queryFn: () => getEvals(skillId),
  })

  // Fetch results
  const { data: results = [] } = useQuery({
    queryKey: ['skill-eval-results', skillId],
    queryFn: () => getEvalResults(skillId),
  })

  // Initialize JSON text from fetched data
  const displayJson = jsonText ?? (evalSet ? JSON.stringify(evalSet, null, 2) : '')

  // Save mutation
  const saveMut = useMutation({
    mutationFn: async () => {
      const parsed = JSON.parse(displayJson) as EvalSet
      await saveEvals(skillId, parsed)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skill-evals', skillId] })
      setJsonError(null)
      toast.success('测试集已保存')
    },
    onError: (err) => {
      const msg = err instanceof SyntaxError ? 'JSON 格式错误' : '保存失败'
      setJsonError(msg)
      toast.error(msg)
    },
  })

  // Run eval mutation
  const runMut = useMutation({
    mutationFn: () => runEval(skillId),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['skill-eval-results', skillId] })
      toast.success(`评测已启动 (${data.run_id})`)
      setActiveTab('results')
    },
    onError: () => toast.error('启动评测失败'),
  })

  return (
    <div className="p-4">
      {/* Tabs */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1">
          {(['edit', 'results'] as const).map((t) => (
            <button
              key={t}
              className={cn(
                'px-2.5 py-1 text-xs rounded transition-colors',
                activeTab === t
                  ? 'bg-accent-dim text-accent'
                  : 'text-text3 hover:text-text hover:bg-bg2',
              )}
              onClick={() => setActiveTab(t)}
            >
              {t === 'edit' ? '测试集' : '结果'}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {activeTab === 'edit' && (
            <button
              type="button"
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending}
              className="rounded-lg border border-border px-3 py-1 text-xs text-text2 transition-colors hover:border-accent/40 disabled:opacity-50"
            >
              保存测试集
            </button>
          )}
          <button
            type="button"
            onClick={() => runMut.mutate()}
            disabled={runMut.isPending}
            className="rounded-lg bg-accent px-3 py-1 text-xs font-medium text-[#0f172a] transition-colors hover:bg-accent/80 disabled:opacity-50"
          >
            {runMut.isPending ? '运行中...' : '\u25B6 运行评测'}
          </button>
        </div>
      </div>

      {/* Edit tab: JSON editor */}
      {activeTab === 'edit' && (
        <div>
          <textarea
            value={displayJson}
            onChange={(e) => {
              setJsonText(e.target.value)
              setJsonError(null)
            }}
            spellCheck={false}
            rows={12}
            className="w-full rounded-lg border border-border bg-bg p-3 font-mono text-xs text-text placeholder:text-text3 focus:border-accent/50 focus:outline-none resize-y"
            placeholder='{\n  "skill_name": "my-skill",\n  "evals": [\n    {\n      "id": 1,\n      "prompt": "...",\n      "expected_behavior": "...",\n      "assertions": []\n    }\n  ]\n}'
          />
          {jsonError && <div className="mt-1 text-xs text-red">{jsonError}</div>}
          <div className="mt-2 text-[11px] text-text3">
            assertion check 语法: tool_used:工具名 | output_contains:关键词|关键词 | output_not_contains:关键词 | subagent_used:名 | status:ok|warning|critical
          </div>
        </div>
      )}

      {/* Results tab */}
      {activeTab === 'results' && (
        <div className="space-y-4">
          {results.length === 0 ? (
            <div className="text-xs text-text3 text-center py-6">暂无评测结果</div>
          ) : (
            results.map((run) => <EvalRunCard key={run.run_id} run={run} />)
          )}
        </div>
      )}
    </div>
  )
}

// ── Eval run result card ────────────────────────────────

function EvalRunCard({ run }: { run: EvalRunResult }) {
  const [expanded, setExpanded] = useState(false)
  const summary = run.summary

  return (
    <div className="rounded-xl border border-border bg-bg p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[11px] font-medium',
              run.status === 'completed'
                ? 'bg-green/10 text-green'
                : run.status === 'running'
                  ? 'bg-yellow/10 text-yellow'
                  : 'bg-red/10 text-red',
            )}
          >
            {run.status}
          </span>
          <span className="text-xs text-text3">{run.run_id.slice(0, 8)}</span>
          <span className="text-xs text-text3">{run.started_at}</span>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-text3 hover:text-text transition-colors"
        >
          {expanded ? '收起' : '展开'}
        </button>
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="mt-3 grid grid-cols-4 gap-3">
          <StatCell label="通过率" value={`${(summary.pass_rate * 100).toFixed(0)}%`} />
          <StatCell label="通过/总数" value={`${summary.passed}/${summary.total}`} />
          <StatCell label="平均 Token" value={String(summary.avg_tokens)} />
          <StatCell label="平均耗时" value={`${summary.avg_duration_ms}ms`} />
        </div>
      )}

      {/* Expanded: A/B comparison cards */}
      {expanded && run.results && (
        <div className="mt-4 space-y-3">
          {run.results.map((r) => (
            <EvalCaseCard key={r.eval_id} result={r} />
          ))}
        </div>
      )}
    </div>
  )
}

function EvalCaseCard({ result }: { result: EvalCaseResult }) {
  return (
    <div
      className={cn(
        'rounded-lg border p-3',
        result.passed ? 'border-green/30 bg-green/5' : 'border-red/30 bg-red/5',
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-text">
          Case #{result.eval_id}
        </span>
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-[11px]',
            result.passed ? 'bg-green/10 text-green' : 'bg-red/10 text-red',
          )}
        >
          {result.passed ? 'PASS' : 'FAIL'}
        </span>
      </div>

      {/* A/B comparison */}
      <div className="grid grid-cols-2 gap-3">
        <ABCard title="有技能" side={result.with_skill} />
        <ABCard title="无技能" side={result.without_skill} />
      </div>

      {/* Assertions */}
      {result.assertions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {result.assertions.map((a, i) => (
            <span
              key={i}
              className={cn(
                'rounded px-1.5 py-0.5 text-[11px]',
                a.passed ? 'bg-green/10 text-green' : 'bg-red/10 text-red',
              )}
            >
              {a.passed ? '\u2713' : '\u2717'} {a.name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function ABCard({ title, side }: { title: string; side: EvalCaseResult['with_skill'] }) {
  return (
    <div className="rounded-lg bg-bg2 p-2.5">
      <div className="text-[11px] font-medium text-text3 mb-1.5">{title}</div>
      <div className="text-xs text-text2 line-clamp-3 mb-2">{side.output_summary}</div>
      <div className="flex items-center gap-3 text-[11px] text-text3">
        <span>{side.tokens_used} tok</span>
        <span>{side.duration_ms}ms</span>
        <span>{side.tool_calls.length} tools</span>
      </div>
    </div>
  )
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-bg2 p-2.5 text-center">
      <div className="text-[11px] text-text3">{label}</div>
      <div className="mt-1 text-sm font-semibold text-text">{value}</div>
    </div>
  )
}

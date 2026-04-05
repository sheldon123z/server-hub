/**
 * BatchOperationPage — Fleet 批量操作入口页
 * 预置模板卡片 + 自定义操作按钮 + 历史记录标签
 */
import { useState } from 'react'
import { cn } from '@/lib/utils'
import BatchJobWizard from './BatchJobWizard'
import BatchJobProgress from './BatchJobProgress'
import BatchHistory from './BatchHistory'

// ---------------------------------------------------------------------------
// 预置模板卡片配置
// ---------------------------------------------------------------------------
interface PresetCard {
  id: string
  name: string
  description: string
  icon: string
  iconColor: string
  bg: string
  border: string
}

const PRESET_CARDS: PresetCard[] = [
  {
    id: 'sys_info',
    name: '批量系统信息',
    description: '并行采集所有服务器的 CPU、内存、磁盘信息',
    icon: 'ti-server-2',
    iconColor: 'text-accent',
    bg: 'bg-accent/5',
    border: 'border-accent/20',
  },
  {
    id: 'docker_prune',
    name: '批量 Docker 清理',
    description: '并行清理未使用的容器、镜像和数据卷，释放磁盘空间',
    icon: 'ti-brand-docker',
    iconColor: 'text-sky-400',
    bg: 'bg-sky-500/5',
    border: 'border-sky-500/20',
  },
  {
    id: 'security_check',
    name: '批量安全检查',
    description: '并行执行安全审计脚本，扫描常见漏洞和配置问题',
    icon: 'ti-shield-check',
    iconColor: 'text-green',
    bg: 'bg-green/5',
    border: 'border-green/20',
  },
  {
    id: 'service_restart',
    name: '批量服务重启',
    description: '滚动重启指定 systemd 服务，保持高可用',
    icon: 'ti-refresh',
    iconColor: 'text-yellow',
    bg: 'bg-yellow/5',
    border: 'border-yellow/20',
  },
]

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------
export default function BatchOperationPage() {
  const [showWizard, setShowWizard] = useState(false)
  const [initialPreset, setInitialPreset] = useState('')
  const [viewJobId, setViewJobId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'create' | 'history'>('create')

  const openWizard = (presetId: string) => {
    setInitialPreset(presetId)
    setShowWizard(true)
  }

  const handleCreated = (jobId: string) => {
    setShowWizard(false)
    setViewJobId(jobId)
    setActiveTab('history')
  }

  return (
    <div className="space-y-5">
      {/* ── 页头 ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text">Fleet 批量操作</h1>
          <p className="text-xs text-text3 mt-0.5">
            向多台服务器并行或串行下发操作，实时追踪执行进度
          </p>
        </div>
        <button
          onClick={() => openWizard('custom')}
          className="flex items-center gap-2 bg-accent text-[#0f172a] px-4 py-2 rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
        >
          <i className="ti ti-terminal-2" />
          自定义操作
        </button>
      </div>

      {/* ── 标签栏 ── */}
      <div className="flex gap-1 border-b border-border pb-0">
        {(
          [
            ['create', '快速操作'],
            ['history', '历史记录'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={cn(
              'px-4 py-2 text-sm border-b-2 -mb-px transition-colors',
              activeTab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-text3 hover:text-text2',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── 快速操作 ── */}
      {activeTab === 'create' && (
        <div className="space-y-4">
          <p className="text-xs text-text3">
            选择预置模板快速开始，或点击右上角「自定义操作」输入命令
          </p>

          {/* 预置卡片网格 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {PRESET_CARDS.map((card) => (
              <button
                key={card.id}
                onClick={() => openWizard(card.id)}
                className={cn(
                  'flex flex-col items-start p-5 rounded-xl border text-left transition-all',
                  'hover:scale-[1.02] hover:shadow-lg active:scale-100',
                  card.bg,
                  card.border,
                )}
              >
                <i className={cn('ti', card.icon, card.iconColor, 'text-2xl mb-3')} />
                <div className="text-sm font-semibold text-text mb-1">{card.name}</div>
                <div className="text-xs text-text3 leading-relaxed">
                  {card.description}
                </div>
              </button>
            ))}

            {/* 自定义卡片 */}
            <button
              onClick={() => openWizard('custom')}
              className="flex flex-col items-start p-5 rounded-xl border border-dashed border-border bg-bg2 text-left transition-all hover:border-accent/40 hover:bg-accent/5 active:scale-[0.98]"
            >
              <i className="ti ti-plus text-text3 text-2xl mb-3" />
              <div className="text-sm font-semibold text-text mb-1">自定义命令</div>
              <div className="text-xs text-text3 leading-relaxed">
                输入任意 Shell 命令，自由选择执行策略
              </div>
            </button>
          </div>

          {/* 使用提示 */}
          <div className="bg-bg2 border border-border rounded-lg p-4 text-xs text-text3 space-y-1.5">
            <div className="font-medium text-text2 mb-2">执行策略说明</div>
            <div>
              <span className="text-text font-medium">并行</span>
              {' '}— 全部服务器同时执行，最快完成，适合只读操作
            </div>
            <div>
              <span className="text-text font-medium">串行</span>
              {' '}— 逐台顺序执行，适合有依赖顺序的场景
            </div>
            <div>
              <span className="text-text font-medium">滚动</span>
              {' '}— 每批 N 台并行，滚动推进，适合服务重启等保可用场景
            </div>
          </div>
        </div>
      )}

      {/* ── 历史记录 ── */}
      {activeTab === 'history' && (
        <BatchHistory onViewJob={(id) => setViewJobId(id)} />
      )}

      {/* ── 向导 Modal ── */}
      {showWizard && (
        <BatchJobWizard
          initialPresetId={initialPreset}
          onClose={() => setShowWizard(false)}
          onCreated={handleCreated}
        />
      )}

      {/* ── 进度 Modal ── */}
      {viewJobId && (
        <BatchJobProgress
          jobId={viewJobId}
          onClose={() => setViewJobId(null)}
        />
      )}
    </div>
  )
}

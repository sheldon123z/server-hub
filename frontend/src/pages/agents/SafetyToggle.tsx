/**
 * SafetyToggle - Segmented control for supervised/autonomous mode.
 * Switching to autonomous shows a confirm dialog.
 */

import { useState } from 'react'
import { cn } from '@/lib/utils'

export interface SafetyToggleProps {
  value: 'supervised' | 'autonomous'
  onChange: (mode: 'supervised' | 'autonomous') => void
}

export function SafetyToggle({ value, onChange }: SafetyToggleProps) {
  const [showConfirm, setShowConfirm] = useState(false)

  function handleClick(mode: 'supervised' | 'autonomous') {
    if (mode === value) return
    if (mode === 'autonomous') {
      setShowConfirm(true)
    } else {
      onChange(mode)
    }
  }

  function confirmAutonomous() {
    onChange('autonomous')
    setShowConfirm(false)
  }

  return (
    <>
      <div className="flex items-center bg-bg rounded border border-border text-xs">
        <button
          className={cn(
            'px-2 py-1 rounded-l transition-colors',
            value === 'supervised'
              ? 'bg-accent-dim text-accent'
              : 'text-text3 hover:text-text',
          )}
          onClick={() => handleClick('supervised')}
        >
          监督
        </button>
        <button
          className={cn(
            'px-2 py-1 rounded-r transition-colors',
            value === 'autonomous'
              ? 'bg-accent-dim text-accent'
              : 'text-text3 hover:text-text',
          )}
          onClick={() => handleClick('autonomous')}
        >
          自主
        </button>
      </div>

      {/* Confirm dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50">
          <div className="bg-card border border-border rounded-xl shadow-2xl p-5 max-w-sm mx-4 space-y-4">
            <h3 className="text-sm font-medium text-text">切换到自主模式?</h3>
            <p className="text-xs text-text2 leading-relaxed">
              自主模式下，Agent 将不再需要人工审批即可执行危险操作（如重启服务、修改文件等）。
              仍有 Shell 黑名单底线防护。
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-xs rounded text-text3 hover:text-text hover:bg-bg2 transition-colors"
                onClick={() => setShowConfirm(false)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-xs rounded bg-yellow/15 text-yellow hover:bg-yellow/25 transition-colors"
                onClick={confirmAutonomous}
              >
                确认切换
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

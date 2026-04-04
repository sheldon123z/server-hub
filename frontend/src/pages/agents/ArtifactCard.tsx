/**
 * ArtifactCard - 内联 Artifact 卡片，显示在对话流工具调用之后。
 * 点击后打开右栏 Artifact 查看器。
 */

import { FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getFileName } from '@/lib/file-utils'
import { useArtifactStore } from '@/stores/artifactStore'

interface ArtifactCardProps {
  filePath: string
  action: 'write_file' | 'edit_file'
}

export function ArtifactCard({ filePath, action }: ArtifactCardProps) {
  const label = action === 'write_file' ? '新建' : '编辑'

  return (
    <button
      type="button"
      title={filePath}
      onClick={() => useArtifactStore.getState().select(filePath)}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-xs',
        'text-text transition-colors hover:bg-bg2 cursor-pointer',
      )}
    >
      <FileText size={12} className="shrink-0 text-accent" />
      <span className="font-medium">{getFileName(filePath)}</span>
      <span
        className={cn(
          'rounded px-1 py-0.5 text-[10px] font-medium leading-none',
          action === 'write_file'
            ? 'bg-green/15 text-green'
            : 'bg-accent/15 text-accent',
        )}
      >
        {label}
      </span>
    </button>
  )
}

import { GripVertical } from 'lucide-react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { cn } from '@/lib/utils'

export function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof Group>) {
  return (
    <Group
      className={cn('flex h-full w-full', className)}
      {...props}
    />
  )
}

export const ResizablePanel = Panel

export function ResizableHandle({
  withHandle,
  className,
  ...props
}: Omit<React.ComponentProps<typeof Separator>, 'children'> & {
  withHandle?: boolean
}) {
  return (
    <Separator
      className={cn(
        'relative flex w-px items-center justify-center bg-border',
        'after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2',
        'hover:bg-accent/50 transition-colors',
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border border-border bg-bg2">
          <GripVertical className="h-2.5 w-2.5 text-text3" />
        </div>
      )}
    </Separator>
  )
}

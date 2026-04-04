/**
 * Collapsible — CSS transition 折叠/展开容器
 */
import { useState, useRef, useEffect, createContext, useContext } from 'react'
import { cn } from '@/lib/utils'

interface CollapsibleProps {
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
  className?: string
}

const CollapsibleContext = createContext<{ isOpen: boolean; toggle: () => void }>({
  isOpen: false,
  toggle: () => {},
})

export function useCollapsible() {
  return useContext(CollapsibleContext)
}

export function Collapsible({
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  children,
  className,
}: CollapsibleProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen

  const toggle = () => {
    const next = !isOpen
    setInternalOpen(next)
    onOpenChange?.(next)
  }

  return (
    <CollapsibleContext.Provider value={{ isOpen, toggle }}>
      <div className={className}>{children}</div>
    </CollapsibleContext.Provider>
  )
}

export function CollapsibleTrigger({ children, className }: { children: React.ReactNode; className?: string }) {
  const { toggle } = useCollapsible()
  return (
    <button onClick={toggle} className={cn('w-full text-left', className)} type="button">
      {children}
    </button>
  )
}

export function CollapsibleContent({ children, className }: { children: React.ReactNode; className?: string }) {
  const { isOpen } = useCollapsible()
  const contentRef = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number | undefined>(undefined)

  useEffect(() => {
    if (contentRef.current) {
      setHeight(contentRef.current.scrollHeight)
    }
  }, [children, isOpen])

  return (
    <div
      className={cn('overflow-hidden transition-all duration-200 ease-in-out', className)}
      style={{ maxHeight: isOpen ? (height ?? 'none') : 0, opacity: isOpen ? 1 : 0 }}
    >
      <div ref={contentRef}>{children}</div>
    </div>
  )
}

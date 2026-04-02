/**
 * 组件注册中心
 *
 * 基于 Zustand 的 UI 组件渲染器注册中心，支持动态注册和查找。
 * 内置渲染器通过动态 import() 延迟加载，减少首屏体积。
 */
import { create } from 'zustand'
import type { ComponentType } from 'react'
import type { UIComponentData } from '@/types/agent'

// ── 类型定义 ──

export interface RendererProps {
  component: UIComponentData
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
  loadingActions?: Set<string>
}

interface ComponentRegistryState {
  renderers: Map<string, ComponentType<RendererProps>>
  register: (type: string, renderer: ComponentType<RendererProps>) => void
  getRenderer: (type: string) => ComponentType<RendererProps> | null
}

// ── Store ──

export const useComponentRegistry = create<ComponentRegistryState>((set, get) => ({
  renderers: new Map(),

  register: (type, renderer) => {
    set((state) => {
      const next = new Map(state.renderers)
      next.set(type, renderer)
      return { renderers: next }
    })
  },

  getRenderer: (type) => {
    return get().renderers.get(type) ?? null
  },
}))

// ── 内置组件延迟注册 ──

let _builtInRegistered = false

/**
 * 注册内置渲染器组件。
 * 使用动态 import() 实现延迟加载，仅在实际需要时加载对应组件。
 * 多次调用安全——仅首次生效。
 */
export async function registerBuiltInComponents(): Promise<void> {
  if (_builtInRegistered) return
  _builtInRegistered = true

  const { register } = useComponentRegistry.getState()

  // 延迟注册四种内置渲染器
  const registrations: Array<[string, () => Promise<{ default: ComponentType<RendererProps> }>]> = [
    [
      'chart',
      // Lazy-loaded renderer (component types widened via dynamic import)
      () =>
        import('@/components/agent/renderers/ChartRenderer').then((m) => ({
          default: m.ChartRenderer as unknown as ComponentType<RendererProps>,
        })),
    ],
    [
      'table',
      () =>
        import('@/components/agent/renderers/DataTable').then((m) => ({
          default: m.DataTable as unknown as ComponentType<RendererProps>,
        })),
    ],
    [
      'form',
      () =>
        import('@/components/agent/renderers/ConfigForm').then((m) => ({
          default: m.ConfigForm as unknown as ComponentType<RendererProps>,
        })),
    ],
    [
      'card',
      () =>
        import('@/components/agent/renderers/StatusCard').then((m) => ({
          default: m.StatusCard as unknown as ComponentType<RendererProps>,
        })),
    ],
  ]

  // 并行加载所有渲染器
  const results = await Promise.allSettled(registrations.map(([, loader]) => loader()))

  for (let i = 0; i < results.length; i++) {
    const result = results[i]
    if (result.status === 'fulfilled') {
      register(registrations[i][0], result.value.default)
    } else {
      console.warn(`[ComponentRegistry] Failed to load renderer "${registrations[i][0]}":`, result.reason)
    }
  }
}

import { Component, type ReactNode } from 'react'

/**
 * 错误边界组件属性
 */
interface Props {
  /** 被包裹的子组件树 */
  children: ReactNode
  /**
   * 渲染错误时的降级 UI；
   * 传入 null 可完全隐藏出错区域，不传则展示默认错误面板（含重试按钮）
   */
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * React 错误边界
 * 捕获子组件树的渲染异常，展示降级 UI 或默认错误面板
 * 通过 'fallback' in props 区分「未传 fallback」和「显式传入 null」
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      // 区分"未传 fallback"和"显式传入 null/false"
      // ?? 运算符对 null 和 undefined 一视同仁，无法区分二者
      if ('fallback' in this.props) {
        return this.props.fallback as ReactNode
      }
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
          <div className="text-red text-lg font-semibold">页面渲染出错</div>
          <pre className="text-xs text-text3 bg-bg2 p-4 rounded-lg max-w-lg overflow-auto">
            {this.state.error?.message}
          </pre>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 bg-accent text-[#0f172a] rounded-md text-sm font-medium"
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

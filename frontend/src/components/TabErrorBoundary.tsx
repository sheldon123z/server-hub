/**
 * TabErrorBoundary - 标签页级错误边界
 * 捕获单个标签页的渲染异常，避免整个页面白屏。
 * 生产环境不暴露 error.message 详情。
 */

import { Component, type ReactNode } from 'react'

interface Props {
  /** 标签页名称，用于错误提示 */
  tabName: string
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class TabErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      const isDev = import.meta.env.DEV
      return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red/30 bg-red/5 p-8">
          <div className="text-base font-semibold text-red">
            "{this.props.tabName}" 标签页渲染出错
          </div>
          <p className="text-sm text-text3">该标签页发生了意外错误，其他标签页不受影响。</p>
          {isDev && this.state.error && (
            <pre className="mt-1 max-h-32 max-w-full overflow-auto rounded-lg bg-bg2 p-3 text-xs text-text3">
              {this.state.error.message}
            </pre>
          )}
          <button
            type="button"
            onClick={this.handleRetry}
            className="mt-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-[#0f172a] transition-colors hover:bg-accent/80"
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

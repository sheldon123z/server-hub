/**
 * UIComponentErrorBoundary — catches render errors from individual
 * UI component cards so one broken component doesn't crash the entire chat.
 */

import { Component, type ReactNode } from 'react'

interface Props {
  componentId: string
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class UIComponentErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      const isDev = import.meta.env.DEV

      return (
        <div className="border border-red/30 bg-red/5 rounded-lg p-3 text-sm">
          <div className="font-medium text-red mb-1">组件渲染失败</div>
          {isDev && (
            <>
              <p className="text-xs text-text3 mb-2">
                组件 ID: {this.props.componentId}
              </p>
              <pre className="text-xs text-text3 bg-bg2 p-2 rounded overflow-auto max-h-24">
                {this.state.error?.message}
              </pre>
            </>
          )}
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-2 px-2 py-1 text-xs rounded bg-bg3 text-text2 hover:text-text transition-colors"
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

type Props = {
  children: ReactNode
  /**
   * Change this to clear a caught error. App passes the current pathname, so
   * navigating away from a page that crashed recovers without a full reload.
   */
  resetKey?: string
}

type State = { error: Error | null; resetKey?: string }

/**
 * The last line of defence against a blank screen.
 *
 * Without a boundary, one exception thrown while rendering -- an unexpected
 * `null` in an API payload is the usual one -- unmounts the entire React tree
 * and leaves the user on an empty white page with no way forward except
 * guessing that a reload might help. This catches it, says what happened in
 * plain words, and offers the two actions that actually work.
 *
 * It does not catch errors in event handlers or async code (React never
 * routes those through boundaries); those already surface as toasts and
 * inline alerts.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  // Derived before render rather than reset in componentDidUpdate, which
  // would render the error screen once more before clearing it.
  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey }
    }
    return null
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept in the console so a bug report can include it. Nothing is sent
    // anywhere: the app has no error-reporting service, and adding one is a
    // privacy decision, not a UI one.
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <main className="error-screen" id="main-content">
        <div className="error-card" role="alert">
          <h1 className="error-title">Something went wrong on this page</h1>
          <p className="error-body">
            TailorUp hit an unexpected error while showing this screen. Your data is safe: nothing
            was lost or changed. Reloading usually fixes it.
          </p>
          <div className="error-actions">
            <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
              Reload page
            </button>
            <a className="btn btn-ghost" href="/">
              Go to home page
            </a>
          </div>
          {import.meta.env.DEV ? (
            <pre className="error-detail">{this.state.error.message}</pre>
          ) : null}
        </div>
      </main>
    )
  }
}

export default ErrorBoundary

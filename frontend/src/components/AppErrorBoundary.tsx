import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { reportClientException } from '../utils/exceptionReporter';

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
  message: string;
}

/**
 * Catches React render/lifecycle exceptions on every page and forwards them
 * to the Insights Exception Report.
 */
export default class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      message: error?.message || 'Unexpected application error',
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportClientException({
      severity: 'EXCEPTION',
      source: 'ui',
      category: 'react_render',
      message: error?.message || 'React render error',
      details: [
        error?.stack ? error.stack.slice(0, 1500) : '',
        info.componentStack ? info.componentStack.slice(0, 1500) : '',
      ].filter(Boolean),
      exception_type: error?.name || 'Error',
      related_resource: 'react',
      related_id: 'error_boundary',
    });
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleDismiss = (): void => {
    this.setState({ hasError: false, message: '' });
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-bg px-4">
        <div className="max-w-lg w-full rounded-2xl border border-red-200 bg-card p-6 shadow-sm">
          <h1 className="text-lg font-bold text-text-main">Something went wrong</h1>
          <p className="mt-2 text-sm text-text-muted">
            This error was captured in Insights → Exception Report. You can reload the page or
            continue if the screen recovers.
          </p>
          <p className="mt-3 text-xs text-red-700 break-words">{this.state.message}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={this.handleReload}
              className="inline-flex items-center rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
            >
              Reload
            </button>
            <button
              type="button"
              onClick={this.handleDismiss}
              className="inline-flex items-center rounded-lg border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  }
}

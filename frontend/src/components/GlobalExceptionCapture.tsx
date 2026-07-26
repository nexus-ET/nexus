import { useEffect } from 'react';
import {
  autoResolveTransientExceptionsOnPageRefresh,
  reportClientException,
} from '../utils/exceptionReporter';

/**
 * Installs window-level error listeners once so uncaught JS errors and
 * unhandled promise rejections from any Nexus page are sent to Exception Report.
 * Also auto-resolves transient client exceptions after a healthy page refresh.
 */
export default function GlobalExceptionCapture(): null {
  useEffect(() => {
    autoResolveTransientExceptionsOnPageRefresh();

    const onError = (event: ErrorEvent) => {
      const message = event.message || event.error?.message || 'Unhandled window error';
      reportClientException({
        severity: 'EXCEPTION',
        source: 'ui',
        category: 'window_onerror',
        message,
        details: [
          event.filename ? `file=${event.filename}:${event.lineno || 0}:${event.colno || 0}` : '',
          event.error?.stack ? String(event.error.stack).slice(0, 1500) : '',
        ].filter(Boolean),
        exception_type: event.error?.name || 'Error',
        related_resource: 'window',
        related_id: 'onerror',
      });
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      let message = 'Unhandled promise rejection';
      let exceptionType = 'UnhandledRejection';
      const details: string[] = [];

      if (reason instanceof Error) {
        message = reason.message || message;
        exceptionType = reason.name || exceptionType;
        if (reason.stack) details.push(reason.stack.slice(0, 1500));
      } else if (typeof reason === 'string') {
        message = reason;
      } else if (reason != null) {
        try {
          message = JSON.stringify(reason).slice(0, 500);
        } catch {
          message = String(reason).slice(0, 500);
        }
      }

      reportClientException({
        severity: 'EXCEPTION',
        source: 'ui',
        category: 'unhandled_rejection',
        message,
        details,
        exception_type: exceptionType,
        related_resource: 'window',
        related_id: 'unhandledrejection',
      });
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  return null;
}

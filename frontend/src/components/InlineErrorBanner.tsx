import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

type InlineErrorBannerProps = {
  message: string | null;
  onDismiss: () => void;
};

const InlineErrorBanner: React.FC<InlineErrorBannerProps> = ({ message, onDismiss }) => {
  if (!message) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="mx-3 mt-3 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 shadow-sm"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
      <span className="min-w-0 flex-1 text-sm font-semibold">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 rounded p-0.5 text-amber-700 transition hover:bg-amber-100 hover:text-amber-950"
        aria-label="Dismiss error"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
};

export default InlineErrorBanner;

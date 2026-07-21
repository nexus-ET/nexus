import type { ReactNode } from 'react';

interface EmptyListMessageProps {
  message: ReactNode;
  className?: string;
  compact?: boolean;
}

/**
 * Shared empty-state panel for list / table sections across Nexus.
 */
const EmptyListMessage: React.FC<EmptyListMessageProps> = ({
  message,
  className = '',
  compact = false,
}) => (
  <div
    role="status"
    className={`rounded-xl border border-dashed border-border-subtle text-center text-sm text-text-muted ${
      compact ? 'px-4 py-5' : 'px-4 py-8'
    } ${className}`.trim()}
  >
    {message}
  </div>
);

export default EmptyListMessage;

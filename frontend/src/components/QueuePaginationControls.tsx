import type { CSSProperties, ReactNode } from 'react';

type QueuePaginationControlsProps = {
  page: number;
  totalPages: number;
  hasMorePages?: boolean;
  disabled?: boolean;
  onPageChange: (page: number) => void;
  className?: string;
  style?: CSSProperties;
  buttonClassName?: string;
  metaClassName?: string;
  buttonStyle?: CSSProperties;
  metaStyle?: CSSProperties;
  disabledButtonStyle?: CSSProperties;
};

const defaultWrap: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '8px',
};

const defaultButton: CSSProperties = {
  padding: '6px 10px',
  borderRadius: '6px',
  border: '1px solid #cbd5e1',
  backgroundColor: '#ffffff',
  color: '#0f172a',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer',
  flexShrink: 0,
};

const defaultDisabled: CSSProperties = {
  opacity: 0.45,
  cursor: 'not-allowed',
};

const defaultMeta: CSSProperties = {
  fontSize: '11px',
  fontWeight: 600,
  color: '#64748b',
  textAlign: 'center',
  flex: 1,
};

export default function QueuePaginationControls({
  page,
  totalPages,
  hasMorePages = false,
  disabled = false,
  onPageChange,
  className,
  style,
  buttonClassName,
  metaClassName,
  buttonStyle,
  metaStyle,
  disabledButtonStyle,
}: QueuePaginationControlsProps): ReactNode {
  const prevDisabled = page <= 1 || disabled;
  const nextDisabled = disabled || (page >= totalPages && !hasMorePages);

  return (
    <div className={className} style={{ ...defaultWrap, ...style }}>
      <button
        type="button"
        className={buttonClassName}
        style={{
          ...defaultButton,
          ...buttonStyle,
          ...(prevDisabled ? { ...defaultDisabled, ...disabledButtonStyle } : {}),
        }}
        disabled={prevDisabled}
        onClick={() => onPageChange(Math.max(1, page - 1))}
      >
        Previous
      </button>
      <span className={metaClassName} style={{ ...defaultMeta, ...metaStyle }}>
        Page {page} of {Math.max(1, totalPages)}
      </span>
      <button
        type="button"
        className={buttonClassName}
        style={{
          ...defaultButton,
          ...buttonStyle,
          ...(nextDisabled ? { ...defaultDisabled, ...disabledButtonStyle } : {}),
        }}
        disabled={nextDisabled}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </button>
    </div>
  );
}

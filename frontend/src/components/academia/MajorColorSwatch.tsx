import type { CSSProperties } from 'react';

import { majorColorStyles } from '../../utils/majorColors';

interface MajorColorSwatchProps {
  color?: string | null;
  label?: string;
  size?: 'sm' | 'md';
  className?: string;
}

const SIZE_CLASSES = {
  sm: 'h-3 w-3',
  md: 'h-4 w-4',
} as const;

export default function MajorColorSwatch({
  color,
  label,
  size = 'md',
  className = '',
}: MajorColorSwatchProps) {
  const styles = majorColorStyles(color);
  const swatchStyle: CSSProperties = styles.swatchStyle ?? {
    backgroundColor: 'var(--color-border-subtle)',
  };

  return (
    <span
      className={`inline-block shrink-0 rounded-full border border-black/10 ${SIZE_CLASSES[size]} ${className}`}
      style={swatchStyle}
      title={label ? `${label} color` : 'Major color'}
      aria-hidden={label ? undefined : true}
    />
  );
}

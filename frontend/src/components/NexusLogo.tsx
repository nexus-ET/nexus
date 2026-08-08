interface NexusLogoProps {
  /** Visual size of the mark in pixels (CSS width/height). */
  size?: number;
  className?: string;
  alt?: string;
}

const LOGO_SRC = '/brand/nexus-n-logo-option-b.png?v=7';

/**
 * Official Nexus "N" mark (option B — indigo badge with italic N + cyan accent).
 */
const NexusLogo: React.FC<NexusLogoProps> = ({
  size = 40,
  className = '',
  alt = 'Nexus',
}) => (
  <img
    src={LOGO_SRC}
    alt={alt}
    width={size}
    height={size}
    className={`block shrink-0 object-contain ${className}`}
    style={{ width: size, height: size }}
    decoding="async"
  />
);

export default NexusLogo;

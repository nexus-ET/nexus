const EMAIL_USERNAME_PATTERN = /^[a-zA-Z0-9](?:[a-zA-Z0-9._+-]*[a-zA-Z0-9])?$/;

export const splitEmailUsername = (email: string, businessEmailDomain?: string | null): string => {
  const trimmed = email.trim();
  if (!trimmed) return '';

  const atIndex = trimmed.lastIndexOf('@');
  if (atIndex === -1) return trimmed;

  const localPart = trimmed.slice(0, atIndex);
  const domainPart = trimmed.slice(atIndex + 1).toLowerCase();
  const configuredDomain = businessEmailDomain?.trim().toLowerCase();

  if (configuredDomain && domainPart === configuredDomain) {
    return localPart;
  }

  return localPart;
};

export const buildBusinessEmail = (username: string, businessEmailDomain: string): string => {
  const cleanedUsername = username.trim().toLowerCase();
  const cleanedDomain = businessEmailDomain.trim().toLowerCase();
  return `${cleanedUsername}@${cleanedDomain}`;
};

export const validateEmailUsername = (
  username: string,
  businessEmailDomain?: string | null
): string | null => {
  const trimmed = username.trim();

  if (!trimmed) {
    return 'Email username is required.';
  }

  if (trimmed.includes('@')) {
    return 'Enter only the username — do not include @ or the domain.';
  }

  if (!EMAIL_USERNAME_PATTERN.test(trimmed)) {
    return 'Username may only contain letters, numbers, dots, hyphens, underscores, and plus signs.';
  }

  if (!businessEmailDomain?.trim()) {
    return 'Business email domain is not configured. Set it in Application Settings first.';
  }

  return null;
};

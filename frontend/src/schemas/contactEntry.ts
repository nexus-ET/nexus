import { z } from 'zod';

import {
  EMAIL_CONTACT_TYPES,
  EMAIL_TYPE_GENERAL,
  FAX_CONTACT_TYPES,
  FAX_TYPE_MAIN,
  PHONE_CONTACT_TYPES,
  PHONE_TYPE_MAIN,
  WEB_LINK_TYPE_WEBSITE,
  WEB_LINK_TYPES,
} from '../constants/contactTypes';

export interface ContactEntry {
  type: string;
  value: string;
}

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmailAddress(value: string): boolean {
  return emailPattern.test(value.trim());
}

export const contactEntrySchema = z.object({
  type: z.string().min(1, 'Contact type is required'),
  value: z.string().max(250),
});

/** Validates email format for any non-empty values; empty rows are allowed. */
export const optionalEmailContactListSchema = z
  .array(contactEntrySchema)
  .superRefine((entries, ctx) => {
    const allowed = new Set(EMAIL_CONTACT_TYPES.map(option => option.value));
    entries.forEach((entry, index) => {
      if (!allowed.has(entry.type)) {
        ctx.addIssue({
          code: 'custom',
          message: 'Invalid email type',
          path: [index, 'type'],
        });
      }
      const value = entry.value.trim();
      if (value && !isValidEmailAddress(value)) {
        ctx.addIssue({
          code: 'custom',
          message: 'Enter a valid email address (example: name@school.edu)',
          path: [index, 'value'],
        });
      }
    });
  });

function normalizeContactItems(
  raw: unknown,
  allowedTypes: readonly string[],
  defaultType: string
): ContactEntry[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    return [{ type: defaultType, value: '' }];
  }

  const normalized: ContactEntry[] = [];
  raw.forEach((item, index) => {
    if (typeof item === 'string') {
      const value = item.trim();
      if (!value) return;
      normalized.push({
        type: index === 0 ? defaultType : allowedTypes[allowedTypes.length - 1],
        value,
      });
      return;
    }

    if (item && typeof item === 'object') {
      const record = item as Partial<ContactEntry>;
      const value = String(record.value || '').trim();
      const fallbackType = index === 0 ? defaultType : allowedTypes[allowedTypes.length - 1];
      const type = String(record.type || '').trim() || fallbackType;
      normalized.push({
        type: allowedTypes.includes(type) ? type : fallbackType,
        value,
      });
    }
  });

  return normalized.length > 0 ? normalized : [{ type: defaultType, value: '' }];
}

export function normalizePhoneContacts(raw: unknown): ContactEntry[] {
  return normalizeContactItems(
    raw,
    PHONE_CONTACT_TYPES.map(option => option.value),
    PHONE_TYPE_MAIN
  );
}

export function normalizeFaxContacts(
  raw: unknown,
  legacyFaxNumber?: string | null
): ContactEntry[] {
  if (Array.isArray(raw) && raw.length > 0) {
    return normalizeContactItems(
      raw,
      FAX_CONTACT_TYPES.map(option => option.value),
      FAX_TYPE_MAIN
    );
  }
  const legacy = (legacyFaxNumber || '').trim();
  if (legacy) {
    return [{ type: FAX_TYPE_MAIN, value: legacy }];
  }
  return createDefaultFaxContacts();
}

export function normalizeEmailContacts(raw: unknown): ContactEntry[] {
  return normalizeContactItems(
    raw,
    EMAIL_CONTACT_TYPES.map(option => option.value),
    EMAIL_TYPE_GENERAL
  );
}

export function createDefaultPhoneContacts(): ContactEntry[] {
  return [{ type: PHONE_TYPE_MAIN, value: '' }];
}

export function createDefaultFaxContacts(): ContactEntry[] {
  return [{ type: FAX_TYPE_MAIN, value: '' }];
}

export function createDefaultEmailContacts(): ContactEntry[] {
  return [{ type: EMAIL_TYPE_GENERAL, value: '' }];
}

export function createDefaultWebLinks(): ContactEntry[] {
  return [{ type: WEB_LINK_TYPE_WEBSITE, value: '' }];
}

export function isValidWebUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function normalizeWebLinks(raw: unknown, legacyUrl?: string | null): ContactEntry[] {
  if (Array.isArray(raw) && raw.length > 0) {
    return normalizeContactItems(
      raw,
      WEB_LINK_TYPES.map(option => option.value),
      WEB_LINK_TYPE_WEBSITE
    );
  }
  const legacy = (legacyUrl || '').trim();
  if (legacy) {
    return [{ type: WEB_LINK_TYPE_WEBSITE, value: legacy }];
  }
  return createDefaultWebLinks();
}

/** Prefer Website-typed URL; otherwise first non-empty link. */
export function primaryWebUrl(entries: ContactEntry[]): string | null {
  const serialized = serializeContacts(entries);
  if (!serialized.length) return null;
  const website = serialized.find(entry => entry.type === WEB_LINK_TYPE_WEBSITE);
  return (website || serialized[0]).value;
}

export function serializeContacts(entries: ContactEntry[]): ContactEntry[] {
  return entries
    .map(entry => ({ type: entry.type, value: entry.value.trim() }))
    .filter(entry => entry.value);
}

export function formatContactList(entries: ContactEntry[]): string {
  const serialized = serializeContacts(entries);
  if (!serialized.length) return '—';
  return serialized.map(entry => `${entry.type}: ${entry.value}`).join(', ');
}

export const phoneContactListSchema = z
  .array(contactEntrySchema)
  .superRefine((entries, ctx) => {
    const allowed = new Set(PHONE_CONTACT_TYPES.map(option => option.value));
    let hasPhone = false;

    entries.forEach((entry, index) => {
      if (!allowed.has(entry.type)) {
        ctx.addIssue({
          code: 'custom',
          message: 'Invalid phone type',
          path: [index, 'type'],
        });
      }
      if (entry.value.trim()) {
        hasPhone = true;
      }
    });

    if (!hasPhone) {
      ctx.addIssue({
        code: 'custom',
        message: 'At least one phone number is required',
        path: [0, 'value'],
      });
    }
  });

/** Optional fax list — same types as phone; empty values are allowed. */
export const faxContactListSchema = z.array(contactEntrySchema).superRefine((entries, ctx) => {
  const allowed = new Set(FAX_CONTACT_TYPES.map(option => option.value));
  entries.forEach((entry, index) => {
    if (!allowed.has(entry.type)) {
      ctx.addIssue({
        code: 'custom',
        message: 'Invalid fax type',
        path: [index, 'type'],
      });
    }
  });
});

export const emailContactListSchema = z
  .array(contactEntrySchema)
  .superRefine((entries, ctx) => {
    const allowed = new Set(EMAIL_CONTACT_TYPES.map(option => option.value));
    let hasEmail = false;

    entries.forEach((entry, index) => {
      if (!allowed.has(entry.type)) {
        ctx.addIssue({
          code: 'custom',
          message: 'Invalid email type',
          path: [index, 'type'],
        });
      }
      const value = entry.value.trim();
      if (value && !isValidEmailAddress(value)) {
        ctx.addIssue({
          code: 'custom',
          message: 'Enter a valid email address (example: name@school.edu)',
          path: [index, 'value'],
        });
      }
      if (value) {
        hasEmail = true;
      }
    });

    if (!hasEmail) {
      ctx.addIssue({
        code: 'custom',
        message: 'At least one email address is required',
        path: [0, 'value'],
      });
    }
  });

/** Optional web links — empty values allowed; non-empty must be http(s) URLs. */
export const webLinkListSchema = z.array(contactEntrySchema).superRefine((entries, ctx) => {
  const allowed = new Set(WEB_LINK_TYPES.map(option => option.value));
  entries.forEach((entry, index) => {
    if (!allowed.has(entry.type)) {
      ctx.addIssue({
        code: 'custom',
        message: 'Invalid web link type',
        path: [index, 'type'],
      });
    }
    const value = entry.value.trim();
    if (value && !isValidWebUrl(value)) {
      ctx.addIssue({
        code: 'custom',
        message: 'Website URL must be a valid link',
        path: [index, 'value'],
      });
    }
    if (value.length > 250) {
      ctx.addIssue({
        code: 'custom',
        message: 'URL must be 250 characters or fewer',
        path: [index, 'value'],
      });
    }
  });
});

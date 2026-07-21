import { z } from 'zod';

import { emptyToNull, IMAGE_MIME_TYPES, MAX_PICTURE_BYTES } from './shared';

function isAllowedMediaUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (
    trimmed.startsWith('/api/v1/academia/media/') ||
    trimmed.startsWith('/academia/media/') ||
    trimmed.startsWith('/uploads/')
  ) {
    return true;
  }
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export const wizardPictureItemSchema = z
  .object({
    local_id: z.string().optional(),
    url: z.preprocess(emptyToNull, z.string().nullable().optional()),
    caption: z.preprocess(emptyToNull, z.string().max(255).nullable().optional()),
    picture_type: z.enum(['gallery', 'logo', 'banner', 'campus']).default('gallery'),
    file_name: z.preprocess(emptyToNull, z.string().nullable().optional()),
    file_size: z.number().nullable().optional(),
    file_type: z.preprocess(emptyToNull, z.string().nullable().optional()),
    college_id: z.number().nullable().optional(),
    college_local_id: z.preprocess(emptyToNull, z.string().nullable().optional()),
    storage_key: z.preprocess(emptyToNull, z.string().nullable().optional()),
  })
  .superRefine((value, ctx) => {
    const hasUrl = Boolean(value.url?.trim());
    const hasFileMeta = Boolean(value.file_name && value.file_size && value.file_type);
    if (!hasUrl && !hasFileMeta) {
      ctx.addIssue({
        code: 'custom',
        message: 'Provide an image URL or upload an image file',
        path: ['url'],
      });
      return;
    }
    if (hasUrl && value.url && !isAllowedMediaUrl(value.url)) {
      ctx.addIssue({
        code: 'custom',
        message: 'Image URL must be a valid link',
        path: ['url'],
      });
    }
    if (hasFileMeta) {
      if (
        value.file_type &&
        !IMAGE_MIME_TYPES.includes(value.file_type as (typeof IMAGE_MIME_TYPES)[number])
      ) {
        ctx.addIssue({
          code: 'custom',
          message: 'Image must be SVG, PNG, WebP, or JPEG',
          path: ['file_type'],
        });
      }
      if (value.file_size && value.file_size > MAX_PICTURE_BYTES) {
        ctx.addIssue({
          code: 'custom',
          message: 'Image must be 500 KB or smaller',
          path: ['file_size'],
        });
      }
    }
  });

export const wizardPicturesStepSchema = z.array(wizardPictureItemSchema);

export type WizardPictureItem = z.infer<typeof wizardPictureItemSchema>;

export const emptyWizardPictureDraft: WizardPictureItem = {
  local_id: '',
  url: null,
  caption: null,
  picture_type: 'gallery',
  file_name: null,
  file_size: null,
  file_type: null,
  college_id: null,
  college_local_id: null,
  storage_key: null,
};

export function createEmptyWizardPictureDraft(): WizardPictureItem {
  return {
    ...emptyWizardPictureDraft,
    local_id: crypto.randomUUID(),
  };
}

/** Mirror backend sanitize_asset_filename so client-side duplicate checks match R2 keys. */
export function sanitizeWizardPictureFilename(filename: string): string {
  const rawName = filename.split(/[/\\]/).pop() || filename;
  const lastDot = rawName.lastIndexOf('.');
  const stem = lastDot > 0 ? rawName.slice(0, lastDot) : rawName;
  const suffix = lastDot > 0 ? rawName.slice(lastDot).toLowerCase() : '';
  const sanitizedStem = stem
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `${sanitizedStem || 'image'}${suffix}`;
}

/** Convert private R2 API URLs to the backend media proxy so <img> can load them. */
/** Prefer stored file_name; fall back to basename from storage_key or URL. */
export function pictureDisplayFileName(
  picture: Pick<WizardPictureItem, 'file_name' | 'storage_key' | 'url'>
): string {
  const named = (picture.file_name || '').trim();
  if (named) return named;

  const fromKey = (picture.storage_key || '').trim().split('/').filter(Boolean).pop();
  if (fromKey) {
    try {
      return decodeURIComponent(fromKey);
    } catch {
      return fromKey;
    }
  }

  const rawUrl = (picture.url || '').trim();
  if (rawUrl) {
    try {
      const path = rawUrl.includes('://') ? new URL(rawUrl).pathname : rawUrl;
      const fromUrl = path.split('/').filter(Boolean).pop();
      if (fromUrl) return decodeURIComponent(fromUrl);
    } catch {
      /* ignore invalid URLs */
    }
  }

  return 'Gallery image';
}

export function rewriteStoredMediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const value = url.trim();
  if (!value) return null;

  const markers = ['/api/v1/academia/media/', '/academia/media/', '/uploads/'];
  for (const marker of markers) {
    const index = value.indexOf(marker);
    if (index >= 0) {
      const key = value.slice(index + marker.length).replace(/^\/+/, '');
      return key ? `/api/v1/academia/media/${key}` : value;
    }
  }

  const s3Marker = 'r2.cloudflarestorage.com/';
  const s3Index = value.indexOf(s3Marker);
  if (s3Index >= 0) {
    const key = value.slice(s3Index + s3Marker.length).replace(/^\/+/, '');
    const parts = key.split('/').filter(Boolean);
    const assetTypeIndex = parts.findIndex(part =>
      ['logo', 'banner', 'gallery'].includes(part)
    );
    if (assetTypeIndex >= 1 && parts.length >= assetTypeIndex + 2) {
      return `/api/v1/academia/media/${parts.slice(assetTypeIndex - 1).join('/')}`;
    }
    return key ? `/api/v1/academia/media/${key}` : value;
  }

  return value;
}

export function hydrateWizardPicture(raw: Partial<WizardPictureItem>): WizardPictureItem {
  return {
    ...createEmptyWizardPictureDraft(),
    ...raw,
    local_id: raw.local_id || crypto.randomUUID(),
    url: rewriteStoredMediaUrl(raw.url || null),
    caption: raw.caption || null,
    picture_type: raw.picture_type === 'campus' ? 'banner' : raw.picture_type || 'gallery',
    file_name: raw.file_name || null,
    file_size: raw.file_size ?? null,
    file_type: raw.file_type || null,
    college_id: raw.college_id ?? null,
    college_local_id: raw.college_local_id || null,
    storage_key: raw.storage_key || null,
  };
}

export function pictureToApiPayload(picture: WizardPictureItem) {
  const {
    local_id: _localId,
    file_name,
    file_size,
    file_type,
    college_id,
    college_local_id,
    storage_key,
    ...rest
  } = picture;
  if (!rest.url?.trim()) {
    throw new Error('An image URL is required to save this picture. Upload support will attach a URL later.');
  }
  return {
    url: rest.url.trim(),
    caption: rest.caption?.trim() || null,
    picture_type: rest.picture_type,
    file_name: file_name || null,
    file_type: file_type || null,
    file_size: file_size ?? null,
    college_id: college_id ?? null,
    college_local_id: college_local_id?.trim() || null,
    storage_key: storage_key?.trim() || null,
  };
}

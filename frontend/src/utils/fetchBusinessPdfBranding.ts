import {
  formatBusinessAddressLines,
  type BusinessProfileAddressSource,
} from './studentProfilePreview';
import { apiFetch, getStoredToken, resolveBaseUrl } from './api';
import type { PdfBusinessBranding } from './pdfLayout';

interface BusinessProfileResponse extends BusinessProfileAddressSource {
  business_name?: string | null;
  has_logo?: boolean;
  logo_url?: string | null;
  office_phone_number?: string | null;
  office_email?: string | null;
  email_domain?: string | null;
}

/**
 * Load tenant PDF branding (name, address, optional logo data URL)
 * from the live business profile — never hardcode company details.
 */
export async function fetchBusinessPdfBranding(): Promise<PdfBusinessBranding> {
  const profile = (await apiFetch('settings/business-branding')) as BusinessProfileResponse;

  const branding: PdfBusinessBranding = {
    businessName: (profile.business_name || '').trim() || undefined,
    addressLines: formatBusinessAddressLines(profile),
    phone: (profile.office_phone_number || '').trim() || undefined,
    email: (profile.office_email || '').trim() || undefined,
    website: (profile.email_domain || '').trim() || undefined,
    logoDataUrl: null,
  };

  if (!profile.has_logo) {
    return branding;
  }

  const token = getStoredToken();
  if (!token) {
    return branding;
  }

  try {
    const base = resolveBaseUrl().replace(/\/$/, '');
    const response = await fetch(`${base}/settings/business-profile/logo`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'ngrok-skip-browser-warning': 'true',
      },
    });
    if (!response.ok) {
      return branding;
    }
    const blob = await response.blob();
    if (!blob.type.startsWith('image/') || blob.type.includes('svg')) {
      // jsPDF cannot reliably embed SVG; skip unsupported formats.
      return branding;
    }
    branding.logoDataUrl = await blobToDataUrl(blob);
  } catch {
    // Logo is optional chrome; reports still export without it.
  }

  return branding;
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Failed to read logo.'));
    reader.readAsDataURL(blob);
  });
}

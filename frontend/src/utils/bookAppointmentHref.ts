import { isSafeInternalPath } from './api';

/** Build /book-appointment URL with an existing Nexus lead pre-selected. */
export function bookAppointmentHref(
  lead: {
    id: number;
    full_name: string;
    email?: string | null;
    phone_number?: string | null;
  },
  options?: { returnTo?: string | null }
): string {
  const params = new URLSearchParams();
  params.set('leadId', String(lead.id));
  params.set('mode', 'existing');
  const name = lead.full_name.trim();
  if (name) params.set('name', name);
  const email = lead.email?.trim();
  if (email && !email.includes('@edutrust.nexus')) params.set('email', email);
  const phone = lead.phone_number?.trim();
  if (phone) params.set('phone', phone);
  const returnTo = options?.returnTo?.trim();
  if (returnTo && isSafeInternalPath(returnTo)) {
    params.set('returnTo', returnTo);
  }
  return `/book-appointment?${params.toString()}`;
}

/** Safe internal path from book-appointment ?returnTo=, else All Leads. */
export function bookAppointmentReturnTo(raw: string | null | undefined): string {
  const trimmed = raw?.trim();
  if (trimmed && isSafeInternalPath(trimmed)) return trimmed;
  return '/offline-leads';
}

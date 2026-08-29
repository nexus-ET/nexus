import { useMemo } from 'react';

import { toContactTypeOptions, type ContactTypeOption } from '../constants/contactTypes';
import { useAdminSettingsStore } from '../stores/adminSettingsStore';

/** Email contact type dropdown options from admin settings (reactive). */
export function useEmailContactTypeOptions(): ContactTypeOption[] {
  const emailContactTypes = useAdminSettingsStore(state => state.emailContactTypes);
  return useMemo(() => toContactTypeOptions(emailContactTypes), [emailContactTypes]);
}

/** Phone (and fax) contact type dropdown options from admin settings (reactive). */
export function usePhoneContactTypeOptions(): ContactTypeOption[] {
  const phoneContactTypes = useAdminSettingsStore(state => state.phoneContactTypes);
  return useMemo(() => toContactTypeOptions(phoneContactTypes), [phoneContactTypes]);
}

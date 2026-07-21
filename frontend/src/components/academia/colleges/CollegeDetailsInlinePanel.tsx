import { useCallback, useEffect, useState } from 'react';
import { Loader2, Save } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import { EMAIL_CONTACT_TYPES, PHONE_CONTACT_TYPES } from '../../../constants/contactTypes';
import {
  createDefaultEmailContacts,
  createDefaultPhoneContacts,
  emailContactListSchema,
  normalizeEmailContacts,
  normalizePhoneContacts,
  phoneContactListSchema,
  serializeContacts,
  type ContactEntry,
} from '../../../schemas/contactEntry';
import type { CollegeRecord } from '../../../types/institutions';
import { useCountries } from '../../../hooks/useCountries';
import LabeledContactListField from '../form/LabeledContactListField';
import InlineExpandPanel from '../form/InlineExpandPanel';

interface CollegeDetailsInlinePanelProps {
  collegeId: number;
  onClose: () => void;
  onSaved: () => void;
}

const readOnlyFieldClass =
  'rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm text-text-main';

const CollegeDetailsInlinePanel: React.FC<CollegeDetailsInlinePanelProps> = ({
  collegeId,
  onClose,
  onSaved,
}) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [college, setCollege] = useState<CollegeRecord | null>(null);
  const [deanName, setDeanName] = useState('');
  const [webUrl, setWebUrl] = useState('');
  const [phoneNumbers, setPhoneNumbers] = useState<ContactEntry[]>(createDefaultPhoneContacts());
  const [emailAddresses, setEmailAddresses] = useState<ContactEntry[]>(createDefaultEmailContacts());
  const [phoneErrors, setPhoneErrors] = useState<string[]>([]);
  const [emailErrors, setEmailErrors] = useState<string[]>([]);
  const [defaultPhoneCountryIso2, setDefaultPhoneCountryIso2] = useState('');
  const { countries: phoneCountries } = useCountries();

  const loadCollege = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const record = await apiFetch<CollegeRecord>(`academia/colleges/${collegeId}`);
      setCollege(record);
      setDeanName(record.dean_name || '');
      setWebUrl(record.web_url || '');
      setPhoneNumbers(normalizePhoneContacts(record.phone_numbers));
      setEmailAddresses(normalizeEmailContacts(record.email_addresses));
      setPhoneErrors([]);
      setEmailErrors([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load college details.');
      setCollege(null);
    } finally {
      setLoading(false);
    }
  }, [collegeId]);

  useEffect(() => {
    if (!college?.institution_id || !phoneCountries.length) {
      setDefaultPhoneCountryIso2('');
      return;
    }
    void apiFetch<{ country_id?: number | null }>(`academia/institutions/${college.institution_id}`)
      .then(institution => {
        setDefaultPhoneCountryIso2(
          phoneCountries.find(country => country.id === institution.country_id)?.iso2 ?? ''
        );
      })
      .catch(() => setDefaultPhoneCountryIso2(''));
  }, [college?.institution_id, phoneCountries]);

  useEffect(() => {
    void loadCollege();
  }, [loadCollege]);

  const campusAddressDisplay = [college?.campus_address, college?.campus_location_label]
    .filter(Boolean)
    .join(' · ') || '—';

  const handleSave = async () => {
    if (!college) return;

    const phoneResult = phoneContactListSchema.safeParse(phoneNumbers);
    const emailResult = emailContactListSchema.safeParse(emailAddresses);
    if (!phoneResult.success || !emailResult.success) {
      setPhoneErrors(
        phoneNumbers.map((_, index) => {
          const issue = phoneResult.error?.issues.find(item => item.path[0] === index);
          return (
            issue?.message ||
            phoneResult.error?.issues.find(item => item.path.length === 0)?.message
          );
        })
      );
      setEmailErrors(
        emailAddresses.map((_, index) => {
          const issue = emailResult.error?.issues.find(item => item.path[0] === index);
          return (
            issue?.message ||
            emailResult.error?.issues.find(item => item.path.length === 0)?.message
          );
        })
      );
      setError('Please fix the phone and email contact details.');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch(`academia/colleges/${college.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          dean_name: deanName.trim() || null,
          web_url: webUrl.trim() || null,
          phone_numbers: serializeContacts(phoneNumbers),
          email_addresses: serializeContacts(emailAddresses),
        }),
      });
      setSuccess('College details saved successfully.');
      onSaved();
      window.setTimeout(() => {
        onClose();
      }, 600);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save college details.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <InlineExpandPanel
      title={college?.name || 'College details'}
      subtitle="View Details"
      onClose={onClose}
      loading={loading}
      loadingLabel="Loading college and campus details..."
      error={error}
      success={success}
      footer={
        !loading ? (
          <div className="flex justify-end">
            <button
              type="button"
              disabled={saving || !college}
              onClick={() => void handleSave()}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              Save
            </button>
          </div>
        ) : null
      }
    >
      {college ? (
        <>
          <section className="rounded-xl border border-border-subtle bg-card p-4 space-y-3">
            <h5 className="text-sm font-semibold text-text-main">Linked campus</h5>
            <p className="text-xs text-text-muted">
              Read-only — sourced from the parent campus record.
            </p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase text-text-muted">
                  Campus name
                </label>
                <div className={readOnlyFieldClass}>{college.campus_name || '—'}</div>
              </div>
              <div className="md:col-span-2">
                <label className="mb-1 block text-xs font-semibold uppercase text-text-muted">
                  Campus address
                </label>
                <div className={readOnlyFieldClass}>{campusAddressDisplay}</div>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-semibold text-text-main">Dean name</label>
              <input
                type="text"
                value={deanName}
                onChange={event => setDeanName(event.target.value)}
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
                placeholder="Dean or director name"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-semibold text-text-main">Web URL</label>
              <input
                type="url"
                value={webUrl}
                onChange={event => setWebUrl(event.target.value)}
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
                placeholder="https://..."
              />
            </div>
          </section>

          <LabeledContactListField
            label="Phone numbers"
            items={phoneNumbers}
            typeOptions={PHONE_CONTACT_TYPES}
            onChange={setPhoneNumbers}
            valuePlaceholder="Phone number"
            valueInputType="tel"
            addLabel="Add phone"
            errors={phoneErrors}
            required
            phoneCountries={phoneCountries}
            defaultPhoneCountryIso2={defaultPhoneCountryIso2}
          />

          <LabeledContactListField
            label="Email addresses"
            items={emailAddresses}
            typeOptions={EMAIL_CONTACT_TYPES}
            onChange={setEmailAddresses}
            valuePlaceholder="Email address"
            valueInputType="email"
            addLabel="Add email"
            errors={emailErrors}
            typeSelectWidthClass="w-full sm:w-[9.5rem]"
            required
          />
        </>
      ) : null}
    </InlineExpandPanel>
  );
};

export default CollegeDetailsInlinePanel;

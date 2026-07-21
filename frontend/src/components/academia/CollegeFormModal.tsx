import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { EMAIL_CONTACT_TYPES, PHONE_CONTACT_TYPES } from '../../constants/contactTypes';
import { PHONE_LOCAL_PLACEHOLDER } from '../../utils/phoneCountry';
import {
  createDefaultEmailContacts,
  createDefaultPhoneContacts,
  emailContactListSchema,
  normalizeEmailContacts,
  normalizePhoneContacts,
  phoneContactListSchema,
  serializeContacts,
  type ContactEntry,
} from '../../schemas/contactEntry';
import type { CampusRecord, CollegeRecord, InstitutionRecord } from '../../types/institutions';
import { useCountries } from '../../hooks/useCountries';
import LabeledContactListField from './form/LabeledContactListField';
import SearchableSelect from './SearchableSelect';

interface CollegeFormModalProps {
  open: boolean;
  college: CollegeRecord | null;
  presetInstitutionId?: string;
  presetCampusId?: string;
  onClose: () => void;
  onSaved: () => void;
}

const CollegeFormModal: React.FC<CollegeFormModalProps> = ({
  open,
  college,
  presetInstitutionId = '',
  presetCampusId = '',
  onClose,
  onSaved,
}) => {
  const [institutions, setInstitutions] = useState<InstitutionRecord[]>([]);
  const [campuses, setCampuses] = useState<CampusRecord[]>([]);
  const [loadingCampuses, setLoadingCampuses] = useState(false);
  const [institutionId, setInstitutionId] = useState('');
  const [campusId, setCampusId] = useState('');
  const [name, setName] = useState('');
  const [deanName, setDeanName] = useState('');
  const [phoneNumbers, setPhoneNumbers] = useState<ContactEntry[]>(createDefaultPhoneContacts());
  const [emailAddresses, setEmailAddresses] = useState<ContactEntry[]>(createDefaultEmailContacts());
  const [phoneErrors, setPhoneErrors] = useState<string[]>([]);
  const [emailErrors, setEmailErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { countries: phoneCountries } = useCountries();

  useEffect(() => {
    if (!open) return;
    void apiFetch<InstitutionRecord[]>('academia/institutions').then(data => {
      setInstitutions(Array.isArray(data) ? data : []);
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const loadCollege = async () => {
      setInstitutionId(college ? String(college.institution_id) : presetInstitutionId || '');
      setCampusId(college ? String(college.campus_id) : presetCampusId || '');
      setName(college?.name || '');
      setDeanName(college?.dean_name || '');
      setError(null);
      setPhoneErrors([]);
      setEmailErrors([]);

      if (college?.id) {
        try {
          const fullCollege = await apiFetch<CollegeRecord>(`academia/colleges/${college.id}`);
          setPhoneNumbers(normalizePhoneContacts(fullCollege.phone_numbers));
          setEmailAddresses(normalizeEmailContacts(fullCollege.email_addresses));
        } catch {
          setPhoneNumbers(normalizePhoneContacts(college.phone_numbers));
          setEmailAddresses(normalizeEmailContacts(college.email_addresses));
        }
      } else {
        setPhoneNumbers(createDefaultPhoneContacts());
        setEmailAddresses(createDefaultEmailContacts());
      }
    };

    void loadCollege();
  }, [college, open, presetCampusId, presetInstitutionId]);

  useEffect(() => {
    if (!open || !institutionId) {
      setCampuses([]);
      return;
    }
    setLoadingCampuses(true);
    void apiFetch<CampusRecord[]>(`academia/campuses?institution_id=${institutionId}`)
      .then(data => {
        setCampuses(Array.isArray(data) ? data : []);
      })
      .finally(() => setLoadingCampuses(false));
  }, [institutionId, open]);

  useEffect(() => {
    if (!open || !institutionId || college || presetCampusId) return;
    setCampusId('');
  }, [college, institutionId, open, presetCampusId]);

  const institutionOptions = useMemo(
    () =>
      institutions.map(institution => ({
        value: String(institution.id),
        label: institution.name,
      })),
    [institutions]
  );

  const campusOptions = useMemo(
    () =>
      campuses.map(campus => ({
        value: String(campus.id),
        label: campus.location_label
          ? `${campus.name} (${campus.location_label})`
          : campus.name,
      })),
    [campuses]
  );

  const selectedInstitution = institutions.find(item => String(item.id) === institutionId)?.name;
  const selectedCampus = campuses.find(item => String(item.id) === campusId)?.name;
  const selectedInstitutionRecord = institutions.find(item => String(item.id) === institutionId);
  const defaultPhoneCountryIso2 =
    phoneCountries.find(country => country.id === selectedInstitutionRecord?.country_id)?.iso2 ?? '';
  const breadcrumbPreview =
    selectedInstitution && selectedCampus && name.trim()
      ? `${selectedInstitution} > ${selectedCampus} > ${name.trim()}`
      : selectedInstitution && selectedCampus
        ? `${selectedInstitution} > ${selectedCampus} > …`
        : null;

  if (!open) return null;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!institutionId) {
      setError('Select an institution first.');
      return;
    }
    if (!campusId) {
      setError('Select a campus under that institution.');
      return;
    }
    if (!name.trim()) {
      setError('College name is required.');
      return;
    }

    const phoneResult = phoneContactListSchema.safeParse(phoneNumbers);
    const emailResult = emailContactListSchema.safeParse(emailAddresses);
    if (!phoneResult.success || !emailResult.success) {
      setPhoneErrors(
        phoneNumbers.map((_, index) => {
          const issue = phoneResult.error?.issues.find(item => item.path[0] === index);
          return issue?.message || phoneResult.error?.issues.find(item => item.path.length === 0)?.message;
        })
      );
      setEmailErrors(
        emailAddresses.map((_, index) => {
          const issue = emailResult.error?.issues.find(item => item.path[0] === index);
          return issue?.message || emailResult.error?.issues.find(item => item.path.length === 0)?.message;
        })
      );
      setError('Please fix the phone and email contact details.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload = {
        institution_id: Number(institutionId),
        campus_id: Number(campusId),
        name: name.trim(),
        dean_name: deanName.trim() || null,
        phone_numbers: serializeContacts(phoneNumbers),
        email_addresses: serializeContacts(emailAddresses),
      };
      if (college) {
        await apiFetch(`academia/colleges/${college.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/colleges', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save college');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">
              {college ? 'Edit College' : 'Create College'}
            </h3>
            <p className="text-xs text-text-muted">Institution → Campus → College</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <SearchableSelect
            label="Step 1 — Institution"
            value={institutionId}
            options={institutionOptions}
            onChange={setInstitutionId}
            placeholder="Select institution..."
            required
          />
          <SearchableSelect
            label="Step 2 — Campus"
            value={campusId}
            options={campusOptions}
            onChange={setCampusId}
            placeholder={
              !institutionId
                ? 'Select an institution first'
                : loadingCampuses
                  ? 'Loading campuses...'
                  : campusOptions.length === 0
                    ? 'No campuses for this institution'
                    : 'Select campus...'
            }
            required
            disabled={!institutionId || loadingCampuses || campusOptions.length === 0}
          />
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Step 3 — College name *</span>
            <input
              type="text"
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="e.g. College of Engineering"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Dean name</span>
            <input
              type="text"
              value={deanName}
              onChange={event => setDeanName(event.target.value)}
              placeholder="e.g. Dr. Jane Smith"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>

          <LabeledContactListField
            label="Phone numbers"
            required
            items={phoneNumbers}
            onChange={setPhoneNumbers}
            typeOptions={PHONE_CONTACT_TYPES}
            valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
            valueInputType="tel"
            addLabel="Add phone number"
            errors={phoneErrors}
            phoneCountries={phoneCountries}
            defaultPhoneCountryIso2={defaultPhoneCountryIso2}
          />

          <LabeledContactListField
            label="Email addresses"
            required
            items={emailAddresses}
            onChange={setEmailAddresses}
            typeOptions={EMAIL_CONTACT_TYPES}
            valuePlaceholder="college@university.edu"
            valueInputType="email"
            addLabel="Add email address"
            errors={emailErrors}
            typeSelectWidthClass="w-full sm:w-[9.5rem]"
          />

          {breadcrumbPreview ? (
            <div className="rounded-xl border border-accent/20 bg-accent/5 px-3 py-2 text-xs">
              <span className="font-semibold text-text-muted">Path: </span>
              <span className="font-medium text-text-main">{breadcrumbPreview}</span>
            </div>
          ) : null}
          {error ? <p className="text-sm text-alert">{error}</p> : null}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : null}
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CollegeFormModal;

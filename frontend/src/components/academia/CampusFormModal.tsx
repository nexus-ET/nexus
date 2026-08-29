import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { WEB_LINK_TYPES } from '../../constants/contactTypes';
import { PHONE_LOCAL_PLACEHOLDER } from '../../utils/phoneCountry';
import {
  createDefaultEmailContacts,
  createDefaultPhoneContacts,
  createDefaultWebLinks,
  normalizeEmailContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  optionalEmailContactListSchema,
  optionalPhoneContactListSchema,
  serializeContacts,
  type ContactEntry,
  webLinkListSchema,
} from '../../schemas/contactEntry';
import type { CampusRecord, CityOption, InstitutionRecord } from '../../types/institutions';
import { useCountries } from '../../hooks/useCountries';
import {
  useEmailContactTypeOptions,
  usePhoneContactTypeOptions,
} from '../../hooks/useContactTypeOptions';
import LabeledContactListField from './form/LabeledContactListField';
import SearchableSelect from './SearchableSelect';
import ReadOnlyIdField from './ReadOnlyIdField';

interface CampusFormModalProps {
  open: boolean;
  campus: CampusRecord | null;
  presetInstitutionId?: string;
  onClose: () => void;
  onSaved: () => void;
}

const CampusFormModal: React.FC<CampusFormModalProps> = ({
  open,
  campus,
  presetInstitutionId = '',
  onClose,
  onSaved,
}) => {
  const phoneContactTypes = usePhoneContactTypeOptions();
  const emailContactTypes = useEmailContactTypeOptions();
  const [institutions, setInstitutions] = useState<InstitutionRecord[]>([]);
  const [cities, setCities] = useState<CityOption[]>([]);
  const [institutionId, setInstitutionId] = useState('');
  const [locationId, setLocationId] = useState('');
  const [name, setName] = useState('');
  const [phoneNumbers, setPhoneNumbers] = useState<ContactEntry[]>(createDefaultPhoneContacts());
  const [emailAddresses, setEmailAddresses] = useState<ContactEntry[]>(createDefaultEmailContacts());
  const [webLinks, setWebLinks] = useState<ContactEntry[]>(createDefaultWebLinks());
  const [phoneErrors, setPhoneErrors] = useState<string[]>([]);
  const [emailErrors, setEmailErrors] = useState<string[]>([]);
  const [webLinkErrors, setWebLinkErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { countries: phoneCountries } = useCountries();

  useEffect(() => {
    if (!open) return;
    void Promise.all([
      apiFetch<InstitutionRecord[]>('academia/institutions'),
      fetchAcademiaListItems<CityOption>('academia/cities'),
    ]).then(([institutionData, cityData]) => {
      setInstitutions(Array.isArray(institutionData) ? institutionData : []);
      setCities(cityData);
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const loadCampus = async () => {
      setInstitutionId(campus ? String(campus.institution_id) : presetInstitutionId || '');
      setLocationId(campus?.location_id ? String(campus.location_id) : '');
      setName(campus?.name || '');
      setError(null);
      setPhoneErrors([]);
      setEmailErrors([]);
      setWebLinkErrors([]);

      if (campus?.id) {
        try {
          const fullCampus = await apiFetch<CampusRecord>(`academia/campuses/${campus.id}`);
          setPhoneNumbers(normalizePhoneContacts(fullCampus.phone_numbers));
          setEmailAddresses(normalizeEmailContacts(fullCampus.email_addresses));
          setWebLinks(normalizeWebLinks(fullCampus.web_links));
        } catch {
          setPhoneNumbers(normalizePhoneContacts(campus.phone_numbers));
          setEmailAddresses(normalizeEmailContacts(campus.email_addresses));
          setWebLinks(normalizeWebLinks(campus.web_links));
        }
      } else {
        setPhoneNumbers(createDefaultPhoneContacts());
        setEmailAddresses(createDefaultEmailContacts());
        setWebLinks(createDefaultWebLinks());
      }
    };

    void loadCampus();
  }, [campus, open, presetInstitutionId]);

  const institutionOptions = useMemo(
    () =>
      institutions.map(institution => ({
        value: String(institution.id),
        label: institution.name,
      })),
    [institutions]
  );

  const cityOptions = useMemo(
    () =>
      cities.map(city => ({
        value: String(city.id),
        label: [city.name, city.state_name, city.country_name].filter(Boolean).join(', '),
      })),
    [cities]
  );

  const selectedInstitution = institutions.find(item => String(item.id) === institutionId)?.name;
  const selectedLocation = cityOptions.find(option => option.value === locationId)?.label;
  const selectedCity = cities.find(city => String(city.id) === locationId);
  const defaultPhoneCountryIso2 =
    phoneCountries.find(country => country.id === selectedCity?.country_id)?.iso2 ?? '';

  if (!open) return null;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!institutionId) {
      setError('Select a parent institution first.');
      return;
    }
    if (!locationId) {
      setError('Select a city location for this campus.');
      return;
    }
    if (!name.trim()) {
      setError('Campus name is required.');
      return;
    }

    const phoneResult = optionalPhoneContactListSchema.safeParse(phoneNumbers);
    const emailResult = optionalEmailContactListSchema.safeParse(emailAddresses);
    const webLinkResult = webLinkListSchema.safeParse(webLinks);
    if (!phoneResult.success || !emailResult.success || !webLinkResult.success) {
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
      setWebLinkErrors(
        webLinks.map((_, index) => {
          const issue = webLinkResult.error?.issues.find(item => item.path[0] === index);
          return issue?.message;
        })
      );
      setError('Please fix the phone, email, and web link details.');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload = {
        institution_id: Number(institutionId),
        location_id: Number(locationId),
        name: name.trim(),
        phone_numbers: serializeContacts(phoneNumbers),
        email_addresses: serializeContacts(emailAddresses),
        web_links: serializeContacts(webLinks),
      };
      if (campus) {
        await apiFetch(`academia/campuses/${campus.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/campuses', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save campus');
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
              {campus ? 'Edit Campus' : 'Create Campus'}
            </h3>
            <p className="text-xs text-text-muted">Map campus to Institution → City location</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          {campus ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <ReadOnlyIdField label="Campus ID" value={campus.id} />
              <ReadOnlyIdField label="Institution ID" value={campus.institution_id} />
            </div>
          ) : null}
          <SearchableSelect
            label="Step 1 — Institution"
            value={institutionId}
            options={institutionOptions}
            onChange={setInstitutionId}
            placeholder="Select parent institution..."
            required
          />
          <SearchableSelect
            label="Step 2 — City location"
            value={locationId}
            options={cityOptions}
            onChange={setLocationId}
            placeholder="Search cities..."
            required
          />
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Campus name *</span>
            <input
              type="text"
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="e.g. Westwood Campus, Main Campus"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              required
            />
          </label>

          <LabeledContactListField
            label="Phone numbers"
            items={phoneNumbers}
            onChange={setPhoneNumbers}
            typeOptions={phoneContactTypes}
            valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
            valueInputType="tel"
            addLabel="Add phone number"
            errors={phoneErrors}
            phoneCountries={phoneCountries}
            defaultPhoneCountryIso2={defaultPhoneCountryIso2}
          />

          <LabeledContactListField
            label="Email addresses"
            items={emailAddresses}
            onChange={setEmailAddresses}
            typeOptions={emailContactTypes}
            valuePlaceholder="campus@university.edu"
            valueInputType="email"
            addLabel="Add email address"
            errors={emailErrors}
            typeSelectWidthClass="w-full sm:w-[9.5rem]"
          />

          <LabeledContactListField
            label="Campus web URLs"
            items={webLinks}
            onChange={setWebLinks}
            typeOptions={WEB_LINK_TYPES}
            valuePlaceholder="https://www.university.edu/campus"
            valueInputType="url"
            addLabel="Add web links"
            errors={webLinkErrors}
            typeSelectWidthClass="w-full sm:w-[8.75rem]"
            maxLength={250}
          />

          {selectedInstitution && selectedLocation && name.trim() ? (
            <div className="rounded-xl border border-accent/20 bg-accent/5 px-3 py-2 text-xs">
              <span className="font-semibold text-text-muted">Path: </span>
              <span className="font-medium text-text-main">
                {selectedInstitution} &gt; {name.trim()} ({selectedLocation})
              </span>
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

export default CampusFormModal;

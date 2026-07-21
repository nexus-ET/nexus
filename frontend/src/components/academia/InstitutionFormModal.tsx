import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import type { InstitutionRecord } from '../../types/institutions';
import SearchableSelect from './SearchableSelect';

interface CountryOption {
  id: number;
  name: string;
}

interface InstitutionFormModalProps {
  open: boolean;
  institution: InstitutionRecord | null;
  onClose: () => void;
  onSaved: () => void;
}

const InstitutionFormModal: React.FC<InstitutionFormModalProps> = ({
  open,
  institution,
  onClose,
  onSaved,
}) => {
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [institutionType, setInstitutionType] = useState('');
  const [countryId, setCountryId] = useState('');
  const [accreditationDetails, setAccreditationDetails] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void fetchAcademiaListItems<CountryOption>('academia/countries').then(setCountries);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setName(institution?.name || '');
    setCode(institution?.code || '');
    setInstitutionType(institution?.institution_type || '');
    setCountryId(institution?.country_id ? String(institution.country_id) : '');
    setAccreditationDetails(institution?.accreditation_details || '');
    setError(null);
  }, [institution, open]);

  if (!open) return null;

  const countryOptions = countries.map(country => ({
    value: String(country.id),
    label: country.name,
  }));

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError('Institution name is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: name.trim(),
        code: code.trim() || null,
        institution_type: institutionType.trim() || null,
        country_id: countryId ? Number(countryId) : null,
        accreditation_details: accreditationDetails.trim() || null,
      };
      if (institution) {
        await apiFetch(`academia/institutions/${institution.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/institutions', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save institution');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <h3 className="text-lg font-bold text-text-main">
            {institution ? 'Edit Institution' : 'Create Institution'}
          </h3>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Name *</span>
            <input
              type="text"
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="e.g. University of California"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Accreditation details</span>
            <textarea
              value={accreditationDetails}
              onChange={event => setAccreditationDetails(event.target.value)}
              rows={3}
              placeholder="Regional accreditation, governing body, validity..."
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-text-main">Code</span>
              <input
                type="text"
                value={code}
                onChange={event => setCode(event.target.value)}
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-text-main">Type</span>
              <input
                type="text"
                value={institutionType}
                onChange={event => setInstitutionType(event.target.value)}
                placeholder="Public / Private"
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
            </label>
          </div>
          <SearchableSelect
            label="Country"
            value={countryId}
            options={countryOptions}
            onChange={setCountryId}
            placeholder="Select country..."
          />
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

export default InstitutionFormModal;

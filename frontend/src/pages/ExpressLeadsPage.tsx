import React, { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Loader2, Zap } from 'lucide-react';
import PhoneWithCountryCodeInput from '../components/academia/form/PhoneWithCountryCodeInput';
import SearchableMultiSelect from '../components/academia/SearchableMultiSelect';
import { useConfirmation } from '../context/ConfirmationContext';
import { useCountries } from '../hooks/useCountries';
import { useCreateExpressLead, useExpressLeadDuplicateCheck } from '../hooks/useExpressLeads';
import { useEducationMajors } from '../hooks/useEducationMajors';
import {
  studentInfoAlertErrorClass,
  studentInfoAlertSuccessClass,
  studentInfoFieldErrorClass,
  studentInfoInputClass,
  studentInfoLabelClass,
  studentInfoPrimaryBtnClass,
  studentInfoSectionClass,
} from '../components/studentInfoFormStyles';
import {
  parseExpressDuplicateError,
  type ExpressLeadCreated,
  type ExpressLeadMatch,
  type ExpressLeadMatchedOn,
} from '../types/expressLead';
import { EMAIL_FORMAT_HINT, parseStoredPhone, phoneLocalToDigits } from '../utils/phoneCountry';
import { bookAppointmentHref } from '../utils/bookAppointmentHref';

const EMPTY_FORM = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  target_destination_iso2s: [] as string[],
  target_major_ids: [] as string[],
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function matchKey(row: ExpressLeadMatch): string {
  return `${row.record_kind || 'lead'}:${row.id}`;
}

function mergeMatches(rows: Array<ExpressLeadMatch | null>): ExpressLeadMatch[] {
  const byKey = new Map<string, ExpressLeadMatch>();
  for (const row of rows) {
    if (!row) continue;
    const key = matchKey(row);
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...row });
      continue;
    }
    if (existing.matched_on !== row.matched_on) {
      existing.matched_on = 'both';
    }
    existing.email = existing.email || row.email;
    existing.phone_number = existing.phone_number || row.phone_number;
  }
  return [...byKey.values()];
}

function matchReason(matchedOn: ExpressLeadMatchedOn): string {
  if (matchedOn === 'both') return 'Same email and phone';
  if (matchedOn === 'email') return 'Same email';
  return 'Same phone';
}

function warningHeadline(matches: ExpressLeadMatch[]): string {
  if (matches.length > 1) return 'Existing students found';
  const matchedOn = matches[0]?.matched_on;
  if (matchedOn === 'both') return 'This email and phone already belong to an existing student';
  if (matchedOn === 'email') return 'This email already belongs to an existing student';
  return 'This phone number already belongs to an existing student';
}

function formatCreatedAt(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

const ExpressLeadsPage: React.FC = () => {
  const navigate = useNavigate();
  const openConfirm = useConfirmation();
  const { countries } = useCountries();
  const { majors } = useEducationMajors();
  const createLead = useCreateExpressLead();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [savedLead, setSavedLead] = useState<ExpressLeadCreated | null>(null);
  const [saveMatches, setSaveMatches] = useState<ExpressLeadMatch[]>([]);

  const parsedPhone = useMemo(
    () => parseStoredPhone(form.phone, countries),
    [form.phone, countries]
  );

  const { emailMatch, phoneMatch, isChecking } = useExpressLeadDuplicateCheck(
    form.email,
    parsedPhone.countryIso2,
    parsedPhone.localNumber
  );

  const duplicates = mergeMatches([emailMatch, phoneMatch, ...saveMatches]);
  const emailInvalid = Boolean(form.email.trim()) && !EMAIL_RE.test(form.email.trim());
  const phoneDigits = phoneLocalToDigits(parsedPhone.localNumber);
  const phoneReady = Boolean(parsedPhone.countryIso2) && phoneDigits.length === 10;

  const updateForm = (patch: Partial<typeof EMPTY_FORM>) => {
    setForm(prev => ({ ...prev, ...patch }));
    setError(null);
    setSuccess(null);
    setSavedLead(null);
    setSaveMatches([]);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const first = form.first_name.trim();
    const last = form.last_name.trim();
    if (!first || !last) {
      setError('Enter first name and last name.');
      return;
    }
    if (!phoneReady) {
      setError('Select a country code and enter a valid 10-digit phone number.');
      return;
    }
    if (!form.email.trim()) {
      setError('Enter an email address.');
      return;
    }
    if (emailInvalid) {
      setError(EMAIL_FORMAT_HINT);
      return;
    }
    if (duplicates.length) {
      return;
    }

    try {
      const created = await createLead.mutateAsync({
        first_name: first,
        last_name: last,
        email: form.email.trim(),
        phone_country_iso2: parsedPhone.countryIso2,
        phone_local: phoneDigits,
        target_destination_iso2s: form.target_destination_iso2s,
        target_major_ids: form.target_major_ids
          .map(Number)
          .filter(id => Number.isFinite(id) && id > 0),
      });
      setForm(EMPTY_FORM);
      setSavedLead(created);
      setSuccess(`${created.full_name} saved as an Express lead.`);
      const bookNow = await openConfirm({
        title: 'Book a counselling appointment?',
        variant: 'primary',
        confirmLabel: 'Yes, book appointment',
        cancelLabel: 'Not now',
        message: (
          <>
            <p>
              <strong className="text-text-main">{created.full_name}</strong> was just added as an
              Express lead.
            </p>
            <p className="mt-2">
              Do you want to book a counselling appointment with this student now? Their name,
              email, and phone will be pre-filled on the booking screen.
            </p>
          </>
        ),
      });
      if (bookNow) {
        navigate(bookAppointmentHref(created));
      }
    } catch (err) {
      const raw = err instanceof Error ? err.message : '';
      const duplicate = parseExpressDuplicateError(raw);
      if (duplicate) {
        setSaveMatches(duplicate.matches);
        setError(null);
        return;
      }
      setError(raw || 'Could not save this express lead.');
    }
  };

  return (
    <div className="w-full max-w-4xl space-y-4 p-6 md:p-8 pb-16">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-semibold text-text-main">
          <Zap size={20} />
          Express Leads
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Quickly capture a walk-in or phone enquiry. Required: first name, last name, phone, and
          email. Saved leads appear on Offline Leads for further updates.
        </p>
      </div>

      {success ? (
        <div className={`${studentInfoAlertSuccessClass} flex items-start gap-2`}>
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold">Express lead saved</p>
            <p className="mt-1">
              {success} They now appear on Offline Leads so you can add date of birth, location,
              education, and other details.
            </p>
            <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
              <Link
                to={
                  savedLead
                    ? `/offline-leads?q=${encodeURIComponent(savedLead.full_name)}&edit=${savedLead.id}`
                    : '/offline-leads'
                }
                className="font-semibold underline underline-offset-2"
              >
                Update on Offline Leads
              </Link>
              {savedLead ? (
                <Link
                  to={bookAppointmentHref(savedLead)}
                  className="font-semibold underline underline-offset-2"
                >
                  Book counselling appointment
                </Link>
              ) : null}
              <Link to="/ai-active" className="font-semibold underline underline-offset-2">
                Open AI Active
              </Link>
              <Link to="/prospects" className="font-semibold underline underline-offset-2">
                Open All Prospects
              </Link>
            </p>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className={`${studentInfoAlertErrorClass} flex items-start gap-2`}>
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      ) : null}

      {duplicates.length ? (
        <div
          role="alert"
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-700" />
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <p className="font-semibold">{warningHeadline(duplicates)}</p>
                <p className="mt-1">
                  Do not create another record. Review the matched student below and open their
                  existing profile.
                </p>
              </div>
              {duplicates.map(match => {
                const createdLabel = formatCreatedAt(match.created_at);
                return (
                  <div
                    key={matchKey(match)}
                    className="rounded-lg border border-amber-200 bg-white/70 px-3 py-2.5"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <p className="font-semibold text-amber-950">{match.full_name}</p>
                      <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
                        {matchReason(match.matched_on)}
                      </p>
                    </div>
                    <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
                      <div>
                        <dt className="text-xs font-semibold text-amber-800">Email</dt>
                        <dd>{match.email || '—'}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-semibold text-amber-800">Phone</dt>
                        <dd>{match.phone_number || '—'}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-semibold text-amber-800">Status</dt>
                        <dd>
                          {match.status_label}
                          {match.page_label ? ` · ${match.page_label}` : ''}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-semibold text-amber-800">Found in</dt>
                        <dd>
                          {match.record_kind === 'students_master'
                            ? 'Students Master'
                            : match.source_label || match.source || 'Leads'}
                        </dd>
                      </div>
                      {match.students_master_id ? (
                        <div>
                          <dt className="text-xs font-semibold text-amber-800">
                            Students Master ID
                          </dt>
                          <dd>{match.students_master_id}</dd>
                        </div>
                      ) : null}
                      {match.preferred_country ? (
                        <div>
                          <dt className="text-xs font-semibold text-amber-800">Destination</dt>
                          <dd>{match.preferred_country}</dd>
                        </div>
                      ) : null}
                      {match.academic_summary ? (
                        <div>
                          <dt className="text-xs font-semibold text-amber-800">Programs</dt>
                          <dd>{match.academic_summary}</dd>
                        </div>
                      ) : null}
                      {createdLabel ? (
                        <div>
                          <dt className="text-xs font-semibold text-amber-800">Created</dt>
                          <dd>{createdLabel}</dd>
                        </div>
                      ) : null}
                    </dl>
                    <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                      <Link
                        to={match.page_path}
                        className="font-semibold text-amber-900 underline decoration-amber-400 underline-offset-2"
                      >
                        Check on {match.page_label}
                      </Link>
                      {match.lead_id ? (
                        <Link
                          to={match.prospects_path}
                          className="font-semibold text-amber-900 underline decoration-amber-400 underline-offset-2"
                        >
                          Open in All Prospects
                        </Link>
                      ) : null}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      <form onSubmit={event => void handleSave(event)} className={studentInfoSectionClass}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={studentInfoLabelClass} htmlFor="express-first-name">
              First Name *
            </label>
            <input
              id="express-first-name"
              className={studentInfoInputClass}
              value={form.first_name}
              onChange={e => updateForm({ first_name: e.target.value })}
              autoComplete="given-name"
              required
            />
          </div>
          <div>
            <label className={studentInfoLabelClass} htmlFor="express-last-name">
              Last Name *
            </label>
            <input
              id="express-last-name"
              className={studentInfoInputClass}
              value={form.last_name}
              onChange={e => updateForm({ last_name: e.target.value })}
              autoComplete="family-name"
              required
            />
          </div>
          <div className="sm:col-span-2">
            <PhoneWithCountryCodeInput
              id="express-phone"
              label="Phone number *"
              required
              value={form.phone}
              onChange={value => updateForm({ phone: value })}
              countries={countries}
              defaultCountryIso2="IN"
            />
            {phoneMatch ? (
              <p className={studentInfoFieldErrorClass}>
                This phone already belongs to {phoneMatch.full_name}
                {phoneMatch.record_kind === 'students_master'
                  ? ' on Students Master'
                  : phoneMatch.email
                    ? ` (${phoneMatch.email})`
                    : ''}
                .
              </p>
            ) : null}
          </div>
          <div className="sm:col-span-2">
            <label className={studentInfoLabelClass} htmlFor="express-email">
              Email id *
            </label>
            <input
              id="express-email"
              type="email"
              className={studentInfoInputClass}
              value={form.email}
              onChange={e => updateForm({ email: e.target.value })}
              autoComplete="email"
              required
            />
            {emailInvalid ? (
              <p className={studentInfoFieldErrorClass}>{EMAIL_FORMAT_HINT}</p>
            ) : emailMatch ? (
              <p className={studentInfoFieldErrorClass}>
                This email already belongs to {emailMatch.full_name}
                {emailMatch.record_kind === 'students_master'
                  ? ' on Students Master'
                  : emailMatch.phone_number
                    ? ` (${emailMatch.phone_number})`
                    : ''}
                .
              </p>
            ) : null}
          </div>
          <div>
            <SearchableMultiSelect
              id="express-target-countries"
              label="Target countries"
              values={form.target_destination_iso2s}
              options={countries.map(country => ({
                value: country.iso2,
                label: country.name,
              }))}
              onChange={values =>
                updateForm({ target_destination_iso2s: values.slice(0, 6) })
              }
              maxSelections={6}
              placeholder="Optional — select up to 6"
              hint="Optional. Max 6 countries."
            />
          </div>
          <div>
            <SearchableMultiSelect
              id="express-target-programs"
              label="Target programs"
              values={form.target_major_ids}
              options={[...majors]
                .filter(major => major.is_active)
                .sort(
                  (a, b) =>
                    a.sort_order - b.sort_order || a.label.localeCompare(b.label)
                )
                .map(major => ({
                  value: String(major.id),
                  label: major.label,
                }))}
              onChange={values =>
                updateForm({ target_major_ids: values.slice(0, 6) })
              }
              maxSelections={6}
              placeholder="Optional — select majors"
              hint="Optional. Max 6 majors."
              emptyMessage="No majors available"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button
            type="submit"
            className={studentInfoPrimaryBtnClass}
            disabled={
              createLead.isPending ||
              Boolean(duplicates.length) ||
              emailInvalid ||
              !form.email.trim()
            }
          >
            {createLead.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : null}
            Save
          </button>
          {isChecking ? (
            <span className="text-xs text-text-muted">Checking for an existing lead…</span>
          ) : null}
        </div>
      </form>
    </div>
  );
};

export default ExpressLeadsPage;

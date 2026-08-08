import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import {
  CUSTOM_PATHWAY_SENTINEL,
  FLOWX_APPLICATION_STATUSES,
  FLOWX_FEE_CURRENCIES,
  FLOWX_FEE_STATUSES,
  FLOWX_PATHWAY_TYPES,
} from '../../config/flowxApplication';
import {
  useEnrollFlowxStudent,
  useFlowxApplicationLookups,
  useFlowxCountries,
  useFlowxCountryDestinations,
  useFlowxCountryGeography,
  useFlowxPathways,
} from '../../hooks/useFlowx';

function FieldLabel({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-text-muted">
      {children}
      {required ? <span className="text-red-600"> *</span> : null}
    </label>
  );
}

const inputClass =
  'w-full min-w-0 rounded-md border border-border-subtle bg-surface-bg px-2 py-1.5 text-sm text-text-main outline-none focus:border-accent/50';

const gridClass = 'grid grid-cols-2 gap-x-2 gap-y-2 md:grid-cols-3 xl:grid-cols-6';

/** Full-page Add Application — institution FKs, pathway registry, portal & fees. */
const FlowxAddApplicationPage: React.FC = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const presetLead = params.get('leadId') || '';
  const presetIso = (params.get('iso2') || '').toUpperCase();

  const [leadId, setLeadId] = useState(presetLead);
  const [iso2, setIso2] = useState(presetIso || 'US');
  const [stateId, setStateId] = useState('');
  const [cityId, setCityId] = useState('');
  const [institutionId, setInstitutionId] = useState('');
  const [campusId, setCampusId] = useState('');
  const [collegeId, setCollegeId] = useState('');
  const [levelId, setLevelId] = useState('');
  const [programId, setProgramId] = useState('');
  const [intakeId, setIntakeId] = useState('');
  const [pathwayType, setPathwayType] = useState('direct_institutional_portal');
  const [pathwayName, setPathwayName] = useState('');
  const [customPathwayName, setCustomPathwayName] = useState('');
  const [portalUrl, setPortalUrl] = useState('');
  const [portalUsername, setPortalUsername] = useState('');
  const [portalPasswordHint, setPortalPasswordHint] = useState('');
  const [institutionalAppId, setInstitutionalAppId] = useState('');
  const [applicationStatus, setApplicationStatus] = useState('drafting');
  const [feeStatus, setFeeStatus] = useState('not_required');
  const [feeAmount, setFeeAmount] = useState('');
  const [feeCurrency, setFeeCurrency] = useState('USD');
  const [internalTarget, setInternalTarget] = useState('');
  const [officialDeadline, setOfficialDeadline] = useState('');
  const [error, setError] = useState<string | null>(null);

  const countriesQuery = useFlowxCountries();
  const geographyQuery = useFlowxCountryGeography(
    iso2 || null,
    stateId ? Number(stateId) : null
  );
  const destinationsQuery = useFlowxCountryDestinations(iso2 || null, {
    state_id: stateId ? Number(stateId) : undefined,
    city_id: cityId ? Number(cityId) : undefined,
  });
  const lookupsQuery = useFlowxApplicationLookups({
    institution_id: institutionId ? Number(institutionId) : undefined,
    campus_id: campusId ? Number(campusId) : undefined,
    college_id: collegeId ? Number(collegeId) : undefined,
    level_id: levelId ? Number(levelId) : undefined,
  });
  const pathwaysQuery = useFlowxPathways(pathwayType || null);
  const enrollMutation = useEnrollFlowxStudent();

  const institutions = destinationsQuery.data?.institutions ?? [];
  const states = geographyQuery.data?.states ?? [];
  const cities = geographyQuery.data?.cities ?? [];
  const campuses = lookupsQuery.data?.campuses ?? [];
  const colleges = lookupsQuery.data?.colleges ?? [];
  const levels = lookupsQuery.data?.levels ?? [];
  const programs = lookupsQuery.data?.programs ?? [];
  const intakes = lookupsQuery.data?.intakes ?? [];
  const pathways = pathwaysQuery.data ?? [];
  const isCustomPathway = pathwayName === CUSTOM_PATHWAY_SENTINEL;

  useEffect(() => {
    const first = countriesQuery.data?.[0]?.country_iso2;
    if (first && !(countriesQuery.data ?? []).some(c => c.country_iso2 === iso2)) {
      setIso2(first);
    }
  }, [countriesQuery.data, iso2]);

  useEffect(() => {
    setStateId('');
    setCityId('');
    setInstitutionId('');
    setCampusId('');
    setCollegeId('');
    setIntakeId('');
  }, [iso2]);

  useEffect(() => {
    setCityId('');
    setInstitutionId('');
    setCampusId('');
    setCollegeId('');
    setIntakeId('');
  }, [stateId]);

  useEffect(() => {
    setInstitutionId('');
    setCampusId('');
    setCollegeId('');
    setIntakeId('');
  }, [cityId]);

  useEffect(() => {
    setCampusId('');
    setCollegeId('');
    setIntakeId('');
  }, [institutionId]);

  useEffect(() => {
    setCollegeId('');
    setIntakeId('');
  }, [campusId]);

  useEffect(() => {
    setPathwayName('');
    setCustomPathwayName('');
  }, [pathwayType]);

  useEffect(() => {
    if (!programId) return;
    const prog = programs.find(p => String(p.id) === programId);
    const lid = prog?.extra?.level_id;
    if (lid != null && String(lid) !== levelId) {
      setLevelId(String(lid));
    }
  }, [programId, programs, levelId]);

  const toIsoOrNull = (local: string) => {
    if (!local.trim()) return null;
    const d = new Date(local);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const lid = Number(leadId);
    if (!Number.isFinite(lid) || lid <= 0) {
      setError('Enter a valid lead ID');
      return;
    }
    if (isCustomPathway && !customPathwayName.trim()) {
      setError('Enter a custom pathway name');
      return;
    }
    try {
      const data = await enrollMutation.mutateAsync({
        iso2,
        lead_id: lid,
        institution_id: institutionId ? Number(institutionId) : null,
        college_id: collegeId ? Number(collegeId) : null,
        campus_id: campusId ? Number(campusId) : null,
        level_id: levelId ? Number(levelId) : null,
        qualification_program_id: programId || null,
        intake_id: intakeId ? Number(intakeId) : null,
        pathway_type: pathwayType || null,
        pathway_name: isCustomPathway ? null : pathwayName || null,
        custom_pathway_name: isCustomPathway ? customPathwayName.trim() : null,
        portal_url: portalUrl.trim() || null,
        portal_username: portalUsername.trim() || null,
        portal_password_hint: portalPasswordHint.trim() || null,
        institutional_app_id: institutionalAppId.trim() || null,
        application_status: applicationStatus,
        fee_status: feeStatus,
        fee_amount: feeAmount.trim() ? Number(feeAmount) : null,
        fee_currency: feeCurrency,
        internal_target_date: toIsoOrNull(internalTarget),
        official_deadline: toIsoOrNull(officialDeadline),
      });
      navigate(`/flowx/journeys/${data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create application');
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-2">
        <div>
          <Link
            to={presetLead ? `/flowx/journeys/student/${presetLead}` : '/flowx/journeys'}
            className="mb-0.5 inline-flex items-center gap-1 text-xs font-semibold text-text-muted hover:text-text-main"
          >
            <ArrowLeft size={12} /> Back
          </Link>
          <h2 className="text-xl font-bold text-text-main">Add application</h2>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={presetLead ? `/flowx/journeys/student/${presetLead}` : '/flowx/journeys'}
            className="text-xs font-semibold text-text-muted hover:text-text-main"
          >
            Cancel
          </Link>
          <button
            type="submit"
            form="flowx-add-application-form"
            disabled={enrollMutation.isPending || !leadId}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {enrollMutation.isPending ? 'Creating…' : 'Create application'}
          </button>
        </div>
      </div>

      <form
        id="flowx-add-application-form"
        onSubmit={e => void handleSubmit(e)}
        className="min-h-0 flex-1 space-y-2 overflow-y-auto pb-4"
      >
        <section className="rounded-xl border border-border-subtle bg-card p-3">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-text-muted">
            Student & destination
          </h3>
          <div className={gridClass}>
            <div className="xl:col-span-1">
              <FieldLabel required>Lead ID</FieldLabel>
              <input
                value={leadId}
                onChange={e => setLeadId(e.target.value)}
                disabled={Boolean(presetLead)}
                className={`${inputClass} disabled:opacity-60`}
                placeholder="e.g. 42"
              />
            </div>
            <div>
              <FieldLabel required>Country</FieldLabel>
              <select
                value={iso2}
                onChange={e => setIso2(e.target.value)}
                className={inputClass}
              >
                {(countriesQuery.data ?? []).map(c => (
                  <option key={c.country_iso2} value={c.country_iso2}>
                    {c.country_iso2} · {c.country_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>State</FieldLabel>
              <select
                value={stateId}
                onChange={e => setStateId(e.target.value)}
                disabled={geographyQuery.isLoading || states.length === 0}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">
                  {geographyQuery.isLoading
                    ? 'Loading…'
                    : states.length === 0
                      ? 'None'
                      : 'All states'}
                </option>
                {states.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>City</FieldLabel>
              <select
                value={cityId}
                onChange={e => setCityId(e.target.value)}
                disabled={!stateId || geographyQuery.isFetching || cities.length === 0}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">
                  {!stateId
                    ? 'State first'
                    : geographyQuery.isFetching
                      ? 'Loading…'
                      : cities.length === 0
                        ? 'None'
                        : 'All cities'}
                </option>
                {cities.map(c => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel>University</FieldLabel>
              <select
                value={institutionId}
                onChange={e => setInstitutionId(e.target.value)}
                disabled={destinationsQuery.isLoading}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">
                  {destinationsQuery.isLoading
                    ? 'Loading…'
                    : institutions.length === 0
                      ? `No institutions (${iso2})`
                      : `Select (${institutions.length})`}
                </option>
                {institutions.map(inst => (
                  <option key={inst.id} value={inst.id}>
                    {inst.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-card p-3">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-text-muted">
            Program, campus & pathway
          </h3>
          <div className={gridClass}>
            <div>
              <FieldLabel>Campus</FieldLabel>
              <select
                value={campusId}
                onChange={e => setCampusId(e.target.value)}
                disabled={!institutionId}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">Select</option>
                {campuses.map(c => (
                  <option key={String(c.id)} value={String(c.id)}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>College</FieldLabel>
              <select
                value={collegeId}
                onChange={e => setCollegeId(e.target.value)}
                disabled={!institutionId}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">Select</option>
                {colleges.map(c => (
                  <option key={String(c.id)} value={String(c.id)}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Degree level</FieldLabel>
              <select
                value={levelId}
                onChange={e => {
                  setLevelId(e.target.value);
                  setProgramId('');
                }}
                className={inputClass}
              >
                <option value="">Select</option>
                {levels.map(lv => (
                  <option key={String(lv.id)} value={String(lv.id)}>
                    {lv.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel>Program / course</FieldLabel>
              <select
                value={programId}
                onChange={e => setProgramId(e.target.value)}
                className={inputClass}
              >
                <option value="">Select</option>
                {programs.map(p => (
                  <option key={String(p.id)} value={String(p.id)}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Intake</FieldLabel>
              <select
                value={intakeId}
                onChange={e => setIntakeId(e.target.value)}
                disabled={!institutionId}
                className={`${inputClass} disabled:opacity-50`}
              >
                <option value="">Select</option>
                {intakes.map(i => (
                  <option key={String(i.id)} value={String(i.id)}>
                    {i.name}
                    {i.extra?.year != null ? ` (${String(i.extra.year)})` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel>Pathway type</FieldLabel>
              <select
                value={pathwayType}
                onChange={e => setPathwayType(e.target.value)}
                className={inputClass}
              >
                {FLOWX_PATHWAY_TYPES.map(t => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <FieldLabel>Pathway name</FieldLabel>
              <select
                value={pathwayName}
                onChange={e => setPathwayName(e.target.value)}
                className={inputClass}
              >
                <option value="">Select</option>
                {pathways.map(p => (
                  <option key={p.id} value={p.pathway_name}>
                    {p.pathway_name}
                    {p.is_custom ? ' (custom)' : ''}
                  </option>
                ))}
                <option value={CUSTOM_PATHWAY_SENTINEL}>Other / Custom…</option>
              </select>
            </div>
            {isCustomPathway ? (
              <div className="col-span-2">
                <FieldLabel required>Custom pathway</FieldLabel>
                <input
                  value={customPathwayName}
                  onChange={e => setCustomPathwayName(e.target.value)}
                  className={inputClass}
                  placeholder="Saved to registry"
                />
              </div>
            ) : null}
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-card p-3">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-text-muted">
            Portal, status & deadlines
          </h3>
          <div className={gridClass}>
            <div className="col-span-2">
              <FieldLabel>Portal URL</FieldLabel>
              <input
                type="url"
                value={portalUrl}
                onChange={e => setPortalUrl(e.target.value)}
                className={inputClass}
                placeholder="https://"
              />
            </div>
            <div>
              <FieldLabel>Portal user</FieldLabel>
              <input
                value={portalUsername}
                onChange={e => setPortalUsername(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <FieldLabel>Password hint</FieldLabel>
              <input
                value={portalPasswordHint}
                onChange={e => setPortalPasswordHint(e.target.value)}
                className={inputClass}
                placeholder="Team hint"
              />
            </div>
            <div>
              <FieldLabel>App ID</FieldLabel>
              <input
                value={institutionalAppId}
                onChange={e => setInstitutionalAppId(e.target.value)}
                className={inputClass}
                placeholder="UCAS / Common App…"
              />
            </div>
            <div>
              <FieldLabel>App status</FieldLabel>
              <select
                value={applicationStatus}
                onChange={e => setApplicationStatus(e.target.value)}
                className={inputClass}
              >
                {FLOWX_APPLICATION_STATUSES.map(s => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Fee status</FieldLabel>
              <select
                value={feeStatus}
                onChange={e => setFeeStatus(e.target.value)}
                className={inputClass}
              >
                {FLOWX_FEE_STATUSES.map(s => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Fee amount</FieldLabel>
              <input
                type="number"
                min="0"
                step="0.01"
                value={feeAmount}
                onChange={e => setFeeAmount(e.target.value)}
                className={inputClass}
                placeholder="0.00"
              />
            </div>
            <div>
              <FieldLabel>Currency</FieldLabel>
              <select
                value={feeCurrency}
                onChange={e => setFeeCurrency(e.target.value)}
                className={inputClass}
              >
                {FLOWX_FEE_CURRENCIES.map(c => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel>Internal target</FieldLabel>
              <input
                type="datetime-local"
                value={internalTarget}
                onChange={e => setInternalTarget(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <FieldLabel>Official deadline</FieldLabel>
              <input
                type="datetime-local"
                value={officialDeadline}
                onChange={e => setOfficialDeadline(e.target.value)}
                className={inputClass}
              />
            </div>
          </div>
        </section>

        {error ? (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-800">
            {error}
          </p>
        ) : null}
      </form>
    </div>
  );
};

export default FlowxAddApplicationPage;

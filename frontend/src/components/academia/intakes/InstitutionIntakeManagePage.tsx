import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CalendarDays,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Settings2,
} from 'lucide-react';
import { apiFetch } from '../../../utils/api';
import type {
  InstitutionIntakeCalendar,
  InstitutionIntakeRecord,
  IntakeStatus,
} from '../../../types/academicCalendar';
import {
  INTAKE_STATUS_LABELS,
  INTAKE_TYPE_LABELS,
  getIntakesForYear,
  intakeDisplayName,
  normalizeCalendarYears,
} from '../../../types/academicCalendar';
import IntakeBulkEditTable from './IntakeBulkEditTable';
import IntakeSetupModal from './IntakeSetupModal';
import { useConfirmation } from '../../../context/ConfirmationContext';
import EmptyListMessage from '../../ui/EmptyListMessage';

const statusBadgeClass: Record<IntakeStatus, string> = {
  Draft: 'bg-surface-bg text-text-muted border-border-subtle',
  Open: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/30',
  Closed: 'bg-alert/10 text-alert border-alert/30',
};

const InstitutionIntakeManagePage: React.FC = () => {
  const openConfirm = useConfirmation();
  const { institutionId = '' } = useParams();
  const numericId = Number(institutionId);

  const [institutionName, setInstitutionName] = useState('');
  const [calendar, setCalendar] = useState<InstitutionIntakeCalendar | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [rollingOver, setRollingOver] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    if (!numericId) return;
    setLoading(true);
    setError(null);
    try {
      const [institution, calendarData] = await Promise.all([
        apiFetch<{ id: number; name: string }>(`academia/institutions/${numericId}`),
        apiFetch<InstitutionIntakeCalendar>(
          `academia/institutions/${numericId}/intakes/calendar`
        ),
      ]);
      setInstitutionName(institution.name);
      setCalendar(calendarData);
      const years = normalizeCalendarYears(calendarData);
      setSelectedYear(prev => (prev && years.includes(prev) ? prev : years[0] ?? null));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load intake calendar');
      setCalendar(null);
    } finally {
      setLoading(false);
    }
  }, [numericId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const selectedIntakes = useMemo(
    () => getIntakesForYear(calendar, selectedYear),
    [calendar, selectedYear]
  );

  const calendarYears = useMemo(() => normalizeCalendarYears(calendar), [calendar]);

  const handleRollover = async () => {
    if (!numericId || !calendarYears.length) return;
    const sourceYear = selectedYear ?? calendarYears[0];
    const targetYear = sourceYear + 1;
    if (
      !(await openConfirm({
        title: `Generate ${targetYear} calendar?`,
        message: `Generate ${targetYear} calendar from ${sourceYear} terms? New records will be created as Draft.`,
        confirmLabel: 'Generate',
        variant: 'warning',
      }))
    ) {
      return;
    }
    setRollingOver(true);
    try {
      await apiFetch(`academia/institutions/${numericId}/intakes/rollover`, {
        method: 'POST',
        body: JSON.stringify({ source_year: sourceYear, target_year: targetYear }),
      });
      await loadData();
      setSelectedYear(targetYear);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to roll over calendar');
    } finally {
      setRollingOver(false);
    }
  };

  const renderIntakeCard = (intake: InstitutionIntakeRecord) => (
    <div
      key={intake.id}
      className="relative rounded-2xl border border-border-subtle bg-card p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            {INTAKE_TYPE_LABELS[intake.intake_type]}
          </p>
          <h4 className="mt-1 text-lg font-bold text-text-main">{intakeDisplayName(intake)}</h4>
          <p className="text-xs tabular-nums text-text-muted">
            Intake ID {intake.id}
            {intake.institution_id ? ` · Institution ID ${intake.institution_id}` : ''}
          </p>
          <p className="text-sm text-text-muted">
            Term: <span className="font-medium text-text-main">{intake.term_name || '—'}</span>
            {intake.year ? ` · Year ${intake.year}` : null}
          </p>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusBadgeClass[intake.status]}`}
        >
          {INTAKE_STATUS_LABELS[intake.status]}
        </span>
      </div>

      <div className="mt-4 grid gap-2 text-sm text-text-muted md:grid-cols-3">
        <div>
          <span className="block text-xs uppercase tracking-wide">Start</span>
          <span className="font-medium text-text-main">{intake.start_date || '—'}</span>
        </div>
        <div>
          <span className="block text-xs uppercase tracking-wide">End</span>
          <span className="font-medium text-text-main">
            {intake.end_date || (intake.intake_type === 'Rolling' ? 'Optional' : '—')}
          </span>
        </div>
        <div>
          <span className="block text-xs uppercase tracking-wide">Application deadline</span>
          <span className="font-medium text-text-main">{intake.application_deadline || '—'}</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
          <div>
            <div className="flex items-center gap-2 text-accent">
              <CalendarDays size={18} />
              <span className="text-xs font-semibold uppercase tracking-wide">
                Academic Calendar
              </span>
            </div>
            <h2 className="mt-1 text-2xl font-bold text-text-main">
              {institutionName || 'Institution'} Intakes
            </h2>
            {numericId ? (
              <p className="text-sm tabular-nums text-text-muted">Institution ID {numericId}</p>
            ) : null}
            <p className="text-sm text-text-muted">
              Manage term/season labels, fixed vs rolling rules, and yearly calendar roll-over.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSetupOpen(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg"
            >
              <Settings2 size={16} />
              Intake Setup
            </button>
            <button
              type="button"
              onClick={() => void handleRollover()}
              disabled={rollingOver || !calendarYears.length}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg disabled:opacity-40"
            >
              {rollingOver ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <RefreshCw size={16} />
              )}
              Generate Next Year&apos;s Calendar
            </button>
            <button
              type="button"
              onClick={() => void loadData()}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
            >
              <Plus size={16} />
              Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 px-6 py-12 text-sm text-text-muted">
            <Loader2 size={16} className="animate-spin" />
            Loading intake calendar...
          </div>
        ) : error ? (
          <div className="px-6 py-12 text-sm text-alert">{error}</div>
        ) : !calendarYears.length ? (
          <div className="px-6 py-12 text-center">
            <p className="text-sm text-text-muted">
              No academic calendar configured yet. Run Intake Setup to generate terms from a
              global template.
            </p>
            <button
              type="button"
              onClick={() => setSetupOpen(true)}
              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
            >
              <Settings2 size={16} />
              Start Intake Setup
            </button>
          </div>
        ) : (
          <div className="grid gap-6 p-6 lg:grid-cols-[220px_minmax(0,1fr)]">
            <aside className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Calendar years
              </p>
              {calendarYears.map(year => (
                <button
                  key={year}
                  type="button"
                  onClick={() => setSelectedYear(year)}
                  className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left text-sm font-semibold ${
                    selectedYear === year
                      ? 'border-accent bg-accent/10 text-text-main'
                      : 'border-border-subtle bg-surface-bg text-text-muted hover:text-text-main'
                  }`}
                >
                  {year}
                  <ChevronRight size={16} />
                </button>
              ))}
            </aside>

            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-text-main">
                  {selectedYear ? `${selectedYear} Term Timeline` : 'Term Timeline'}
                </h3>
                <span className="text-sm text-text-muted">
                  {selectedIntakes.length} term{selectedIntakes.length === 1 ? '' : 's'}
                </span>
              </div>

              {selectedIntakes.length === 0 ? (
                <EmptyListMessage
                  message={
                    selectedYear
                      ? `No intakes configured for ${selectedYear} yet.`
                      : 'No intakes configured for this year yet.'
                  }
                />
              ) : (
                <div className="relative space-y-4 before:absolute before:bottom-0 before:left-4 before:top-0 before:w-px before:bg-border-subtle">
                  {selectedIntakes.map(intake => (
                    <div key={intake.id} className="relative pl-10">
                      <span className="absolute left-2 top-5 h-4 w-4 rounded-full border-2 border-accent bg-card" />
                      {renderIntakeCard(intake)}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>

      {selectedIntakes.length > 0 ? (
        <IntakeBulkEditTable
          key={selectedYear ?? 'none'}
          institutionId={numericId}
          intakes={selectedIntakes}
          onSaved={() => void loadData()}
        />
      ) : null}

      <IntakeSetupModal
        open={setupOpen}
        institutionId={numericId}
        onClose={() => setSetupOpen(false)}
        onCreated={() => void loadData()}
      />
    </div>
  );
};

export default InstitutionIntakeManagePage;

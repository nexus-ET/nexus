import { useEffect, useMemo, useState } from 'react';
import { Loader2, Save } from 'lucide-react';
import { apiFetch } from '../../../utils/api';
import type { InstitutionIntakeRecord, IntakeStatus } from '../../../types/academicCalendar';
import { INTAKE_STATUS_LABELS, intakeDisplayName } from '../../../types/academicCalendar';

interface IntakeBulkEditTableProps {
  institutionId: number;
  intakes: InstitutionIntakeRecord[];
  onSaved: () => void;
}

type DraftRow = {
  id: number;
  display_name: string;
  intake_type: string;
  start_date: string;
  end_date: string;
  application_deadline: string;
  status: IntakeStatus;
};

const IntakeBulkEditTable: React.FC<IntakeBulkEditTableProps> = ({
  institutionId,
  intakes,
  onSaved,
}) => {
  const initialRows = useMemo<DraftRow[]>(
    () =>
      intakes.map(intake => ({
        id: intake.id,
        display_name: intakeDisplayName(intake),
        intake_type: intake.intake_type,
        start_date: intake.start_date || '',
        end_date: intake.end_date || '',
        application_deadline: intake.application_deadline || '',
        status: intake.status,
      })),
    [intakes]
  );

  const [rows, setRows] = useState<DraftRow[]>(initialRows);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(initialRows);
  }, [initialRows]);

  if (intakes.length === 0) return null;

  const updateRow = (id: number, patch: Partial<DraftRow>) => {
    setRows(prev => prev.map(row => (row.id === id ? { ...row, ...patch } : row)));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`academia/institutions/${institutionId}/intakes/bulk`, {
        method: 'PUT',
        body: JSON.stringify({
          items: rows.map(row => ({
            id: row.id,
            start_date: row.start_date || null,
            end_date: row.end_date || null,
            application_deadline: row.application_deadline || null,
            status: row.status,
          })),
        }),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save intake dates');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
        <div>
          <h3 className="text-lg font-bold text-text-main">Bulk Edit Terms</h3>
          <p className="text-sm text-text-muted">
            Update dates and status for multiple terms after roll-over or setup.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Save All
        </button>
      </div>

      {error ? <div className="px-6 py-3 text-sm text-alert">{error}</div> : null}

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
            <tr>
              <th className="px-6 py-3 font-semibold">ID</th>
              <th className="px-6 py-3 font-semibold">Term / Season</th>
              <th className="px-6 py-3 font-semibold">Type</th>
              <th className="px-6 py-3 font-semibold">Start</th>
              <th className="px-6 py-3 font-semibold">End</th>
              <th className="px-6 py-3 font-semibold">Application deadline</th>
              <th className="px-6 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} className="border-t border-border-subtle/70">
                <td className="px-6 py-3 tabular-nums text-text-muted">{row.id}</td>
                <td className="px-6 py-3 font-semibold text-text-main">{row.display_name}</td>
                <td className="px-6 py-3 text-text-muted">{row.intake_type}</td>
                <td className="px-6 py-3">
                  <input
                    type="date"
                    value={row.start_date}
                    onChange={event => updateRow(row.id, { start_date: event.target.value })}
                    className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
                  />
                </td>
                <td className="px-6 py-3">
                  <input
                    type="date"
                    value={row.end_date}
                    onChange={event => updateRow(row.id, { end_date: event.target.value })}
                    className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
                    disabled={row.intake_type === 'Rolling'}
                  />
                </td>
                <td className="px-6 py-3">
                  <input
                    type="date"
                    value={row.application_deadline}
                    onChange={event =>
                      updateRow(row.id, { application_deadline: event.target.value })
                    }
                    className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
                  />
                </td>
                <td className="px-6 py-3">
                  <select
                    value={row.status}
                    onChange={event =>
                      updateRow(row.id, { status: event.target.value as IntakeStatus })
                    }
                    className="rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
                  >
                    {Object.entries(INTAKE_STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default IntakeBulkEditTable;

import { useMemo } from 'react';
import { formatAuditFieldLabel } from '../../../schemas/wizard';

interface AcademiaAuditDiffModalProps {
  open: boolean;
  entry: {
    id: number;
    action: string;
    created_at: string;
    old_data: Record<string, unknown> | null;
    new_data: Record<string, unknown> | null;
  } | null;
  onClose: () => void;
}

const flattenEntries = (data: Record<string, unknown> | null): Array<[string, string]> => {
  if (!data) return [];
  return Object.entries(data).map(([key, value]) => [
    key,
    typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '—'),
  ]);
};

const AcademiaAuditDiffModal: React.FC<AcademiaAuditDiffModalProps> = ({ open, entry, onClose }) => {
  const oldRows = useMemo(() => flattenEntries(entry?.old_data ?? null), [entry]);
  const newRows = useMemo(() => flattenEntries(entry?.new_data ?? null), [entry]);

  if (!open || !entry) return null;

  const allKeys = [...new Set([...oldRows.map(([k]) => k), ...newRows.map(([k]) => k)])];

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="border-b border-border-subtle px-5 py-4">
          <h3 className="text-lg font-bold text-text-main">Change diff</h3>
          <p className="text-xs text-text-muted">
            {entry.action} · {new Date(entry.created_at).toLocaleString()}
          </p>
        </div>
        <div className="overflow-y-auto p-5">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-text-muted">
                <th className="pb-2 pr-4 font-semibold">Field</th>
                <th className="pb-2 pr-4 font-semibold">Before</th>
                <th className="pb-2 font-semibold">After</th>
              </tr>
            </thead>
            <tbody>
              {allKeys.map(key => {
                const oldVal = oldRows.find(([k]) => k === key)?.[1] ?? '—';
                const newVal = newRows.find(([k]) => k === key)?.[1] ?? '—';
                const changed = oldVal !== newVal;
                return (
                  <tr key={key} className="border-t border-border-subtle/70 align-top">
                    <td className="py-2 pr-4 font-medium text-text-main">{formatAuditFieldLabel(key)}</td>
                    <td className={`py-2 pr-4 whitespace-pre-wrap ${changed ? 'bg-rose-500/5 text-rose-700' : 'text-text-muted'}`}>
                      {oldVal}
                    </td>
                    <td className={`py-2 whitespace-pre-wrap ${changed ? 'bg-emerald-500/5 text-emerald-700' : 'text-text-muted'}`}>
                      {newVal}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end border-t border-border-subtle px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default AcademiaAuditDiffModal;

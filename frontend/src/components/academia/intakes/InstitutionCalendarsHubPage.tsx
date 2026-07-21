import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarDays, ChevronRight, Loader2 } from 'lucide-react';
import { apiFetch } from '../../../utils/api';
import { institutionIntakesPath } from '../../../config/academiaHubNav';
import type { InstitutionalHierarchySummary } from '../../../types/institutions';

const InstitutionCalendarsHubPage: React.FC = () => {
  const [hierarchy, setHierarchy] = useState<InstitutionalHierarchySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHierarchy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<InstitutionalHierarchySummary>('academia/institutions/hierarchy');
      setHierarchy(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load institutions');
      setHierarchy(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHierarchy();
  }, [loadHierarchy]);

  const institutions = hierarchy?.institutions || [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-muted">
        Open an institution&apos;s academic calendar to configure terms, roll over years, and manage
        intake windows.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 py-10 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin" />
          Loading institutions...
        </div>
      ) : error ? (
        <div className="py-10 text-sm text-alert">{error}</div>
      ) : institutions.length === 0 ? (
        <div className="py-10 text-sm text-text-muted">No institutions found.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="px-6 py-3 font-semibold">Institution</th>
                <th className="px-6 py-3 font-semibold">Campuses</th>
                <th className="px-6 py-3 font-semibold">Academic Calendar</th>
              </tr>
            </thead>
            <tbody>
              {institutions.map(institution => (
                <tr key={institution.id} className="border-t border-border-subtle/70">
                  <td className="px-6 py-3 font-semibold text-text-main">{institution.name}</td>
                  <td className="px-6 py-3 text-text-muted">{institution.campuses.length}</td>
                  <td className="px-6 py-3">
                    <Link
                      to={institutionIntakesPath(institution.id)}
                      className="inline-flex items-center gap-2 rounded-xl bg-accent/10 px-3 py-2 text-sm font-semibold text-accent hover:bg-accent/20"
                    >
                      <CalendarDays size={16} />
                      Open Calendar
                      <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default InstitutionCalendarsHubPage;

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '../../utils/api';
import { LEVELS_PATH, FRAMEWORK_SECTION_PATH } from '../../types/academicFramework';
import type { LevelRecord } from '../../types/level';
import AcademiaBreadcrumbs from './AcademiaBreadcrumbs';
import LevelFormPanel from './LevelFormPanel';
import { useConfirmation } from '../../context/ConfirmationContext';

const FrameworkLevelsPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const openConfirm = useConfirmation();
  const queryClient = useQueryClient();
  const [levels, setLevels] = useState<LevelRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [editingLevel, setEditingLevel] = useState<LevelRecord | null>(null);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');

  const loadLevels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set('q', search.trim());
      const query = params.toString();
      const data = await apiFetch<LevelRecord[]>(
        query ? `academia/levels?${query}` : 'academia/levels'
      );
      setLevels(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load levels');
      setLevels([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadLevels();
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [loadLevels]);

  const openCreate = () => {
    setEditingLevel(null);
    setFormMode('create');
  };

  const openEdit = (level: LevelRecord) => {
    setEditingLevel(level);
    setFormMode('edit');
  };

  const handleSaved = () => {
    setEditingLevel(null);
    setFormMode('create');
    void loadLevels();
    void queryClient.invalidateQueries({ queryKey: ['academia-levels'] });
    void queryClient.invalidateQueries({ queryKey: ['levels'] });
  };

  const handleDelete = async (level: LevelRecord) => {
    if (
      !(await openConfirm({
        title: 'Delete level?',
        message: `Delete level "${level.name}"? Programs and education degrees that use this level must be reassigned first.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      }))
    ) {
      return;
    }
    try {
      await apiFetch(`academia/levels/${level.id}`, { method: 'DELETE' });
      await queryClient.invalidateQueries({ queryKey: ['academia-levels'] });
      await queryClient.invalidateQueries({ queryKey: ['levels'] });
      if (editingLevel?.id === level.id) {
        openCreate();
      }
      void loadLevels();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete level');
    }
  };

  return (
    <div className={embedded ? 'space-y-0' : 'space-y-6'}>
      {embedded ? null : (
        <AcademiaBreadcrumbs
          items={[
            { label: 'Academia Hub', path: '/academia' },
            { label: 'Academic Framework', path: FRAMEWORK_SECTION_PATH },
            { label: 'Levels', path: LEVELS_PATH },
          ]}
        />
      )}

      <div className={embedded ? '' : 'rounded-2xl border border-border-subtle bg-card shadow-sm'}>
        <div
          className={`flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4 ${
            embedded ? 'justify-end' : ''
          }`}
        >
          {embedded ? null : (
            <div>
              <h2 className="text-xl font-bold text-text-main">Levels</h2>
              <p className="text-sm text-text-muted">
                Master academic levels that sit above programs (e.g. Undergraduate, Graduate).
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg"
          >
            <Plus size={16} />
            Create Level
          </button>
        </div>

        <div className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.9fr)]">
          <div className="space-y-4">
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-text-main">Search</span>
              <input
                type="text"
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder="Search levels..."
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              />
            </label>

            {loading ? (
              <div className="flex items-center gap-2 py-10 text-sm text-text-muted">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            ) : error ? (
              <div className="py-10 text-sm text-alert">{error}</div>
            ) : levels.length === 0 ? (
              <div className="py-10 text-sm text-text-muted">No levels found.</div>
            ) : (
              <div className="overflow-x-auto rounded-2xl border border-border-subtle">
                <table className="min-w-full text-sm">
                  <thead className="bg-surface-bg text-left text-xs uppercase tracking-wide text-text-muted">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Name</th>
                      <th className="px-4 py-3 font-semibold">Code</th>
                      <th className="px-4 py-3 font-semibold">Description</th>
                      <th className="px-4 py-3 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {levels.map(level => (
                      <tr
                        key={level.id}
                        className={`border-t border-border-subtle/70 ${
                          editingLevel?.id === level.id ? 'bg-accent/5' : ''
                        }`}
                      >
                        <td className="px-4 py-3 font-semibold text-text-main">{level.name}</td>
                        <td className="px-4 py-3 font-mono text-text-muted">{level.code}</td>
                        <td className="max-w-md px-4 py-3 text-text-muted">
                          {level.description || '—'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => openEdit(level)}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent/10"
                            >
                              <Pencil size={14} />
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDelete(level)}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                            >
                              <Trash2 size={14} />
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <LevelFormPanel
            key={`${formMode}-${editingLevel?.id ?? 'new'}`}
            level={editingLevel}
            mode={formMode}
            onCancel={openCreate}
            onSaved={handleSaved}
          />
        </div>
      </div>
    </div>
  );
};

export default FrameworkLevelsPage;

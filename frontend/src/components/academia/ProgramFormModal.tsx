import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../utils/api';
import { fetchAcademiaListItems } from '../../utils/academiaList';
import { useAcademiaLevels } from '../../hooks/useLevels';
import { levelSelectOptions } from '../../constants/levels';
import { ACADEMIC_FRAMEWORK_STEP_LABELS } from '../../schemas/academicFrameworkHierarchy';
import type { DegreeRecord, ProgramRecord } from '../../types/academicFramework';
import SearchableSelect from './SearchableSelect';
import RichTextEditor from '../ui/rich-text-editor';

interface ProgramFormModalProps {
  open: boolean;
  program: ProgramRecord | null;
  presetDegreeId?: string;
  onClose: () => void;
  onSaved: () => void;
}

const ProgramFormModal: React.FC<ProgramFormModalProps> = ({
  open,
  program,
  presetDegreeId = '',
  onClose,
  onSaved,
}) => {
  const { levels } = useAcademiaLevels(open);
  const [levelId, setLevelId] = useState('');
  const [degrees, setDegrees] = useState<DegreeRecord[]>([]);
  const [loadingDegrees, setLoadingDegrees] = useState(false);
  const [degreeId, setDegreeId] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDegreeId(program ? String(program.degree_id) : presetDegreeId || '');
    setName(program?.name || program?.label || '');
    setDescription(program?.description || '');
    setError(null);
  }, [open, presetDegreeId, program]);

  useEffect(() => {
    if (!open || !program) return;
    void apiFetch<DegreeRecord>(`academia/degrees/${program.degree_id}`).then(degree => {
      if (degree?.level_id) {
        setLevelId(String(degree.level_id));
      }
    });
  }, [open, program]);

  useEffect(() => {
    if (!open || program || !presetDegreeId) return;
    void apiFetch<DegreeRecord>(`academia/degrees/${presetDegreeId}`).then(degree => {
      if (degree?.level_id) {
        setLevelId(String(degree.level_id));
      }
    });
  }, [open, presetDegreeId, program]);

  useEffect(() => {
    if (!open || !levelId) {
      setDegrees([]);
      return;
    }
    setLoadingDegrees(true);
    void fetchAcademiaListItems<DegreeRecord>('academia/degrees', { level_id: levelId })
      .then(setDegrees)
      .finally(() => setLoadingDegrees(false));
  }, [levelId, open]);

  useEffect(() => {
    if (!open || program || presetDegreeId) return;
    setDegreeId('');
  }, [levelId, open, presetDegreeId, program]);

  const degreeOptions = useMemo(
    () =>
      degrees.map(degree => ({
        value: String(degree.id),
        label: degree.name,
      })),
    [degrees]
  );

  if (!open) return null;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!levelId) {
      setError('Select a level first.');
      return;
    }
    if (!degreeId) {
      setError('Select a parent program first.');
      return;
    }
    if (!name.trim()) {
      setError('Major name is required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        program_id: degreeId,
        name: name.trim(),
        description: description.trim() || null,
      };
      if (program) {
        await apiFetch(`academia/programs/${program.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
      } else {
        await apiFetch('academia/programs', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save program');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <h3 className="text-lg font-bold text-text-main">
            {program ? 'Edit Major' : 'Create Major'}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-text-muted hover:bg-surface-bg hover:text-text-main"
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <SearchableSelect
            label={ACADEMIC_FRAMEWORK_STEP_LABELS.level}
            value={levelId}
            options={levelSelectOptions(levels)}
            onChange={setLevelId}
            placeholder="Select level..."
            required
          />
          <SearchableSelect
            label={ACADEMIC_FRAMEWORK_STEP_LABELS.program}
            value={degreeId}
            options={degreeOptions}
            onChange={setDegreeId}
            placeholder={
              !levelId
                ? 'Select a level first'
                : loadingDegrees
                  ? 'Loading programs...'
                  : degreeOptions.length === 0
                    ? 'No programs for this level'
                    : 'e.g. BEng, BSc, MBA'
            }
            required
            disabled={!levelId || loadingDegrees || degreeOptions.length === 0}
          />
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Major name *</span>
            <input
              type="text"
              value={name}
              onChange={event => setName(event.target.value)}
              placeholder="e.g. Mechanical Engineering, Computer Science"
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              required
            />
          </label>
          <RichTextEditor
            label="Description"
            content={description}
            onChange={setDescription}
            maxLength={5000}
            placeholder="Brief overview of this major or discipline..."
          />
          {error ? <p className="text-sm text-alert">{error}</p> : null}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted hover:text-text-main"
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

export default ProgramFormModal;

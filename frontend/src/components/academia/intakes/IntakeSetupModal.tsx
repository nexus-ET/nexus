import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { apiFetch } from '../../../utils/api';
import type { GlobalAcademicTemplate } from '../../../types/academicCalendar';

interface IntakeSetupModalProps {
  open: boolean;
  institutionId: number;
  onClose: () => void;
  onCreated: () => void;
}

const IntakeSetupModal: React.FC<IntakeSetupModalProps> = ({
  open,
  institutionId,
  onClose,
  onCreated,
}) => {
  const [templates, setTemplates] = useState<GlobalAcademicTemplate[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [templateId, setTemplateId] = useState('');
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoadingTemplates(true);
    void apiFetch<GlobalAcademicTemplate[]>('academia/academic-templates')
      .then(data => setTemplates(Array.isArray(data) ? data : []))
      .finally(() => setLoadingTemplates(false));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setTemplateId('');
    setYear(String(new Date().getFullYear()));
    setError(null);
  }, [open]);

  if (!open) return null;

  const selectedTemplate = templates.find(item => String(item.id) === templateId);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!templateId) {
      setError('Select an academic template.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`academia/institutions/${institutionId}/intakes/setup`, {
        method: 'POST',
        body: JSON.stringify({
          template_id: Number(templateId),
          year: Number(year),
        }),
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set up intakes');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-border-subtle bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <h3 className="text-lg font-bold text-text-main">Intake Setup</h3>
            <p className="text-xs text-text-muted">
              Select a global academic template to generate term records for your institution.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-text-muted hover:bg-surface-bg">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Academic template *</span>
            <select
              value={templateId}
              onChange={event => setTemplateId(event.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
              disabled={loadingTemplates}
            >
              <option value="">
                {loadingTemplates ? 'Loading templates...' : 'Select template...'}
              </option>
              {templates.map(template => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>

          {selectedTemplate ? (
            <div className="rounded-xl border border-border-subtle bg-surface-bg/60 p-4 text-sm">
              <p className="font-semibold text-text-main">{selectedTemplate.name}</p>
              {selectedTemplate.description ? (
                <p className="mt-1 text-text-muted">{selectedTemplate.description}</p>
              ) : null}
              <ul className="mt-3 space-y-1 text-text-muted">
                {selectedTemplate.default_intake_configs.map(config => (
                  <li key={config.term_name}>
                    {config.term_name} · {config.intake_type} · {config.expected_duration_months} mo
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <label className="block space-y-1 text-sm">
            <span className="font-medium text-text-main">Academic year *</span>
            <input
              type="number"
              min={2000}
              max={2100}
              value={year}
              onChange={event => setYear(event.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>

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
              Generate Calendar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default IntakeSetupModal;

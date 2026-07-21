import { AlertTriangle, Loader2, Save } from 'lucide-react';

interface UnsavedChangesDialogProps {
  open: boolean;
  saving?: boolean;
  onSave: () => void;
  onDiscard: () => void;
  onCancel: () => void;
}

const UnsavedChangesDialog: React.FC<UnsavedChangesDialogProps> = ({
  open,
  saving = false,
  onSave,
  onDiscard,
  onCancel,
}) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="unsaved-changes-title"
        className="w-full max-w-md rounded-2xl border border-border-subtle bg-card p-6 shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <div className="rounded-full bg-amber-100 p-2 text-amber-700">
            <AlertTriangle size={20} />
          </div>
          <div className="space-y-2">
            <h3 id="unsaved-changes-title" className="text-lg font-bold text-text-main">
              Unsaved changes
            </h3>
            <p className="text-sm text-text-muted">
              You have unsaved edits on this step. Save your work before leaving, or your changes
              will be lost.
            </p>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted disabled:opacity-50"
          >
            Stay on step
          </button>
          <button
            type="button"
            onClick={onDiscard}
            disabled={saving}
            className="rounded-xl border border-alert/30 px-4 py-2 text-sm font-semibold text-alert disabled:opacity-50"
          >
            Leave without saving
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save step
          </button>
        </div>
      </div>
    </div>
  );
};

export default UnsavedChangesDialog;

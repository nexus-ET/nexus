import { useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';

import IntakeConfigureContent, {
  type IntakeConfigureContentHandle,
  type IntakeConfigureContentProps,
} from './IntakeConfigureContent';

interface IntakeConfigurePanelProps extends IntakeConfigureContentProps {
  entityName: string;
  onClose: () => void;
}

const IntakeConfigurePanel: React.FC<IntakeConfigurePanelProps> = ({
  entityName,
  onClose,
  ...contentProps
}) => {
  const contentRef = useRef<IntakeConfigureContentHandle>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [savingClose, setSavingClose] = useState(false);
  const [hasDateConflicts, setHasDateConflicts] = useState(false);
  const { onDirtyChange, onValidationChange, ...restContentProps } = contentProps;

  const requestClose = () => {
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  };

  const saveAndClose = async () => {
    setSavingClose(true);
    const saveError = await contentRef.current?.saveAll();
    setSavingClose(false);
    if (!saveError) {
      setConfirmClose(false);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30">
      <div className="flex h-full w-full max-w-xl flex-col bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-text-muted">Configure Calendar</p>
            <h3 className="text-lg font-bold text-text-main">{entityName}</h3>
          </div>
          <button type="button" onClick={requestClose} className="text-sm font-semibold text-text-muted">
            <X size={16} className="mr-1 inline" />
            Close
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <IntakeConfigureContent
            ref={contentRef}
            {...restContentProps}
            onClose={requestClose}
            onDirtyChange={nextDirty => {
              setDirty(nextDirty);
              onDirtyChange?.(nextDirty);
            }}
            onValidationChange={hasConflicts => {
              setHasDateConflicts(hasConflicts);
              onValidationChange?.(hasConflicts);
            }}
          />
        </div>
      </div>

      {confirmClose ? (
        <div className="fixed inset-0 z-[140] flex items-center justify-center bg-black/50 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="unsaved-calendar-title"
            className="w-full max-w-md rounded-2xl border border-border-subtle bg-card p-5 shadow-2xl"
          >
            <h3 id="unsaved-calendar-title" className="text-lg font-bold text-text-main">
              Save calendar changes?
            </h3>
            <p className="mt-2 text-sm text-text-muted">
              You have unsaved calendar changes. Save them before closing.
            </p>
            {hasDateConflicts ? (
              <p className="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                Resolve the highlighted date conflicts before saving.
              </p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={savingClose}
                onClick={() => setConfirmClose(false)}
                className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingClose || hasDateConflicts}
                onClick={() => void saveAndClose()}
                className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
              >
                {savingClose ? <Loader2 size={16} className="animate-spin" /> : null}
                Save & close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default IntakeConfigurePanel;

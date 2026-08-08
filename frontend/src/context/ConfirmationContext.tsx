import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import ConfirmationModal, {
  type ConfirmationModalOptions,
} from '../components/ConfirmationModal';

type OpenConfirm = (options: ConfirmationModalOptions) => Promise<boolean>;

interface PendingConfirmation {
  options: ConfirmationModalOptions;
  resolve: (confirmed: boolean) => void;
}

const ConfirmationContext = createContext<OpenConfirm | null>(null);

export const ConfirmationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [active, setActive] = useState<PendingConfirmation | null>(null);
  const activeRef = useRef<PendingConfirmation | null>(null);
  const queueRef = useRef<PendingConfirmation[]>([]);

  const showNext = useCallback(() => {
    const next = queueRef.current.shift() ?? null;
    activeRef.current = next;
    setActive(next);
  }, []);

  const settle = useCallback(
    (confirmed: boolean) => {
      const current = activeRef.current;
      if (!current) return;
      activeRef.current = null;
      setActive(null);
      current.resolve(confirmed);
      showNext();
    },
    [showNext]
  );

  const openConfirm = useCallback<OpenConfirm>(
    options =>
      new Promise<boolean>(resolve => {
        const pending = { options, resolve };
        if (activeRef.current) {
          queueRef.current.push(pending);
          return;
        }
        activeRef.current = pending;
        setActive(pending);
      }),
    []
  );

  useEffect(
    () => () => {
      activeRef.current?.resolve(false);
      queueRef.current.forEach(item => item.resolve(false));
      queueRef.current = [];
    },
    []
  );

  const value = useMemo(() => openConfirm, [openConfirm]);

  return (
    <ConfirmationContext.Provider value={value}>
      {children}
      <ConfirmationModal
        open={Boolean(active)}
        title={active?.options.title ?? ''}
        message={active?.options.message ?? ''}
        confirmLabel={active?.options.confirmLabel}
        cancelLabel={active?.options.cancelLabel}
        variant={active?.options.variant}
        mode={active?.options.mode}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmationContext.Provider>
  );
};

export const useConfirmation = (): OpenConfirm => {
  const context = useContext(ConfirmationContext);
  if (!context) {
    throw new Error('useConfirmation must be used within ConfirmationProvider');
  }
  return context;
};

/** HTML replacement for window.alert — single OK dialog. */
export const useAlert = () => {
  const openConfirm = useConfirmation();
  return useCallback(
    (options: Omit<ConfirmationModalOptions, 'mode' | 'cancelLabel'>) =>
      openConfirm({
        ...options,
        mode: 'alert',
        variant: options.variant ?? 'warning',
        confirmLabel: options.confirmLabel ?? 'OK',
      }).then(() => undefined),
    [openConfirm]
  );
};

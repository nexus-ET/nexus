import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useBlocker, useLocation } from 'react-router-dom';

import ConfirmationModal from '../components/ConfirmationModal';

export const UNSAVED_CHANGES_CONFIRM = {
  title: 'Leave without saving?',
  message:
    'You have unsaved changes. If you leave now, your changes will be lost.',
  confirmLabel: 'Leave',
  cancelLabel: 'Stay',
  variant: 'warning' as const,
};

type DirtyGetter = () => boolean;

type BlockerControls = {
  getState: () => string;
  reset: () => void;
  proceed: () => void;
};

interface UnsavedChangesContextValue {
  shouldBlockNavigation: () => boolean;
  setSourceDirty: (sourceId: string, dirty: boolean) => void;
  setSourceGetter: (sourceId: string, getter: DirtyGetter | null) => void;
  /**
   * Allow the next in-app navigation without prompting.
   * Resets any wedged React Router blocker first (do not call proceed — that
   * desyncs URL vs rendered route).
   */
  releaseSource: (sourceId: string) => void;
  allowNextNavigation: () => void;
  clearNavigationBypass: () => void;
  /** @internal used by the navigation guard */
  registerBlockerControls: (controls: BlockerControls | null) => void;
}

const UnsavedChangesContext = createContext<UnsavedChangesContextValue | null>(null);

export const UnsavedChangesProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [boolSources, setBoolSources] = useState<Record<string, boolean>>({});
  const boolSourcesRef = useRef(boolSources);
  boolSourcesRef.current = boolSources;

  const gettersRef = useRef<Record<string, DirtyGetter>>({});
  const allowNextNavigationRef = useRef(false);
  const blockerControlsRef = useRef<BlockerControls | null>(null);

  const getIsDirty = useCallback(() => {
    if (Object.values(boolSourcesRef.current).some(Boolean)) return true;
    return Object.values(gettersRef.current).some(getter => {
      try {
        return Boolean(getter());
      } catch {
        return false;
      }
    });
  }, []);

  const shouldBlockNavigation = useCallback(() => {
    if (allowNextNavigationRef.current) {
      return false;
    }
    return getIsDirty();
  }, [getIsDirty]);

  const setSourceDirty = useCallback((sourceId: string, dirty: boolean) => {
    setBoolSources(prev => {
      if (dirty) {
        if (prev[sourceId]) return prev;
        return { ...prev, [sourceId]: true };
      }
      if (!(sourceId in prev)) return prev;
      const next = { ...prev };
      delete next[sourceId];
      return next;
    });
  }, []);

  const setSourceGetter = useCallback((sourceId: string, getter: DirtyGetter | null) => {
    if (!getter) {
      delete gettersRef.current[sourceId];
      return;
    }
    gettersRef.current[sourceId] = getter;
  }, []);

  const resetWedgedBlocker = useCallback(() => {
    const controls = blockerControlsRef.current;
    if (controls?.getState() === 'blocked') {
      // reset() cancels the stuck transition. proceed() after a partial URL update
      // is what left the address bar on /history while the wizard UI stayed mounted.
      controls.reset();
    }
  }, []);

  const allowNextNavigation = useCallback(() => {
    allowNextNavigationRef.current = true;
  }, []);

  const releaseSource = useCallback(
    (sourceId: string) => {
      allowNextNavigationRef.current = true;
      setBoolSources(prev => {
        if (!(sourceId in prev)) return prev;
        const next = { ...prev };
        delete next[sourceId];
        boolSourcesRef.current = next;
        return next;
      });
      // Clear a wedged blocked transition so the following navigate() can commit
      // a fresh route change (proceed() here desyncs URL vs UI).
      resetWedgedBlocker();
    },
    [resetWedgedBlocker]
  );

  const clearNavigationBypass = useCallback(() => {
    allowNextNavigationRef.current = false;
  }, []);

  const registerBlockerControls = useCallback((controls: BlockerControls | null) => {
    blockerControlsRef.current = controls;
  }, []);

  const value = useMemo(
    () => ({
      shouldBlockNavigation,
      setSourceDirty,
      setSourceGetter,
      releaseSource,
      allowNextNavigation,
      clearNavigationBypass,
      registerBlockerControls,
    }),
    [
      shouldBlockNavigation,
      setSourceDirty,
      setSourceGetter,
      releaseSource,
      allowNextNavigation,
      clearNavigationBypass,
      registerBlockerControls,
    ]
  );

  return (
    <UnsavedChangesContext.Provider value={value}>{children}</UnsavedChangesContext.Provider>
  );
};

function useUnsavedChangesContext(): UnsavedChangesContextValue {
  const context = useContext(UnsavedChangesContext);
  if (!context) {
    throw new Error('useUnsavedChanges must be used within UnsavedChangesProvider');
  }
  return context;
}

export function useAllowNextNavigation() {
  return useUnsavedChangesContext().allowNextNavigation;
}

/**
 * Register a dirty flag for the current screen/form.
 * Returns `release()` to allow the next navigation without a second prompt.
 */
export function useUnsavedChanges(dirty: boolean, sourceId: string) {
  const { setSourceDirty, releaseSource } = useUnsavedChangesContext();

  useEffect(() => {
    setSourceDirty(sourceId, dirty);
    return () => setSourceDirty(sourceId, false);
  }, [dirty, setSourceDirty, sourceId]);

  return useMemo(
    () => ({
      release: () => releaseSource(sourceId),
    }),
    [releaseSource, sourceId]
  );
}

/**
 * Register a dirty getter (for forms that track dirty in refs without re-rendering).
 * The getter is evaluated when navigation is attempted.
 */
export function useUnsavedChangesGetter(getDirty: () => boolean, sourceId: string) {
  const { setSourceGetter, releaseSource } = useUnsavedChangesContext();
  const getDirtyRef = useRef(getDirty);
  getDirtyRef.current = getDirty;

  useEffect(() => {
    setSourceGetter(sourceId, () => getDirtyRef.current());
    return () => setSourceGetter(sourceId, null);
  }, [setSourceGetter, sourceId]);

  return useMemo(
    () => ({
      release: () => releaseSource(sourceId),
    }),
    [releaseSource, sourceId]
  );
}

/**
 * Blocks in-app navigations when any registered source is dirty.
 * Uses a declarative modal tied to blocker.state — never an async confirm race.
 */
export const UnsavedChangesNavigationGuard: React.FC = () => {
  const {
    shouldBlockNavigation,
    allowNextNavigation,
    clearNavigationBypass,
    registerBlockerControls,
  } = useUnsavedChangesContext();
  const location = useLocation();
  const locationKeyRef = useRef(`${location.pathname}${location.search}`);

  useEffect(() => {
    const nextKey = `${location.pathname}${location.search}`;
    if (locationKeyRef.current !== nextKey) {
      locationKeyRef.current = nextKey;
      clearNavigationBypass();
    }
  }, [clearNavigationBypass, location.pathname, location.search]);

  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (!shouldBlockNavigation()) return false;
    return (
      currentLocation.pathname !== nextLocation.pathname ||
      currentLocation.search !== nextLocation.search
    );
  });

  useEffect(() => {
    registerBlockerControls({
      getState: () => blocker.state,
      reset: () => {
        if (blocker.state === 'blocked') blocker.reset?.();
      },
      proceed: () => {
        if (blocker.state === 'blocked') blocker.proceed?.();
      },
    });
    return () => registerBlockerControls(null);
  }, [blocker, registerBlockerControls]);

  const blocked = blocker.state === 'blocked';

  return (
    <ConfirmationModal
      open={blocked}
      title={UNSAVED_CHANGES_CONFIRM.title}
      message={UNSAVED_CHANGES_CONFIRM.message}
      confirmLabel={UNSAVED_CHANGES_CONFIRM.confirmLabel}
      cancelLabel={UNSAVED_CHANGES_CONFIRM.cancelLabel}
      variant={UNSAVED_CHANGES_CONFIRM.variant}
      onConfirm={() => {
        allowNextNavigation();
        if (blocker.state === 'blocked') {
          blocker.proceed?.();
        }
      }}
      onCancel={() => {
        if (blocker.state === 'blocked') {
          blocker.reset?.();
        }
      }}
    />
  );
};

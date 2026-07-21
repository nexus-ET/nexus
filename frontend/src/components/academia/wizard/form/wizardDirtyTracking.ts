import { useRef, useCallback, useEffect } from 'react';

const VOLATILE_DRAFT_KEYS = new Set(['local_id']);

function normalizeSnapshotValue(value: unknown): unknown {
  if (value === undefined) return null;
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map(normalizeSnapshotValue);
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const next: Record<string, unknown> = {};
  for (const key of keys) {
    if (VOLATILE_DRAFT_KEYS.has(key)) continue;
    next[key] = normalizeSnapshotValue(record[key]);
  }
  return next;
}

/** Stable JSON for dirty comparisons (sorted keys, no volatile draft ids). */
export function serializeWizardSnapshot(value: unknown): string {
  return JSON.stringify(normalizeSnapshotValue(value));
}

/** Drop fields that change on every empty-draft factory call (e.g. random local_id). */
export function stripVolatileDraftFields<T extends Record<string, unknown>>(value: T): T {
  const next = { ...value };
  for (const key of VOLATILE_DRAFT_KEYS) {
    delete next[key];
  }
  return next as T;
}

export function isWizardListDraftEmpty<T extends Record<string, unknown>>(
  draft: T,
  emptyTemplate: T
): boolean {
  return (
    serializeWizardSnapshot(stripVolatileDraftFields(draft)) ===
    serializeWizardSnapshot(stripVolatileDraftFields(emptyTemplate))
  );
}

export function getWizardListStepSnapshot<TDraft extends Record<string, unknown>, TItem>(
  items: TItem[],
  toPayload: (item: TItem) => unknown,
  options: {
    editingIndex: number | null;
    getDraft: () => TDraft;
    emptyDraftTemplate: TDraft;
    draftToSnapshot?: (draft: TDraft) => unknown;
  }
) {
  const { editingIndex, getDraft, emptyDraftTemplate, draftToSnapshot } = options;
  const draft = getDraft();
  const includeDraft =
    editingIndex !== null || !isWizardListDraftEmpty(draft, emptyDraftTemplate);

  const snapshot: {
    items: unknown[];
    draft?: unknown;
    editingIndex?: number | null;
  } = {
    items: items.map(toPayload),
  };

  if (includeDraft) {
    snapshot.editingIndex = editingIndex;
    snapshot.draft = draftToSnapshot
      ? draftToSnapshot(draft)
      : stripVolatileDraftFields(draft);
  }

  return snapshot;
}

export function useWizardStepSnapshot<T>(getSnapshotValue: () => T) {
  const savedRef = useRef<string>('');
  const getSnapshotRef = useRef(getSnapshotValue);
  getSnapshotRef.current = getSnapshotValue;

  const markClean = useCallback(() => {
    savedRef.current = serializeWizardSnapshot(getSnapshotRef.current());
  }, []);

  // Establish a clean baseline once the step mounts so Back/Cancel can detect edits.
  useEffect(() => {
    if (!savedRef.current) {
      savedRef.current = serializeWizardSnapshot(getSnapshotRef.current());
    }
  }, []);

  const isDirty = useCallback(() => {
    if (!savedRef.current) return false;
    return serializeWizardSnapshot(getSnapshotRef.current()) !== savedRef.current;
  }, []);

  return { markClean, isDirty, savedRef };
}

/** Blur the focused control so deferred field commits (e.g. phone) run before validation. */
export async function flushFocusedFormControl(): Promise<void> {
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }
  await new Promise<void>(resolve => {
    requestAnimationFrame(() => resolve());
  });
}

/**
 * Reset local step state when server/default props change — not when dirty snapshot changes.
 * Including markClean in effect deps causes add-to-list to immediately wipe the new row.
 *
 * Return `false` from `resetFromDefaults` to skip the follow-up markClean (e.g. when the
 * parent draft echoed a local edit and the step intentionally skipped resetting).
 */
export function useWizardListStepDefaultsSync(
  defaults: unknown,
  resetFromDefaults: () => boolean | void,
  markClean: () => void
): void {
  const resetRef = useRef(resetFromDefaults);
  const markCleanRef = useRef(markClean);
  resetRef.current = resetFromDefaults;
  markCleanRef.current = markClean;
  const lastKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const key = serializeWizardSnapshot(defaults);
    if (lastKeyRef.current === key) return;
    lastKeyRef.current = key;
    const applied = resetRef.current();
    if (applied === false) return;
    const frameId = requestAnimationFrame(() => {
      markCleanRef.current();
    });
    return () => cancelAnimationFrame(frameId);
  }, [defaults]);
}

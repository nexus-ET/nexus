/** Cross-tab sync for candidate test scores (Aspirations ↔ Test Scores). */

export const TEST_SCORES_CHANGED_EVENT = 'nexus:test-scores-changed';

export type TestScoresChangedDetail = {
  bookingId: number;
  source?: 'aspirations' | 'test-scores-tab' | string;
};

export function emitTestScoresChanged(detail: TestScoresChangedDetail) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<TestScoresChangedDetail>(TEST_SCORES_CHANGED_EVENT, { detail })
  );
}

export function subscribeTestScoresChanged(
  bookingId: number,
  handler: (detail: TestScoresChangedDetail) => void
) {
  const listener = (event: Event) => {
    const custom = event as CustomEvent<TestScoresChangedDetail>;
    if (custom.detail?.bookingId !== bookingId) return;
    handler(custom.detail);
  };
  window.addEventListener(TEST_SCORES_CHANGED_EVENT, listener);
  return () => window.removeEventListener(TEST_SCORES_CHANGED_EVENT, listener);
}

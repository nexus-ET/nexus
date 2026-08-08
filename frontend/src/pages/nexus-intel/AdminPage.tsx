import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react';
import {
  useApproveScrapeReview,
  useApproveScrapeReviewsBulk,
  useIntelScrapeReviews,
  useIntelScraperConfigs,
  useRunIntelScraper,
  useUpdateScraperInterval,
} from '../../hooks/useNexusIntel';
import { intelCountryLabel, type IntelScrapeRunResult } from '../../types/nexusIntel';

type FlashTone = 'success' | 'info' | 'warning' | 'error';

interface FlashMessage {
  tone: FlashTone;
  text: string;
}

const FLASH_STYLES: Record<FlashTone, string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  info: 'border-accent/30 bg-accent/10 text-text-main',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  error: 'border-alert/30 bg-alert/10 text-alert',
};

const AdminPage: React.FC = () => {
  const configsQuery = useIntelScraperConfigs(true);
  const reviewsQuery = useIntelScrapeReviews(true);
  const runScraper = useRunIntelScraper();
  const updateInterval = useUpdateScraperInterval();
  const approveReview = useApproveScrapeReview();
  const approveBulk = useApproveScrapeReviewsBulk();
  const [draftHours, setDraftHours] = useState<Record<string, string>>({});
  const [selectedReviewIds, setSelectedReviewIds] = useState<Set<string>>(new Set());
  const [selectedScraperIds, setSelectedScraperIds] = useState<Set<string>>(new Set());
  const [runningScraperIds, setRunningScraperIds] = useState<Set<string>>(new Set());
  const [batchInProgress, setBatchInProgress] = useState(false);
  const [flash, setFlash] = useState<FlashMessage | null>(null);

  const configs = configsQuery.data || [];
  const reviews = reviewsQuery.data || [];
  const scraperIds = useMemo(() => configs.map(config => config.id), [configs]);
  const reviewIds = useMemo(() => reviews.map(review => review.id), [reviews]);
  const anyScraperRunning = runningScraperIds.size > 0 || batchInProgress;

  useEffect(() => {
    setSelectedScraperIds(prev => {
      const next = new Set<string>();
      for (const id of prev) {
        if (scraperIds.includes(id)) next.add(id);
      }
      return next;
    });
  }, [scraperIds]);

  useEffect(() => {
    setSelectedReviewIds(prev => {
      const next = new Set<string>();
      for (const id of prev) {
        if (reviewIds.includes(id)) next.add(id);
      }
      return next;
    });
  }, [reviewIds]);

  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(null), 8000);
    return () => window.clearTimeout(timer);
  }, [flash]);

  const showFlash = (tone: FlashTone, text: string) => setFlash({ tone, text });

  const handleRunResult = (result: {
    ran: number;
    reviews_created: number;
    unchanged?: number;
    errors?: number;
  }) => {
    const parts = [
      `Ran ${result.ran}`,
      `created ${result.reviews_created} review(s)`,
      `${result.unchanged ?? 0} unchanged`,
      `${result.errors ?? 0} error(s)`,
    ];
    const text = `${parts[0]} scraper(s): ${parts.slice(1).join(', ')}.`;
    const tone =
      (result.errors ?? 0) > 0
        ? 'warning'
        : result.reviews_created > 0
          ? 'success'
          : 'info';
    showFlash(tone, text);
  };

  /** Scrapes run one-by-one on the server — only mark the active ID as RUNNING. */
  const runScrapersSequentially = async (ids: string[]) => {
    const uniqueIds = [...new Set(ids)].filter(Boolean);
    if (!uniqueIds.length || batchInProgress) return;

    setBatchInProgress(true);
    const totals: IntelScrapeRunResult = {
      ran: 0,
      reviews_created: 0,
      unchanged: 0,
      errors: 0,
    };

    try {
      for (const id of uniqueIds) {
        setRunningScraperIds(new Set([id]));
        try {
          const result = await runScraper.mutateAsync(id);
          totals.ran += result.ran ?? 1;
          totals.reviews_created += result.reviews_created ?? 0;
          totals.unchanged += result.unchanged ?? 0;
          totals.errors += result.errors ?? 0;
        } catch (error) {
          totals.ran += 1;
          totals.errors += 1;
          showFlash(
            'error',
            error instanceof Error
              ? error.message
              : 'A scraper run failed; continuing with the next.'
          );
        }
      }
      handleRunResult(totals);
    } finally {
      setRunningScraperIds(new Set());
      setBatchInProgress(false);
    }
  };

  const allScrapersSelected =
    scraperIds.length > 0 && scraperIds.every(id => selectedScraperIds.has(id));
  const someScrapersSelected = selectedScraperIds.size > 0 && !allScrapersSelected;
  const selectedScraperCount = selectedScraperIds.size;

  const allReviewsSelected =
    reviewIds.length > 0 && reviewIds.every(id => selectedReviewIds.has(id));
  const someReviewsSelected = selectedReviewIds.size > 0 && !allReviewsSelected;
  const selectedReviewCount = selectedReviewIds.size;
  const approving = approveReview.isPending || approveBulk.isPending;

  const toggleAllScrapers = () => {
    if (allScrapersSelected) {
      setSelectedScraperIds(new Set());
      return;
    }
    setSelectedScraperIds(new Set(scraperIds));
  };

  const toggleScraper = (id: string) => {
    setSelectedScraperIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllReviews = () => {
    if (allReviewsSelected) {
      setSelectedReviewIds(new Set());
      return;
    }
    setSelectedReviewIds(new Set(reviewIds));
  };

  const toggleReview = (id: string) => {
    setSelectedReviewIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleRunSelectedScrapers = () => {
    if (!selectedScraperCount || batchInProgress) return;
    void runScrapersSequentially(Array.from(selectedScraperIds));
  };

  const handleRunAllScrapers = () => {
    if (!scraperIds.length || batchInProgress) return;
    void runScrapersSequentially(scraperIds);
  };

  const handleRunOneScraper = (configId: string) => {
    if (batchInProgress || runningScraperIds.has(configId)) return;
    void runScrapersSequentially([configId]);
  };

  const handleBulkApprove = () => {
    if (!selectedReviewCount) return;
    const ids = Array.from(selectedReviewIds);
    approveBulk.mutate(ids, {
      onSuccess: result => {
        setSelectedReviewIds(new Set());
        if (!result.approved) {
          showFlash(
            'warning',
            result.skipped
              ? `No reviews were approved (${result.skipped} skipped). They may already be processed — refresh and try again.`
              : 'No reviews were approved. Refresh and try again.'
          );
          return;
        }
        showFlash(
          'success',
          `Approved & applied ${result.approved} review(s)${
            result.skipped ? ` (${result.skipped} skipped)` : ''
          }.`
        );
      },
      onError: error => {
        showFlash('error', error instanceof Error ? error.message : 'Bulk approve failed.');
      },
    });
  };

  const FlashIcon =
    flash?.tone === 'success'
      ? CheckCircle2
      : flash?.tone === 'warning'
        ? AlertTriangle
        : flash?.tone === 'error'
          ? AlertTriangle
          : Info;

  return (
    <div className="space-y-4">
      {flash ? (
        <div
          role="status"
          className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${FLASH_STYLES[flash.tone]}`}
        >
          <FlashIcon size={16} className="mt-0.5 shrink-0" />
          <p className="min-w-0 flex-1 font-medium">{flash.text}</p>
          <button
            type="button"
            onClick={() => setFlash(null)}
            className="rounded-md p-0.5 opacity-70 transition-opacity hover:opacity-100"
            aria-label="Dismiss message"
          >
            <X size={14} />
          </button>
        </div>
      ) : null}

      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-text-main">Regulatory Scraper Config</h2>
            <p className="text-sm text-text-muted">
              Live HTTP fetch with content hashing. Sources run one at a time — Status shows
              RUNNING only for the active fetch. Approving applies the snapshot (and refreshes
              linked glossary explanations when matched).
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {configs.length > 0 ? (
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-text-main">
                <input
                  type="checkbox"
                  checked={allScrapersSelected}
                  ref={el => {
                    if (el) el.indeterminate = someScrapersSelected;
                  }}
                  onChange={toggleAllScrapers}
                  className="h-4 w-4"
                />
                Select all
              </label>
            ) : null}
            <button
              type="button"
              disabled={!selectedScraperCount || anyScraperRunning}
              onClick={handleRunSelectedScrapers}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-card px-4 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
            >
              {batchInProgress ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Processing…
                </>
              ) : (
                `Run selected${selectedScraperCount ? ` (${selectedScraperCount})` : ''}`
              )}
            </button>
            <button
              type="button"
              disabled={!scraperIds.length || anyScraperRunning}
              onClick={handleRunAllScrapers}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {batchInProgress ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Processing…
                </>
              ) : (
                'Run all scrapers'
              )}
            </button>
          </div>
        </div>
        <div className="headless-scroll-viewport overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-text-muted">
              <tr>
                <th className="py-2 pr-3 w-10">
                  <span className="sr-only">Select</span>
                </th>
                <th className="py-2 pr-3">Source</th>
                <th className="py-2 pr-3">Country</th>
                <th className="py-2 pr-3">Interval (hours)</th>
                <th className="py-2 pr-3">Last fetch</th>
                <th className="py-2 pr-3">HTTP</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {configs.map(config => {
                const isRunning = runningScraperIds.has(config.id);
                return (
                <tr
                  key={config.id}
                  className={`border-t border-border-subtle ${isRunning ? 'bg-accent/5' : ''}`}
                >
                  <td className="py-2 pr-3 align-middle">
                    <input
                      type="checkbox"
                      checked={selectedScraperIds.has(config.id)}
                      onChange={() => toggleScraper(config.id)}
                      className="h-4 w-4"
                      aria-label={`Select scraper ${config.source_name}`}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <div className="font-semibold text-text-main">{config.source_name}</div>
                    <a
                      href={config.target_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-accent hover:underline break-all"
                    >
                      {config.target_url}
                    </a>
                    {config.linked_glossary_term ? (
                      <div className="mt-1 text-xs text-text-muted">
                        Linked: {config.linked_glossary_term}
                      </div>
                    ) : (
                      <div className="mt-1 text-xs text-text-muted">No glossary link</div>
                    )}
                  </td>
                  <td className="py-2 pr-3">{intelCountryLabel(config.country_code)}</td>
                  <td className="py-2 pr-3">
                    <input
                      type="number"
                      min={1}
                      className="w-24 rounded-lg border border-border-subtle bg-surface-bg px-2 py-1"
                      value={draftHours[config.id] ?? String(config.scrape_interval_hours)}
                      onChange={e =>
                        setDraftHours(prev => ({ ...prev, [config.id]: e.target.value }))
                      }
                    />
                  </td>
                  <td className="py-2 pr-3 text-text-muted">
                    {config.last_fetched_at
                      ? new Date(config.last_fetched_at).toLocaleString()
                      : config.last_run_at
                        ? new Date(config.last_run_at).toLocaleString()
                        : 'Never'}
                  </td>
                  <td className="py-2 pr-3 text-text-muted">
                    {config.last_http_status ?? '—'}
                  </td>
                  <td className="py-2 pr-3">
                    {isRunning ? (
                      <div className="inline-flex items-center gap-1.5 font-semibold text-accent">
                        <Loader2 size={14} className="animate-spin" />
                        RUNNING
                      </div>
                    ) : (
                      <div>{config.status}</div>
                    )}
                    {!isRunning && config.last_error ? (
                      <div
                        className="mt-1 max-w-[14rem] text-xs text-red-600 line-clamp-2"
                        title={config.last_error}
                      >
                        {config.last_error}
                      </div>
                    ) : null}
                    {!isRunning && !config.last_error && config.last_content_hash ? (
                      <div className="mt-1 text-xs text-text-muted font-mono">
                        {config.last_content_hash.slice(0, 10)}…
                      </div>
                    ) : null}
                  </td>
                  <td className="py-2">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-border-subtle px-2 py-1 text-xs font-semibold"
                        onClick={() =>
                          updateInterval.mutate({
                            configId: config.id,
                            scrape_interval_hours: Number(
                              draftHours[config.id] ?? config.scrape_interval_hours
                            ),
                          })
                        }
                      >
                        Save interval
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-border-subtle px-2 py-1 text-xs font-semibold disabled:opacity-60"
                        disabled={anyScraperRunning}
                        aria-busy={isRunning}
                        onClick={() => handleRunOneScraper(config.id)}
                      >
                        Run
                      </button>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-text-main">Change Reviews (NEEDS_REVIEW)</h2>
            <p className="text-sm text-text-muted">
              First baselines and content diffs land here. Approving stores the snapshot on the
              scraper and refreshes a linked glossary explanation when one is matched.
            </p>
          </div>
          {reviews.length > 0 ? (
            <div className="flex flex-wrap items-center gap-3">
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-text-main">
                <input
                  type="checkbox"
                  checked={allReviewsSelected}
                  ref={el => {
                    if (el) el.indeterminate = someReviewsSelected;
                  }}
                  onChange={toggleAllReviews}
                  className="h-4 w-4"
                />
                Select all
              </label>
              <button
                type="button"
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                disabled={!selectedReviewCount || approving}
                onClick={handleBulkApprove}
              >
                {approveBulk.isPending
                  ? 'Approving…'
                  : `Approve & apply selected${selectedReviewCount ? ` (${selectedReviewCount})` : ''}`}
              </button>
            </div>
          ) : null}
        </div>

        {!reviews.length ? (
          <p className="text-sm text-text-muted">No pending reviews.</p>
        ) : (
          <ul className="space-y-3">
            {reviews.map(review => {
              const checked = selectedReviewIds.has(review.id);
              return (
                <li
                  key={review.id}
                  className="rounded-xl border border-border-subtle bg-surface-bg p-3 text-sm"
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleReview(review.id)}
                      className="mt-1 h-4 w-4 shrink-0"
                      aria-label={`Select review from ${review.source_name || review.scraper_config_id}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-text-main">
                        {review.source_name || review.scraper_config_id}
                      </div>
                      <p className="mt-1 text-text-muted">{review.diff_summary}</p>
                      <div className="mt-2 grid gap-2 md:grid-cols-2">
                        <pre className="headless-scroll-viewport overflow-x-auto rounded-lg bg-card p-2 text-xs text-text-muted">
                          {review.old_text || '(no previous text)'}
                        </pre>
                        <pre className="headless-scroll-viewport overflow-x-auto rounded-lg bg-card p-2 text-xs text-text-muted">
                          {review.new_text}
                        </pre>
                      </div>
                      <button
                        type="button"
                        className="mt-3 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                        disabled={approving}
                        onClick={() =>
                          approveReview.mutate(review.id, {
                            onSuccess: () => {
                              setSelectedReviewIds(prev => {
                                const next = new Set(prev);
                                next.delete(review.id);
                                return next;
                              });
                              showFlash('success', 'Review approved & applied.');
                            },
                            onError: error => {
                              showFlash(
                                'error',
                                error instanceof Error ? error.message : 'Approve failed.'
                              );
                            },
                          })
                        }
                      >
                        Approve & apply
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
};

export default AdminPage;

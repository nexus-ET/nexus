import { useEffect, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { ProspectListItem } from '../../types/prospect';
import { formatProspectDate, platformBadgeStyle } from '../../utils/prospectMessages';
import HeadlessScrollArea, {
  type HeadlessScrollAreaHandle,
} from '../HeadlessScrollArea';
import QueuePaginationControls from '../QueuePaginationControls';
import {
  emptyState,
  listItem,
  listItemActive,
  listItemBadges,
  listItemBadge,
  listItemMeta,
  listItemName,
  listItemStage,
  listItemTop,
  listPagination,
  listPaginationTop,
  listPanel,
  listScroll,
  pageBtn,
  pageMeta,
} from './prospectsLayout';

const ROW_HEIGHT = 76;

type ProspectsListPanelProps = {
  items: ProspectListItem[];
  selectedLeadId: number | null;
  onSelect: (leadId: number) => void;
  isLoading: boolean;
  page: number;
  totalPages: number;
  hasMorePages: boolean;
  onPageChange: (page: number) => void;
  filteredTotal?: number;
  errorMessage?: string | null;
  scrollStorageKey: string;
  hidden?: boolean;
  /** Below lg, hide the list once a lead is open so detail is the only pane. */
  stackHidden?: boolean;
};

function formatStageLabel(stage?: string): string {
  const normalized = (stage || '').toUpperCase().replace(/-/g, '_');
  if (normalized.includes('HANDOFF')) return 'Handoff';
  if (normalized.includes('ARCHIVE')) return 'Archive';
  if (normalized === 'AI_ACTIVE') return 'AI Active';
  return stage || 'Unknown';
}

export default function ProspectsListPanel({
  items,
  selectedLeadId,
  onSelect,
  isLoading,
  page,
  totalPages,
  hasMorePages,
  onPageChange,
  filteredTotal = 0,
  errorMessage,
  scrollStorageKey,
  hidden = false,
  stackHidden = false,
}: ProspectsListPanelProps) {
  const scrollAreaRef = useRef<HeadlessScrollAreaHandle | null>(null);
  const restoredRef = useRef(false);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollAreaRef.current?.getViewport() ?? null,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();

  useEffect(() => {
    restoredRef.current = false;
  }, [scrollStorageKey]);

  useEffect(() => {
    const viewport = scrollAreaRef.current?.getViewport();
    if (restoredRef.current || isLoading || !viewport) return;
    const saved = sessionStorage.getItem(scrollStorageKey);
    if (saved) {
      viewport.scrollTop = Number(saved);
    }
    restoredRef.current = true;
  }, [isLoading, items.length, scrollStorageKey]);

  useEffect(() => {
    const viewport = scrollAreaRef.current?.getViewport();
    if (!viewport) return;
    viewport.scrollTop = 0;
    sessionStorage.setItem(scrollStorageKey, '0');
  }, [page, scrollStorageKey]);

  const handleSelect = (leadId: number) => {
    const viewport = scrollAreaRef.current?.getViewport();
    if (viewport) {
      sessionStorage.setItem(scrollStorageKey, String(viewport.scrollTop));
    }
    onSelect(leadId);
  };

  const showPagination = !isLoading && !errorMessage && (filteredTotal > 0 || items.length > 0);

  return (
    <aside
      className={
        hidden ? 'hidden' : `${listPanel}${stackHidden ? ' max-lg:!hidden' : ''}`
      }
    >
      {showPagination ? (
        <QueuePaginationControls
          page={page}
          totalPages={totalPages}
          hasMorePages={hasMorePages}
          disabled={isLoading}
          onPageChange={onPageChange}
          className={`${listPagination} ${listPaginationTop}`}
          buttonClassName={pageBtn}
          metaClassName={pageMeta}
        />
      ) : null}

      <HeadlessScrollArea
        ref={scrollAreaRef}
        className={listScroll}
      >
        {errorMessage ? (
          <div className={emptyState}>{errorMessage}</div>
        ) : isLoading ? (
          <div className={emptyState}>Loading prospects...</div>
        ) : items.length === 0 ? (
          <div className={emptyState}>No prospects match your filters.</div>
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualItems.map(virtualRow => {
              const item = items[virtualRow.index];
              if (!item) return null;

              return (
                <div
                  key={virtualRow.key}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <button
                    type="button"
                    className={`${listItem}${item.id === selectedLeadId ? ` ${listItemActive}` : ''}`}
                    onClick={() => handleSelect(item.id)}
                  >
                    <div className={listItemTop}>
                      <span className={listItemName}>{item.full_name}</span>
                      <div className={listItemBadges}>
                        {item.platform_badge ? (
                          <span
                            className={listItemBadge}
                            style={platformBadgeStyle(item.platform_badge)}
                          >
                            {item.platform_badge}
                          </span>
                        ) : null}
                        <span className={listItemStage}>
                          {formatStageLabel(item.stage)}
                        </span>
                      </div>
                    </div>
                    <div className={listItemMeta}>
                      <span>{formatProspectDate(item.received_at)}</span>
                    </div>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </HeadlessScrollArea>
    </aside>
  );
}

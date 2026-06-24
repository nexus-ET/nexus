import { useEffect, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { ProspectListItem } from '../../types/prospect';
import { formatProspectDate, platformBadgeStyle } from '../../utils/prospectMessages';

const ROW_HEIGHT = 76;

type ProspectsListPanelProps = {
  items: ProspectListItem[];
  selectedLeadId: number | null;
  onSelect: (leadId: number) => void;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  errorMessage?: string | null;
  scrollStorageKey: string;
  hidden?: boolean;
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
  isFetchingNextPage,
  hasNextPage,
  fetchNextPage,
  errorMessage,
  scrollStorageKey,
  hidden = false,
}: ProspectsListPanelProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const restoredRef = useRef(false);

  const rowCount = hasNextPage ? items.length + 1 : items.length;

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  const virtualItems = virtualizer.getVirtualItems();

  useEffect(() => {
    restoredRef.current = false;
  }, [scrollStorageKey]);

  useEffect(() => {
    if (restoredRef.current || isLoading || !parentRef.current) return;
    const saved = sessionStorage.getItem(scrollStorageKey);
    if (saved) {
      parentRef.current.scrollTop = Number(saved);
    }
    restoredRef.current = true;
  }, [isLoading, items.length, scrollStorageKey]);

  useEffect(() => {
    const lastItem = virtualItems.at(-1);
    if (!lastItem) return;
    if (lastItem.index >= items.length - 1 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [virtualItems, items.length, hasNextPage, isFetchingNextPage, fetchNextPage]);

  const handleSelect = (leadId: number) => {
    if (parentRef.current) {
      sessionStorage.setItem(scrollStorageKey, String(parentRef.current.scrollTop));
    }
    onSelect(leadId);
  };

  return (
    <aside className={`prospects-list-panel${hidden ? ' prospects-list-panel--hidden' : ''}`}>
      <div ref={parentRef} className="prospects-list-panel__scroll custom-scroll-region">
        {errorMessage ? (
          <div className="prospects-empty">{errorMessage}</div>
        ) : isLoading ? (
          <div className="prospects-empty">Loading prospects...</div>
        ) : items.length === 0 ? (
          <div className="prospects-empty">No prospects match your filters.</div>
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualItems.map(virtualRow => {
              const isLoaderRow = virtualRow.index >= items.length;
              const item = items[virtualRow.index];

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
                  {isLoaderRow ? (
                    <div className="prospects-list-panel__sentinel">
                      {isFetchingNextPage ? 'Loading more...' : 'Scroll for more'}
                    </div>
                  ) : (
                    <button
                      type="button"
                      className={`prospects-list-item${item.id === selectedLeadId ? ' is-active' : ''}`}
                      onClick={() => handleSelect(item.id)}
                    >
                      <div className="prospects-list-item__top">
                        <span className="prospects-list-item__name">{item.full_name}</span>
                        <div className="prospects-list-item__badges">
                          {item.platform_badge ? (
                            <span
                              className="prospects-list-item__badge"
                              style={platformBadgeStyle(item.platform_badge)}
                            >
                              {item.platform_badge}
                            </span>
                          ) : null}
                          <span className="prospects-list-item__stage">
                            {formatStageLabel(item.stage)}
                          </span>
                        </div>
                      </div>
                      <div className="prospects-list-item__meta">
                        <span>{formatProspectDate(item.received_at)}</span>
                      </div>
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}

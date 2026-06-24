import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import ProspectsToolbar from '../components/prospects/ProspectsToolbar';
import ProspectsListPanel from '../components/prospects/ProspectsListPanel';
import ProspectDetailPanel from '../components/prospects/ProspectDetailPanel';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import {
  useProspectDetail,
  useProspectsInfinite,
  useProspectsSummary,
} from '../hooks/useProspects';
import {
  buildProspectsPath,
  parseLeadIdParam,
  prospectsScrollStorageKey,
  readDetailTab,
  readFilters,
  type ProspectDetailTab,
} from '../utils/prospectsUrl';
import './ProspectsPage.css';

function useIsCompactLayout(breakpoint = 900): boolean {
  const [isCompact, setIsCompact] = useState(
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  );

  useEffect(() => {
    const onResize = () => setIsCompact(window.innerWidth < breakpoint);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [breakpoint]);

  return isCompact;
}

export default function ProspectsPage() {
  const navigate = useNavigate();
  const { leadId: leadIdParam } = useParams<{ leadId?: string }>();
  const [searchParams] = useSearchParams();
  const isCompact = useIsCompactLayout();
  const [manualFocus, setManualFocus] = useState(false);

  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const debouncedFilters = useDebouncedValue(filters, 350);
  const activeTab = readDetailTab(searchParams);
  const selectedLeadId = parseLeadIdParam(leadIdParam);

  const scrollStorageKey = prospectsScrollStorageKey(filters);
  const focusMode = Boolean(selectedLeadId && (isCompact || manualFocus));

  useEffect(() => {
    const legacyLeadId = searchParams.get('leadId');
    if (legacyLeadId && !leadIdParam) {
      navigate(buildProspectsPath(parseLeadIdParam(legacyLeadId), filters, activeTab), {
        replace: true,
      });
    }
  }, [searchParams, leadIdParam, filters, activeTab, navigate]);

  const summaryQuery = useProspectsSummary();
  const listQuery = useProspectsInfinite(debouncedFilters);
  const detailQuery = useProspectDetail(selectedLeadId);

  const items = useMemo(
    () => listQuery.data?.pages.flatMap(page => page.items) ?? [],
    [listQuery.data]
  );
  const filteredTotal = listQuery.data?.pages[0]?.filtered_total ?? 0;

  const updateFilters = (next: Partial<typeof filters>) => {
    const merged = { ...filters, ...next };
    navigate(buildProspectsPath(selectedLeadId, merged, activeTab), { replace: true });
  };

  const handleSelectLead = (leadId: number) => {
    if (isCompact) setManualFocus(true);
    navigate(buildProspectsPath(leadId, filters, activeTab), { replace: true });
  };

  const handleBackToList = () => {
    setManualFocus(false);
    navigate(buildProspectsPath(null, filters, activeTab), { replace: true });
  };

  const handleTabChange = (tab: ProspectDetailTab) => {
    if (!selectedLeadId) return;
    navigate(buildProspectsPath(selectedLeadId, filters, tab), { replace: true });
  };

  const handleToggleFocus = () => {
    setManualFocus(current => !current);
  };

  const listError =
    listQuery.error instanceof Error
      ? listQuery.error.message
      : listQuery.isError
        ? 'Failed to load prospects.'
        : null;

  return (
    <div className={`prospects-page${focusMode ? ' prospects-page--focus' : ''}`}>
      <ProspectsToolbar
        filters={filters}
        onChange={updateFilters}
        filteredTotal={filteredTotal}
      />

      <div className="prospects-page__panels">
        <ProspectsListPanel
          items={items}
          selectedLeadId={selectedLeadId}
          onSelect={handleSelectLead}
          isLoading={listQuery.isLoading}
          isFetchingNextPage={listQuery.isFetchingNextPage}
          hasNextPage={Boolean(listQuery.hasNextPage)}
          fetchNextPage={() => listQuery.fetchNextPage()}
          errorMessage={listError}
          scrollStorageKey={scrollStorageKey}
          hidden={focusMode}
        />

        <ProspectDetailPanel
          leadId={selectedLeadId}
          detail={detailQuery.data}
          isLoading={detailQuery.isLoading}
          summary={summaryQuery.data}
          activeTab={activeTab}
          onTabChange={handleTabChange}
          onBack={handleBackToList}
          showBackButton={focusMode}
          isFocusMode={focusMode}
          onToggleFocus={handleToggleFocus}
        />
      </div>
    </div>
  );
}

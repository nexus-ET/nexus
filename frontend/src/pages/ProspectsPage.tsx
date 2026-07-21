import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import ProspectsToolbar from '../components/prospects/ProspectsToolbar';
import ProspectsListPanel from '../components/prospects/ProspectsListPanel';
import ProspectDetailPanel from '../components/prospects/ProspectDetailPanel';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import {
  useProspectDetail,
  useProspectsInfinite,
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

export type ProspectsPageProps = {
  pageTitle?: string;
  statusCategory?: string;
  basePath?: string;
};

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

export default function ProspectsPage({
  pageTitle = 'All Prospects',
  statusCategory = '',
  basePath = '/prospects',
}: ProspectsPageProps) {
  const navigate = useNavigate();
  const { leadId: leadIdParam } = useParams<{ leadId?: string }>();
  const [searchParams] = useSearchParams();
  const isCompact = useIsCompactLayout();
  const [manualFocus, setManualFocus] = useState(false);

  const filters = useMemo(
    () => readFilters(searchParams, statusCategory),
    [searchParams, statusCategory]
  );
  const debouncedFilters = useDebouncedValue(filters, 350);
  const activeTab = readDetailTab(searchParams);
  const selectedLeadId = parseLeadIdParam(leadIdParam);

  const scrollStorageKey = prospectsScrollStorageKey(filters, basePath);
  const focusMode = Boolean(selectedLeadId && (isCompact || manualFocus));

  useEffect(() => {
    const legacyLeadId = searchParams.get('leadId');
    if (legacyLeadId && !leadIdParam) {
      navigate(buildProspectsPath(parseLeadIdParam(legacyLeadId), filters, activeTab, basePath), {
        replace: true,
      });
    }
  }, [searchParams, leadIdParam, filters, activeTab, navigate, basePath]);

  const listQuery = useProspectsInfinite(debouncedFilters);
  const detailQuery = useProspectDetail(selectedLeadId);

  const items = useMemo(
    () => listQuery.data?.pages.flatMap(page => page.items) ?? [],
    [listQuery.data]
  );
  const filteredTotal = listQuery.data?.pages[0]?.filtered_total ?? 0;

  const pulseLeads = useMemo(
    () =>
      items.map(item => ({
        id: item.id,
        name: item.name || item.full_name || `Lead #${item.id}`,
        email: item.email,
        phone: item.phone ?? undefined,
        phone_number: item.phone_number ?? undefined,
        preferred_country: item.preferred_country,
        preferred_course: item.preferred_course,
        target_program: item.target_program,
        target_degree: item.target_degree,
        target_major: item.target_major,
        current_location: item.current_location,
        study_interest_complete: item.study_interest_complete ?? undefined,
        intake_step: item.intake_step ?? undefined,
        intake_step_label: item.intake_step_label ?? undefined,
        intake_complete: item.intake_complete ?? undefined,
        status: item.status || item.stage,
        updated_at: item.updated_at || item.received_at || undefined,
        latest_interaction_time: item.latest_interaction_time || item.updated_at || item.received_at || undefined,
      })),
    [items]
  );

  const updateFilters = (next: Partial<typeof filters>) => {
    const merged = { ...filters, ...next, category: statusCategory || next.category || filters.category };
    navigate(buildProspectsPath(selectedLeadId, merged, activeTab, basePath), { replace: true });
  };

  const handleSelectLead = (leadId: number) => {
    if (isCompact) setManualFocus(true);
    navigate(buildProspectsPath(leadId, filters, activeTab, basePath), { replace: true });
  };

  const handleBackToList = () => {
    setManualFocus(false);
    navigate(buildProspectsPath(null, filters, activeTab, basePath), { replace: true });
  };

  const handleTabChange = (tab: ProspectDetailTab) => {
    if (!selectedLeadId) return;
    navigate(buildProspectsPath(selectedLeadId, filters, tab, basePath), { replace: true });
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
        title={pageTitle}
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
          pulseLeads={pulseLeads}
          isPulseLoading={listQuery.isLoading}
          onSelectPulseLead={handleSelectLead}
          activeTab={activeTab}
          onTabChange={handleTabChange}
          onBack={handleBackToList}
          showBackButton={focusMode}
          isFocusMode={focusMode}
          onToggleFocus={handleToggleFocus}
          studentProfileTabs={basePath === '/students/counselling'}
        />
      </div>
    </div>
  );
}

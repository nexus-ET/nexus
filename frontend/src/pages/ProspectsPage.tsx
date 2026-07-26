import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import ProspectsToolbar from '../components/prospects/ProspectsToolbar';
import ProspectsListPanel from '../components/prospects/ProspectsListPanel';
import ProspectDetailPanel from '../components/prospects/ProspectDetailPanel';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import {
  useProspectDetail,
  useProspectsPage,
} from '../hooks/useProspects';
import {
  buildProspectsPath,
  parseLeadIdParam,
  PROSPECTS_PAGE_SIZE_KEY,
  prospectsScrollStorageKey,
  readDetailTab,
  readFilters,
  type ProspectDetailTab,
} from '../utils/prospectsUrl';
import { isTablePageSize, storeTablePageSize } from '../utils/tablePageSize';
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

  const listQuery = useProspectsPage(debouncedFilters);
  const detailQuery = useProspectDetail(selectedLeadId);

  const items = listQuery.data?.items ?? [];
  const filteredTotal = listQuery.data?.filtered_total ?? 0;
  const hasMorePages = Boolean(listQuery.data?.has_more);
  const page = Math.max(1, filters.page || 1);
  const pageSize = filters.pageSize || 50;
  const totalPages = Math.max(1, Math.ceil(filteredTotal / pageSize) || 1);
  const rangeStart = filteredTotal === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, filteredTotal);
  const rangeLabel =
    filteredTotal > 0 ? `${rangeStart}–${rangeEnd}` : null;

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
        wants_consultation_call: item.wants_consultation_call ?? undefined,
        consultation_scheduled_at: item.consultation_scheduled_at ?? undefined,
        consultation_session_date: item.consultation_session_date ?? undefined,
        consultation_session_time: item.consultation_session_time ?? undefined,
        assigned_counsellor_name: item.assigned_counsellor_name ?? undefined,
        appointment_status: item.appointment_status ?? undefined,
        english_test_scores: item.english_test_scores ?? undefined,
        gre_score: item.gre_score ?? undefined,
        gmat_score: item.gmat_score ?? undefined,
        test_scores: item.test_scores ?? undefined,
        status: item.status || item.stage,
        updated_at: item.updated_at || item.received_at || undefined,
        // Do not fall back to updated_at/received_at — that made never-contacted
        // leads show up under "Recently replied".
        latest_interaction_time: item.latest_interaction_time || undefined,
        total_messages_received: item.total_messages_received ?? 0,
        unread_count: item.unread_count ?? 0,
        has_ai_messages: Boolean(item.has_ai_messages),
        has_messages: Boolean(item.has_messages),
      })),
    [items]
  );

  const updateFilters = (next: Partial<typeof filters>) => {
    const merged = { ...filters, ...next, category: statusCategory || next.category || filters.category };
    if (next.pageSize != null && isTablePageSize(next.pageSize)) {
      storeTablePageSize(PROSPECTS_PAGE_SIZE_KEY, next.pageSize);
    }
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
        rangeLabel={rangeLabel}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        title={pageTitle}
        page={page}
        totalPages={totalPages}
        hasMorePages={hasMorePages}
        isLoading={listQuery.isLoading}
      />

      <div className="prospects-page__panels">
        <ProspectsListPanel
          items={items}
          selectedLeadId={selectedLeadId}
          onSelect={handleSelectLead}
          isLoading={listQuery.isLoading}
          page={page}
          totalPages={totalPages}
          hasMorePages={hasMorePages}
          onPageChange={nextPage => updateFilters({ page: nextPage })}
          filteredTotal={filteredTotal}
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

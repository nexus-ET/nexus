import React from 'react';
import {
  CONTACT_STATUS_OPTIONS,
  DEFAULT_INTERACTION_DAYS,
  INTERACTION_DAYS_OPTIONS,
  LEAD_QUEUE_PAGE_SIZE_OPTIONS,
  type ContactStatusFilter,
  type InteractionDaysFilter,
  type LeadQueuePageSize,
} from '../utils/leadQueueFilters';

const filterStyles = {
  section: {
    padding: '12px',
    borderBottom: '1px solid #e2e8f0',
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  select: {
    width: '100%',
    boxSizing: 'border-box' as const,
    padding: '10px 12px',
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    color: '#0f172a',
    fontSize: '13px',
    outline: 'none',
    cursor: 'pointer',
  },
  searchInput: {
    width: '100%',
    boxSizing: 'border-box' as const,
    padding: '10px 12px',
    backgroundColor: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    color: '#0f172a',
    fontSize: '13px',
    outline: 'none',
  },
  searchHint: {
    margin: 0,
    fontSize: '11px',
    color: '#94a3b8',
    lineHeight: 1.4,
  },
  row: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
  },
  field: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '4px',
  },
  fieldLabel: {
    fontSize: '11px',
    fontWeight: 600,
    color: '#64748b',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  },
};

interface LeadQueueSidebarFiltersProps {
  interactionDays: InteractionDaysFilter;
  onInteractionDaysChange: (days: InteractionDaysFilter) => void;
  contactStatus: ContactStatusFilter;
  onContactStatusChange: (status: ContactStatusFilter) => void;
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  pageSize: LeadQueuePageSize;
  onPageSizeChange: (pageSize: LeadQueuePageSize) => void;
  searchDisabled?: boolean;
}

export default function LeadQueueSidebarFilters({
  interactionDays,
  onInteractionDaysChange,
  contactStatus,
  onContactStatusChange,
  searchQuery,
  onSearchQueryChange,
  pageSize,
  onPageSizeChange,
  searchDisabled = false,
}: LeadQueueSidebarFiltersProps) {
  const isSearching = searchQuery.trim().length > 0;

  return (
    <div style={filterStyles.section}>
      <div style={filterStyles.row}>
        <label style={filterStyles.field}>
          <span style={filterStyles.fieldLabel}>Activity</span>
          <select
            value={interactionDays}
            onChange={event =>
              onInteractionDaysChange(Number(event.target.value) as InteractionDaysFilter)
            }
            style={filterStyles.select}
            aria-label="Filter candidates by recent activity"
            disabled={isSearching}
          >
            {INTERACTION_DAYS_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label style={filterStyles.field}>
          <span style={filterStyles.fieldLabel}>Rows</span>
          <select
            value={pageSize}
            onChange={event =>
              onPageSizeChange(Number(event.target.value) as LeadQueuePageSize)
            }
            style={filterStyles.select}
            aria-label="Candidates shown per page in the sidebar"
          >
            {LEAD_QUEUE_PAGE_SIZE_OPTIONS.map(size => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label style={filterStyles.field}>
        <span style={filterStyles.fieldLabel}>Contact status</span>
        <select
          value={contactStatus}
          onChange={event =>
            onContactStatusChange(event.target.value as ContactStatusFilter)
          }
          style={filterStyles.select}
          aria-label="Filter by whether WhatsApp chat has started"
        >
          {CONTACT_STATUS_OPTIONS.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <input
        type="text"
        placeholder="Search candidates..."
        value={searchQuery}
        onChange={event => onSearchQueryChange(event.target.value)}
        style={filterStyles.searchInput}
        disabled={searchDisabled}
      />

      {isSearching ? (
        <p style={filterStyles.searchHint}>
          Searching all candidates — the activity filter is ignored while you search.
        </p>
      ) : interactionDays === DEFAULT_INTERACTION_DAYS ? (
        <p style={filterStyles.searchHint}>
          Showing candidates with activity in the last 5 days. Use Contact status to separate
          chats already started from people not contacted yet.
        </p>
      ) : (
        <p style={filterStyles.searchHint}>
          Use Rows and Previous/Next to browse pages. Contact status filters by whether a
          WhatsApp chat has started.
        </p>
      )}
    </div>
  );
}

import React from 'react';
import {
  DEFAULT_INTERACTION_DAYS,
  INTERACTION_DAYS_OPTIONS,
  type InteractionDaysFilter,
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
};

interface LeadQueueSidebarFiltersProps {
  interactionDays: InteractionDaysFilter;
  onInteractionDaysChange: (days: InteractionDaysFilter) => void;
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  searchDisabled?: boolean;
}

export default function LeadQueueSidebarFilters({
  interactionDays,
  onInteractionDaysChange,
  searchQuery,
  onSearchQueryChange,
  searchDisabled = false,
}: LeadQueueSidebarFiltersProps) {
  const isSearching = searchQuery.trim().length > 0;

  return (
    <div style={filterStyles.section}>
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
          Showing candidates with activity in the last 5 days.
        </p>
      ) : null}
    </div>
  );
}

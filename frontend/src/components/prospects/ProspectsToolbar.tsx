import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Search } from 'lucide-react';
import type { ProspectsFilters } from '../../types/prospect';
import {
  CONTACT_STATUS_OPTIONS,
  formatViewingRecordsLabel,
  type ContactStatusFilter,
} from '../../utils/leadQueueFilters';
import {
  TABLE_PAGE_SIZE_OPTIONS,
  type TablePageSize,
} from '../../utils/tablePageSize';
import QueuePaginationControls from '../QueuePaginationControls';

type ProspectsToolbarProps = {
  filters: ProspectsFilters;
  onChange: (next: Partial<ProspectsFilters>) => void;
  filteredTotal?: number;
  rangeLabel?: string | null;
  rangeStart?: number;
  rangeEnd?: number;
  title?: string;
  page?: number;
  totalPages?: number;
  hasMorePages?: boolean;
  isLoading?: boolean;
  showTitleRow?: boolean;
};

export default function ProspectsToolbar({
  filters,
  onChange,
  filteredTotal,
  rangeLabel,
  rangeStart = 0,
  rangeEnd = 0,
  title = 'All Prospects',
  page = 1,
  totalPages = 1,
  hasMorePages = false,
  isLoading = false,
  showTitleRow = true,
}: ProspectsToolbarProps) {
  const dateFromValue = filters.dateFrom ? new Date(filters.dateFrom) : null;
  const dateToValue = filters.dateTo ? new Date(filters.dateTo) : null;
  const total = filteredTotal ?? 0;
  const showPagination = !isLoading && total > 0;
  const viewingLabel = formatViewingRecordsLabel(rangeStart, rangeEnd, total);

  return (
    <div className="prospects-toolbar">
      {showTitleRow ? (
        <div className="prospects-toolbar__title-row">
          <div className="prospects-toolbar__title">
            <h2>{title}</h2>
            <p className="prospects-toolbar__viewing" title={viewingLabel}>
              {viewingLabel}
            </p>
            {typeof filteredTotal === 'number' ? (
              <span
                className="prospects-toolbar__count"
                title={
                  rangeLabel
                    ? `Showing ${rangeLabel} of ${filteredTotal} matching prospects`
                    : `${filteredTotal} matching prospects`
                }
              >
                {rangeLabel ? `${rangeLabel}/${filteredTotal}` : `${filteredTotal} matches`}
              </span>
            ) : null}
          </div>

          {showPagination ? (
            <QueuePaginationControls
              page={page}
              totalPages={totalPages}
              hasMorePages={hasMorePages}
              disabled={isLoading}
              onPageChange={nextPage => onChange({ page: nextPage })}
              className="prospects-toolbar__pagination"
              buttonClassName="prospects-list-panel__page-btn"
              metaClassName="prospects-list-panel__page-meta"
            />
          ) : null}
        </div>
      ) : null}

      <div className="prospects-toolbar__controls">
        <label className="prospects-toolbar__search">
          <Search size={16} />
          <input
            type="text"
            placeholder="Search name, email, phone..."
            value={filters.q}
            onChange={event => onChange({ q: event.target.value, page: 1 })}
          />
        </label>

        <label className="prospects-toolbar__field">
          <span>From</span>
          <DatePicker
            selected={dateFromValue}
            onChange={date =>
              onChange({
                dateFrom: date ? date.toISOString().slice(0, 10) : '',
                page: 1,
              })
            }
            dateFormat="yyyy-MM-dd"
            placeholderText="Start date"
            isClearable
            className="prospects-toolbar__date"
          />
        </label>

        <label className="prospects-toolbar__field">
          <span>To</span>
          <DatePicker
            selected={dateToValue}
            onChange={date =>
              onChange({
                dateTo: date ? date.toISOString().slice(0, 10) : '',
                page: 1,
              })
            }
            dateFormat="yyyy-MM-dd"
            placeholderText="End date"
            isClearable
            className="prospects-toolbar__date"
          />
        </label>

        <label className="prospects-toolbar__field">
          <span>Source</span>
          <select
            value={filters.source}
            onChange={event => onChange({ source: event.target.value, page: 1 })}
          >
            <option value="ALL">All sources</option>
            <option value="FACEBOOK_LEAD">Facebook</option>
            <option value="INSTAGRAM_LEAD">Instagram</option>
            <option value="WHATSAPP">WhatsApp</option>
          </select>
        </label>

        <label className="prospects-toolbar__field">
          <span>Contact status</span>
          <select
            value={filters.contactStatus}
            onChange={event =>
              onChange({
                contactStatus: event.target.value as ContactStatusFilter,
                page: 1,
              })
            }
            aria-label="Filter by whether WhatsApp chat has started"
          >
            {CONTACT_STATUS_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="prospects-toolbar__field">
          <span>Rows</span>
          <select
            value={filters.pageSize}
            onChange={event =>
              onChange({
                pageSize: Number(event.target.value) as TablePageSize,
                page: 1,
              })
            }
            aria-label="Prospects page size"
          >
            {TABLE_PAGE_SIZE_OPTIONS.map(size => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

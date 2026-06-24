import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import { Search } from 'lucide-react';
import type { ProspectsFilters } from '../../types/prospect';

type ProspectsToolbarProps = {
  filters: ProspectsFilters;
  onChange: (next: Partial<ProspectsFilters>) => void;
  filteredTotal?: number;
};

export default function ProspectsToolbar({
  filters,
  onChange,
  filteredTotal,
}: ProspectsToolbarProps) {
  const dateFromValue = filters.dateFrom ? new Date(filters.dateFrom) : null;
  const dateToValue = filters.dateTo ? new Date(filters.dateTo) : null;

  return (
    <div className="prospects-toolbar">
      <div className="prospects-toolbar__title">
        <h2>All Prospects</h2>
        {typeof filteredTotal === 'number' ? (
          <span className="prospects-toolbar__count">{filteredTotal} matches</span>
        ) : null}
      </div>

      <div className="prospects-toolbar__controls">
        <label className="prospects-toolbar__search">
          <Search size={16} />
          <input
            type="text"
            placeholder="Search name, email, phone..."
            value={filters.q}
            onChange={event => onChange({ q: event.target.value })}
          />
        </label>

        <label className="prospects-toolbar__field">
          <span>From</span>
          <DatePicker
            selected={dateFromValue}
            onChange={date =>
              onChange({ dateFrom: date ? date.toISOString().slice(0, 10) : '' })
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
              onChange({ dateTo: date ? date.toISOString().slice(0, 10) : '' })
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
            onChange={event => onChange({ source: event.target.value })}
          >
            <option value="ALL">All sources</option>
            <option value="FACEBOOK_LEAD">Facebook</option>
            <option value="INSTAGRAM_LEAD">Instagram</option>
            <option value="WHATSAPP">WhatsApp</option>
          </select>
        </label>
      </div>
    </div>
  );
}

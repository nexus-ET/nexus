import { Link } from 'react-router-dom';
import { CalendarClock } from 'lucide-react';

import type { CalendarIntakeAlert } from '../../types/hierarchicalIntake';

interface CalendarAlertsWidgetProps {
  alerts: CalendarIntakeAlert[];
}

const CalendarAlertsWidget: React.FC<CalendarAlertsWidgetProps> = ({ alerts }) => {
  if (!alerts.length) {
    return (
      <section className="rounded-2xl border border-border-subtle bg-card p-5">
        <div className="flex items-center gap-2">
          <CalendarClock size={18} className="text-accent" />
          <h3 className="text-lg font-bold text-text-main">Calendar Alerts</h3>
        </div>
        <p className="mt-3 text-sm text-text-muted">All institutions have upcoming intake schedules configured.</p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-border-subtle bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <CalendarClock size={18} className="text-accent" />
          <h3 className="text-lg font-bold text-text-main">Calendar Alerts</h3>
        </div>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
          {alerts.length} pending
        </span>
      </div>
      <ul className="mt-4 space-y-3">
        {alerts.map(alert => (
          <li key={alert.id} className="rounded-xl border border-border-subtle px-4 py-3">
            <p className="font-semibold text-text-main">
              {alert.institution_name} · {alert.entity_name}
            </p>
            <p className="text-sm text-text-muted">
              Missing intake schedule for {alert.term_name} {alert.year}
              {alert.days_until_start != null ? ` · ${alert.days_until_start} days until class start` : ''}
            </p>
            {alert.link_path ? (
              <Link to={alert.link_path} className="mt-2 inline-block text-sm font-semibold text-accent">
                Configure intakes
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
};

export default CalendarAlertsWidget;

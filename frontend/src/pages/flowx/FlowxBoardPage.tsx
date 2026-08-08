import { useState } from 'react';
import { Link } from 'react-router-dom';
import HeadlessScrollArea from '../../components/HeadlessScrollArea';
import { useFlowxBoard, useFlowxCountries } from '../../hooks/useFlowx';
import { slaChipClass, slaLabel } from '../../types/flowx';

const FlowxBoardPage: React.FC = () => {
  const [country, setCountry] = useState('');
  const countriesQuery = useFlowxCountries();
  const boardQuery = useFlowxBoard(country || undefined);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold text-text-main">By Country Board</h2>
          <p className="text-sm text-text-muted">
            Active students grouped by destination journey stage — who is where in the process.
          </p>
        </div>
        <select
          value={country}
          onChange={e => setCountry(e.target.value)}
          className="rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm"
        >
          <option value="">All countries</option>
          {(countriesQuery.data ?? []).map(c => (
            <option key={c.country_iso2} value={c.country_iso2}>
              {c.country_iso2} · {c.country_name}
            </option>
          ))}
        </select>
      </div>

      {boardQuery.isLoading ? (
        <p className="text-sm text-text-muted">Loading board…</p>
      ) : (
        <HeadlessScrollArea className="min-h-0 flex-1" axes="both">
          <div className="flex min-h-[420px] gap-3 pb-2">
            {(boardQuery.data?.columns ?? []).map(col => (
              <div
                key={col.stage_key}
                className="flex w-[210px] shrink-0 flex-col rounded-2xl border border-border-subtle bg-card p-2"
              >
                <div className="mb-2 flex items-center justify-between px-1">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{col.label}</p>
                  <span className="rounded-md bg-surface-bg px-1.5 text-[10px] font-medium">{col.cards.length}</span>
                </div>
                <div className="space-y-2">
                  {col.cards.length === 0 ? (
                    <p className="px-1 text-[11px] text-text-muted">No students</p>
                  ) : (
                    col.cards.map(card => (
                      <Link
                        key={card.enrollment_id}
                        to={`/flowx/journeys/${card.enrollment_id}`}
                        className="block rounded-xl border border-border-subtle bg-surface-bg/50 p-2.5 transition hover:border-accent/40"
                      >
                        <p className="truncate text-sm font-semibold text-text-main">{card.lead_name}</p>
                        <p className="mt-0.5 truncate text-[11px] text-text-muted">
                          {card.country_iso2}
                          {card.college_name
                            ? ` · ${card.college_name}`
                            : card.institution_name
                              ? ` · ${card.institution_name}`
                              : ` · ${card.country_name}`}
                        </p>
                        <span
                          className={`mt-1 inline-block rounded border px-1 text-[9px] font-semibold ${slaChipClass(
                            card.sla_health
                          )}`}
                        >
                          {slaLabel(card.sla_health)}
                        </span>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        </HeadlessScrollArea>
      )}
    </div>
  );
};

export default FlowxBoardPage;

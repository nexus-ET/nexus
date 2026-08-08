import { useMemo, useState } from 'react';
import { useCountryComparison, useProofOfFunds } from '../../hooks/useNexusIntel';

const COMPARE_COUNTRIES = [
  'UK',
  'CA',
  'AU',
  'DE',
  'US',
  'JP',
  'FR',
  'AE',
  'NZ',
  'SG',
  'IE',
  'NL',
  'NO',
  'PL',
  'HK',
  'MY',
  'QA',
  'IN',
  'RU',
  'SE',
  'CH',
] as const;

const WorkflowsPage: React.FC = () => {
  const [country, setCountry] = useState<(typeof COMPARE_COUNTRIES)[number]>('CA');
  const [tuition, setTuition] = useState('25000');
  const [living, setLiving] = useState('20000');
  const [scholarships, setScholarships] = useState('0');
  const [selected, setSelected] = useState<string[]>(['UK', 'CA']);
  const fundsMutation = useProofOfFunds();
  const comparisonQuery = useCountryComparison(selected);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const toggleCountry = (code: string) => {
    setSelected(prev => {
      if (prev.includes(code)) return prev.filter(item => item !== code);
      if (prev.length >= 3) return prev;
      return [...prev, code];
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
        <h2 className="text-lg font-bold text-text-main">Proof of Funds Calculator</h2>
        <p className="text-sm text-text-muted">
          Estimate required balance using destination guidelines (tuition + living − scholarships).
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-sm space-y-1">
            <span className="font-semibold text-text-muted">Country</span>
            <select
              value={country}
              onChange={e => setCountry(e.target.value as (typeof COMPARE_COUNTRIES)[number])}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2"
            >
              {COMPARE_COUNTRIES.map(code => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm space-y-1">
            <span className="font-semibold text-text-muted">Tuition</span>
            <input
              type="number"
              min={0}
              value={tuition}
              onChange={e => setTuition(e.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="font-semibold text-text-muted">Living costs</span>
            <input
              type="number"
              min={0}
              value={living}
              onChange={e => setLiving(e.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="font-semibold text-text-muted">Scholarships</span>
            <input
              type="number"
              min={0}
              value={scholarships}
              onChange={e => setScholarships(e.target.value)}
              className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white"
          onClick={() =>
            fundsMutation.mutate({
              country_code: country,
              tuition: Number(tuition) || 0,
              living_costs: Number(living) || 0,
              scholarships: Number(scholarships) || 0,
            })
          }
        >
          Calculate
        </button>
        {fundsMutation.data ? (
          <div className="rounded-xl border border-border-subtle bg-surface-bg p-3 space-y-2 text-sm">
            <p className="text-lg font-bold text-text-main">
              {fundsMutation.data.currency} {fundsMutation.data.required_balance.toLocaleString()}
            </p>
            <p className="text-text-muted">Holding period: {fundsMutation.data.holding_days} days</p>
            <ul className="list-disc pl-5 text-text-muted">
              {fundsMutation.data.notes.map(note => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
        <h2 className="text-lg font-bold text-text-main">Side-by-Side Comparison</h2>
        <p className="text-sm text-text-muted">
          Compare up to 3 destinations on funds, PSW, language, dependents, and work limits.
        </p>
        <div className="flex flex-wrap gap-2">
          {COMPARE_COUNTRIES.map(code => (
            <button
              key={code}
              type="button"
              onClick={() => toggleCountry(code)}
              className={`rounded-full border px-3 py-1 text-sm font-semibold ${
                selectedSet.has(code)
                  ? 'border-accent/40 bg-accent/10 text-text-main'
                  : 'border-border-subtle text-text-muted'
              }`}
            >
              {code}
            </button>
          ))}
        </div>
        <div className="headless-scroll-viewport overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-text-muted">
              <tr>
                <th className="py-2 pr-3">Country</th>
                <th className="py-2 pr-3">Tuition</th>
                <th className="py-2 pr-3">PSW</th>
                <th className="py-2 pr-3">Language</th>
                <th className="py-2 pr-3">Dependents</th>
                <th className="py-2 pr-3">Work limits</th>
                <th className="py-2">Funds</th>
              </tr>
            </thead>
            <tbody>
              {(comparisonQuery.data || []).map(row => (
                <tr key={row.country_code} className="border-t border-border-subtle align-top">
                  <td className="py-2 pr-3 font-semibold">{row.country_code}</td>
                  <td className="py-2 pr-3 text-text-muted">{row.tuition_band}</td>
                  <td className="py-2 pr-3 text-text-muted">{row.psw_rights}</td>
                  <td className="py-2 pr-3 text-text-muted">{row.language_requirements || '—'}</td>
                  <td className="py-2 pr-3 text-text-muted">{row.dependent_rules}</td>
                  <td className="py-2 pr-3 text-text-muted">{row.work_limits}</td>
                  <td className="py-2 text-text-muted">{row.proof_of_funds_summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default WorkflowsPage;

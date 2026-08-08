import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Calculator,
  Loader2,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { findCountryByIso2, useCountries } from '../hooks/useCountries';
import { useFxRate, useRoiBenchmarks } from '../hooks/useNexusIntel';
import { useConsultationStore } from '../stores/consultationStore';
import {
  aspirationsToForm,
  emptyAspirationsForm,
  type StudentAspirationsResponse,
} from '../types/studentAspirations';
import type { UniversityShortlistItem, UniversityShortlistResponse } from '../types/universityShortlist';
import { CountryFlag } from '../utils/countryFlag';
import { apiFetch } from '../utils/api';
import { formatInrWithWords } from '../utils/indianCurrency';
import {
  applySensitivity,
  computeRoi,
  formatMoney,
  type RoiBenchmarkInputs,
  type RoiSensitivity,
} from '../utils/roiCalculator';

interface RoiCalculatorTabProps {
  bookingId: number;
}

type InstitutionOption = {
  institution_id: number;
  institution_name: string;
  country_iso2: string;
};

function FieldNumber({
  label,
  value,
  onChange,
  step = 1,
  min = 0,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  step?: number;
  min?: number;
  suffix?: string;
}) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-semibold text-text-muted">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          step={step}
          min={min}
          value={Number.isFinite(value) ? value : 0}
          onChange={e => onChange(Number(e.target.value))}
          className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-text-main"
        />
        {suffix ? <span className="shrink-0 text-xs text-text-muted">{suffix}</span> : null}
      </div>
    </label>
  );
}

const DISPLAY_CURRENCIES = [
  'INR',
  'USD',
  'GBP',
  'EUR',
  'CAD',
  'AUD',
  'NZD',
  'SGD',
  'JPY',
  'CHF',
  'AED',
  'HKD',
  'MYR',
  'PLN',
] as const;

const CURRENCY_LABELS: Record<string, string> = {
  INR: 'INR — Indian Rupee',
  USD: 'USD — US Dollar',
  GBP: 'GBP — British Pound',
  EUR: 'EUR — Euro',
  CAD: 'CAD — Canadian Dollar',
  AUD: 'AUD — Australian Dollar',
  NZD: 'NZD — New Zealand Dollar',
  SGD: 'SGD — Singapore Dollar',
  JPY: 'JPY — Japanese Yen',
  CHF: 'CHF — Swiss Franc',
  AED: 'AED — UAE Dirham',
  HKD: 'HKD — Hong Kong Dollar',
  MYR: 'MYR — Malaysian Ringgit',
  PLN: 'PLN — Polish Złoty',
};

function ResultStat({
  label,
  value,
  hint,
  converted,
}: {
  label: string;
  value: string;
  hint?: string;
  converted?: {
    title: string;
    number: string;
    words?: string;
    rateNote?: string;
  } | null;
}) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 text-lg font-bold text-text-main">{value}</p>
      {converted ? (
        <div className="mt-2 space-y-0.5 rounded-lg border border-primary/15 bg-primary/5 px-2 py-1.5">
          <p className="text-[10px] font-bold uppercase tracking-wide text-primary">{converted.title}</p>
          <p className="text-sm font-semibold text-text-main">{converted.number}</p>
          {converted.words ? (
            <p className="text-xs capitalize leading-snug text-text-muted">{converted.words}</p>
          ) : null}
          {converted.rateNote ? (
            <p className="text-[10px] text-text-muted">{converted.rateNote}</p>
          ) : null}
        </div>
      ) : null}
      {hint ? <p className="mt-0.5 text-xs text-text-muted">{hint}</p> : null}
    </div>
  );
}

const RoiCalculatorTab: React.FC<RoiCalculatorTabProps> = ({ bookingId }) => {
  const { countries } = useCountries();
  const form = useConsultationStore(state => state.form);
  const hydrated = useConsultationStore(state => state.hydrated);
  const loadingAspirations = useConsultationStore(state => state.loading);
  const loadSeq = useRef(0);

  const [activeIso2, setActiveIso2] = useState<string | null>(null);
  const [institutionId, setInstitutionId] = useState<number | null>(null);
  const [sensitivity, setSensitivity] = useState<RoiSensitivity>('expected');
  const [inputs, setInputs] = useState<RoiBenchmarkInputs | null>(null);
  const [baseline, setBaseline] = useState<RoiBenchmarkInputs | null>(null);
  const [displayCurrency, setDisplayCurrency] = useState<string>('INR');

  useEffect(() => {
    const seq = ++loadSeq.current;
    const hydrate = useConsultationStore.getState().hydrate;
    const setLoading = useConsultationStore.getState().setLoading;
    const setError = useConsultationStore.getState().setError;
    useConsultationStore.setState({ bookingId });

    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const response = (await apiFetch(
          `bookings/mine/${bookingId}/aspirations`
        )) as StudentAspirationsResponse;
        if (cancelled || seq !== loadSeq.current) return;
        hydrate({
          form: aspirationsToForm(response.aspirations),
          bookingId,
          savedAt: response.saved_at || null,
        });
      } catch (err) {
        if (cancelled || seq !== loadSeq.current) return;
        setError(err instanceof Error ? err.message : 'Failed to load aspirations.');
        hydrate({ form: emptyAspirationsForm(), bookingId, savedAt: null });
      } finally {
        if (!cancelled && seq === loadSeq.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [bookingId]);

  const destinationIso2s = useMemo(() => {
    const fromTargets = form.target_countries.map(item => item.iso2.toUpperCase());
    const fromLegacy = (form.study_countries_iso2 || []).map(code => code.toUpperCase());
    const merged = [...fromTargets, ...fromLegacy].filter(
      code => code && code !== 'OTHER' && /^[A-Z]{2}$/.test(code)
    );
    return Array.from(new Set(merged));
  }, [form.target_countries, form.study_countries_iso2]);

  useEffect(() => {
    if (!destinationIso2s.length) {
      setActiveIso2(null);
      return;
    }
    setActiveIso2(prev =>
      prev && destinationIso2s.includes(prev) ? prev : destinationIso2s[0]
    );
  }, [destinationIso2s]);

  const shortlistQuery = useQuery({
    queryKey: ['university-shortlist', bookingId, 'roi-calculator'],
    queryFn: () =>
      apiFetch<UniversityShortlistResponse>(`bookings/mine/${bookingId}/university-shortlist`),
    staleTime: 60_000,
  });

  const institutionsForCountry = useMemo(() => {
    const items = shortlistQuery.data?.run?.items || [];
    const map = new Map<number, InstitutionOption>();
    items.forEach((item: UniversityShortlistItem) => {
      const iso = (item.institution_country_iso2 || '').toUpperCase();
      if (!activeIso2 || iso !== activeIso2) return;
      if (!map.has(item.institution_id)) {
        map.set(item.institution_id, {
          institution_id: item.institution_id,
          institution_name: item.institution_name || `Institution #${item.institution_id}`,
          country_iso2: iso,
        });
      }
    });
    return Array.from(map.values());
  }, [shortlistQuery.data, activeIso2]);

  useEffect(() => {
    if (!institutionsForCountry.length) {
      setInstitutionId(null);
      return;
    }
    setInstitutionId(prev =>
      prev != null && institutionsForCountry.some(i => i.institution_id === prev)
        ? prev
        : institutionsForCountry[0].institution_id
    );
  }, [institutionsForCountry]);

  const benchmarksQuery = useRoiBenchmarks({
    country: activeIso2,
    institutionId,
    enabled: Boolean(activeIso2),
  });

  const fxAsOf = benchmarksQuery.data?.as_of || null;
  const modelCurrency = (inputs?.currency || benchmarksQuery.data?.inputs.currency || '').toUpperCase();
  const needsFx = Boolean(modelCurrency) && displayCurrency.toUpperCase() !== modelCurrency;
  const fxQuery = useFxRate({
    base: modelCurrency || null,
    quote: displayCurrency,
    asOf: fxAsOf,
    enabled: needsFx,
  });

  useEffect(() => {
    const next = benchmarksQuery.data?.inputs;
    if (!next) return;
    setBaseline(next);
    setInputs(next);
    setSensitivity('expected');
  }, [benchmarksQuery.data]);

  const effectiveInputs = useMemo(() => {
    if (!inputs) return null;
    return applySensitivity(inputs, sensitivity);
  }, [inputs, sensitivity]);

  const result = useMemo(
    () => (effectiveInputs ? computeRoi(effectiveInputs) : null),
    [effectiveInputs]
  );

  const patchInput = <K extends keyof RoiBenchmarkInputs>(key: K, value: RoiBenchmarkInputs[K]) => {
    setInputs(prev => (prev ? { ...prev, [key]: value } : prev));
  };

  const chartData = useMemo(
    () =>
      (result?.series || []).map(point => ({
        name: point.label,
        Abroad: Math.round(point.abroadCumulative),
        Home: Math.round(point.homeCumulative),
        Income: Math.round(point.abroadIncome),
        Expense: Math.round(point.abroadExpense),
      })),
    [result]
  );

  if (loadingAspirations && !hydrated) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-text-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading ROI Calculator…
      </div>
    );
  }

  if (!destinationIso2s.length) {
    return (
      <div className="mx-auto max-w-xl space-y-3 px-4 py-12 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Calculator size={22} />
        </div>
        <h3 className="text-base font-bold text-text-main">No destinations selected yet</h3>
        <p className="text-sm text-text-muted leading-relaxed">
          Add target countries in Aspirations, then return here to model college ROI scenarios.
        </p>
      </div>
    );
  }

  const currency = effectiveInputs?.currency || 'USD';

  const convertedFor = (amount: number) => {
    if (!modelCurrency) return null;
    const quote = displayCurrency.toUpperCase();
    if (quote === modelCurrency) {
      const same =
        quote === 'INR'
          ? formatInrWithWords(amount)
          : { number: formatMoney(amount, quote), words: undefined };
      return {
        title: `${quote} (model currency)`,
        number: same.number,
        words: same.words,
        rateNote: `Already in ${quote} — no conversion applied.`,
      };
    }
    const rate = fxQuery.data?.rate;
    if (!rate || !Number.isFinite(rate)) {
      return fxQuery.isLoading
        ? {
            title: `${quote} equivalent`,
            number: 'Converting…',
            rateNote: `Fetching ${modelCurrency}→${quote} rate…`,
          }
        : null;
    }
    const converted = amount * rate;
    const rateDate = fxQuery.data?.as_of || fxAsOf || 'today';
    if (quote === 'INR') {
      const formatted = formatInrWithWords(converted);
      return {
        title: 'INR equivalent',
        number: formatted.number,
        words: formatted.words,
        rateNote: `1 ${currency} = ₹${rate.toFixed(4)} · FX as of ${rateDate}${
          fxQuery.data?.source === 'fallback' ? ' (indicative)' : ''
        }`,
      };
    }
    return {
      title: `${quote} equivalent`,
      number: formatMoney(converted, quote),
      rateNote: `1 ${currency} = ${rate.toFixed(4)} ${quote} · FX as of ${rateDate}${
        fxQuery.data?.source === 'fallback' ? ' (indicative)' : ''
      }`,
    };
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-primary">ROI Calculator</p>
          <h3 className="text-base font-bold text-text-main">College return on investment</h3>
          <p className="mt-0.5 text-xs text-text-muted">
            Prefills from aspirations &amp; shortlist benchmarks — edit freely, then compare abroad vs
            home cash flows.
          </p>
        </div>
        {benchmarksQuery.data ? (
          <button
            type="button"
            onClick={() => baseline && setInputs(baseline)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border-subtle px-3 py-2 text-xs font-semibold text-text-muted hover:bg-surface-bg"
          >
            <RefreshCw size={14} />
            Reset to benchmarks
          </button>
        ) : null}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
        {destinationIso2s.map(iso2 => {
          const country = findCountryByIso2(countries, iso2);
          const active = activeIso2 === iso2;
          return (
            <button
              key={iso2}
              type="button"
              onClick={() => setActiveIso2(iso2)}
              className={`inline-flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition ${
                active
                  ? 'border-primary bg-primary text-white shadow-sm'
                  : 'border-border-subtle bg-card text-text-main hover:border-primary/40'
              }`}
            >
              <CountryFlag iso2={iso2} size="sm" />
              {country?.name || iso2}
            </button>
          );
        })}
      </div>

      {institutionsForCountry.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setInstitutionId(null)}
            className={`rounded-xl border px-3 py-2 text-xs font-semibold ${
              institutionId == null
                ? 'border-primary bg-primary text-white'
                : 'border-border-subtle text-text-muted'
            }`}
          >
            Country baseline
          </button>
          {institutionsForCountry.map(inst => (
            <button
              key={inst.institution_id}
              type="button"
              onClick={() => setInstitutionId(inst.institution_id)}
              className={`max-w-[14rem] truncate rounded-xl border px-3 py-2 text-xs font-semibold ${
                institutionId === inst.institution_id
                  ? 'border-primary bg-primary text-white'
                  : 'border-border-subtle text-text-main'
              }`}
            >
              {inst.institution_name}
            </button>
          ))}
        </div>
      ) : (
        <p className="rounded-lg border border-border-subtle bg-surface-bg/70 px-3 py-2 text-xs text-text-muted">
          Tip: add a Shortlist institution for metro-adjusted living &amp; salary baselines.{' '}
          <Link to="#" className="pointer-events-none font-semibold text-primary">
            (use Shortlist tab)
          </Link>
        </p>
      )}

      {benchmarksQuery.isLoading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-text-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading ROI benchmarks…
        </div>
      ) : benchmarksQuery.isError ? (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {benchmarksQuery.error instanceof Error
            ? benchmarksQuery.error.message
            : 'Failed to load ROI benchmarks.'}
        </p>
      ) : inputs && effectiveInputs && result ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <aside className="space-y-3 rounded-xl border border-border-subtle bg-card p-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-primary">Inputs</p>
              <p className="text-sm font-semibold text-text-main">
                {benchmarksQuery.data?.location_label || activeIso2}
              </p>
              <p className="text-xs text-text-muted">
                Model currency {currency}
                {form.programs?.[0] ? ` · Program ${form.programs[0]}` : ''}
              </p>
            </div>

            <label className="block space-y-1 text-sm">
              <span className="font-semibold text-text-muted">Convert summary to</span>
              <select
                value={displayCurrency}
                onChange={e => setDisplayCurrency(e.target.value)}
                className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-text-main"
              >
                {DISPLAY_CURRENCIES.map(code => (
                  <option key={code} value={code}>
                    {CURRENCY_LABELS[code] || code}
                    {code === currency ? ' (model)' : ''}
                  </option>
                ))}
                {currency && !(DISPLAY_CURRENCIES as readonly string[]).includes(currency) ? (
                  <option value={currency}>{currency} (model)</option>
                ) : null}
              </select>
              <span className="block text-[11px] text-text-muted">
                Applies to NPV differential &amp; Total investment cards.
              </span>
            </label>

            <div className="flex flex-wrap gap-2">
              {(
                [
                  ['conservative', 'Conservative'],
                  ['expected', 'Expected'],
                  ['optimistic', 'Optimistic'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSensitivity(key)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                    sensitivity === key
                      ? 'border-primary bg-primary text-white'
                      : 'border-border-subtle text-text-muted'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="space-y-3 border-t border-border-subtle pt-3">
              <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                Academic &amp; direct costs
              </p>
              <FieldNumber
                label="Program years"
                value={inputs.program_years}
                onChange={v => patchInput('program_years', v)}
                step={0.5}
                min={0.5}
              />
              <FieldNumber
                label="Annual tuition"
                value={inputs.annual_tuition}
                onChange={v => patchInput('annual_tuition', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Visa / application fees"
                value={inputs.visa_fees}
                onChange={v => patchInput('visa_fees', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Health insurance / year"
                value={inputs.health_insurance_annual}
                onChange={v => patchInput('health_insurance_annual', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Books & supplies / year"
                value={inputs.books_supplies_annual}
                onChange={v => patchInput('books_supplies_annual', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Scholarship / year"
                value={inputs.scholarship_annual}
                onChange={v => patchInput('scholarship_annual', v)}
                suffix={currency}
              />
            </div>

            <div className="space-y-3 border-t border-border-subtle pt-3">
              <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                Living &amp; opportunity
              </p>
              <FieldNumber
                label="Monthly rent"
                value={inputs.monthly_rent}
                onChange={v => patchInput('monthly_rent', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Monthly groceries"
                value={inputs.monthly_groceries}
                onChange={v => patchInput('monthly_groceries', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Monthly transit"
                value={inputs.monthly_transit}
                onChange={v => patchInput('monthly_transit', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Other living / month"
                value={inputs.monthly_other_living}
                onChange={v => patchInput('monthly_other_living', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Part-time earnings / year"
                value={inputs.part_time_earnings_annual}
                onChange={v => patchInput('part_time_earnings_annual', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Home counterfactual salary"
                value={inputs.home_counterfactual_salary}
                onChange={v => patchInput('home_counterfactual_salary', v)}
                suffix={currency}
              />
            </div>

            <div className="space-y-3 border-t border-border-subtle pt-3">
              <p className="text-xs font-bold uppercase tracking-wide text-text-muted">
                Career projections
              </p>
              <FieldNumber
                label="Destination starting salary"
                value={inputs.destination_starting_salary}
                onChange={v => patchInput('destination_starting_salary', v)}
                suffix={currency}
              />
              <FieldNumber
                label="Salary growth (destination)"
                value={inputs.destination_salary_growth}
                onChange={v => patchInput('destination_salary_growth', v)}
                step={0.005}
                min={0}
                suffix="decimal"
              />
              <FieldNumber
                label="Career horizon (years)"
                value={inputs.career_horizon_years}
                onChange={v => patchInput('career_horizon_years', Math.round(v))}
                step={1}
                min={1}
              />
              <FieldNumber
                label="Discount rate"
                value={inputs.discount_rate}
                onChange={v => patchInput('discount_rate', v)}
                step={0.005}
                min={0}
                suffix="decimal"
              />
              <FieldNumber
                label="Dest. effective tax rate"
                value={inputs.destination_effective_tax_rate}
                onChange={v => patchInput('destination_effective_tax_rate', v)}
                step={0.01}
                min={0}
                suffix="decimal"
              />
              <FieldNumber
                label="Home effective tax rate"
                value={inputs.home_effective_tax_rate}
                onChange={v => patchInput('home_effective_tax_rate', v)}
                step={0.01}
                min={0}
                suffix="decimal"
              />
            </div>
          </aside>

          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ResultStat
                label="Break-even"
                value={result.breakEvenLabel}
                hint="First year abroad path catches up vs home"
              />
              <ResultStat
                label="ROI %"
                value={`${result.roiPercent.toFixed(1)}%`}
                hint="(Abroad earnings − home earnings − investment) / investment"
              />
              <ResultStat
                label="NPV differential"
                value={formatMoney(result.npvDifferential, currency)}
                hint={`Discounted abroad − home @ ${(effectiveInputs.discount_rate * 100).toFixed(1)}%`}
                converted={convertedFor(result.npvDifferential)}
              />
              <ResultStat
                label="Total investment"
                value={formatMoney(result.totalInvestment, currency)}
                hint={`Living ~${formatMoney(result.livingAnnual, currency)}/yr during study`}
                converted={convertedFor(result.totalInvestment)}
              />
            </div>

            <section className="rounded-xl border border-border-subtle bg-card p-4 space-y-2">
              <div className="flex items-center gap-2">
                <TrendingUp size={16} className="text-primary" />
                <h4 className="text-sm font-bold text-text-main">
                  Cumulative cash: Studying abroad vs staying home
                </h4>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(value: number | string) =>
                        formatMoney(typeof value === 'number' ? value : Number(value), currency)
                      }
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="Abroad"
                      stroke="#322f86"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="Home"
                      stroke="#386fa4"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="rounded-xl border border-border-subtle bg-card p-4 space-y-2">
              <h4 className="text-sm font-bold text-text-main">
                Abroad path — annual income vs expense
              </h4>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      formatter={(value: number | string) =>
                        formatMoney(typeof value === 'number' ? value : Number(value), currency)
                      }
                    />
                    <Legend />
                    <Line type="monotone" dataKey="Income" stroke="#059669" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="Expense" stroke="#dc2626" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <p className="text-[11px] leading-relaxed text-text-muted">
              As of {benchmarksQuery.data?.as_of}.{' '}
              {needsFx
                ? fxQuery.data
                  ? `FX ${fxQuery.data.base}/${fxQuery.data.quote} = ${fxQuery.data.rate.toFixed(4)} as of ${fxQuery.data.as_of} (${fxQuery.data.source}). `
                  : fxQuery.isLoading
                    ? `Fetching ${modelCurrency}→${displayCurrency} FX rate… `
                    : fxQuery.isError
                      ? `Could not load ${modelCurrency}→${displayCurrency} FX rate. `
                      : ''
                : displayCurrency === modelCurrency
                  ? `Summary shown in model currency (${modelCurrency}). `
                  : ''}
              {benchmarksQuery.data?.disclaimer}{' '}
              <Link
                to="/nexus-intel/workflows"
                className="font-semibold text-primary hover:underline"
              >
                Open Intel Workflows
              </Link>{' '}
              for proof-of-funds. Qualitative ROI talk-track remains in Future Insights.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default RoiCalculatorTab;

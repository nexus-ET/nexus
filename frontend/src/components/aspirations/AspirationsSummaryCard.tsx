import React, { useMemo } from 'react';
import {
  detectAspirationMismatches,
  generateAspirationSummary,
  computeAspirationsProgress,
} from '../../config/aspirations.config';
import { useCountries } from '../../hooks/useCountries';
import { useGpaCgpaScores } from '../../hooks/useGpaCgpaScores';
import { useLevels } from '../../hooks/useLevels';
import { useConsultationStore } from '../../stores/consultationStore';
import { AlertTriangle, CheckCircle2, Sparkles } from 'lucide-react';

export function AspirationsSummaryCard() {
  const form = useConsultationStore(state => state.form);
  const { countries } = useCountries();
  const { levels } = useLevels();
  const { scores } = useGpaCgpaScores();

  const progress = useMemo(() => computeAspirationsProgress(form), [form]);
  const flags = useMemo(() => detectAspirationMismatches(form), [form]);

  const summary = useMemo(() => {
    const countryNames = Object.fromEntries(
      countries.map(country => [country.iso2.toUpperCase(), country.name])
    );
    const levelNames = Object.fromEntries(levels.map(level => [level.code, level.name]));
    const standingLabels = Object.fromEntries(scores.map(score => [score.code, score.label]));
    return generateAspirationSummary(form, { countryNames, levelNames, standingLabels });
  }, [countries, form, levels, scores]);

  return (
    <div className="rounded-xl border border-border-subtle bg-gradient-to-br from-slate-50 via-white to-emerald-50/40 p-4 shadow-sm space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-primary" />
          <div>
            <h4 className="text-sm font-bold text-text-main">Aspirations Summary</h4>
            <p className="text-xs text-text-muted">Live counselor brief from current selections</p>
          </div>
        </div>
        <div className="min-w-[140px]">
          <div className="flex items-center justify-between text-xs font-semibold text-text-muted mb-1">
            <span>Progress</span>
            <span>
              {progress.completed}/{progress.total} · {progress.percent}%
            </span>
          </div>
          <div className="h-2 rounded-full bg-surface-bg border border-border-subtle overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>
      </div>

      <p className="text-sm text-text-main leading-relaxed">{summary}</p>

      {flags.length ? (
        <div className="space-y-2">
          {flags.map(flag => (
            <div
              key={flag.id}
              className={`rounded-lg border px-3 py-2 text-sm ${
                flag.severity === 'warning'
                  ? 'border-amber-200 bg-amber-50 text-amber-950'
                  : 'border-sky-200 bg-sky-50 text-sky-950'
              }`}
            >
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-semibold">{flag.title}</p>
                  <p className="text-sm opacity-90 mt-0.5">{flag.detail}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : progress.completed > 0 ? (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          <CheckCircle2 size={14} className="shrink-0" />
          No contradiction flags detected for the current combination.
        </div>
      ) : null}
    </div>
  );
}

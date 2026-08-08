import React from 'react';
import {
  ASPIRATION_OPTION_CATALOGS,
  getAspirationQuestion,
  isQuestionComplete,
} from '../../config/aspirations.config';
import { useConsultationStore } from '../../stores/consultationStore';
import {
  setFundingCoverage,
  toggleFundingSource,
  getFundingCoverage,
  isFundingSourceSelected,
  type BudgetOption,
  type FundingSourceOption,
  type GrantScholarshipTypeOption,
} from '../../types/studentAspirations';
import {
  AspirationBlock,
  AspirationSectionShell,
  OptionCardGroup,
  fieldLabelClass,
} from './AspirationControls';

export function FinancialFrameworkSection() {
  const form = useConsultationStore(state => state.form);
  const patchForm = useConsultationStore(state => state.patchForm);
  const validationErrors = useConsultationStore(state => state.validationErrors);

  const hasError = (keywords: string[]) =>
    validationErrors.some(message =>
      keywords.some(keyword => message.toLowerCase().includes(keyword.toLowerCase()))
    );

  const q6 = getAspirationQuestion('budget_funding');

  return (
    <AspirationSectionShell
      title="Financial Framework"
      progressLabel={isQuestionComplete('budget_funding', form) ? '1/1 complete' : '0/1 complete'}
    >
      <AspirationBlock
        code={q6.code}
        title={q6.title}
        complete={isQuestionComplete('budget_funding', form)}
      >
        <p className={fieldLabelClass}>Budget range</p>
        <OptionCardGroup
          name="budget"
          options={ASPIRATION_OPTION_CATALOGS.budgets}
          value={form.budget[0] || ''}
          onChange={next => patchForm({ budget: [next as BudgetOption] })}
          columns="fit"
          hasError={hasError(['budget'])}
        />

        <div className="mt-4">
          <p className={fieldLabelClass}>Primary funding source</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {ASPIRATION_OPTION_CATALOGS.funding_sources.map(option => {
              const source = option.value as FundingSourceOption;
              const selected = isFundingSourceSelected(form.funding_sources, source);
              const coverage = getFundingCoverage(form.funding_sources, source);
              const showError = hasError(['funding']);
              return (
                <div
                  key={source}
                  className={`rounded-lg border p-3 space-y-2 transition-colors ${
                    selected
                      ? 'border-primary bg-primary text-white'
                      : showError
                        ? 'border-red-300 bg-surface-bg/40'
                        : 'border-border-subtle bg-surface-bg/40'
                  }`}
                >
                  <button
                    type="button"
                    aria-pressed={selected}
                    className={`w-full text-left text-sm font-bold cursor-pointer ${
                      selected ? 'text-white' : 'text-text-main'
                    }`}
                    onClick={() =>
                      patchForm(prev => ({
                        funding_sources: toggleFundingSource(
                          prev.funding_sources,
                          source,
                          !selected
                        ),
                      }))
                    }
                  >
                    {option.label}
                  </button>
                  <div
                    className={`flex flex-wrap gap-x-3 gap-y-1 text-sm ${
                      selected ? 'text-white' : 'text-text-main'
                    }`}
                  >
                    {ASPIRATION_OPTION_CATALOGS.funding_coverage.map(coverageOption => (
                      <label
                        key={coverageOption.value}
                        className="inline-flex items-center gap-1.5 cursor-pointer"
                      >
                        <input
                          type="radio"
                          name={`funding-coverage-${source}`}
                          checked={coverage === coverageOption.value}
                          disabled={!selected}
                          onChange={() =>
                            patchForm(prev => ({
                              funding_sources: setFundingCoverage(
                                prev.funding_sources,
                                source,
                                coverageOption.value as GrantScholarshipTypeOption
                              ),
                            }))
                          }
                        />
                        <span>{coverageOption.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </AspirationBlock>
    </AspirationSectionShell>
  );
}

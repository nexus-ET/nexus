import React, { useMemo } from 'react';
import {
  ASPIRATION_OPTION_CATALOGS,
  COUNTRY_PRIORITY_OPTIONS,
  PREFERRED_STUDY_COUNTRY_ISO2,
  STUDY_COUNTRY_OTHER_VALUE,
  getAspirationQuestion,
  isQuestionComplete,
  type CountryPriorityOption,
  type TargetCountrySelection,
} from '../../config/aspirations.config';
import { useCountries } from '../../hooks/useCountries';
import { useConsultationStore } from '../../stores/consultationStore';
import type {
  PostStudyGoalOption,
  WhyStudyAbroadOption,
} from '../../types/studentAspirations';
import { toggleListValue } from '../../types/studentAspirations';
import {
  AspirationBlock,
  AspirationSectionShell,
  OptionCardGroup,
  PillToggleGrid,
  fieldLabelClass,
  textInputClass,
} from './AspirationControls';

export function CoreVisionSection() {
  const form = useConsultationStore(state => state.form);
  const patchForm = useConsultationStore(state => state.patchForm);
  const validationErrors = useConsultationStore(state => state.validationErrors);
  const { countries } = useCountries();

  const countryOptions = useMemo(() => {
    const byIso = new Map(countries.map(country => [country.iso2.toUpperCase(), country.name]));
    const preferred = PREFERRED_STUDY_COUNTRY_ISO2.map(iso2 => ({
      value: iso2,
      label: byIso.get(iso2) || iso2,
    })).sort((a, b) => a.label.localeCompare(b.label));
    return [...preferred, { value: STUDY_COUNTRY_OTHER_VALUE, label: 'Others' }];
  }, [countries]);

  const selectedIso = form.target_countries.map(item => item.iso2);
  const hasError = (keywords: string[]) =>
    validationErrors.some(message =>
      keywords.some(keyword => message.toLowerCase().includes(keyword.toLowerCase()))
    );

  const q1 = getAspirationQuestion('primary_motivation');
  const q2 = getAspirationQuestion('post_study_goal');
  const q3 = getAspirationQuestion('target_countries');
  const MAX_TARGET_COUNTRIES = 6;

  const setTargetCountries = (
    next: TargetCountrySelection[] | ((prev: TargetCountrySelection[]) => TargetCountrySelection[])
  ) => {
    patchForm(prev => {
      const resolved = typeof next === 'function' ? next(prev.target_countries) : next;
      return {
        target_countries: resolved.slice(0, MAX_TARGET_COUNTRIES),
        study_countries_iso2: resolved.slice(0, MAX_TARGET_COUNTRIES).map(item => item.iso2),
        study_countries_other: resolved
          .slice(0, MAX_TARGET_COUNTRIES)
          .some(item => item.iso2 === STUDY_COUNTRY_OTHER_VALUE)
          ? prev.study_countries_other
          : '',
      };
    });
  };

  const toggleCountry = (iso2: string, checked: boolean) => {
    setTargetCountries(current => {
      if (!checked) return current.filter(item => item.iso2 !== iso2);
      if (current.some(item => item.iso2 === iso2)) return current;
      if (current.length >= MAX_TARGET_COUNTRIES) return current;
      return [
        ...current,
        {
          iso2,
          priority: current.length === 0 ? 'TOP_CHOICE' : 'ALTERNATIVE',
        },
      ];
    });
  };

  const setCountryPriority = (iso2: string, priority: CountryPriorityOption) => {
    setTargetCountries(current =>
      current.map(item => (item.iso2 === iso2 ? { ...item, priority } : item))
    );
  };

  return (
    <AspirationSectionShell
      title="Core Vision & Destination"
      progressLabel={`${
        ['primary_motivation', 'post_study_goal', 'target_countries'].filter(id =>
          isQuestionComplete(id as 'primary_motivation', form)
        ).length
      }/3 complete`}
    >
      <AspirationBlock
        code={q1.code}
        title={q1.title}
        complete={isQuestionComplete('primary_motivation', form)}
      >
        <OptionCardGroup
          name="primary_motivation"
          options={ASPIRATION_OPTION_CATALOGS.motivations}
          value=""
          onChange={() => undefined}
          multi
          selectedValues={form.why_study_abroad}
          onToggle={(value, checked) => {
            patchForm(prev => {
              const why_study_abroad = toggleListValue(
                prev.why_study_abroad,
                value as WhyStudyAbroadOption,
                checked
              );
              return {
                why_study_abroad,
                why_study_abroad_other: why_study_abroad.includes('OTHER')
                  ? prev.why_study_abroad_other
                  : '',
              };
            });
          }}
          columns="fit"
          hasError={hasError(['primary motivation', 'others — primary'])}
        />
        {form.why_study_abroad.includes('OTHER') ? (
          <div className="mt-3">
            <label className={fieldLabelClass}>Others — describe your motivation</label>
            <input
              type="text"
              value={form.why_study_abroad_other}
              maxLength={100}
              onChange={event => patchForm({ why_study_abroad_other: event.target.value })}
              className={textInputClass}
              placeholder="Enter up to 100 characters"
            />
          </div>
        ) : null}
      </AspirationBlock>

      <AspirationBlock
        code={q2.code}
        title={q2.title}
        complete={isQuestionComplete('post_study_goal', form)}
      >
        <OptionCardGroup
          name="post_study_goals"
          options={ASPIRATION_OPTION_CATALOGS.post_study_goals}
          value=""
          onChange={() => undefined}
          multi
          selectedValues={form.post_study_goals}
          onToggle={(value, checked) => {
            patchForm(prev => {
              const post_study_goals = toggleListValue(
                prev.post_study_goals,
                value as PostStudyGoalOption,
                checked
              );
              return {
                post_study_goals,
                post_study_goal_other: post_study_goals.includes('OTHER')
                  ? prev.post_study_goal_other
                  : '',
              };
            });
          }}
          columns="fit"
          hasError={hasError(['post-study', 'desired career', 'others — career'])}
        />
        {form.post_study_goals.includes('OTHER') ? (
          <div className="mt-3">
            <label className={fieldLabelClass}>Others — enter your desired career goals</label>
            <input
              type="text"
              value={form.post_study_goal_other}
              maxLength={200}
              onChange={event => patchForm({ post_study_goal_other: event.target.value })}
              className={textInputClass}
              placeholder="Enter up to 200 characters"
            />
            <p className="mt-1 text-sm text-text-muted">
              {form.post_study_goal_other.length}/200 characters
            </p>
          </div>
        ) : null}
      </AspirationBlock>

      <AspirationBlock
        code={q3.code}
        title={q3.title}
        complete={isQuestionComplete('target_countries', form)}
      >
        <p className="text-sm text-text-muted mb-2">
          Select up to 6 destinations, then mark each as Top Choice or Open to Alternatives.
          {selectedIso.length > 0 ? ` (${selectedIso.length}/6 selected)` : ''}
        </p>
        {selectedIso.length >= MAX_TARGET_COUNTRIES ? (
          <p className="mb-2 text-xs font-semibold text-amber-800">
            Maximum of 6 countries reached. Deselect one to choose another.
          </p>
        ) : null}
        <PillToggleGrid
          options={countryOptions}
          selected={selectedIso}
          onToggle={toggleCountry}
          hasError={hasError(['target countries', 'others — target'])}
          renderSelectedExtra={iso2 => {
            const current = form.target_countries.find(item => item.iso2 === iso2);
            if (!current) return null;
            return (
              <div className="flex gap-1 px-0.5">
                {COUNTRY_PRIORITY_OPTIONS.map(option => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() =>
                      setCountryPriority(iso2, option.value as CountryPriorityOption)
                    }
                    className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${
                      current.priority === option.value
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border-subtle text-text-muted bg-white'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            );
          }}
        />
        {selectedIso.includes(STUDY_COUNTRY_OTHER_VALUE) ? (
          <div className="mt-3">
            <label className={fieldLabelClass}>Others — enter country or countries</label>
            <input
              type="text"
              value={form.study_countries_other}
              maxLength={100}
              onChange={event => patchForm({ study_countries_other: event.target.value })}
              className={textInputClass}
              placeholder="Enter up to 100 characters"
            />
          </div>
        ) : null}
      </AspirationBlock>
    </AspirationSectionShell>
  );
}

import React, { useMemo } from 'react';
import {
  getAspirationQuestion,
  isQuestionComplete,
} from '../../config/aspirations.config';
import { useEducationMajors } from '../../hooks/useEducationMajors';
import {
  filterFullTimeStudyYearsByLevel,
  useFullTimeStudyYears,
} from '../../hooks/useFullTimeStudyYears';
import { findGpaCgpaScore, useGpaCgpaScores } from '../../hooks/useGpaCgpaScores';
import { useLevels } from '../../hooks/useLevels';
import {
  findQualificationProgram,
  useQualificationPrograms,
} from '../../hooks/useQualificationPrograms';
import { useConsultationStore } from '../../stores/consultationStore';
import {
  MAX_TARGET_PROGRAMS,
  PROGRAM_OTHER_VALUE,
  toggleListValue,
} from '../../types/studentAspirations';
import {
  AspirationBlock,
  AspirationSectionShell,
  OptionCardGroup,
  fieldLabelClass,
  selectClass,
  textInputClass,
} from './AspirationControls';

const fluidSelectClass = selectClass.replace('max-w-lg', 'max-w-none');

export function AcademicProfileSection() {
  const form = useConsultationStore(state => state.form);
  const patchForm = useConsultationStore(state => state.patchForm);
  const validationErrors = useConsultationStore(state => state.validationErrors);
  const { levels } = useLevels();
  const { majors } = useEducationMajors();
  const { scores } = useGpaCgpaScores();
  const { options: studyYearOptions } = useFullTimeStudyYears();
  const { programs: qualificationPrograms } = useQualificationPrograms();

  const hasError = (keywords: string[]) =>
    validationErrors.some(message =>
      keywords.some(keyword => message.toLowerCase().includes(keyword.toLowerCase()))
    );

  const levelOptions = useMemo(
    () =>
      [...levels]
        .sort((a, b) => a.id - b.id || a.name.localeCompare(b.name))
        .map(level => ({
          value: level.code,
          label: level.name,
          title: level.name,
        })),
    [levels]
  );

  const levelSelectOptions = useMemo(
    () =>
      [...levels]
        .sort((a, b) => a.id - b.id || a.name.localeCompare(b.name))
        .map(level => ({ value: String(level.id), label: level.name, code: level.code })),
    [levels]
  );

  const filteredStudyYears = useMemo(
    () => filterFullTimeStudyYearsByLevel(studyYearOptions, form.current_level_id),
    [studyYearOptions, form.current_level_id]
  );

  const filteredPrograms = useMemo(() => {
    if (!form.current_level_id) return [];
    return qualificationPrograms
      .filter(program => program.level_id === Number(form.current_level_id))
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
  }, [qualificationPrograms, form.current_level_id]);

  const selectedCurrentProgram = useMemo(
    () => findQualificationProgram(qualificationPrograms, form.current_program_code),
    [qualificationPrograms, form.current_program_code]
  );

  const mappedProgramMajors = selectedCurrentProgram?.majors ?? [];

  const filteredMajors = useMemo(() => {
    if (!form.current_program_code || !mappedProgramMajors.length) {
      return [];
    }
    const labels = new Set(mappedProgramMajors.map(major => major.label.trim().toLowerCase()));
    const codes = new Set(
      mappedProgramMajors
        .map(major => (major.code || '').trim().toUpperCase())
        .filter(Boolean)
    );
    const otherMajors = majors.filter(major => major.is_other && major.is_active);
    const matched = majors.filter(
      major =>
        major.is_active &&
        !major.is_other &&
        (labels.has(major.label.trim().toLowerCase()) ||
          Boolean(major.code && codes.has(major.code.trim().toUpperCase())))
    );
    if (matched.length) {
      return [...matched, ...otherMajors];
    }
    return [
      ...mappedProgramMajors.map(major => ({
        id: major.id,
        code: major.code,
        label: major.label,
        is_other: false,
        sort_order: 0,
        is_active: true,
      })),
      ...otherMajors,
    ];
  }, [form.current_program_code, majors, mappedProgramMajors]);

  const programOptions = useMemo(() => {
    const seen = new Set<string>();
    const options: { value: string; label: string }[] = [];
    [...majors]
      .filter(major => major.is_active && !major.is_other)
      .sort((a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label))
      .forEach(major => {
        const label = major.label.trim();
        if (!label) return;
        const key = label.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        options.push({ value: label, label });
      });
    options.push({ value: PROGRAM_OTHER_VALUE, label: 'Others' });
    return options;
  }, [majors]);

  const standingOptions = useMemo(
    () =>
      [...scores]
        .sort((a, b) => a.sort_order - b.sort_order || a.label.localeCompare(b.label))
        .map(score => ({ value: score.code, label: score.label })),
    [scores]
  );

  const selectedStanding = findGpaCgpaScore(scores, form.academic_standing_code);
  const q4 = getAspirationQuestion('academic_standing');
  const q5 = getAspirationQuestion('degree_program');

  return (
    <AspirationSectionShell
      title="Academic Profile & Program Fit"
      progressLabel={`${
        ['academic_standing', 'degree_program'].filter(id =>
          isQuestionComplete(id as 'academic_standing', form)
        ).length
      }/2 complete`}
    >
      <AspirationBlock
        code={q4.code}
        title={q4.title}
        complete={isQuestionComplete('academic_standing', form)}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3 items-start">
          <div>
            <label className={fieldLabelClass} htmlFor="q4-level">
              Levels
            </label>
            <select
              id="q4-level"
              className={`${fluidSelectClass} ${
                hasError(['current level']) ? 'border-red-300 ring-1 ring-red-100' : ''
              }`}
              value={form.current_level_id}
              onChange={event => {
                patchForm({
                  current_level_id: event.target.value,
                  current_full_time_study_years: '',
                  current_program_code: '',
                  current_major: '',
                  academic_standing_code: '',
                  academic_standing_other: '',
                });
              }}
            >
              <option value="">Select level</option>
              {levelSelectOptions.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="q4-study-years">
              Full-Time Study Years
            </label>
            <select
              id="q4-study-years"
              className={`${fluidSelectClass} ${
                hasError(['full-time study']) ? 'border-red-300 ring-1 ring-red-100' : ''
              }`}
              value={form.current_full_time_study_years}
              disabled={!form.current_level_id}
              onChange={event =>
                patchForm({ current_full_time_study_years: event.target.value })
              }
            >
              <option value="">
                {form.current_level_id
                  ? filteredStudyYears.length
                    ? 'Select study years'
                    : 'No study years for this level'
                  : 'Select level first'}
              </option>
              {filteredStudyYears.map(option => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="q4-program">
              Current Programs
            </label>
            <select
              id="q4-program"
              className={`${fluidSelectClass} ${
                hasError(['current program']) ? 'border-red-300 ring-1 ring-red-100' : ''
              }`}
              value={form.current_program_code}
              disabled={!form.current_level_id}
              onChange={event => {
                const nextCode = event.target.value;
                const program = findQualificationProgram(qualificationPrograms, nextCode);
                const mapped = program?.majors ?? [];
                const autoMajor = mapped.length === 1 ? mapped[0].label : '';
                patchForm({
                  current_program_code: nextCode,
                  current_major: autoMajor,
                });
              }}
            >
              <option value="">
                {form.current_level_id
                  ? filteredPrograms.length
                    ? 'Select program'
                    : 'No programs for this level'
                  : 'Select level first'}
              </option>
              {filteredPrograms.map(program => (
                <option key={program.code} value={program.code}>
                  {program.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="q4-major">
              Major
            </label>
            <select
              id="q4-major"
              className={`${fluidSelectClass} ${
                hasError(['major is required']) ? 'border-red-300 ring-1 ring-red-100' : ''
              }`}
              value={
                filteredMajors.some(major => major.label === form.current_major)
                  ? form.current_major
                  : ''
              }
              disabled={!form.current_program_code}
              onChange={event => patchForm({ current_major: event.target.value })}
            >
              <option value="">
                {form.current_program_code
                  ? filteredMajors.length
                    ? 'Select major'
                    : 'No majors for this program'
                  : 'Select program first'}
              </option>
              {filteredMajors.map(major => (
                <option key={major.code || major.id} value={major.label}>
                  {major.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="q4-standing">
              Academic scores
            </label>
            <select
              id="q4-standing"
              className={`${fluidSelectClass} ${
                hasError(['academic scores']) ? 'border-red-300 ring-1 ring-red-100' : ''
              }`}
              value={form.academic_standing_code}
              onChange={event => {
                const nextCode = event.target.value;
                const nextScore = findGpaCgpaScore(scores, nextCode);
                patchForm({
                  academic_standing_code: nextCode,
                  academic_standing_other: nextScore?.is_other ? form.academic_standing_other : '',
                });
              }}
              disabled={!form.current_level_id}
            >
              <option value="">
                {form.current_level_id ? 'Select academic score' : 'Select a level first'}
              </option>
              {standingOptions.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedStanding?.is_other ? (
          <div className="mt-3">
            <label className={fieldLabelClass}>Enter standing details</label>
            <input
              type="text"
              value={form.academic_standing_other}
              onChange={event => patchForm({ academic_standing_other: event.target.value })}
              className={textInputClass}
              placeholder="e.g. GPA 3.2 / 85%"
            />
          </div>
        ) : null}
      </AspirationBlock>

      <AspirationBlock
        code={q5.code}
        title={q5.title}
        complete={isQuestionComplete('degree_program', form)}
      >
        <p className={`${fieldLabelClass}`}>Degree</p>
        <OptionCardGroup
          name="study_level_code"
          options={levelOptions}
          value={form.study_level_code}
          onChange={study_level_code =>
            patchForm({
              study_level_code,
            })
          }
          columns="fit"
          hasError={hasError(['degree selection'])}
        />

        <div className="mt-4">
          <p className={`${fieldLabelClass}`}>
            Programs
            {form.programs.length > 0
              ? ` (${form.programs.length}/${MAX_TARGET_PROGRAMS} selected)`
              : ''}
          </p>
          {form.programs.length >= MAX_TARGET_PROGRAMS ? (
            <p className="mb-2 text-xs font-semibold text-amber-800">
              Maximum of {MAX_TARGET_PROGRAMS} programs reached. Deselect one to choose another.
            </p>
          ) : null}
          <OptionCardGroup
            name="programs"
            options={programOptions}
            value=""
            onChange={() => undefined}
            multi
            selectedValues={form.programs}
            onToggle={(value, checked) => {
              patchForm(prev => {
                if (checked && prev.programs.length >= MAX_TARGET_PROGRAMS) {
                  return {};
                }
                const programs = toggleListValue(prev.programs, value, checked).slice(
                  0,
                  MAX_TARGET_PROGRAMS
                );
                return {
                  programs,
                  programs_other: programs.includes(PROGRAM_OTHER_VALUE)
                    ? prev.programs_other
                    : '',
                };
              });
            }}
            columns={6}
            hasError={hasError(['program selection', 'others — programs', 'up to 4 programs'])}
          />
          {form.programs.includes(PROGRAM_OTHER_VALUE) ? (
            <div className="mt-3">
              <label className={fieldLabelClass}>Others — enter program or programs</label>
              <input
                type="text"
                value={form.programs_other}
                maxLength={50}
                onChange={event => patchForm({ programs_other: event.target.value })}
                className={textInputClass}
                placeholder="Enter up to 50 characters"
              />
            </div>
          ) : null}
        </div>
      </AspirationBlock>
    </AspirationSectionShell>
  );
}

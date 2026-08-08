import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import { FileDown, Loader2, Mic, MicOff, Save, Sparkles, UserRound } from 'lucide-react';
import { useBusinessTimezone } from '../context/BusinessTimezoneContext';
import { useCountries } from '../hooks/useCountries';
import { useGpaCgpaScores } from '../hooks/useGpaCgpaScores';
import { useLevels } from '../hooks/useLevels';
import { useQualificationPrograms } from '../hooks/useQualificationPrograms';
import { apiFetch } from '../utils/api';
import { exportStudentProfilePdf } from '../utils/exportStudentProfilePdf';
import { fetchBusinessPdfBranding } from '../utils/fetchBusinessPdfBranding';
import {
  buildStudentProfilePreviewModel,
} from '../utils/studentProfilePreview';
import {
  aspirationsToForm,
  emptyAspirationsForm,
  type StudentAspirationsFormState,
} from '../types/studentAspirations';
import SearchableMultiSelect from './academia/SearchableMultiSelect';
import CreateProfileModal from './CreateProfileModal';
import {
  FORWARD_STATUS_BLOCKED_MESSAGE,
  getSelectableStatusOptions,
  isStageBlockedBeforeAppointment,
  isUpcomingAppointment,
  resolvePreselectedStageId,
} from './SessionOutcomeSection';

type SpeechRecognitionConstructor = new () => SpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

interface CounsellingSummarizeResponse {
  preferred_universities: string[];
  scholarship_interests: string;
  career_goals: string;
  recommendations: string;
  next_follow_up: string | null;
}

interface CounsellingSessionNoteResponse {
  booking_id: number;
  ai_transcription?: string | null;
  preferred_universities?: string[];
  scholarship_interests?: string | null;
  career_goals?: string | null;
  officer_recommendations?: string | null;
  next_follow_up?: string | null;
  updated_at?: string | null;
}

interface RecommendedInstitutionOption {
  value: string;
  label: string;
  kind: string;
  name: string;
  country_id?: number | null;
  country_name?: string | null;
  state_name?: string | null;
  city_name?: string | null;
}

interface RecommendedInstitutionOptionsResponse {
  options: RecommendedInstitutionOption[];
}

interface StatusDefinition {
  id: number;
  stage_name: string;
  category: string;
  description?: string | null;
  next_stage_id?: number | null;
  is_terminal?: boolean;
}

interface SessionActivityData {
  booking?: {
    status?: string | null;
    session_status_label?: string | null;
  } | null;
  status_definitions: StatusDefinition[];
  current_status_definition_id?: number | null;
  suggested_next_status_definition_id?: number | null;
  previous_stage_id?: number | null;
  appointment_date?: string | null;
  calendar_today?: string | null;
  forward_status_changes_blocked?: boolean;
  backward_status_ids?: number[];
  can_update_status: boolean;
}

interface CounsellingSessionPanelProps {
  bookingId: number;
  candidateName: string;
  onSaved?: () => void;
  onStatusUpdated?: () => void | Promise<void>;
}

interface PersonalProfileName {
  first_name?: string | null;
  middle_name?: string | null;
  last_name?: string | null;
}

function composePersonalProfileName(profile: PersonalProfileName | null | undefined): string {
  if (!profile) return '';
  return [profile.first_name, profile.middle_name, profile.last_name]
    .map(part => (part || '').trim())
    .filter(Boolean)
    .join(' ');
}

function resolveRecommendedInstitutionValues(
  rawValues: string[],
  options: RecommendedInstitutionOption[]
): string[] {
  const allowed = new Set(options.map(option => option.value));
  const byLabel = new Map(options.map(option => [option.label.trim().toLowerCase(), option.value]));
  const byName = new Map<string, string>();
  options.forEach(option => {
    const key = option.name.trim().toLowerCase();
    if (!byName.has(key) || option.kind === 'institution') {
      byName.set(key, option.value);
    }
  });

  const resolved: string[] = [];
  const seen = new Set<string>();
  rawValues.forEach(raw => {
    const token = raw.trim();
    if (!token) return;
    const value =
      (allowed.has(token) ? token : null) ||
      byLabel.get(token.toLowerCase()) ||
      byName.get(token.toLowerCase()) ||
      '';
    if (!value || seen.has(value)) return;
    seen.add(value);
    resolved.push(value);
  });
  return resolved;
}

function buildRecommendedInstitutionsQuery(filters: {
  countryIds: string[];
  levelId?: string;
  majorIds?: string[];
  programIds?: string[];
}): string {
  const params = new URLSearchParams();
  filters.countryIds.forEach(id => params.append('country_ids', id));
  if (filters.levelId) params.set('level_id', filters.levelId);
  (filters.majorIds || []).forEach(id => params.append('major_ids', id));
  (filters.programIds || []).forEach(id => params.append('program_ids', id));
  const query = params.toString();
  return query
    ? `counselling/recommended-institutions?${query}`
    : 'counselling/recommended-institutions';
}

const CounsellingSessionPanel: React.FC<CounsellingSessionPanelProps> = ({
  bookingId,
  candidateName,
  onSaved,
  onStatusUpdated,
}) => {
  const { countries } = useCountries();
  const { levels } = useLevels();
  const { programs: qualificationPrograms } = useQualificationPrograms();
  const { formatDate } = useBusinessTimezone();
  const { scores: gpaScores } = useGpaCgpaScores();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [loadingInstitutions, setLoadingInstitutions] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [aiTranscription, setAiTranscription] = useState('');
  const [selectedCountryIds, setSelectedCountryIds] = useState<string[]>([]);
  const [selectedLevelId, setSelectedLevelId] = useState('');
  const [selectedMajorIds, setSelectedMajorIds] = useState<string[]>([]);
  const [selectedProgramIds, setSelectedProgramIds] = useState<string[]>([]);
  const [preferredUniversities, setPreferredUniversities] = useState<string[]>([]);
  const [institutionOptions, setInstitutionOptions] = useState<RecommendedInstitutionOption[]>([]);
  const [scholarshipInterests, setScholarshipInterests] = useState('');
  const [careerGoals, setCareerGoals] = useState('');
  const [officerRecommendations, setOfficerRecommendations] = useState('');
  const [nextFollowUp, setNextFollowUp] = useState<Date | null>(null);
  const [isDictating, setIsDictating] = useState(false);
  const [dictationSupported, setDictationSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const transcriptionRef = useRef('');
  const dictationBaseRef = useRef('');
  const dictationCommittedRef = useRef('');
  const dictationInterimRef = useRef('');
  const skipInstitutionFetchRef = useRef(true);

  const [activity, setActivity] = useState<SessionActivityData | null>(null);
  const [nextStatusId, setNextStatusId] = useState<number | ''>('');
  const [stageWarning, setStageWarning] = useState<string | null>(null);
  const lastValidStatusIdRef = useRef<number | ''>('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileAspirations, setProfileAspirations] =
    useState<StudentAspirationsFormState | null>(null);

  const speechRecognitionCtor = useMemo(
    () => window.SpeechRecognition || window.webkitSpeechRecognition,
    []
  );

  const countrySelectOptions = useMemo(
    () =>
      [...countries]
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(country => ({ value: String(country.id), label: country.name })),
    [countries]
  );

  const levelSelectOptions = useMemo(
    () => levels.map(level => ({ value: String(level.id), label: level.name })),
    [levels]
  );

  const majorSelectOptions = useMemo(() => {
    if (!selectedLevelId) return [];
    const levelId = Number(selectedLevelId);
    const byId = new Map<number, { id: number; label: string }>();
    for (const program of qualificationPrograms) {
      if (program.level_id !== levelId) continue;
      for (const major of program.majors ?? []) {
        byId.set(major.id, { id: major.id, label: major.label });
      }
    }
    return Array.from(byId.values())
      .sort((a, b) => a.label.localeCompare(b.label))
      .map(major => ({ value: String(major.id), label: major.label }));
  }, [qualificationPrograms, selectedLevelId]);

  const programSelectOptions = useMemo(() => {
    if (!selectedLevelId || !selectedMajorIds.length) return [];
    const levelId = Number(selectedLevelId);
    const majorIdSet = new Set(selectedMajorIds.map(Number));
    return qualificationPrograms
      .filter(
        program =>
          program.level_id === levelId &&
          (program.majors ?? []).some(major => majorIdSet.has(major.id))
      )
      .map(program => ({
        value: program.id,
        label: program.name || program.label || program.code,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [qualificationPrograms, selectedLevelId, selectedMajorIds]);

  const searchableInstitutionOptions = useMemo(
    () => institutionOptions.map(option => ({ value: option.value, label: option.label })),
    [institutionOptions]
  );

  useEffect(() => {
    transcriptionRef.current = aiTranscription;
  }, [aiTranscription]);

  useEffect(() => {
    setDictationSupported(Boolean(speechRecognitionCtor));
  }, [speechRecognitionCtor]);

  const applyNote = useCallback((note: CounsellingSessionNoteResponse) => {
    setAiTranscription(note.ai_transcription || '');
    setScholarshipInterests(note.scholarship_interests || '');
    setCareerGoals(note.career_goals || '');
    setOfficerRecommendations(note.officer_recommendations || '');
    setNextFollowUp(note.next_follow_up ? new Date(note.next_follow_up) : null);
  }, []);

  const applyActivity = useCallback((data: SessionActivityData) => {
    setActivity(data);
    const selectable = getSelectableStatusOptions(
      data.status_definitions,
      data.current_status_definition_id
    );
    const preselected = resolvePreselectedStageId(data, selectable);
    lastValidStatusIdRef.current = preselected;
    setNextStatusId(preselected);
    setStageWarning(null);
  }, []);

  const loadInstitutions = useCallback(
    async (countryIds: string[]) => {
      if (!countryIds.length) {
        setInstitutionOptions([]);
        setPreferredUniversities([]);
        return [];
      }
      setLoadingInstitutions(true);
      try {
        const response = (await apiFetch(
          buildRecommendedInstitutionsQuery({ countryIds })
        )) as RecommendedInstitutionOptionsResponse;
        const options = Array.isArray(response?.options) ? response.options : [];
        setInstitutionOptions(options);
        setPreferredUniversities(prev =>
          prev.filter(value => options.some(option => option.value === value))
        );
        return options;
      } finally {
        setLoadingInstitutions(false);
      }
    },
    []
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      skipInstitutionFetchRef.current = true;
      try {
        const [note, activityData, allInstitutions] = await Promise.all([
          apiFetch(`bookings/mine/${bookingId}/session-notes`) as Promise<CounsellingSessionNoteResponse>,
          apiFetch(`bookings/mine/${bookingId}/activity`) as Promise<SessionActivityData>,
          apiFetch('counselling/recommended-institutions') as Promise<RecommendedInstitutionOptionsResponse>,
        ]);
        if (cancelled) return;

        const allOptions = Array.isArray(allInstitutions?.options) ? allInstitutions.options : [];
        const resolvedInstitutions = resolveRecommendedInstitutionValues(
          note.preferred_universities || [],
          allOptions
        );
        const derivedCountryIds = Array.from(
          new Set(
            resolvedInstitutions
              .map(value => allOptions.find(option => option.value === value)?.country_id)
              .filter((id): id is number => typeof id === 'number' && id > 0)
              .map(String)
          )
        );

        applyNote(note);
        applyActivity(activityData);
        setSelectedCountryIds(derivedCountryIds);
        setSelectedLevelId('');
        setSelectedMajorIds([]);
        setSelectedProgramIds([]);
        setPreferredUniversities(resolvedInstitutions);

        if (derivedCountryIds.length) {
          const filtered = allOptions.filter(
            option =>
              option.country_id != null && derivedCountryIds.includes(String(option.country_id))
          );
          setInstitutionOptions(filtered);
        } else {
          setInstitutionOptions([]);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load session notes.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          window.setTimeout(() => {
            skipInstitutionFetchRef.current = false;
          }, 0);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applyActivity, applyNote, bookingId]);

  useEffect(() => {
    if (skipInstitutionFetchRef.current || loading) return;
    let cancelled = false;
    const run = async () => {
      try {
        await loadInstitutions(selectedCountryIds);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load institutions for the selected countries.'
          );
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [loadInstitutions, loading, selectedCountryIds]);

  useEffect(() => {
    const allowedMajorIds = new Set(majorSelectOptions.map(option => option.value));
    setSelectedMajorIds(prev => {
      const next = prev.filter(id => allowedMajorIds.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [majorSelectOptions]);

  useEffect(() => {
    const allowedProgramIds = new Set(programSelectOptions.map(option => option.value));
    setSelectedProgramIds(prev => {
      const next = prev.filter(id => allowedProgramIds.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [programSelectOptions]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      recognitionRef.current = null;
    };
  }, []);

  const flushDictationToTranscription = useCallback(() => {
    if (dictationInterimRef.current) {
      dictationCommittedRef.current += dictationInterimRef.current;
      dictationInterimRef.current = '';
    }
    const merged = `${dictationBaseRef.current}${dictationCommittedRef.current}`.trimEnd();
    const withSpacing =
      dictationBaseRef.current && dictationCommittedRef.current && !dictationBaseRef.current.endsWith(' ')
        ? `${dictationBaseRef.current.trimEnd()} ${dictationCommittedRef.current.trim()}`
        : merged;
    setAiTranscription(withSpacing);
    transcriptionRef.current = withSpacing;
  }, []);

  const stopDictation = useCallback(() => {
    flushDictationToTranscription();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setIsDictating(false);
  }, [flushDictationToTranscription]);

  const startDictation = () => {
    if (!speechRecognitionCtor) {
      setError('Speech dictation is not supported in this browser. Try Chrome or Edge.');
      return;
    }
    setError(null);
    dictationBaseRef.current = transcriptionRef.current;
    dictationCommittedRef.current = '';
    dictationInterimRef.current = '';

    const recognition = new speechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalChunk = '';
      let interimChunk = '';

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const spoken = result[0]?.transcript ?? '';
        if (!spoken) continue;
        if (result.isFinal) {
          finalChunk += spoken;
        } else {
          interimChunk += spoken;
        }
      }

      if (finalChunk) {
        dictationCommittedRef.current += finalChunk;
        dictationInterimRef.current = '';
      } else if (interimChunk) {
        dictationInterimRef.current = interimChunk;
      }

      const preview = `${dictationBaseRef.current}${dictationCommittedRef.current}${dictationInterimRef.current}`;
      setAiTranscription(preview);
      transcriptionRef.current = preview;
    };

    recognition.onerror = () => {
      stopDictation();
      setError('Dictation stopped due to a microphone or speech recognition error.');
    };

    recognition.onend = () => {
      flushDictationToTranscription();
      recognitionRef.current = null;
      setIsDictating(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsDictating(true);
  };

  const toggleDictation = () => {
    if (isDictating) {
      stopDictation();
      return;
    }
    startDictation();
  };

  const selectableOptions = useMemo(
    () =>
      activity
        ? getSelectableStatusOptions(activity.status_definitions, activity.current_status_definition_id)
        : [],
    [activity]
  );

  const currentStatus = useMemo(
    () =>
      activity?.status_definitions.find(item => item.id === activity.current_status_definition_id) ??
      null,
    [activity]
  );

  const selectedStatus = useMemo(
    () => selectableOptions.find(item => item.id === nextStatusId) ?? null,
    [selectableOptions, nextStatusId]
  );

  const upcomingAppointment = useMemo(
    () => isUpcomingAppointment(activity?.appointment_date, activity?.calendar_today),
    [activity]
  );

  const forwardChangeBlocked = useMemo(
    () =>
      upcomingAppointment &&
      isStageBlockedBeforeAppointment(
        activity?.current_status_definition_id,
        nextStatusId,
        activity?.backward_status_ids ?? []
      ),
    [activity, nextStatusId, upcomingAppointment]
  );

  const handleStageChange = (value: number | '') => {
    if (
      value &&
      activity?.current_status_definition_id &&
      isUpcomingAppointment(activity.appointment_date, activity.calendar_today) &&
      isStageBlockedBeforeAppointment(
        activity.current_status_definition_id,
        value,
        activity.backward_status_ids ?? []
      )
    ) {
      setStageWarning(FORWARD_STATUS_BLOCKED_MESSAGE);
      setNextStatusId(lastValidStatusIdRef.current);
      return;
    }

    setStageWarning(null);
    setError(null);
    lastValidStatusIdRef.current = value;
    setNextStatusId(value);
  };

  const openCreateProfile = async () => {
    const missing: string[] = [];
    if (!preferredUniversities.length) missing.push('Recommended Institutions');
    if (!selectedLevelId) missing.push('Level');
    if (!selectedMajorIds.length) missing.push('Majors');
    if (!selectedProgramIds.length) missing.push('Programs');

    if (missing.length) {
      setSuccess(null);
      setError(
        `Select the required information before creating the profile: ${missing.join(', ')}.`
      );
      return;
    }

    setProfileOpen(true);
    setProfileLoading(true);
    try {
      const response = (await apiFetch(`bookings/mine/${bookingId}/aspirations`)) as {
        aspirations?: Record<string, unknown> | null;
      };
      setProfileAspirations(
        response?.aspirations
          ? aspirationsToForm(response.aspirations)
          : emptyAspirationsForm()
      );
    } catch (err) {
      setProfileAspirations(emptyAspirationsForm());
      setError(err instanceof Error ? err.message : 'Failed to load aspirations for profile.');
    } finally {
      setProfileLoading(false);
    }
  };

  const selectedProfileInstitutions = useMemo(() => {
    const byValue = new Map(institutionOptions.map(option => [option.value, option]));
    return preferredUniversities
      .map(value => byValue.get(value))
      .filter((option): option is RecommendedInstitutionOption => Boolean(option));
  }, [institutionOptions, preferredUniversities]);

  const handleGeneratePdf = async () => {
    const missing: string[] = [];
    if (!preferredUniversities.length) missing.push('Recommended Institutions');
    if (!selectedLevelId) missing.push('Level');
    if (!selectedMajorIds.length) missing.push('Majors');
    if (!selectedProgramIds.length) missing.push('Programs');

    if (missing.length) {
      setSuccess(null);
      setError(
        `Select the required information before generating the report: ${missing.join(', ')}.`
      );
      return;
    }

    try {
      setGeneratingPdf(true);
      setError(null);
      let aspirations = profileAspirations;

      const [aspirationsSettled, brandingSettled, profileSettled] = await Promise.allSettled([
        aspirations
          ? Promise.resolve(null)
          : (apiFetch(`bookings/mine/${bookingId}/aspirations`) as Promise<{
              aspirations?: Record<string, unknown> | null;
            }>),
        fetchBusinessPdfBranding(),
        apiFetch(`bookings/mine/${bookingId}/profile`) as Promise<{
          profile?: PersonalProfileName | null;
        }>,
      ]);

      if (!aspirations) {
        if (aspirationsSettled.status === 'fulfilled' && aspirationsSettled.value) {
          aspirations = aspirationsSettled.value.aspirations
            ? aspirationsToForm(aspirationsSettled.value.aspirations)
            : emptyAspirationsForm();
        } else {
          aspirations = emptyAspirationsForm();
        }
        setProfileAspirations(aspirations);
      }

      const branding =
        brandingSettled.status === 'fulfilled'
          ? brandingSettled.value
          : { businessName: undefined, addressLines: [], logoDataUrl: null };

      // Personal Profile name wins; the lead name is only a fallback.
      const reportCandidateName =
        (profileSettled.status === 'fulfilled'
          ? composePersonalProfileName(profileSettled.value?.profile)
          : '') || candidateName;

      const standingLabels = Object.fromEntries(
        gpaScores.map(score => [score.code, score.label])
      );
      const model = buildStudentProfilePreviewModel({
        candidateName: reportCandidateName,
        generatedAtLabel: formatDate(new Date()),
        companyName: branding.businessName,
        companyAddressLines: branding.addressLines || [],
        logoDataUrl: branding.logoDataUrl,
        aspirations,
        countries,
        levels,
        standingLabels,
        qualificationPrograms,
        selectedInstitutions: selectedProfileInstitutions,
        selectedLevelId,
        selectedMajorIds,
        selectedProgramIds,
        scholarshipInterests,
      });
      const safeName = reportCandidateName.replace(/[^\w\-]+/g, '_').slice(0, 40) || 'student';
      exportStudentProfilePdf(
        model,
        `student-profile-${safeName}-${new Date().toISOString().slice(0, 10)}.pdf`
      );
      setSuccess('Student profile PDF downloaded.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate student profile PDF.');
    } finally {
      setGeneratingPdf(false);
    }
  };

  const handleSummarize = async () => {
    const raw = aiTranscription.trim();
    if (!raw) {
      setError('Add dictation or type session notes before summarizing.');
      return;
    }
    try {
      setSummarizing(true);
      setError(null);
      setSuccess(null);
      const result = (await apiFetch('counselling/summarize', {
        method: 'POST',
        body: JSON.stringify({ raw_text: raw }),
      })) as CounsellingSummarizeResponse;

      if (result.preferred_universities?.length) {
        const matched = resolveRecommendedInstitutionValues(
          result.preferred_universities,
          institutionOptions
        );
        if (matched.length) {
          setPreferredUniversities(matched);
        }
      }
      if (result.scholarship_interests?.trim()) {
        setScholarshipInterests(result.scholarship_interests.trim());
      }
      if (result.career_goals?.trim()) {
        setCareerGoals(result.career_goals.trim());
      }
      if (result.recommendations?.trim()) {
        setOfficerRecommendations(result.recommendations.trim());
      }
      if (result.next_follow_up) {
        setNextFollowUp(new Date(result.next_follow_up));
      }
      setSuccess('AI summary applied to the form. Review and edit before saving.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to summarize session notes.');
    } finally {
      setSummarizing(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      await apiFetch(`bookings/mine/${bookingId}/session-notes`, {
        method: 'POST',
        body: JSON.stringify({
          ai_transcription: aiTranscription.trim() || null,
          preferred_universities: preferredUniversities,
          scholarship_interests: scholarshipInterests.trim() || null,
          career_goals: careerGoals.trim() || null,
          officer_recommendations: officerRecommendations.trim() || null,
          next_follow_up: nextFollowUp ? nextFollowUp.toISOString().slice(0, 10) : null,
        }),
      });

      let statusApplied = false;
      const shouldApplyStatus =
        Boolean(nextStatusId) &&
        Boolean(activity?.can_update_status) &&
        nextStatusId !== activity?.current_status_definition_id;

      if (shouldApplyStatus && forwardChangeBlocked) {
        setSuccess(
          'Session notes saved. Status was not changed — forward stage updates are blocked until the appointment date.'
        );
        onSaved?.();
        return;
      }

      if (shouldApplyStatus && nextStatusId) {
        const statusNotes =
          officerRecommendations.trim() ||
          careerGoals.trim() ||
          'Updated from counselling session.';
        await apiFetch(`bookings/mine/${bookingId}/status`, {
          method: 'POST',
          body: JSON.stringify({
            status_definition_id: Number(nextStatusId),
            notes: statusNotes,
          }),
        });
        statusApplied = true;
        await onStatusUpdated?.();
        const refreshed = (await apiFetch(
          `bookings/mine/${bookingId}/activity`
        )) as SessionActivityData;
        applyActivity(refreshed);
      }

      setSuccess(
        statusApplied
          ? 'Session notes and status saved.'
          : 'Counselling session notes saved.'
      );
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save session notes.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading counselling session...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Document the counselling session for <strong className="text-text-main">{candidateName}</strong>.
        Dictate or type notes, summarize with AI, then save structured fields.
      </p>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {success}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <section className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-text-main">AI Assistant</h4>
            <p className="text-xs text-text-muted mt-1">Voice input and AI extraction for session notes.</p>
          </div>

          <div className="rounded-xl border border-violet-200 bg-violet-50/70 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-violet-900">Voice / Audio Input</p>
                <p className="text-xs text-violet-800/80 mt-0.5">
                  {dictationSupported
                    ? 'Tap the microphone and speak your session notes.'
                    : 'Dictation works best in Chrome or Edge on desktop.'}
                </p>
              </div>
              <button
                type="button"
                onClick={toggleDictation}
                disabled={!dictationSupported}
                className={`inline-flex h-12 w-12 items-center justify-center rounded-full border shadow-sm transition-colors ${
                  isDictating
                    ? 'border-red-300 bg-red-100 text-red-700'
                    : 'border-violet-300 bg-white text-violet-700 hover:bg-violet-100'
                } disabled:opacity-50`}
                aria-label={isDictating ? 'Stop dictation' : 'Start dictation'}
              >
                {isDictating ? <MicOff size={22} /> : <Mic size={22} />}
              </button>
            </div>
            {isDictating && (
              <p className="text-xs font-medium text-red-700 animate-pulse">Listening… tap again to stop.</p>
            )}
          </div>

          <button
            type="button"
            onClick={handleSummarize}
            disabled={summarizing || !aiTranscription.trim()}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-60"
          >
            {summarizing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            AI Summarize &amp; Auto-Fill
          </button>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">
              AI Transcription / Summary Preview
            </label>
            <textarea
              value={aiTranscription}
              onChange={event => setAiTranscription(event.target.value)}
              rows={10}
              placeholder="Dictated or typed session notes appear here..."
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm resize-y"
            />
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-card p-4 space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-text-main">Session Form</h4>
            <p className="text-xs text-text-muted mt-1">Structured counselling documentation.</p>
          </div>

          {(currentStatus || activity?.current_status_definition_id) && (
            <div className="rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Current status
              </p>
              <p className="mt-0.5 text-base font-bold text-text-main leading-snug">
                {currentStatus?.stage_name || 'Unknown'}
              </p>
            </div>
          )}

          {upcomingAppointment ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              This appointment is scheduled for{' '}
              {activity?.appointment_date
                ? new Date(`${activity.appointment_date}T12:00:00`).toLocaleDateString(undefined, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })
                : 'a future date'}
              . Forward stage and follow-up changes are disabled until then. You can still move the candidate to an
              earlier stage.
            </div>
          ) : null}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-text-muted mb-1.5">Country</label>
              <SearchableMultiSelect
                values={selectedCountryIds}
                options={countrySelectOptions}
                onChange={values => {
                  setSelectedCountryIds(values);
                  if (!values.length) {
                    setSelectedLevelId('');
                    setSelectedMajorIds([]);
                    setSelectedProgramIds([]);
                  }
                }}
                placeholder="Select one or more countries…"
                emptyMessage="No countries available."
                hint="Select countries to load matching institutions and colleges."
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-muted mb-1.5">
                Recommended Institutions
              </label>
              <SearchableMultiSelect
                values={preferredUniversities}
                options={searchableInstitutionOptions}
                onChange={setPreferredUniversities}
                disabled={!selectedCountryIds.length || loadingInstitutions}
                placeholder={
                  !selectedCountryIds.length
                    ? 'Select countries first…'
                    : loadingInstitutions
                      ? 'Loading institutions…'
                      : 'Search institutions and colleges…'
                }
                emptyMessage={
                  !selectedCountryIds.length
                    ? 'Select one or more countries to load institutions.'
                    : searchableInstitutionOptions.length === 0
                      ? 'No institutions or colleges found for the selected filters.'
                      : 'No matches found.'
                }
                hint="Only Academia Institutions and Colleges for the selected countries can be chosen."
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-text-muted mb-1.5">Level</label>
              <select
                value={selectedLevelId}
                disabled={!selectedCountryIds.length}
                onChange={event => {
                  setSelectedLevelId(event.target.value);
                  setSelectedMajorIds([]);
                  setSelectedProgramIds([]);
                }}
                className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm disabled:opacity-60"
              >
                <option value="">
                  {selectedCountryIds.length ? 'Select a level…' : 'Select countries first…'}
                </option>
                {levelSelectOptions.map(level => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-muted mb-1.5">Majors</label>
              <SearchableMultiSelect
                values={selectedMajorIds}
                options={majorSelectOptions}
                onChange={values => {
                  setSelectedMajorIds(values);
                  setSelectedProgramIds([]);
                }}
                disabled={!selectedLevelId}
                placeholder={
                  selectedLevelId
                    ? majorSelectOptions.length
                      ? 'Select one or more majors…'
                      : 'No majors for this level'
                    : 'Select a level first…'
                }
                emptyMessage={
                  selectedLevelId
                    ? 'No majors found for this level.'
                    : 'Select a level to load majors.'
                }
                hint="Majors are loaded from programs under the selected level."
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Programs</label>
            <SearchableMultiSelect
              values={selectedProgramIds}
              options={programSelectOptions}
              onChange={setSelectedProgramIds}
              disabled={!selectedMajorIds.length}
              placeholder={
                selectedMajorIds.length
                  ? programSelectOptions.length
                    ? 'Select one or more programs…'
                    : 'No programs for selected majors'
                  : 'Select majors first…'
              }
              emptyMessage={
                selectedMajorIds.length
                  ? 'No programs found for the selected majors.'
                  : 'Select majors to load programs.'
              }
              hint="Programs update based on the selected level and majors."
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Officer Recommendations</label>
            <textarea
              value={officerRecommendations}
              onChange={event => setOfficerRecommendations(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm resize-y"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Next Follow-up</label>
            <DatePicker
              selected={nextFollowUp}
              onChange={(date: Date | null) => setNextFollowUp(date)}
              dateFormat="dd MMM yyyy"
              placeholderText="Select follow-up date"
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              wrapperClassName="w-full"
              popperProps={{ strategy: 'fixed' }}
              isClearable
            />
          </div>

          <div className="space-y-1">
            <label className="block">
              <span className="text-xs font-semibold text-text-muted">Next stage</span>
              <select
                value={nextStatusId}
                onChange={event =>
                  handleStageChange(event.target.value ? Number(event.target.value) : '')
                }
                disabled={!activity?.can_update_status}
                className="mt-1.5 w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm disabled:opacity-60"
              >
                {selectableOptions.length === 0 ? (
                  <option value="">No next stages available</option>
                ) : (
                  selectableOptions.map(stage => {
                    const optionBlocked =
                      upcomingAppointment &&
                      isStageBlockedBeforeAppointment(
                        activity?.current_status_definition_id,
                        stage.id,
                        activity?.backward_status_ids ?? []
                      );
                    return (
                      <option key={stage.id} value={stage.id} disabled={optionBlocked}>
                        {stage.stage_name}
                        {optionBlocked ? ' (available after appointment date)' : ''}
                      </option>
                    );
                  })
                )}
              </select>
            </label>
            {stageWarning ? (
              <p className="text-[11px] text-amber-800 leading-snug">{stageWarning}</p>
            ) : null}
            {selectedStatus?.description ? (
              <p className="text-[11px] text-text-muted leading-snug">{selectedStatus.description}</p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-semibold text-text-dark-bg hover:opacity-90 disabled:opacity-60"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Save Session Notes
            </button>
            <button
              type="button"
              onClick={() => void openCreateProfile()}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-xs font-semibold text-violet-900 hover:bg-violet-100"
            >
              <UserRound size={14} />
              Create Profile
            </button>
            <button
              type="button"
              onClick={() => void handleGeneratePdf()}
              disabled={generatingPdf}
              className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border-subtle bg-card px-3 py-2 text-xs font-semibold text-text-main hover:bg-surface-bg disabled:opacity-60"
            >
              {generatingPdf ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <FileDown size={14} />
              )}
              Generate PDF
            </button>
          </div>
        </section>
      </div>

      <CreateProfileModal
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        candidateName={candidateName}
        loading={profileLoading}
        aspirations={profileAspirations}
        countries={countries}
        levels={levels}
        qualificationPrograms={qualificationPrograms}
        selectedInstitutions={selectedProfileInstitutions}
        selectedLevelId={selectedLevelId}
        selectedMajorIds={selectedMajorIds}
        selectedProgramIds={selectedProgramIds}
        scholarshipInterests={scholarshipInterests}
      />
    </div>
  );
};

export default CounsellingSessionPanel;

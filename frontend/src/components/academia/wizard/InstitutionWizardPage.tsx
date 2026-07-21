import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { Loader2, Save, Upload } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import { fetchAcademiaListItems } from '../../../utils/academiaList';
import { normalizeWebLinks, serializeContacts } from '../../../schemas/contactEntry';
import {
  WIZARD_STEP_LABELS,
  WIZARD_UI_STEP_COUNT,
  apiStepToUiStep,
  clampUiStep,
  emptyWizardInstitution,
  hydrateWizardCampus,
  hydrateWizardCourseOffering,
  hydrateWizardIntake,
  hydrateWizardPicture,
  mapApiStepsToUi,
  mergeWizardCollegesByName,
  normalizeWizardInstitution,
  pictureToApiPayload,
  uiStepToApiStep,
  type WizardCollegeItem,
  type WizardCourseOfferingItem,
  type WizardDraft,
  type WizardInstitutionFormValues,
  type WizardIntakeItem,
  type WizardPictureItem,
} from '../../../schemas/wizard';
import type { WizardCampusItem } from '../../../schemas/wizard/step2-campus';
import {
  hydrateWizardCollege,
  repairWizardAcademicCollegeLinks,
} from '../../../schemas/wizard/step3-colleges';
import {
  INSTITUTIONS_SECTION_PATH,
  institutionHistoryPath,
  institutionWizardPath,
} from '../../../config/academiaHubNav';
import AcademiaBreadcrumbs from '../AcademiaBreadcrumbs';
import WizardStepNavigator from './WizardStepNavigator';
import InstitutionWizardStep1 from './InstitutionWizardStep1';
import InstitutionWizardStep2 from './InstitutionWizardStep2';
import InstitutionWizardStep3 from './InstitutionWizardStep3';
import InstitutionWizardStep4 from './InstitutionWizardStep4';
import InstitutionWizardStep5 from './InstitutionWizardStep5';
import InstitutionWizardStep6 from './InstitutionWizardStep6';
import type { WizardStepHandle } from './form/wizardStepRef';
import { useConfirmation } from '../../../context/ConfirmationContext';
import { useUnsavedChangesGetter } from '../../../context/UnsavedChangesContext';
import {
  geographyCountriesToPhoneCountries,
  resolveGeographyCountryIso2,
  type GeographyCountry,
} from '../../../types/geography';

interface StateOption {
  id: number;
  name: string;
}

interface CityOption {
  id: number;
  name: string;
  country_name?: string | null;
  state_name?: string | null;
}

type WizardStep2Handle = WizardStepHandle<WizardCampusItem[]> & {
  getCampusDrafts?: () => WizardCampusItem[];
};

const UNSAVED_LEAVE_MESSAGE =
  'You have unsaved edits on this step. If you leave now, your changes will be lost.';

const InstitutionWizardPage: React.FC = () => {
  const openConfirm = useConfirmation();
  const navigate = useNavigate();
  const location = useLocation();
  const { draftId: draftIdParam, institutionId: institutionIdParam } = useParams();
  const isCreateFlow = location.pathname.endsWith('/new');
  const isEditFlow = Boolean(institutionIdParam);
  const wizardTitle = isEditFlow ? 'Edit Institution' : 'Add Institution';
  const requestedStep = useMemo(() => {
    const raw = Number(new URLSearchParams(location.search).get('step'));
    if (!Number.isInteger(raw)) return null;
    return clampUiStep(raw) ?? (raw >= 1 && raw <= 6 ? apiStepToUiStep(raw) : null);
  }, [location.search]);

  const step1Ref = useRef<WizardStepHandle<WizardInstitutionFormValues>>(null);
  const step2Ref = useRef<WizardStep2Handle>(null);
  const step3Ref = useRef<WizardStepHandle<WizardCollegeItem[]>>(null);
  const step4Ref = useRef<WizardStepHandle<WizardCourseOfferingItem[]>>(null);
  const step5Ref = useRef<WizardStepHandle<WizardIntakeItem[]>>(null);
  const step6Ref = useRef<WizardStepHandle<WizardPictureItem[]>>(null);

  const [draft, setDraft] = useState<WizardDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [step3Campuses, setStep3Campuses] = useState<WizardCampusItem[]>([]);
  const [step3CollegesLive, setStep3CollegesLive] = useState<WizardCollegeItem[]>([]);
  const [step5Colleges, setStep5Colleges] = useState<WizardCollegeItem[]>([]);
  const [step5HasLiveIntakes, setStep5HasLiveIntakes] = useState(false);
  /** When true, unsaved-changes guard must not block (publish / intentional leave). */
  const skipUnsavedBlockRef = useRef(false);

  // Stale banners should not survive reload, step changes, or back/forward cache restore.
  useEffect(() => {
    setSuccess(null);
    setError(null);
  }, [currentStep, draftIdParam, requestedStep]);

  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setSuccess(null);
        setError(null);
      }
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => setSuccess(null), 5000);
    return () => window.clearTimeout(timer);
  }, [success]);

  const [countries, setCountries] = useState<GeographyCountry[]>([]);
  const [states, setStates] = useState<StateOption[]>([]);
  const [institutionCities, setInstitutionCities] = useState<CityOption[]>([]);

  const loadStatesForCountry = useCallback(async (countryId: number | null) => {
    if (!countryId) {
      setStates([]);
      return;
    }
    const data = await fetchAcademiaListItems<StateOption>('academia/states', {
      country_id: String(countryId),
    });
    setStates(data);
  }, []);

  const loadInstitutionCities = useCallback(
    async (countryId: number | null, stateId: number | null) => {
      if (!countryId) {
        setInstitutionCities([]);
        return;
      }
      const data = await fetchAcademiaListItems<CityOption>('academia/cities', {
        country_id: String(countryId),
        state_id: stateId ? String(stateId) : undefined,
      });
      setInstitutionCities(data);
    },
    []
  );

  const loadReferenceData = useCallback(async () => {
    const countryData = await fetchAcademiaListItems<GeographyCountry>('academia/countries');
    setCountries(
      countryData.map(country => ({
            id: country.id,
            name: country.name,
            iso2: country.iso2,
            dial_code: country.dial_code,
          }))
    );
  }, []);

  const handleCountryChange = useCallback(
    (countryId: number | null) => {
      void loadStatesForCountry(countryId);
      void loadInstitutionCities(countryId, null);
    },
    [loadInstitutionCities, loadStatesForCountry]
  );

  const handleStateChange = useCallback(
    (stateId: number | null) => {
      const countryId =
        step1Ref.current?.getValues()?.country_id ||
        draft?.payload?.institution?.country_id ||
        null;
      void loadInstitutionCities(countryId, stateId);
    },
    [draft?.payload?.institution?.country_id, loadInstitutionCities]
  );

  const hydrateFromDraft = useCallback(
    (data: WizardDraft, options?: { syncStep?: boolean }) => {
      setDraft(data);
      if (options?.syncStep ?? true) {
        const fromDraft = apiStepToUiStep(data.current_step ?? 1);
        setCurrentStep(requestedStep ?? fromDraft);
      }
      const institution = data.payload?.institution;
      if (institution) {
        void loadStatesForCountry(institution.country_id || null);
        void loadInstitutionCities(institution.country_id || null, institution.state_id || null);
      }
    },
    [loadInstitutionCities, loadStatesForCountry, requestedStep]
  );

  const initDraft = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await loadReferenceData();
      if (draftIdParam) {
        const data = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draftIdParam}`);
        // Published versions are immutable — open a fresh draft from the live institution.
        if (data.status !== 'draft' && data.institution_id) {
          const created = await apiFetch<WizardDraft>(
            `academia/wizard/drafts/from-institution/${data.institution_id}`,
            { method: 'POST' }
          );
          hydrateFromDraft(created);
          navigate(
            `${institutionWizardPath(created.id)}${requestedStep ? `?step=${requestedStep}` : ''}`,
            { replace: true }
          );
          return;
        }
        if (data.status !== 'draft') {
          setError(
            'This wizard version is already published and cannot be edited. Open the institution from Institutions to start a new draft.'
          );
          hydrateFromDraft(data);
          return;
        }
        hydrateFromDraft(data);
        return;
      }
      if (institutionIdParam) {
        const created = await apiFetch<WizardDraft>(
          `academia/wizard/drafts/from-institution/${institutionIdParam}`,
          { method: 'POST' }
        );
        hydrateFromDraft(created);
        navigate(
          `${institutionWizardPath(created.id)}${requestedStep ? `?step=${requestedStep}` : ''}`,
          { replace: true }
        );
        return;
      }
      if (isCreateFlow) {
        const created = await apiFetch<WizardDraft>('academia/wizard/drafts', {
          method: 'POST',
          body: JSON.stringify({ title: 'New Institution' }),
        });
        hydrateFromDraft(created);
        navigate(institutionWizardPath(created.id), { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load wizard');
    } finally {
      setLoading(false);
    }
  }, [
    draftIdParam,
    hydrateFromDraft,
    institutionIdParam,
    isCreateFlow,
    loadReferenceData,
    navigate,
  ]);

  useEffect(() => {
    void initDraft();
  }, [initDraft]);

  useEffect(() => {
    if (!requestedStep || requestedStep === currentStep) return;
    setCurrentStep(requestedStep);
  }, [currentStep, requestedStep]);

  const institutionDefaults = useMemo(
    () => normalizeWizardInstitution(draft?.payload?.institution || emptyWizardInstitution),
    [draft?.payload?.institution]
  );

  /** Prefer live Step 1 form values; fall back to draft defaults for web URLs. */
  const getLiveInstitutionValues = useCallback((): WizardInstitutionFormValues => {
    const live = step1Ref.current?.getFormValues?.();
    const fromApi = step1Ref.current?.getValues?.();
    const fallback = normalizeWizardInstitution(fromApi || institutionDefaults);
    const base = live ? normalizeWizardInstitution(live) : fallback;

    const liveWebLinks = serializeContacts(base.web_links || []);
    if (liveWebLinks.length > 0) {
      return {
        ...base,
        web_links: normalizeWebLinks(base.web_links, (base as { institution_web_url?: string | null }).institution_web_url),
      };
    }

    const fallbackWebLinks = serializeContacts(fallback.web_links || []);
    if (fallbackWebLinks.length > 0) {
      return {
        ...base,
        web_links: normalizeWebLinks(
          fallback.web_links,
          (fallback as { institution_web_url?: string | null }).institution_web_url
        ),
      };
    }

    return {
      ...base,
      web_links: normalizeWebLinks(
        institutionDefaults.web_links,
        (institutionDefaults as { institution_web_url?: string | null }).institution_web_url
      ),
    };
  }, [institutionDefaults]);

  const campusDefaults = useMemo(() => {
    if (draft?.payload?.campuses?.length) {
      return draft.payload.campuses.map(item => hydrateWizardCampus(item));
    }
    if (draft?.payload?.campus) {
      return [hydrateWizardCampus(draft.payload.campus)];
    }
    return [];
  }, [draft?.payload?.campus, draft?.payload?.campuses]);

  useEffect(() => {
    if (currentStep !== 2) return;
    const liveCampuses = step2Ref.current?.getCampusDrafts?.();
    setStep3Campuses(
      liveCampuses?.length ? liveCampuses : campusDefaults
    );
  }, [campusDefaults, currentStep]);

  const rawCourseDefaults = useMemo(
    () => (draft?.payload?.courses || []).map(item => hydrateWizardCourseOffering(item)),
    [draft?.payload?.courses]
  );

  const repairedAcademics = useMemo(() => {
    const rawColleges = (draft?.payload?.colleges || []).map(item => hydrateWizardCollege(item));
    return repairWizardAcademicCollegeLinks(rawColleges, rawCourseDefaults);
  }, [draft?.payload?.colleges, rawCourseDefaults]);

  const collegeDefaults = useMemo(
    () => mergeWizardCollegesByName(repairedAcademics.colleges),
    [repairedAcademics.colleges]
  );

  useEffect(() => {
    setStep3CollegesLive(collegeDefaults);
  }, [collegeDefaults, draft?.id]);

  useEffect(() => {
    if (currentStep !== 3) return;
    const liveColleges = step3Ref.current?.getValues?.() || [];
    if (!liveColleges.length) return;
    // Align once when entering Academics; avoid fighting Step3 onCollegesChange updates.
    const repaired = repairWizardAcademicCollegeLinks(liveColleges, rawCourseDefaults);
    setStep3CollegesLive(mergeWizardCollegesByName(repaired.colleges));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-align when the step changes
  }, [currentStep]);

  useEffect(() => {
    if (currentStep !== 4) return;
    const liveColleges = step3Ref.current?.getValues?.() || [];
    setStep5Colleges(
      liveColleges.length
        ? mergeWizardCollegesByName(liveColleges)
        : collegeDefaults
    );
  }, [collegeDefaults, currentStep]);

  const step4Academics = useMemo(() => {
    const colleges = step3CollegesLive.length ? step3CollegesLive : collegeDefaults;
    return repairWizardAcademicCollegeLinks(colleges, rawCourseDefaults);
  }, [collegeDefaults, rawCourseDefaults, step3CollegesLive]);

  const courseDefaults = useMemo(
    () => step4Academics.courses.map(item => hydrateWizardCourseOffering(item)),
    [step4Academics.courses]
  );

  const defaultCollegeOverrides = useMemo(() => {
    const raw = draft?.payload?.college_academic_overrides;
    return Array.isArray(raw)
      ? raw.map(item => String(item).trim()).filter(Boolean)
      : [];
  }, [draft?.payload?.college_academic_overrides]);

  const intakeDefaults = useMemo(
    () => (draft?.payload?.intakes || []).map(item => hydrateWizardIntake(item)),
    [draft?.payload?.intakes]
  );

  const pictureDefaults = useMemo(
    () => (draft?.payload?.pictures || []).map(item => hydrateWizardPicture(item)),
    [draft?.payload?.pictures]
  );

  const defaultCollegePictureOverrides = useMemo(() => {
    const raw = draft?.payload?.college_picture_overrides;
    return Array.isArray(raw)
      ? raw.map(item => String(item).trim()).filter(Boolean)
      : [];
  }, [draft?.payload?.college_picture_overrides]);

  const handleGalleryPicturesChange = useCallback(
    (
      pictures: WizardPictureItem[],
      meta?: { collegePictureOverrides: string[] }
    ) => {
      setDraft(previous => {
        if (!previous) return previous;
        return {
          ...previous,
          payload: {
            ...previous.payload,
            pictures: pictures.map(picture => pictureToApiPayload(picture)),
            college_picture_overrides:
              meta?.collegePictureOverrides ??
              previous.payload?.college_picture_overrides ??
              [],
          },
        };
      });
    },
    []
  );

  const stepsWithData = useMemo(() => {
    if (!draft) return [];
    const payload = draft.payload;
    const apiSteps: number[] = [];
    if (payload.institution) apiSteps.push(1);
    if ((payload.campuses?.length || 0) > 0 || payload.campus) apiSteps.push(2);
    if ((payload.colleges?.length || 0) > 0) apiSteps.push(3);
    if ((payload.courses?.length || 0) > 0) apiSteps.push(4);
    if ((payload.intakes?.length || 0) > 0 || step5HasLiveIntakes) apiSteps.push(5);
    if (
      (payload.pictures || []).some(
        picture => typeof picture?.url === 'string' && picture.url.trim().length > 0
      )
    ) {
      apiSteps.push(6);
    }
    return mapApiStepsToUi(apiSteps);
  }, [draft, step5HasLiveIntakes]);

  const campusesUnlocked = Boolean(draft?.institution_id);
  const completedUiSteps = useMemo(
    () => mapApiStepsToUi(draft?.completed_steps || []),
    [draft?.completed_steps]
  );

  const phoneCountries = useMemo(() => geographyCountriesToPhoneCountries(countries), [countries]);
  const defaultPhoneCountryIso2 = useMemo(() => {
    const institutionCountryId = draft?.payload?.institution?.country_id;
    if (institutionCountryId) {
      return resolveGeographyCountryIso2(countries, institutionCountryId);
    }
    const firstCampusCountryId = campusDefaults[0]?.country_id;
    return resolveGeographyCountryIso2(countries, firstCampusCountryId);
  }, [campusDefaults, countries, draft?.payload?.institution?.country_id]);

  const stepDataKey = String(draft?.id ?? 'new');

  const getActiveStepRef = () => {
    switch (currentStep) {
      case 1:
        return step1Ref;
      case 2:
        return step3Ref;
      case 3:
        return step4Ref;
      case 4:
        return step5Ref;
      case 5:
        return step6Ref;
      default:
        return null;
    }
  };

  const validateCurrentStep = async (options?: { requireCampuses?: boolean }): Promise<boolean> => {
    if (currentStep === 1) {
      if (!step1Ref.current) {
        setSuccess(null);
        setError('This step is still loading. Wait a moment and try again.');
        return false;
      }
      const institutionValid = await step1Ref.current.validate();
      if (!institutionValid) {
        setSuccess(null);
        setError(
          step1Ref.current.getValidationError?.()?.trim() ||
            'Please fix the highlighted institution fields before continuing.'
        );
        window.requestAnimationFrame(() => {
          document
            .querySelector('[data-wizard-step-error], [class*="ring-alert"], .text-alert')
            ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        return false;
      }

      const requireCampuses = options?.requireCampuses ?? false;
      if (!requireCampuses && !campusesUnlocked) {
        return true;
      }

      if (!step2Ref.current) {
        setSuccess(null);
        setError('Campus section is still loading. Wait a moment and try again.');
        return false;
      }
      const campusValid = await step2Ref.current.validate();
      if (!campusValid) {
        setSuccess(null);
        setError(
          step2Ref.current.getValidationError?.()?.trim() ||
            'Add at least one campus before continuing.'
        );
        window.requestAnimationFrame(() => {
          document
            .querySelector('[data-wizard-campus-lock], [data-wizard-step-error], [class*="ring-alert"], .text-alert')
            ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        return false;
      }
      return true;
    }

    const ref = getActiveStepRef();
    if (!ref?.current) {
      setSuccess(null);
      setError('This step is still loading. Wait a moment and try again.');
      return false;
    }
    const valid = await ref.current.validate();
    if (!valid) {
      setSuccess(null);
      const stepMessage = ref.current.getValidationError?.()?.trim();
      setError(stepMessage || 'Please fix the highlighted fields before continuing.');
      window.requestAnimationFrame(() => {
        document
          .querySelector('[data-wizard-step-error], [class*="ring-alert"], .text-alert')
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
    return valid;
  };

  const getCurrentStepData = () => {
    if (currentStep === 1) {
      return {
        institution: step1Ref.current?.getValues() ?? null,
        campuses: step2Ref.current?.getValues() ?? [],
      };
    }
    const ref = getActiveStepRef();
    if (!ref?.current) return null;
    return ref.current.getValues();
  };

  const isCurrentStepDirty = useCallback(() => {
    if (skipUnsavedBlockRef.current) return false;
    if (currentStep === 1) {
      return Boolean(step1Ref.current?.isDirty?.() || step2Ref.current?.isDirty?.());
    }
    const ref = getActiveStepRef();
    return ref?.current?.isDirty?.() ?? false;
  }, [currentStep]);

  const unsavedChanges = useUnsavedChangesGetter(isCurrentStepDirty, 'institution-wizard');

  const markCurrentStepClean = useCallback(() => {
    unsavedChanges.release();
    requestAnimationFrame(() => {
      if (currentStep === 1) {
        step1Ref.current?.markClean?.();
        step2Ref.current?.markClean?.();
        return;
      }
      getActiveStepRef()?.current?.markClean?.();
    });
  }, [currentStep, unsavedChanges]);

  const confirmLeaveUnsavedChanges = useCallback(async () => {
    if (!isCurrentStepDirty()) return true;
    return openConfirm({
      title: 'Leave without saving?',
      message: UNSAVED_LEAVE_MESSAGE,
      confirmLabel: 'Leave',
      cancelLabel: 'Stay',
      variant: 'warning',
    });
  }, [isCurrentStepDirty, openConfirm]);

  const requestStepChange = useCallback(
    async (nextStep: number) => {
      if (nextStep === currentStep) return;
      if (!(await confirmLeaveUnsavedChanges())) return;
      setSuccess(null);
      setError(null);
      getActiveStepRef()?.current?.markClean?.();
      unsavedChanges.release();
      setCurrentStep(nextStep);
      if (draft?.id) {
        navigate(`${institutionWizardPath(draft.id)}?step=${nextStep}`, { replace: true });
      }
    },
    [confirmLeaveUnsavedChanges, currentStep, draft?.id, navigate, unsavedChanges]
  );

  const requestLeaveWizard = useCallback(
    async (path: string) => {
      if (!(await confirmLeaveUnsavedChanges())) return;
      setSuccess(null);
      setError(null);
      getActiveStepRef()?.current?.markClean?.();
      unsavedChanges.release();
      navigate(path);
    },
    [confirmLeaveUnsavedChanges, navigate, unsavedChanges]
  );

  const skipCoursesStep = async () => {
    if (!draft || currentStep !== 3) return;

    const linkedCount = step4Ref.current?.getValues()?.length ?? 0;
    if (linkedCount > 0) {
      const confirmed = await openConfirm({
        title: 'Skip academics?',
        message: 'Any academics in the list will not be saved for this institution.',
        confirmLabel: 'Skip anyway',
        variant: 'warning',
      });
      if (!confirmed) return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
        method: 'POST',
        body: JSON.stringify({
          step: 4,
          data: [],
          mark_complete: true,
        }),
      });
      hydrateFromDraft(updated, { syncStep: false });
      step4Ref.current?.reset?.([]);
      step4Ref.current?.markClean?.();
      setSuccess('Academics step skipped.');
      setCurrentStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip courses step');
    } finally {
      setSaving(false);
    }
  };

  const persistStep4Courses = useCallback(
    async (
      coursesPayload: unknown[],
      meta?: { collegeAcademicOverrides: string[] }
    ) => {
      if (!draft) return;
      setSaving(true);
      setError(null);
      setSuccess(null);
      try {
        const updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 4,
            data: {
              courses: coursesPayload,
              college_academic_overrides: meta?.collegeAcademicOverrides ?? [],
            },
            mark_complete: true,
          }),
        });
        hydrateFromDraft(updated, { syncStep: false });
        step4Ref.current?.markClean?.();
        setSuccess(
          coursesPayload.length === 0
            ? 'All linked academics removed and saved.'
            : 'Academics updated and saved.'
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save academics after unlink');
      } finally {
        setSaving(false);
      }
    },
    [draft, hydrateFromDraft]
  );

  const handleAcademicsAddCollege = useCallback(
    (college: WizardCollegeItem) => {
      setStep3CollegesLive(prev => mergeWizardCollegesByName([...prev, college]));
      setDraft(previous => {
        if (!previous) return previous;
        const nextColleges = mergeWizardCollegesByName([
          ...(previous.payload?.colleges || []).map(item => hydrateWizardCollege(item)),
          college,
        ]);
        return {
          ...previous,
          payload: {
            ...previous.payload,
            colleges: nextColleges,
          },
        };
      });
    },
    []
  );

  const handleAcademicsRemoveCollege = useCallback((collegeLocalId: string) => {
    const collegeKey = `college:${collegeLocalId}`;
    setStep3CollegesLive(prev =>
      prev.filter(item => (item.local_id || item.name) !== collegeLocalId)
    );
    setStep5Colleges(prev =>
      prev.filter(item => (item.local_id || item.name) !== collegeLocalId)
    );
    setDraft(previous => {
      if (!previous) return previous;
      const nextColleges = (previous.payload?.colleges || [])
        .map(item => hydrateWizardCollege(item))
        .filter(item => (item.local_id || item.name) !== collegeLocalId);
      const nextCourses = (previous.payload?.courses || []).filter(item => {
        const localId = String(item?.college_local_id || '').trim();
        if (localId) return localId !== collegeLocalId;
        return true;
      });
      const nextPictures = (previous.payload?.pictures || []).filter(item => {
        const localId = String(item?.college_local_id || '').trim();
        if (localId) return localId !== collegeLocalId;
        return true;
      });
      const nextPictureOverrides = (
        Array.isArray(previous.payload?.college_picture_overrides)
          ? previous.payload.college_picture_overrides
          : []
      )
        .map(item => String(item).trim())
        .filter(item => item && item !== collegeLocalId);
      const nextAcademicOverrides = (
        Array.isArray(previous.payload?.college_academic_overrides)
          ? previous.payload.college_academic_overrides
          : []
      )
        .map(item => String(item).trim())
        .filter(item => item && item !== collegeLocalId && item !== collegeKey);
      return {
        ...previous,
        payload: {
          ...previous.payload,
          colleges: nextColleges,
          courses: nextCourses,
          pictures: nextPictures,
          college_picture_overrides: nextPictureOverrides,
          college_academic_overrides: nextAcademicOverrides,
        },
      };
    });
  }, []);

  const persistStep6Pictures = useCallback(
    async (
      picturesPayload: WizardPictureItem[],
      meta: { collegePictureOverrides: string[] }
    ) => {
      if (!draft) return;
      setSaving(true);
      setError(null);
      setSuccess(null);
      try {
        const updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 6,
            data: {
              pictures: picturesPayload.map(picture => pictureToApiPayload(picture)),
              college_picture_overrides: meta.collegePictureOverrides ?? [],
            },
            mark_complete: true,
          }),
        });
        // Keep Step 6 from briefly re-inheriting university images while overrides hydrate.
        step6Ref.current?.markClean?.();
        hydrateFromDraft(updated, { syncStep: false });
        setSuccess('Gallery updated and saved.');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save gallery after unlink');
      } finally {
        setSaving(false);
      }
    },
    [draft, hydrateFromDraft]
  );

  const saveStep = async (advance = false) => {
    if (!draft) return;
    if (draft.status !== 'draft') {
      setError(
        'This wizard version is already published and cannot be edited. Use Continue editing to open a new draft.'
      );
      return;
    }

    if (currentStep === 1) {
      const requireCampuses = advance || campusesUnlocked;
      if (!(await validateCurrentStep({ requireCampuses }))) return;

      const institutionData = step1Ref.current?.getValues();
      if (!institutionData) {
        setError('Institution form is still loading.');
        return;
      }

      setSaving(true);
      setError(null);
      setSuccess(null);
      try {
        const hadInstitutionId = Boolean(draft.institution_id);
        let updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 1,
            data: institutionData,
            mark_complete: true,
          }),
        });
        hydrateFromDraft(updated, { syncStep: false });

        const institutionReady = Boolean(updated.institution_id);
        if (!institutionReady) {
          setError('Institution saved, but no institution id was returned. Try saving again.');
          return;
        }

        if (!hadInstitutionId && !advance) {
          markCurrentStepClean();
          setSuccess(
            'Institution saved. Campuses are now unlocked — add at least one campus below, then continue.'
          );
          window.requestAnimationFrame(() => {
            document
              .querySelector('[data-wizard-campus-lock]')
              ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          });
          return;
        }

        const campusData = step2Ref.current?.getValues() ?? [];
        const campusValid = await step2Ref.current?.validate();
        if (!campusValid) {
          setError(
            step2Ref.current?.getValidationError?.()?.trim() ||
              'Add at least one campus before continuing.'
          );
          return;
        }

        updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 2,
            data: campusData,
            mark_complete: true,
          }),
        });
        hydrateFromDraft(updated, { syncStep: false });
        markCurrentStepClean();
        setSuccess(
          advance
            ? 'Institution and campuses saved.'
            : 'Institution and campuses saved. You can continue when ready.'
        );

        if (advance && currentStep < WIZARD_UI_STEP_COUNT) {
          const nextStep = currentStep + 1;
          setCurrentStep(nextStep);
          navigate(`${institutionWizardPath(draft.id)}?step=${nextStep}`, { replace: true });
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to save step');
      } finally {
        setSaving(false);
      }
      return;
    }

    if (!(await validateCurrentStep())) return;

    const apiStep = uiStepToApiStep(currentStep);
    const hadUnsavedEdits = isCurrentStepDirty();

    if (currentStep === 4) {
      const persisted = await step5Ref.current?.persistPending?.();
      if (persisted === false) {
        setSuccess(null);
        setError(
          step5Ref.current?.getValidationError?.()?.trim() ||
            'Intake calendars were not saved. Complete term dates and levels, then try again.'
        );
        window.requestAnimationFrame(() => {
          document
            .querySelector('[data-wizard-step-error], .text-alert')
            ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
        return;
      }
    }

    let data: unknown;
    try {
      data = getCurrentStepData();
      if (currentStep === 3) {
        data = {
          courses: data,
          college_academic_overrides:
            step4Ref.current?.getCollegeAcademicOverrides?.() ??
            draft.payload?.college_academic_overrides ??
            [],
        };
      }
      if (currentStep === 5) {
        const liveOverrides = step6Ref.current?.getCollegePictureOverrides?.() ?? [];
        const draftOverrides = Array.isArray(draft.payload?.college_picture_overrides)
          ? draft.payload.college_picture_overrides
          : [];
        data = {
          pictures: data,
          college_picture_overrides: [
            ...new Set(
              [...liveOverrides, ...draftOverrides]
                .map(item => String(item).trim())
                .filter(Boolean)
            ),
          ],
        };
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
        method: 'POST',
        body: JSON.stringify({
          step: apiStep,
          data,
          mark_complete: true,
        }),
      });
      hydrateFromDraft(updated, { syncStep: false });
      markCurrentStepClean();
      setSuccess(
        hadUnsavedEdits
          ? `Step ${currentStep} saved.`
          : `Step ${currentStep} is up to date — nothing new to save.`
      );
      if (advance && currentStep < WIZARD_UI_STEP_COUNT) {
        const nextStep = currentStep + 1;
        setCurrentStep(nextStep);
        navigate(`${institutionWizardPath(draft.id)}?step=${nextStep}`, { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save step');
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    if (!draft) return;
    if (draft.status !== 'draft') {
      setError(
        'This wizard version is already published. Open Edit from Institutions to continue making changes.'
      );
      return;
    }
    if (!(await validateCurrentStep({ requireCampuses: currentStep === 1 }))) return;

    const apiStep = uiStepToApiStep(currentStep);
    let data: unknown;
    try {
      if (currentStep === 1) {
        // Persist both institution and campuses before publish from this page.
        const institutionData = step1Ref.current?.getValues();
        await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 1,
            data: institutionData,
            mark_complete: true,
          }),
        });
        data = step2Ref.current?.getValues() ?? [];
        await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: 2,
            data,
            mark_complete: true,
          }),
        });
      } else {
        if (currentStep === 4) {
          const persisted = await step5Ref.current?.persistPending?.();
          if (persisted === false) {
            setError(
              step5Ref.current?.getValidationError?.()?.trim() ||
                'Intake calendars were not saved. Complete term dates and levels, then try again.'
            );
            return;
          }
        }
        data = getCurrentStepData();
        if (currentStep === 3) {
          data = {
            courses: data,
            college_academic_overrides:
              step4Ref.current?.getCollegeAcademicOverrides?.() ??
              draft.payload?.college_academic_overrides ??
              [],
          };
        }
        if (currentStep === 5) {
          const liveOverrides = step6Ref.current?.getCollegePictureOverrides?.() ?? [];
          const draftOverrides = Array.isArray(draft.payload?.college_picture_overrides)
            ? draft.payload.college_picture_overrides
            : [];
          data = {
            pictures: data,
            college_picture_overrides: [
              ...new Set(
                [...liveOverrides, ...draftOverrides]
                  .map(item => String(item).trim())
                  .filter(Boolean)
              ),
            ],
          };
        }
        await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/steps`, {
          method: 'POST',
          body: JSON.stringify({
            step: apiStep,
            data,
            mark_complete: true,
          }),
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
      return;
    }

    setPublishing(true);
    setError(null);
    try {
      const published = await apiFetch<WizardDraft>(`academia/wizard/drafts/${draft.id}/publish`, {
        method: 'POST',
      });
      const institutionId = published.institution_id ?? draft.institution_id;
      const destination = institutionId
        ? institutionHistoryPath(institutionId)
        : INSTITUTIONS_SECTION_PATH;

      // Soft navigate after clearing any wedged unsaved-changes blocker.
      // (A blocked proceed() previously updated the URL to /history while the wizard stayed mounted.)
      skipUnsavedBlockRef.current = true;
      unsavedChanges.release();
      if (currentStep === 1) {
        step1Ref.current?.markClean?.();
        step2Ref.current?.markClean?.();
      } else {
        getActiveStepRef()?.current?.markClean?.();
      }
      // Defer one tick so blocker.reset() from release() commits before navigate.
      window.setTimeout(() => {
        navigate(destination, { replace: true });
      }, 0);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to publish';
      const institutionId = draft.institution_id;
      if (institutionId && /already published/i.test(message)) {
        skipUnsavedBlockRef.current = true;
        unsavedChanges.release();
        window.setTimeout(() => {
          navigate(institutionHistoryPath(institutionId), { replace: true });
        }, 0);
        return;
      }
      setError(message);
    } finally {
      setPublishing(false);
    }
  };

  const renderStep = () => (
    <>
      <div className={currentStep === 1 ? 'space-y-4' : 'hidden'}>
        <InstitutionWizardStep1
          key={`step1-${stepDataKey}`}
          ref={step1Ref}
          defaultValues={institutionDefaults}
          countries={countries}
          states={states}
          cities={institutionCities}
          onCountryChange={handleCountryChange}
          onStateChange={handleStateChange}
        />
        <div className="border-t border-dashed border-border-subtle pt-3">
          <div className="mb-3 rounded-xl border border-accent/20 bg-accent/5 px-3 py-2">
            <p className="text-sm font-semibold text-text-main">Campuses for this institution</p>
            <p className="text-xs text-text-muted">
              {campusesUnlocked
                ? 'Institution is saved. Add one or more campuses below, then save & continue.'
                : 'Save the institution profile above to unlock campus entry.'}
            </p>
          </div>
          <InstitutionWizardStep2
            key={`step2-${stepDataKey}-${campusesUnlocked ? 'open' : 'locked'}`}
            ref={step2Ref}
            defaultCampuses={campusDefaults}
            countries={countries}
            getInstitutionValues={getLiveInstitutionValues}
            onSaveStep={advance => void saveStep(advance)}
            saving={saving}
            embedded
            locked={!campusesUnlocked}
          />
        </div>
      </div>
      <div className={currentStep === 2 ? undefined : 'hidden'}>
        <InstitutionWizardStep3
          key={`step3-${stepDataKey}`}
          ref={step3Ref}
          defaultColleges={collegeDefaults}
          campuses={step3Campuses.length ? step3Campuses : campusDefaults}
          countries={countries}
          institutionId={draft?.institution_id ?? null}
          institutionName={institutionDefaults.name || draft?.title || 'Institution'}
          phoneCountries={phoneCountries}
          defaultPhoneCountryIso2={defaultPhoneCountryIso2}
          getInstitutionValues={getLiveInstitutionValues}
          onCollegesChange={setStep3CollegesLive}
        />
      </div>
      <div className={currentStep === 3 ? undefined : 'hidden'}>
        <InstitutionWizardStep4
          key={`step4-${stepDataKey}`}
          ref={step4Ref}
          defaultCourses={courseDefaults}
          layout="hierarchy"
          colleges={step4Academics.colleges}
          defaultCollegeOverrides={defaultCollegeOverrides}
          institutionName={
            institutionDefaults.name || draft?.title || 'University'
          }
          onPersistCourses={persistStep4Courses}
          onAddCollege={handleAcademicsAddCollege}
          onRemoveCollege={handleAcademicsRemoveCollege}
        />
      </div>
      <div className={currentStep === 4 ? undefined : 'hidden'}>
        <InstitutionWizardStep5
          key={`step5-${stepDataKey}`}
          ref={step5Ref}
          institutionId={draft?.institution_id ?? null}
          institutionName={institutionDefaults.name || draft?.title || 'Institution'}
          colleges={step5Colleges.length ? step5Colleges : collegeDefaults}
          defaultIntakes={intakeDefaults}
          onHasIntakesChange={setStep5HasLiveIntakes}
          onRemoveCollege={handleAcademicsRemoveCollege}
        />
      </div>
      <div className={currentStep === 5 ? undefined : 'hidden'}>
        <InstitutionWizardStep6
          key={`step6-${stepDataKey}`}
          ref={step6Ref}
          institutionId={draft?.institution_id ?? null}
          defaultPictures={pictureDefaults}
          isActive={currentStep === 5}
          onPicturesChange={handleGalleryPicturesChange}
          onPersistPictures={persistStep6Pictures}
          layout="hierarchy"
          colleges={mergeWizardCollegesByName(
            step5Colleges.length ? step5Colleges : collegeDefaults
          )}
          institutionName={institutionDefaults.name || draft?.title || 'University'}
          defaultCollegeOverrides={defaultCollegePictureOverrides}
          onRemoveCollege={handleAcademicsRemoveCollege}
        />
      </div>
    </>
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-muted">
        <Loader2 size={16} className="animate-spin" /> Loading wizard...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <AcademiaBreadcrumbs
        items={[
          { label: 'Academia Hub', path: '/academia' },
          { label: 'Institutions', path: INSTITUTIONS_SECTION_PATH },
          { label: wizardTitle },
        ]}
      />

      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-4 py-3 sm:px-5">
          <div>
            <h2 className="text-xl font-bold text-text-main sm:text-2xl">{wizardTitle}</h2>
            <p className="text-sm text-text-muted">
              {draft?.title} · Step {currentStep} of {WIZARD_UI_STEP_COUNT} —{' '}
              {WIZARD_STEP_LABELS[currentStep - 1]}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveStep(false)}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {currentStep === 1 && !campusesUnlocked ? 'Save institution' : 'Save step'}
            </button>
            {currentStep < WIZARD_UI_STEP_COUNT ? (
              <button
                type="button"
                disabled={saving}
                onClick={() => void saveStep(true)}
                className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
              >
                Save & continue
              </button>
            ) : null}
          </div>
        </div>

        <div className="border-b border-border-subtle px-4 pt-1 sm:px-5">
          <WizardStepNavigator
            currentStep={currentStep}
            completedSteps={completedUiSteps}
            stepsWithData={stepsWithData}
            onStepClick={step => void requestStepChange(step)}
          />
        </div>

        <div className="p-4 sm:p-5">{renderStep()}</div>

        {error ? <div className="px-4 pb-3 text-sm text-alert sm:px-5">{error}</div> : null}
        {success ? <div className="px-4 pb-3 text-sm text-emerald-700 sm:px-5">{success}</div> : null}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle px-4 py-3 sm:px-5">
          <button
            type="button"
            onClick={() => void requestLeaveWizard(INSTITUTIONS_SECTION_PATH)}
            className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
          >
            Cancel
          </button>
          <div className="flex flex-wrap gap-2">
            {currentStep > 1 ? (
              <button
                type="button"
                onClick={() => void requestStepChange(currentStep - 1)}
                className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
              >
                Back
              </button>
            ) : null}
            <button
              type="button"
              disabled={saving}
              onClick={() => void saveStep(false)}
              className="inline-flex items-center gap-2 rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-main disabled:opacity-50"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {currentStep === 1 && !campusesUnlocked ? 'Save institution' : 'Save step'}
            </button>
            {currentStep < WIZARD_UI_STEP_COUNT ? (
              <>
                {currentStep === 3 ? (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void skipCoursesStep()}
                    className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted disabled:opacity-50"
                  >
                    Skip step
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void saveStep(true)}
                  className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
                >
                  Save & continue
                </button>
              </>
            ) : draft?.status === 'draft' ? (
              <button
                type="button"
                disabled={publishing}
                onClick={() => void publish()}
                className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
              >
                {publishing ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                Publish institution
              </button>
            ) : (
              <button
                type="button"
                disabled={!draft?.institution_id || saving}
                onClick={() => {
                  if (!draft?.institution_id) return;
                  void (async () => {
                    setSaving(true);
                    setError(null);
                    try {
                      const created = await apiFetch<WizardDraft>(
                        `academia/wizard/drafts/from-institution/${draft.institution_id}`,
                        { method: 'POST' }
                      );
                      unsavedChanges.release();
                      hydrateFromDraft(created);
                      navigate(institutionWizardPath(created.id), { replace: true });
                      setSuccess('Opened a new draft from the published institution. You can edit and publish again.');
                    } catch (err) {
                      setError(
                        err instanceof Error
                          ? err.message
                          : 'Failed to open a new draft from this institution.'
                      );
                    } finally {
                      setSaving(false);
                    }
                  })();
                }}
                className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
              >
                Continue editing
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default InstitutionWizardPage;

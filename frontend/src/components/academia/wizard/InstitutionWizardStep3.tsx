import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { apiFetch } from '../../../utils/api';
import {
  formatContactList,
  normalizeEmailContacts,
  normalizeFaxContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  serializeContacts,
} from '../../../schemas/contactEntry';
import RichTextEditor from '../../ui/rich-text-editor';
import TextPromptModal from '../../TextPromptModal';
import LabeledContactListField from '../form/LabeledContactListField';
import SelectField from '../form/SelectField';
import { WEB_LINK_TYPES } from '../../../constants/contactTypes';
import type { WizardCampusItem } from '../../../schemas/wizard/step2-campus';
import type { WizardInstitutionFormValues } from '../../../schemas/wizard/step1-institution';
import {
  collegeToApiPayload,
  createEmptyWizardCollegeDraft,
  emptyWizardCollegeDraft,
  hydrateWizardCollege,
  mergeWizardCollegesByName,
  SCHOOL_COLLEGE_CATEGORY_OPTIONS,
  wizardCollegeItemSchema,
  wizardCollegesStepSchema,
  type WizardCollegeItem,
} from '../../../schemas/wizard/step3-colleges';
import type { CampusRecord } from '../../../types/institutions';
import WizardFieldError from './form/WizardFieldError';
import type { WizardStepHandle } from './form/wizardStepRef';
import {
  flushFocusedFormControl,
  getWizardListStepSnapshot,
  useWizardListStepDefaultsSync,
  useWizardStepSnapshot,
} from './form/wizardDirtyTracking';
import type { CountryRecord } from '../../../types/country';
import type { GeographyCountry } from '../../../types/geography';
import CollegeCampusLinkPanel, {
  type WizardCollegeCampusLink,
} from './CollegeCampusLinkPanel';
import {
  campusLinksMatch,
  findCampusDraftForLink,
  mergeUniqueCampusLinks,
} from './wizardCampusIdentity';
import { wizardInputClass, wizardLabelClass, wizardSchoolMetaRowClass, wizardSchoolNamingRowClass, wizardSectionTitleClass } from './form/wizardFormStyles';
import { useConfirmation } from '../../../context/ConfirmationContext';
import WizardCollegeTabBar from './WizardCollegeTabBar';
import EmptyListMessage from '../../ui/EmptyListMessage';
import ReadOnlyIdField from '../ReadOnlyIdField';

interface InstitutionWizardStep3Props {
  defaultColleges: WizardCollegeItem[];
  campuses: WizardCampusItem[];
  countries: GeographyCountry[];
  institutionId: number | null;
  institutionName?: string;
  phoneCountries: CountryRecord[];
  defaultPhoneCountryIso2: string;
  getInstitutionValues?: () => WizardInstitutionFormValues;
  onCollegesChange?: (colleges: WizardCollegeItem[]) => void;
}

const INSTITUTION_TAB = 'institution';

function collegeTabKey(college: Pick<WizardCollegeItem, 'local_id' | 'name'>, index: number) {
  return college.local_id || `college-${index}-${college.name || 'untitled'}`;
}

function normalizeCollegeNameKey(name: string | null | undefined): string {
  return (name || '').trim().toLowerCase();
}

function findDuplicateCollegeName(
  colleges: WizardCollegeItem[],
  name: string,
  excludeIndex: number | null = null
): WizardCollegeItem | undefined {
  const nameKey = normalizeCollegeNameKey(name);
  if (!nameKey) return undefined;
  return colleges.find(
    (college, index) =>
      index !== excludeIndex && normalizeCollegeNameKey(college.name) === nameKey
  );
}

function syncPrimaryCampusFields(
  linkedCampuses: WizardCollegeCampusLink[]
): Pick<
  WizardCollegeItem,
  'campus_id' | 'campus_local_id' | 'campus_name' | 'campus_address' | 'campus_location_label'
> {
  const primary = linkedCampuses[0];
  return {
    campus_id: primary?.campus_id ?? null,
    campus_local_id: primary?.campus_local_id ?? null,
    campus_name: primary?.name ?? null,
    campus_address: primary?.address ?? null,
    campus_location_label: primary?.location_label ?? null,
  };
}

/** Keep each campus link's own contact set; never overwrite edits from another campus. */
function applyLinkedCampusState(linkedCampuses: WizardCollegeCampusLink[]) {
  const normalizedLinks = linkedCampuses.map(link => ({
    ...link,
    phone_numbers: normalizePhoneContacts(link.phone_numbers),
    fax_numbers: normalizeFaxContacts(
      link.fax_numbers,
      (link as { fax_number?: string | null }).fax_number
    ),
    email_addresses: normalizeEmailContacts(link.email_addresses),
    web_links: normalizeWebLinks(link.web_links),
    cascade_contacts: Boolean(link.cascade_contacts),
  }));
  return {
    linked_campuses: normalizedLinks,
    ...syncPrimaryCampusFields(normalizedLinks),
  };
}

function contactKey(type: string, value: string) {
  return `${type}:${value.trim().toLowerCase()}`;
}

/** Drop college-wide contacts that belonged to the unlinked campus contact set. */
function scrubCollegeContactsAfterUnlink(
  college: Pick<
    WizardCollegeItem,
    'phone_numbers' | 'fax_numbers' | 'email_addresses' | 'campus_address'
  >,
  removedLink: WizardCollegeCampusLink,
  remainingLinks: WizardCollegeCampusLink[]
): Pick<
  WizardCollegeItem,
  'phone_numbers' | 'fax_numbers' | 'email_addresses' | 'campus_address'
> {
  const removedPhones = new Set(
    serializeContacts(removedLink.phone_numbers || []).map(entry =>
      contactKey(entry.type, entry.value)
    )
  );
  const removedFaxes = new Set(
    serializeContacts(removedLink.fax_numbers || []).map(entry =>
      contactKey(entry.type, entry.value)
    )
  );
  const removedEmails = new Set(
    serializeContacts(removedLink.email_addresses || []).map(entry =>
      contactKey(entry.type, entry.value)
    )
  );
  const remainingPhoneKeys = new Set(
    remainingLinks.flatMap(link =>
      serializeContacts(link.phone_numbers || []).map(entry => contactKey(entry.type, entry.value))
    )
  );
  const remainingFaxKeys = new Set(
    remainingLinks.flatMap(link =>
      serializeContacts(link.fax_numbers || []).map(entry => contactKey(entry.type, entry.value))
    )
  );
  const remainingEmailKeys = new Set(
    remainingLinks.flatMap(link =>
      serializeContacts(link.email_addresses || []).map(entry => contactKey(entry.type, entry.value))
    )
  );
  const remainingAddresses = new Set(
    remainingLinks
      .map(link => link.address?.trim().toLowerCase())
      .filter((value): value is string => Boolean(value))
  );

  const nextPhones = normalizePhoneContacts(
    serializeContacts(college.phone_numbers || []).filter(entry => {
      const key = contactKey(entry.type, entry.value);
      if (!removedPhones.has(key)) return true;
      return remainingPhoneKeys.has(key);
    })
  );

  const nextFaxes = normalizeFaxContacts(
    serializeContacts(college.fax_numbers || []).filter(entry => {
      const key = contactKey(entry.type, entry.value);
      if (!removedFaxes.has(key)) return true;
      return remainingFaxKeys.has(key);
    })
  );

  const nextEmails = normalizeEmailContacts(
    serializeContacts(college.email_addresses || []).filter(entry => {
      const key = contactKey(entry.type, entry.value);
      if (!removedEmails.has(key)) return true;
      return remainingEmailKeys.has(key);
    })
  );

  const collegeAddress = college.campus_address?.trim() || '';
  const removedAddress = removedLink.address?.trim() || '';
  const nextAddress =
    remainingLinks[0]?.address ??
    (collegeAddress &&
    removedAddress &&
    collegeAddress.toLowerCase() === removedAddress.toLowerCase() &&
    !remainingAddresses.has(collegeAddress.toLowerCase())
      ? null
      : college.campus_address ?? null);

  // If no campuses remain, drop any leftover college-wide contacts that came from that link.
  if (remainingLinks.length === 0 && removedLink.cascade_contacts) {
    return {
      campus_address: null,
      phone_numbers: createEmptyWizardCollegeDraft().phone_numbers,
      fax_numbers: createEmptyWizardCollegeDraft().fax_numbers,
      email_addresses: createEmptyWizardCollegeDraft().email_addresses,
    };
  }

  return {
    campus_address: nextAddress,
    phone_numbers: nextPhones,
    fax_numbers: nextFaxes,
    email_addresses: nextEmails,
  };
}

const InstitutionWizardStep3 = forwardRef<
  WizardStepHandle<WizardCollegeItem[]>,
  InstitutionWizardStep3Props
>(({ defaultColleges, campuses, countries, institutionId, institutionName = 'Institution', phoneCountries, defaultPhoneCountryIso2, getInstitutionValues, onCollegesChange }, ref) => {
  const openConfirm = useConfirmation();
  const [colleges, setColleges] = useState(() => mergeWizardCollegesByName(defaultColleges));
  const [activeTab, setActiveTab] = useState<string>(INSTITUTION_TAB);
  const [listError, setListError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [savedCampuses, setSavedCampuses] = useState<CampusRecord[]>([]);
  const [addCollegeOpen, setAddCollegeOpen] = useState(false);
  const [inheritInstitutionWebLinks, setInheritInstitutionWebLinks] = useState(false);

  const form = useForm({
    resolver: zodResolver(wizardCollegeItemSchema),
    defaultValues: createEmptyWizardCollegeDraft(),
    mode: 'onSubmit',
  });

  const { control, register, reset, getValues, setValue, trigger, watch, formState: { errors } } = form;
  const linkedCampuses = watch('linked_campuses') || [];
  const watchedCollegeName = watch('name');

  const activeCollegeIndex = useMemo(() => {
    if (activeTab === INSTITUTION_TAB) return null;
    const index = colleges.findIndex((college, itemIndex) => collegeTabKey(college, itemIndex) === activeTab);
    return index >= 0 ? index : null;
  }, [activeTab, colleges]);

  const editingIndex = activeCollegeIndex;

  useEffect(() => {
    if (!institutionId) {
      setSavedCampuses([]);
      return;
    }
    void apiFetch<CampusRecord[]>(`academia/campuses?institution_id=${institutionId}`)
      .then(data => setSavedCampuses(Array.isArray(data) ? data : []))
      .catch(() => setSavedCampuses([]));
  }, [institutionId]);

  const resolveCampusId = useCallback(
    (localId: string, campusName: string, draftCampusId?: number | null) => {
      if (draftCampusId) return draftCampusId;
      const draftCampus = campuses.find(campus => (campus.local_id || campus.name) === localId);
      if (draftCampus?.id) return draftCampus.id;
      const draftIndex = campuses.findIndex(
        campus => (campus.local_id || campus.name) === localId
      );
      if (draftIndex >= 0 && savedCampuses[draftIndex]?.id) {
        return savedCampuses[draftIndex].id;
      }
      return savedCampuses.find(campus => campus.name === campusName)?.id ?? null;
    },
    [campuses, savedCampuses]
  );

  const getSnapshot = useCallback(
    () =>
      getWizardListStepSnapshot(colleges, collegeToApiPayload, {
        editingIndex,
        getDraft: () => getValues() as Record<string, unknown>,
        emptyDraftTemplate: emptyWizardCollegeDraft as Record<string, unknown>,
      }),
    [colleges, editingIndex, getValues]
  );
  const { markClean, isDirty } = useWizardStepSnapshot(getSnapshot);

  const getEffectiveColleges = useCallback((): WizardCollegeItem[] => {
    if (editingIndex === null) return mergeWizardCollegesByName(colleges);
    const editedCollege = hydrateWizardCollege(getValues());
    return mergeWizardCollegesByName(
      colleges.map((college, index) => (index === editingIndex ? editedCollege : college))
    );
  }, [colleges, editingIndex, getValues]);

  useWizardListStepDefaultsSync(
    defaultColleges,
    () => {
      const next = mergeWizardCollegesByName(defaultColleges);
      setColleges(next);
      setActiveTab(INSTITUTION_TAB);
      reset(createEmptyWizardCollegeDraft());
      setDraftError(null);
    },
    markClean
  );

  useEffect(() => {
    onCollegesChange?.(colleges);
  }, [colleges, onCollegesChange]);

  // Keep the college tab label in sync with the name field while editing.
  useEffect(() => {
    if (editingIndex === null) return;
    const nextName = watchedCollegeName ?? '';
    setColleges(prev => {
      const current = prev[editingIndex];
      if (!current || current.name === nextName) return prev;
      return prev.map((item, index) =>
        index === editingIndex ? { ...item, name: nextName } : item
      );
    });

    const duplicate = findDuplicateCollegeName(colleges, nextName, editingIndex);
    setDraftError(prev => {
      if (duplicate && nextName.trim()) {
        return `A school / college named "${nextName.trim()}" already exists. Enter a unique name.`;
      }
      if (prev?.includes('already exists')) return null;
      return prev;
    });
  }, [watchedCollegeName, editingIndex, colleges]);

  useImperativeHandle(ref, () => ({
    validate: async () => {
      if (editingIndex !== null && !(await trigger())) {
        setDraftError('Please fix the highlighted fields before saving this college.');
        return false;
      }
      const nextColleges = getEffectiveColleges();
      const parsed = wizardCollegesStepSchema.safeParse(nextColleges);
      if (!parsed.success) {
        setListError(parsed.error.issues[0]?.message || 'Add at least one college.');
        return false;
      }
      if (editingIndex !== null) {
        setColleges(nextColleges);
      }
      setDraftError(null);
      setListError(null);
      return true;
    },
    getValues: () => getEffectiveColleges().map(collegeToApiPayload),
    reset: values => {
      setColleges(mergeWizardCollegesByName(values));
      setActiveTab(INSTITUTION_TAB);
      reset(createEmptyWizardCollegeDraft());
      markClean();
    },
    isDirty,
    markClean: () => {
      setActiveTab(INSTITUTION_TAB);
      reset(createEmptyWizardCollegeDraft());
      markClean();
    },
  }));

  const persistLinkedCampusState = useCallback(
    (
      nextLinks: WizardCollegeCampusLink[],
      extraFields?: Partial<WizardCollegeItem>
    ) => {
      const nextState = {
        ...applyLinkedCampusState(nextLinks),
        ...extraFields,
      };
      Object.entries(nextState).forEach(([key, value]) => {
        setValue(key as keyof WizardCollegeItem, value as never, { shouldValidate: true });
      });
      if (editingIndex !== null) {
        setColleges(prev =>
          prev.map((item, index) =>
            index === editingIndex
              ? hydrateWizardCollege({
                  ...item,
                  ...getValues(),
                  ...nextState,
                })
              : item
          )
        );
      }
    },
    [editingIndex, getValues, setValue]
  );

  const applyInstitutionWebLinks = useCallback(() => {
    if (!getInstitutionValues) return;
    const institution = getInstitutionValues();
    const inherited = normalizeWebLinks(
      institution.web_links,
      (institution as { institution_web_url?: string | null }).institution_web_url
    );
    setValue(
      'web_links',
      inherited.map(entry => ({ ...entry })),
      { shouldDirty: true, shouldValidate: true }
    );
  }, [getInstitutionValues, setValue]);

  const handleSeedWebLinks = useCallback(
    (webLinks: ReturnType<typeof normalizeWebLinks>) => {
      setInheritInstitutionWebLinks(false);
      setValue(
        'web_links',
        webLinks.map(entry => ({ ...entry })),
        { shouldDirty: true, shouldValidate: true }
      );
    },
    [setValue]
  );

  const handleLinkCampuses = (links: WizardCollegeCampusLink[]) => {
    const current = getValues('linked_campuses') || [];
    const nextLinks = links.map(link => {
      const draftCampus = findCampusDraftForLink(campuses, link);
      const campusId = resolveCampusId(
        link.campus_local_id,
        link.name,
        draftCampus?.id ?? link.campus_id
      );
      return { ...link, campus_id: campusId };
    });
    const next = mergeUniqueCampusLinks(current, nextLinks, campuses);
    if (next.length === current.length) {
      if (links.length > 0) {
        setDraftError('One or more selected campuses are already linked to this college.');
      }
      return;
    }
    setDraftError(null);
    persistLinkedCampusState(next);
  };

  const handleUnlinkCampus = (linkToRemove: WizardCollegeCampusLink) => {
    const current = getValues('linked_campuses') || [];
    const next = current.filter(item => !campusLinksMatch(item, linkToRemove));
    const scrubbed = scrubCollegeContactsAfterUnlink(
      {
        phone_numbers: getValues('phone_numbers'),
        fax_numbers: getValues('fax_numbers'),
        email_addresses: getValues('email_addresses'),
        campus_address: getValues('campus_address'),
      },
      linkToRemove,
      next
    );
    // Drop the campus link and its contact payload, and scrub college-wide copies.
    persistLinkedCampusState(next, scrubbed);
  };

  const handleUpdateLinkedCampus = (updatedLink: WizardCollegeCampusLink) => {
    const current = getValues('linked_campuses') || [];
    const next = current.map(link =>
      campusLinksMatch(link, updatedLink) ? updatedLink : link
    );
    persistLinkedCampusState(next);
  };

  const persistCurrentCollegeDraft = useCallback(async (): Promise<boolean> => {
    if (editingIndex === null) return true;
    await flushFocusedFormControl();
    const draft = hydrateWizardCollege(getValues());
    if (!draft.name.trim()) {
      // Allow switching away from a brand-new empty tab without blocking.
      return true;
    }
    if (findDuplicateCollegeName(colleges, draft.name, editingIndex)) {
      setDraftError(
        `A school / college named "${draft.name.trim()}" already exists. Enter a unique name.`
      );
      return false;
    }
    setColleges(prev =>
      prev.map((item, index) => (index === editingIndex ? draft : item))
    );
    setDraftError(null);
    // An incomplete tab must not trap the user on it. Keep the edits, flag what is
    // still missing near the tab bar, and let the step save enforce the full schema.
    const parsed = wizardCollegeItemSchema.safeParse(draft);
    setListError(
      parsed.success
        ? null
        : `"${draft.name.trim()}" is incomplete — ${
            parsed.error.issues[0]?.message || 'fix the highlighted fields'
          }`
    );
    return true;
  }, [colleges, editingIndex, getValues]);

  const openCollegeTab = useCallback(
    async (tabKey: string) => {
      if (tabKey === activeTab) return;
      if (!(await persistCurrentCollegeDraft())) return;
      if (tabKey === INSTITUTION_TAB) {
        setActiveTab(INSTITUTION_TAB);
        reset(createEmptyWizardCollegeDraft());
        setInheritInstitutionWebLinks(false);
        setDraftError(null);
        return;
      }
      const index = colleges.findIndex((college, itemIndex) => collegeTabKey(college, itemIndex) === tabKey);
      if (index < 0) {
        setActiveTab(INSTITUTION_TAB);
        reset(createEmptyWizardCollegeDraft());
        setInheritInstitutionWebLinks(false);
        return;
      }
      reset(hydrateWizardCollege(colleges[index]));
      setActiveTab(tabKey);
      setInheritInstitutionWebLinks(false);
      setDraftError(null);
    },
    [activeTab, colleges, persistCurrentCollegeDraft, reset]
  );

  const handleAddCollegeTab = async () => {
    if (!(await persistCurrentCollegeDraft())) return;
    setAddCollegeOpen(true);
  };

  const validateNewCollegeName = useCallback(
    (name: string) => {
      if (!name.trim()) {
        return 'Enter a valid school or college name.';
      }
      if (findDuplicateCollegeName(colleges, name)) {
        return `A school / college named "${name.trim()}" already exists. Enter a different name.`;
      }
      return null;
    },
    [colleges]
  );

  const handleConfirmAddCollege = (name: string) => {
    const validationError = validateNewCollegeName(name);
    if (validationError) return;

    const college = hydrateWizardCollege({
      ...createEmptyWizardCollegeDraft(),
      name: name.trim(),
    });
    const next = [...colleges, college];
    setColleges(next);
    const index = next.length - 1;
    const tabKey = collegeTabKey(next[index], index);
    reset(hydrateWizardCollege(college));
    setActiveTab(tabKey);
    setInheritInstitutionWebLinks(false);
    setAddCollegeOpen(false);
    setListError(null);
    setDraftError(null);
  };

  const handleDeleteCollege = async (college: WizardCollegeItem, index: number) => {
    const linkedNames = (college.linked_campuses || []).map(link => link.name).filter(Boolean);
    const campusNote =
      linkedNames.length > 0
        ? `\n\nLinked campuses: ${linkedNames.join(', ')}.`
        : '';
    const confirmed = await openConfirm({
      title: 'Remove school / college?',
      message: `Remove "${college.name}" from this step?${campusNote}\n\nThis only updates the wizard draft until you save the step.`,
      confirmLabel: 'Remove',
      variant: 'warning',
    });
    if (!confirmed) return;
    const removingActive = editingIndex === index;
    setColleges(prev => prev.filter((_, i) => i !== index));
    if (removingActive) {
      setActiveTab(INSTITUTION_TAB);
      reset(createEmptyWizardCollegeDraft());
      setInheritInstitutionWebLinks(false);
      setDraftError(null);
    }
  };

  const linkedCampusEmailErrors = useMemo(() => {
    const byCampus: Record<string, Array<string | undefined>> = {};
    const linkErrors = errors.linked_campuses;
    if (!Array.isArray(linkErrors)) return byCampus;

    linkedCampuses.forEach((link, linkIndex) => {
      const emailErrors = linkErrors[linkIndex]?.email_addresses;
      if (!Array.isArray(emailErrors)) return;
      byCampus[link.campus_local_id] = emailErrors.map(entry => {
        if (!entry || typeof entry !== 'object') return undefined;
        const valueError = (entry as { value?: { message?: string } }).value?.message;
        return valueError || undefined;
      });
    });
    return byCampus;
  }, [errors.linked_campuses, linkedCampuses]);

  const linkedCampusSummary = useMemo(
    () => (college: WizardCollegeItem) => {
      const links = college.linked_campuses || [];
      if (links.length === 0) return '—';
      return links.map(link => link.name).filter(Boolean).join(', ') || '—';
    },
    []
  );

  const collegePhoneSummary = useMemo(
    () => (college: WizardCollegeItem) => {
      const links = college.linked_campuses || [];
      const linkPhones = links.flatMap(link =>
        (link.phone_numbers || []).map(entry => entry.value).filter(Boolean)
      );
      if (linkPhones.length) {
        const unique = [...new Set(linkPhones.map(value => value.trim()))];
        return unique.join(', ');
      }
      return formatContactList(college.phone_numbers);
    },
    []
  );

  const collegeEmailSummary = useMemo(
    () => (college: WizardCollegeItem) => {
      const links = college.linked_campuses || [];
      const linkEmails = links.flatMap(link =>
        (link.email_addresses || []).map(entry => entry.value).filter(Boolean)
      );
      if (linkEmails.length) {
        const unique = [...new Set(linkEmails.map(value => value.trim().toLowerCase()))];
        return unique.join(', ');
      }
      return formatContactList(college.email_addresses);
    },
    []
  );

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-border-subtle bg-card p-5">
        <div className="mb-4">
          <h3 className={wizardSectionTitleClass}>Schools &amp; Colleges</h3>
          <p className="mt-1 text-sm text-text-muted">
            Institution is the primary tab. Add a school / college tab to create or edit each one.
          </p>
        </div>
        <WizardFieldError message={listError || undefined} />

        <WizardCollegeTabBar
          institutionLabel={institutionName || 'Institution'}
          institutionKey={INSTITUTION_TAB}
          colleges={colleges.map((college, index) => {
            const liveName =
              index === editingIndex ? watchedCollegeName || college.name : college.name;
            return {
              key: collegeTabKey(college, index),
              label: liveName?.trim() || 'Untitled school',
              title: liveName?.trim() || 'Untitled school / college',
              badge: college.id ? `ID ${college.id}` : null,
              removable: true,
            };
          })}
          activeKey={activeTab}
          onSelect={key => void openCollegeTab(key)}
          onAdd={() => void handleAddCollegeTab()}
          onRemove={key => {
            const index = colleges.findIndex(
              (college, itemIndex) => collegeTabKey(college, itemIndex) === key
            );
            if (index >= 0) void handleDeleteCollege(colleges[index], index);
          }}
          ariaLabel="Schools and colleges"
        />

        {activeTab === INSTITUTION_TAB ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4">
              <h4 className="text-base font-bold text-text-main">{institutionName || 'Institution'}</h4>
              {institutionId ? (
                <p className="mt-1 text-sm tabular-nums text-text-muted">
                  Institution ID {institutionId}
                </p>
              ) : null}
              <p className="mt-1 text-sm text-text-muted">
                {colleges.length === 0
                  ? 'No schools or colleges yet. Click “Add school / college” to create the first tab.'
                  : `${colleges.length} school${colleges.length === 1 ? '' : 's'} / college${
                      colleges.length === 1 ? '' : 's'
                    } configured. Select a tab to edit details, campus links, and contacts.`}
              </p>
            </div>

            {colleges.length === 0 ? (
              <EmptyListMessage message='No schools or colleges added yet. Click "Add school / college" to start.' />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {colleges.map((college, index) => (
                  <button
                    key={collegeTabKey(college, index)}
                    type="button"
                    onClick={() => void openCollegeTab(collegeTabKey(college, index))}
                    className="rounded-xl border border-border-subtle bg-card p-4 text-left hover:border-accent/40 hover:bg-accent/5"
                  >
                    <p className="font-semibold text-text-main">{college.name || 'Untitled school'}</p>
                    <p className="mt-1 text-xs tabular-nums text-text-muted">
                      {college.id ? `College ID ${college.id}` : 'Unsaved college'}
                      {institutionId ? ` · Institution ID ${institutionId}` : ''}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      {[college.code, college.category || 'College', college.dean_name]
                        .filter(Boolean)
                        .join(' · ') || 'No details yet'}
                    </p>
                    <p className="mt-2 text-xs text-text-muted">
                      Campuses: {linkedCampusSummary(college)}
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      Phone: {collegePhoneSummary(college)} · Email: {collegeEmailSummary(college)}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="mt-4">
            <h4 className="mb-3 text-base font-bold text-text-main">
              {watch('name')?.trim() || 'School / College details'}
            </h4>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {watch('id') ? <ReadOnlyIdField label="College ID" value={watch('id')} /> : null}
              {institutionId ? (
                <ReadOnlyIdField label="Institution ID" value={institutionId} />
              ) : null}
              <div className={`md:col-span-2 ${wizardSchoolNamingRowClass}`}>
                <div>
                  <label className={wizardLabelClass}>School / College Code</label>
                  <input
                    {...register('code')}
                    maxLength={50}
                    placeholder="e.g. ENG"
                    className={wizardInputClass(Boolean(errors.code))}
                  />
                  <WizardFieldError message={errors.code?.message} />
                </div>
                <div>
                  <label className={wizardLabelClass}>School / College name *</label>
                  <input {...register('name')} className={wizardInputClass(Boolean(errors.name))} />
                  <WizardFieldError message={errors.name?.message} />
                </div>
                <Controller
                  control={control}
                  name="category"
                  render={({ field, fieldState }) => (
                    <div>
                      <SelectField
                        label="Category"
                        required
                        value={field.value || 'College'}
                        onChange={field.onChange}
                        placeholder="Select category..."
                        options={[...SCHOOL_COLLEGE_CATEGORY_OPTIONS]}
                      />
                      <WizardFieldError message={fieldState.error?.message} />
                    </div>
                  )}
                />
              </div>
              <div className={`md:col-span-2 ${wizardSchoolMetaRowClass}`}>
                <div>
                  <label className={wizardLabelClass}>Dean name</label>
                  <input
                    {...register('dean_name')}
                    className={wizardInputClass(Boolean(errors.dean_name))}
                  />
                </div>
              </div>
              <div className="md:col-span-2">
                <label className="mb-3 flex cursor-pointer items-start gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2">
                  <input
                    type="checkbox"
                    checked={inheritInstitutionWebLinks}
                    onChange={event => {
                      const checked = event.target.checked;
                      setInheritInstitutionWebLinks(checked);
                      if (checked) applyInstitutionWebLinks();
                    }}
                    className="mt-0.5 accent-accent"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-text-main">
                      Inherit institution web URLs
                    </span>
                    <span className="block text-xs text-text-muted">
                      Copies institution web URLs into this college. You can edit the copied values
                      below, or seed from a linked campus instead.
                    </span>
                  </span>
                </label>
                <Controller
                  control={control}
                  name="web_links"
                  render={({ field }) => (
                    <LabeledContactListField
                      label="College web URLs"
                      items={field.value}
                      onChange={next => {
                        setInheritInstitutionWebLinks(false);
                        field.onChange(next);
                      }}
                      typeOptions={WEB_LINK_TYPES}
                      valuePlaceholder="https://..."
                      valueInputType="url"
                      addLabel="Add web links"
                      errors={(field.value || []).map((_, index) => {
                        const row = errors.web_links?.[index] as
                          | { value?: { message?: string }; type?: { message?: string } }
                          | undefined;
                        return row?.value?.message || row?.type?.message;
                      })}
                      typeSelectWidthClass="w-full sm:w-[8.75rem]"
                      maxLength={250}
                      fullWidth
                    />
                  )}
                />
              </div>

              <CollegeCampusLinkPanel
                campuses={campuses}
                countries={countries}
                linkedCampuses={linkedCampuses}
                onLinkCampuses={handleLinkCampuses}
                onUnlinkCampus={handleUnlinkCampus}
                onUpdateLinkedCampus={handleUpdateLinkedCampus}
                onSeedWebLinks={handleSeedWebLinks}
                phoneCountries={phoneCountries}
                defaultPhoneCountryIso2={defaultPhoneCountryIso2}
                error={
                  typeof errors.linked_campuses?.message === 'string'
                    ? errors.linked_campuses.message
                    : undefined
                }
                emailErrorsByCampus={linkedCampusEmailErrors}
              />

              <div className="md:col-span-2">
                <Controller
                  control={control}
                  name="long_description"
                  render={({ field, fieldState }) => (
                    <RichTextEditor
                      label="Long description"
                      content={field.value || ''}
                      onChange={field.onChange}
                      maxLength={5000}
                      error={fieldState.error?.message}
                    />
                  )}
                />
              </div>
            </div>

            <div className="mt-5 space-y-2">
              <WizardFieldError message={draftError || undefined} />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void openCollegeTab(INSTITUTION_TAB)}
                  className="rounded-xl border border-border-subtle px-4 py-2 text-sm font-semibold text-text-muted"
                >
                  Back to institution
                </button>
              </div>
              <p className="text-xs text-text-muted">
                Edits on this tab are kept when you switch tabs or use Save / Save &amp; continue
                above. Additional campuses belong on the same school / college via Campus linking —
                not as a second tab.
              </p>
            </div>
          </div>
        )}
      </section>

      <TextPromptModal
        open={addCollegeOpen}
        title="Add school / college"
        message={
          'Enter a valid school or college name.\n\n' +
          'Each school / college needs its own unique name. Duplicate names are not allowed.'
        }
        label="School / College name *"
        placeholder="e.g. School of Engineering"
        defaultValue=""
        confirmLabel="Add"
        cancelLabel="Cancel"
        validate={validateNewCollegeName}
        onConfirm={handleConfirmAddCollege}
        onCancel={() => setAddCollegeOpen(false)}
      />
    </div>
  );
});

InstitutionWizardStep3.displayName = 'InstitutionWizardStep3';
export default InstitutionWizardStep3;

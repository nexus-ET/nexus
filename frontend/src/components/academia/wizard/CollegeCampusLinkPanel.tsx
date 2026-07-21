import { useEffect, useMemo, useState } from 'react';
import { Building2, ChevronDown, ChevronRight, Link2, RefreshCw, Unlink } from 'lucide-react';

import { apiFetch } from '../../../utils/api';
import { fetchAcademiaListItems } from '../../../utils/academiaList';
import {
  EMAIL_CONTACT_TYPES,
  FAX_CONTACT_TYPES,
  PHONE_CONTACT_TYPES,
  WEB_LINK_TYPES,
} from '../../../constants/contactTypes';
import {
  formatContactList,
  normalizeEmailContacts,
  normalizeFaxContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  type ContactEntry,
} from '../../../schemas/contactEntry';
import { PHONE_LOCAL_PLACEHOLDER } from '../../../utils/phoneCountry';
import type { WizardCampusItem } from '../../../schemas/wizard/step2-campus';
import type { CountryRecord } from '../../../types/country';
import type { GeographyCountry } from '../../../types/geography';
import { CharCountInput } from '../form/CharCountField';
import LabeledContactListField from '../form/LabeledContactListField';
import SearchableSelect from '../SearchableSelect';
import {
  wizardContactRowClass,
  wizardGeoRowClass,
  wizardLabelClass,
} from '../wizard/form/wizardFormStyles';
import {
  findCampusDraftByKey,
  findCampusDraftForLink,
  isWizardCampusLinked,
  resolveCampusDraftKey,
} from './wizardCampusIdentity';
import { useConfirmation } from '../../../context/ConfirmationContext';
import EmptyListMessage from '../../ui/EmptyListMessage';

export interface WizardCollegeCampusLink {
  campus_local_id: string;
  campus_id?: number | null;
  name: string;
  address?: string | null;
  country_id?: number | null;
  state_id?: number | null;
  location_id?: number | null;
  country_name?: string | null;
  state_name?: string | null;
  city_name?: string | null;
  zipcode?: string | null;
  location_label?: string | null;
  phone_numbers?: ContactEntry[];
  fax_numbers?: ContactEntry[];
  email_addresses?: ContactEntry[];
  web_links?: ContactEntry[];
  cascade_contacts?: boolean;
}

interface GeographyOption {
  id: number;
  name: string;
}

interface CollegeCampusLinkPanelProps {
  campuses: WizardCampusItem[];
  countries: GeographyCountry[];
  linkedCampuses: WizardCollegeCampusLink[];
  onLinkCampuses: (links: WizardCollegeCampusLink[]) => void;
  onUnlinkCampus: (link: WizardCollegeCampusLink) => void;
  onUpdateLinkedCampus: (link: WizardCollegeCampusLink) => void;
  phoneCountries: CountryRecord[];
  defaultPhoneCountryIso2: string;
  error?: string;
  /** Per linked-campus email field errors, keyed by campus_local_id. */
  emailErrorsByCampus?: Record<string, Array<string | undefined>>;
  /** Called when campus seed/copy also inherits web URLs into the college-level field. */
  onSeedWebLinks?: (webLinks: ContactEntry[]) => void;
}

function buildLocationLabel(parts: {
  city?: string | null;
  state?: string | null;
  country?: string | null;
  zipcode?: string | null;
}): string {
  return [parts.city, parts.state, parts.country, parts.zipcode].filter(Boolean).join(' · ') || '—';
}

const CampusGeographyDetails: React.FC<{
  address?: string | null;
  country?: string | null;
  state?: string | null;
  city?: string | null;
  zipcode?: string | null;
  phoneNumbers?: ContactEntry[] | null;
  faxNumbers?: ContactEntry[] | null;
  emailAddresses?: ContactEntry[] | null;
  webLinks?: ContactEntry[] | null;
}> = ({
  address,
  country,
  state,
  city,
  zipcode,
  phoneNumbers,
  faxNumbers,
  emailAddresses,
  webLinks,
}) => {
  const fieldClass = 'min-w-0';
  const labelClass = 'text-[11px] font-semibold uppercase tracking-wide text-text-muted';
  const valueClass = 'truncate text-sm text-text-main';
  const phoneDisplay = formatContactList(phoneNumbers || []);
  const faxDisplay = formatContactList(faxNumbers || []);
  const emailDisplay = formatContactList(emailAddresses || []);
  const webDisplay = formatContactList(webLinks || []);

  return (
    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 md:grid-cols-4">
      <div className={`${fieldClass} col-span-2 md:col-span-4`}>
        <dt className={labelClass}>Address</dt>
        <dd className={`${valueClass} whitespace-normal break-words`} title={address?.trim() || undefined}>
          {address?.trim() || '—'}
        </dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>Country</dt>
        <dd className={valueClass}>{country?.trim() || '—'}</dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>State</dt>
        <dd className={valueClass}>{state?.trim() || '—'}</dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>City</dt>
        <dd className={valueClass}>{city?.trim() || '—'}</dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>Zipcode</dt>
        <dd className={valueClass}>{zipcode?.trim() || '—'}</dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>Phone</dt>
        <dd className={valueClass} title={phoneDisplay === '—' ? undefined : phoneDisplay}>
          {phoneDisplay}
        </dd>
      </div>
      <div className={fieldClass}>
        <dt className={labelClass}>Fax</dt>
        <dd className={valueClass} title={faxDisplay === '—' ? undefined : faxDisplay}>
          {faxDisplay}
        </dd>
      </div>
      <div className={`${fieldClass} col-span-2`}>
        <dt className={labelClass}>Email</dt>
        <dd className={valueClass} title={emailDisplay === '—' ? undefined : emailDisplay}>
          {emailDisplay}
        </dd>
      </div>
      <div className={`${fieldClass} col-span-2 md:col-span-4`}>
        <dt className={labelClass}>Web URLs</dt>
        <dd className={`${valueClass} whitespace-normal break-words`} title={webDisplay === '—' ? undefined : webDisplay}>
          {webDisplay}
        </dd>
      </div>
    </dl>
  );
};

const LinkedCampusAddressEditor: React.FC<{
  link: WizardCollegeCampusLink;
  countries: GeographyCountry[];
  onChange: (patch: Partial<WizardCollegeCampusLink>) => void;
}> = ({ link, countries, onChange }) => {
  const [states, setStates] = useState<GeographyOption[]>([]);
  const [cities, setCities] = useState<GeographyOption[]>([]);

  const countryOptions = useMemo(
    () =>
      countries.map(country => ({
        value: String(country.id),
        label: country.name,
      })),
    [countries]
  );
  const stateOptions = useMemo(
    () => states.map(state => ({ value: String(state.id), label: state.name })),
    [states]
  );
  const cityOptions = useMemo(
    () => cities.map(city => ({ value: String(city.id), label: city.name })),
    [cities]
  );

  useEffect(() => {
    const countryId = link.country_id ?? null;
    if (!countryId) {
      setStates([]);
      return;
    }
    let cancelled = false;
    void fetchAcademiaListItems<GeographyOption>('academia/states', {
      country_id: String(countryId),
    })
      .then(data => {
        if (!cancelled) setStates(data);
      })
      .catch(() => {
        if (!cancelled) setStates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [link.country_id]);

  useEffect(() => {
    const countryId = link.country_id ?? null;
    const stateId = link.state_id ?? null;
    if (!countryId) {
      setCities([]);
      return;
    }
    let cancelled = false;
    void fetchAcademiaListItems<GeographyOption>('academia/cities', {
      country_id: String(countryId),
      state_id: stateId ? String(stateId) : undefined,
    })
      .then(data => {
        if (!cancelled) setCities(data);
      })
      .catch(() => {
        if (!cancelled) setCities([]);
      });
    return () => {
      cancelled = true;
    };
  }, [link.country_id, link.state_id]);

  const resolveCountryName = (countryId: number | null | undefined) =>
    countries.find(item => item.id === countryId)?.name || null;

  return (
    <div className="mt-4 space-y-3">
      <CharCountInput
        label={`Campus address · ${link.name}`}
        maxLength={200}
        value={link.address || ''}
        onChange={value => onChange({ address: value || null })}
        placeholder="Street address, building, or campus location"
      />

      <div className={wizardGeoRowClass}>
        <SearchableSelect
          label="Country"
          value={link.country_id ? String(link.country_id) : ''}
          options={countryOptions}
          onChange={value => {
            const nextCountryId = value ? Number(value) : null;
            const countryName =
              countryOptions.find(option => option.value === value)?.label ||
              resolveCountryName(nextCountryId);
            onChange({
              country_id: nextCountryId,
              country_name: countryName,
              state_id: null,
              state_name: null,
              location_id: null,
              city_name: null,
              location_label: buildLocationLabel({
                country: countryName,
                zipcode: link.zipcode,
              }),
            });
          }}
          placeholder="Select country..."
        />

        <SearchableSelect
          label="State"
          value={link.state_id ? String(link.state_id) : ''}
          options={stateOptions}
          onChange={value => {
            const nextStateId = value ? Number(value) : null;
            const stateName =
              stateOptions.find(option => option.value === value)?.label || null;
            onChange({
              state_id: nextStateId,
              state_name: stateName,
              location_id: null,
              city_name: null,
              location_label: buildLocationLabel({
                state: stateName,
                country: link.country_name,
                zipcode: link.zipcode,
              }),
            });
          }}
          placeholder={link.country_id ? 'Select state...' : 'Select country first'}
          disabled={!link.country_id}
        />

        <SearchableSelect
          label="City"
          value={link.location_id ? String(link.location_id) : ''}
          options={cityOptions}
          onChange={value => {
            const nextCityId = value ? Number(value) : null;
            const cityName =
              cityOptions.find(option => option.value === value)?.label || null;
            onChange({
              location_id: nextCityId,
              city_name: cityName,
              location_label: buildLocationLabel({
                city: cityName,
                state: link.state_name,
                country: link.country_name,
                zipcode: link.zipcode,
              }),
            });
          }}
          placeholder={link.state_id ? 'Select city...' : 'Select state first'}
          disabled={!link.state_id}
        />

        <CharCountInput
          label="Zipcode"
          maxLength={10}
          value={link.zipcode || ''}
          onChange={value => {
            const zipcode = value || null;
            onChange({
              zipcode,
              location_label: buildLocationLabel({
                city: link.city_name,
                state: link.state_name,
                country: link.country_name,
                zipcode,
              }),
            });
          }}
          placeholder="e.g. 02139"
        />
      </div>
    </div>
  );
};

const CollegeCampusLinkPanel: React.FC<CollegeCampusLinkPanelProps> = ({
  campuses,
  countries,
  linkedCampuses,
  onLinkCampuses,
  onUnlinkCampus,
  onUpdateLinkedCampus,
  phoneCountries,
  defaultPhoneCountryIso2,
  error,
  emailErrorsByCampus,
  onSeedWebLinks,
}) => {
  const openConfirm = useConfirmation();
  const [expanded, setExpanded] = useState(true);
  const [selectedLocalIds, setSelectedLocalIds] = useState<string[]>([]);
  const [cascadeContactsOnLink, setCascadeContactsOnLink] = useState(true);
  const [linkNotice, setLinkNotice] = useState<string | null>(null);
  const [lookupStates, setLookupStates] = useState<GeographyOption[]>([]);
  const [lookupCities, setLookupCities] = useState<GeographyOption[]>([]);

  useEffect(() => {
    void Promise.all([
      fetchAcademiaListItems<GeographyOption>('academia/states'),
      fetchAcademiaListItems<GeographyOption>('academia/cities'),
    ])
      .then(([stateData, cityData]) => {
        setLookupStates(stateData);
        setLookupCities(cityData);
      })
      .catch(() => {
        setLookupStates([]);
        setLookupCities([]);
      });
  }, []);

  const resolveCampusGeography = useMemo(
    () =>
      (campus: WizardCampusItem) => {
        const country =
          campus.country_label ||
          countries.find(item => item.id === campus.country_id)?.name ||
          null;
        const state =
          campus.state_label ||
          lookupStates.find(item => item.id === campus.state_id)?.name ||
          null;
        const city =
          campus.city_label ||
          lookupCities.find(item => item.id === campus.location_id)?.name ||
          null;
        const zipcode = campus.zipcode || null;
        const streetAddress = campus.address || null;
        return {
          address: streetAddress,
          country_id: campus.country_id ?? null,
          state_id: campus.state_id ?? null,
          location_id: campus.location_id ?? null,
          country_name: country,
          state_name: state,
          city_name: city,
          zipcode,
          location_label: buildLocationLabel({
            city,
            state,
            country,
            zipcode,
          }),
        };
      },
    [countries, lookupCities, lookupStates]
  );

  // Backfill geo IDs / street address on older linked campuses that only stored labels.
  useEffect(() => {
    for (const link of linkedCampuses) {
      const campus = findCampusDraftForLink(campuses, link);
      if (!campus) continue;
      const geography = resolveCampusGeography(campus);
      const next = {
        address: link.address ?? geography.address,
        country_id: link.country_id ?? geography.country_id,
        state_id: link.state_id ?? geography.state_id,
        location_id: link.location_id ?? geography.location_id,
        country_name: link.country_name || geography.country_name,
        state_name: link.state_name || geography.state_name,
        city_name: link.city_name || geography.city_name,
        zipcode: link.zipcode ?? geography.zipcode,
        location_label: link.location_label || geography.location_label,
      };
      const changed =
        next.address !== (link.address ?? null) ||
        next.country_id !== (link.country_id ?? null) ||
        next.state_id !== (link.state_id ?? null) ||
        next.location_id !== (link.location_id ?? null) ||
        next.zipcode !== (link.zipcode ?? null) ||
        next.country_name !== (link.country_name ?? null) ||
        next.state_name !== (link.state_name ?? null) ||
        next.city_name !== (link.city_name ?? null);
      if (!changed) continue;
      onUpdateLinkedCampus({ ...link, ...next });
    }
  }, [campuses, linkedCampuses, onUpdateLinkedCampus, resolveCampusGeography]);

  const seedContactsFromCampus = (
    link: WizardCollegeCampusLink,
    campus: WizardCampusItem
  ): WizardCollegeCampusLink => {
    const geography = resolveCampusGeography(campus);
    return {
      ...link,
      name: campus.name || link.name,
      ...geography,
      phone_numbers: normalizePhoneContacts(campus.phone_numbers),
      fax_numbers: normalizeFaxContacts(campus.fax_numbers, (campus as { fax_number?: string | null }).fax_number),
      email_addresses: normalizeEmailContacts(campus.email_addresses),
      web_links: normalizeWebLinks(campus.web_links),
      cascade_contacts: true,
    };
  };

  const campusLinkFromDraft = (
    campus: WizardCampusItem,
    savedCampusId?: number | null,
    cascadeContacts = false
  ): WizardCollegeCampusLink => {
    const geography = resolveCampusGeography(campus);
    const base: WizardCollegeCampusLink = {
      campus_local_id: resolveCampusDraftKey(campus),
      campus_id: savedCampusId ?? campus.id ?? null,
      name: campus.name,
      ...geography,
      phone_numbers: cascadeContacts
        ? normalizePhoneContacts(campus.phone_numbers)
        : normalizePhoneContacts([]),
      fax_numbers: cascadeContacts
        ? normalizeFaxContacts(campus.fax_numbers, (campus as { fax_number?: string | null }).fax_number)
        : normalizeFaxContacts([]),
      email_addresses: cascadeContacts
        ? normalizeEmailContacts(campus.email_addresses)
        : normalizeEmailContacts([]),
      web_links: cascadeContacts
        ? normalizeWebLinks(campus.web_links)
        : normalizeWebLinks([]),
      cascade_contacts: cascadeContacts,
    };
    return base;
  };

  const mergeWebLinksFromCampuses = (items: WizardCampusItem[]): ContactEntry[] => {
    const seen = new Set<string>();
    const merged: ContactEntry[] = [];
    for (const campus of items) {
      for (const entry of normalizeWebLinks(campus.web_links)) {
        const value = entry.value.trim();
        if (!value) continue;
        const key = `${entry.type}:${value.toLowerCase()}`;
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push({ ...entry });
      }
    }
    return merged.length > 0 ? merged : normalizeWebLinks([]);
  };

  useEffect(() => {
    setSelectedLocalIds(prev =>
      prev.filter(id => {
        const campus = findCampusDraftByKey(campuses, id);
        return campus ? !isWizardCampusLinked(campus, linkedCampuses) : false;
      })
    );
  }, [linkedCampuses, campuses]);

  const availableToLink = useMemo(
    () => campuses.filter(campus => !isWizardCampusLinked(campus, linkedCampuses)),
    [campuses, linkedCampuses]
  );

  const toggleSelection = (localId: string) => {
    const campus = findCampusDraftByKey(campuses, localId);
    if (campus && isWizardCampusLinked(campus, linkedCampuses)) {
      setLinkNotice('This campus is already linked to this college.');
      return;
    }
    setLinkNotice(null);
    setSelectedLocalIds(prev =>
      prev.includes(localId) ? prev.filter(id => id !== localId) : [...prev, localId]
    );
  };

  const handleLink = () => {
    const toLinkIds: string[] = [];
    const alreadyLinked: string[] = [];

    for (const id of selectedLocalIds) {
      const campus = findCampusDraftByKey(campuses, id);
      if (!campus) continue;
      if (isWizardCampusLinked(campus, linkedCampuses)) {
        alreadyLinked.push(id);
        continue;
      }
      toLinkIds.push(resolveCampusDraftKey(campus));
    }

    if (toLinkIds.length === 0) {
      setLinkNotice(
        alreadyLinked.length > 0
          ? 'Selected campus(es) are already linked to this college.'
          : 'Select at least one campus to link.'
      );
      setSelectedLocalIds([]);
      return;
    }

    if (alreadyLinked.length > 0) {
      setLinkNotice(
        `${alreadyLinked.length} campus${alreadyLinked.length === 1 ? ' is' : 'es are'} already linked and ${alreadyLinked.length === 1 ? 'was' : 'were'} skipped.`
      );
    } else {
      setLinkNotice(null);
    }

    const sourceCampuses = toLinkIds
      .map(localId => campuses.find(item => resolveCampusDraftKey(item) === localId))
      .filter((campus): campus is WizardCampusItem => Boolean(campus));
    const links = sourceCampuses.map(campus =>
      campusLinkFromDraft(campus, undefined, cascadeContactsOnLink)
    );
    if (links.length === 0) return;
    onLinkCampuses(links);
    if (cascadeContactsOnLink) {
      onSeedWebLinks?.(mergeWebLinksFromCampuses(sourceCampuses));
    }
    setSelectedLocalIds([]);
  };

  const handleCopyFromCampus = (link: WizardCollegeCampusLink) => {
    const draftCampus = findCampusDraftForLink(campuses, link);
    if (!draftCampus) {
      setLinkNotice(`Could not find campus details for "${link.name}" to copy.`);
      return;
    }
    const seeded = seedContactsFromCampus(link, draftCampus);
    onUpdateLinkedCampus(seeded);
    onSeedWebLinks?.(normalizeWebLinks(draftCampus.web_links).map(entry => ({ ...entry })));
    setLinkNotice(null);
  };

  const handleToggleCascade = (link: WizardCollegeCampusLink, enabled: boolean) => {
    if (enabled) {
      handleCopyFromCampus({ ...link, cascade_contacts: true });
      return;
    }
    onUpdateLinkedCampus({ ...link, cascade_contacts: false });
  };

  const patchLink = (link: WizardCollegeCampusLink, patch: Partial<WizardCollegeCampusLink>) => {
    onUpdateLinkedCampus({ ...link, ...patch });
  };

  const handleUnlink = async (link: WizardCollegeCampusLink) => {
    const confirmed = await openConfirm({
      title: 'Unlink campus?',
      message: `Unlink campus "${link.name}" from this college?\n\nCollege contact details saved for this campus link will also be removed from the draft.`,
      confirmLabel: 'Unlink',
      variant: 'warning',
    });
    if (!confirmed) return;
    setLinkNotice(null);
    onUnlinkCampus(link);
  };

  return (
    <div className="md:col-span-2 rounded-2xl border border-border-subtle bg-surface-bg/50">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div>
          <p className={wizardLabelClass}>Campus linking</p>
          <p className="text-xs text-text-muted">
            Link one or more campuses and maintain a separate college contact set (including web URLs)
            for each.
          </p>
        </div>
        {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
      </button>

      {expanded ? (
        <div className="space-y-4 border-t border-border-subtle px-4 py-4">
          {campuses.length === 0 ? (
            <p className="text-sm text-amber-700">
              Add at least one campus in Step 2 before linking colleges to a campus.
            </p>
          ) : (
            <>
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  Available campuses
                </p>
                {availableToLink.length === 0 ? (
                  <p className="text-sm text-text-muted">
                    All institution campuses are already linked to this college.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {availableToLink.map(campus => {
                      const localId = resolveCampusDraftKey(campus);
                      const isSelected = selectedLocalIds.includes(localId);
                      const geography = resolveCampusGeography(campus);
                      return (
                        <label
                          key={localId}
                          className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 ${
                            isSelected
                              ? 'border-accent bg-accent/5'
                              : 'border-border-subtle bg-card'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelection(localId)}
                            className="mt-1 accent-accent"
                          />
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-text-main">{campus.name}</p>
                            <CampusGeographyDetails
                              address={campus.address}
                              country={geography.country_name}
                              state={geography.state_name}
                              city={geography.city_name}
                              zipcode={geography.zipcode}
                              phoneNumbers={campus.phone_numbers}
                              faxNumbers={campus.fax_numbers}
                              emailAddresses={campus.email_addresses}
                              webLinks={campus.web_links}
                            />
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border-subtle bg-card px-3 py-3">
                  <input
                    type="checkbox"
                    checked={cascadeContactsOnLink}
                    onChange={event => setCascadeContactsOnLink(event.target.checked)}
                    className="mt-1 accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-text-main">
                      Seed college contacts and web URLs from each selected campus
                    </span>
                    <span className="mt-0.5 block text-xs text-text-muted">
                      Copies address, phone, fax, email, and web URLs into that campus link as a
                      starting point. You can override or add more afterward. Every campus keeps its
                      own set; college web URLs are also updated from the selected campuses.
                    </span>
                  </span>
                </label>
                <button
                  type="button"
                  disabled={selectedLocalIds.length === 0}
                  onClick={handleLink}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-text-dark-bg disabled:opacity-50"
                >
                  <Link2 size={16} />
                  Link selected campus{selectedLocalIds.length === 1 ? '' : 'es'}
                </button>
                {linkNotice ? <p className="text-sm text-amber-700">{linkNotice}</p> : null}
              </div>

              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                  Campus contact sets for this college
                </p>
                {linkedCampuses.length === 0 ? (
                  <EmptyListMessage
                    compact
                    message="No campuses linked yet. Select one or more campuses above and click link."
                  />
                ) : (
                  <div className="space-y-4">
                    <p className="text-xs text-text-muted">
                      These are contact details for the same college at each campus — not separate
                      colleges.
                    </p>
                    {linkedCampuses.map(link => {
                      const phones = normalizePhoneContacts(link.phone_numbers);
                      const emails = normalizeEmailContacts(link.email_addresses);
                      return (
                        <div
                          key={link.campus_local_id}
                          className="rounded-xl border border-accent/20 bg-card p-4"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="flex min-w-0 items-start gap-2">
                              <Building2 size={16} className="mt-0.5 shrink-0 text-accent" />
                              <div>
                                <p className="font-semibold text-text-main">{link.name}</p>
                                <p className="text-xs text-text-muted">
                                  {[link.city_name, link.state_name, link.country_name, link.zipcode]
                                    .filter(Boolean)
                                    .join(' · ') || 'Campus geography'}
                                </p>
                                {link.cascade_contacts ? (
                                  <p className="mt-1 text-xs font-semibold text-emerald-700">
                                    Seeded from campus — editable overrides allowed
                                  </p>
                                ) : null}
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => handleCopyFromCampus(link)}
                                className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-2 py-1 text-xs font-semibold text-text-main hover:bg-surface-bg"
                              >
                                <RefreshCw size={14} />
                                Copy from campus
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleUnlink(link)}
                                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                              >
                                <Unlink size={14} />
                                Unlink
                              </button>
                            </div>
                          </div>

                          <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-lg border border-border-subtle bg-surface-bg/50 px-3 py-2">
                            <input
                              type="checkbox"
                              checked={Boolean(link.cascade_contacts)}
                              onChange={event =>
                                handleToggleCascade(link, event.target.checked)
                              }
                              className="mt-0.5 accent-accent"
                            />
                            <span className="text-xs text-text-muted">
                              <span className="font-semibold text-text-main">
                                Use this campus as the contact and web URL seed
                              </span>{' '}
                              — fills this campus link only. Other linked campuses are unchanged.
                              College web URLs are refreshed from this campus.
                            </span>
                          </label>

                          <LinkedCampusAddressEditor
                            link={link}
                            countries={countries}
                            onChange={patch => patchLink(link, patch)}
                          />

                          <div className="mt-4 space-y-3">
                            <div className={wizardContactRowClass}>
                              <LabeledContactListField
                                label={`Phone numbers · ${link.name}`}
                                items={phones}
                                onChange={next => patchLink(link, { phone_numbers: next })}
                                typeOptions={PHONE_CONTACT_TYPES}
                                valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
                                valueInputType="tel"
                                addLabel="Add phone number"
                                phoneCountries={phoneCountries}
                                defaultPhoneCountryIso2={defaultPhoneCountryIso2}
                                fullWidth={false}
                              />

                              <LabeledContactListField
                                label={`Fax numbers · ${link.name}`}
                                items={normalizeFaxContacts(link.fax_numbers)}
                                onChange={next => patchLink(link, { fax_numbers: next })}
                                typeOptions={FAX_CONTACT_TYPES}
                                valuePlaceholder={PHONE_LOCAL_PLACEHOLDER}
                                valueInputType="tel"
                                addLabel="Add fax number"
                                phoneCountries={phoneCountries}
                                defaultPhoneCountryIso2={defaultPhoneCountryIso2}
                                fullWidth={false}
                              />

                              <LabeledContactListField
                                label={`Email addresses · ${link.name}`}
                                items={emails}
                                onChange={next => patchLink(link, { email_addresses: next })}
                                typeOptions={EMAIL_CONTACT_TYPES}
                                valuePlaceholder="college@university.edu"
                                valueInputType="email"
                                addLabel="Add email address"
                                errors={emailErrorsByCampus?.[link.campus_local_id]}
                                typeSelectWidthClass="w-full sm:w-[9.5rem]"
                                fullWidth={false}
                              />
                            </div>

                            <LabeledContactListField
                              label={`Web URLs · ${link.name}`}
                              items={normalizeWebLinks(link.web_links)}
                              onChange={next => patchLink(link, { web_links: next })}
                              typeOptions={WEB_LINK_TYPES}
                              valuePlaceholder="https://..."
                              valueInputType="url"
                              addLabel="Add web links"
                              typeSelectWidthClass="w-full sm:w-[8.75rem]"
                              maxLength={250}
                              fullWidth
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
          {error ? <p className="text-sm text-alert">{error}</p> : null}
        </div>
      ) : null}
    </div>
  );
};

export default CollegeCampusLinkPanel;

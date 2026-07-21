import { z } from 'zod';

import { emptyToNull, richTextField } from './shared';
import {
  contactEntrySchema,
  createDefaultEmailContacts,
  createDefaultFaxContacts,
  createDefaultPhoneContacts,
  createDefaultWebLinks,
  isValidEmailAddress,
  normalizeEmailContacts,
  normalizeFaxContacts,
  normalizePhoneContacts,
  normalizeWebLinks,
  optionalEmailContactListSchema,
  primaryWebUrl,
  serializeContacts,
  type ContactEntry,
  webLinkListSchema,
} from '../contactEntry';

export const SCHOOL_COLLEGE_CATEGORY_OPTIONS = [
  { value: 'College', label: 'College' },
  { value: 'Professional School', label: 'Professional School' },
  { value: 'Graduate School', label: 'Graduate School' },
  { value: 'Residential College', label: 'Residential College' },
] as const;

export type SchoolCollegeCategory = (typeof SCHOOL_COLLEGE_CATEGORY_OPTIONS)[number]['value'];

const schoolCollegeCategorySchema = z.enum([
  'College',
  'Professional School',
  'Graduate School',
  'Residential College',
]);

const linkedCampusPhoneSchema = z.array(contactEntrySchema).optional().default([]);
const linkedCampusFaxSchema = z.array(contactEntrySchema).optional().default([]);
const linkedCampusEmailSchema = optionalEmailContactListSchema.optional().default([]);

export const wizardCollegeItemSchema = z
  .object({
    local_id: z.string().optional(),
    code: z.preprocess(emptyToNull, z.string().max(50).nullable().optional()),
    name: z.string().min(1, 'School / College name is required').max(255),
    category: schoolCollegeCategorySchema.default('College'),
    dean_name: z.preprocess(emptyToNull, z.string().max(255).nullable().optional()),
    web_links: webLinkListSchema,
    campus_id: z.number().int().positive().optional().nullable(),
    campus_local_id: z.string().optional().nullable(),
    campus_name: z.string().optional().nullable(),
    campus_address: z.preprocess(emptyToNull, z.string().nullable().optional()),
    campus_location_label: z.preprocess(emptyToNull, z.string().nullable().optional()),
    linked_campuses: z
      .array(
        z.object({
          campus_local_id: z.string(),
          campus_id: z.number().int().positive().optional().nullable(),
          name: z.string(),
          address: z.preprocess(emptyToNull, z.string().nullable().optional()),
          country_id: z.number().int().positive().optional().nullable(),
          state_id: z.number().int().positive().optional().nullable(),
          location_id: z.number().int().positive().optional().nullable(),
          country_name: z.preprocess(emptyToNull, z.string().nullable().optional()),
          state_name: z.preprocess(emptyToNull, z.string().nullable().optional()),
          city_name: z.preprocess(emptyToNull, z.string().nullable().optional()),
          zipcode: z.preprocess(emptyToNull, z.string().nullable().optional()),
          location_label: z.preprocess(emptyToNull, z.string().nullable().optional()),
          phone_numbers: linkedCampusPhoneSchema,
          fax_numbers: linkedCampusFaxSchema,
          email_addresses: linkedCampusEmailSchema,
          web_links: webLinkListSchema.optional().default([]),
          cascade_contacts: z.boolean().optional().default(false),
        })
      )
      .optional()
      .default([]),
    long_description: richTextField(5000, 'Long description'),
    accreditation: richTextField(500, 'Accreditation'),
    phone_numbers: z.array(contactEntrySchema).default([]),
    fax_numbers: z.array(contactEntrySchema).default([]),
    email_addresses: z.array(contactEntrySchema).default([]),
  })
  .superRefine((data, ctx) => {
    const links = data.linked_campuses || [];
    if (links.length === 0) {
      ctx.addIssue({
        code: 'custom',
        message: 'Link at least one campus and add phone and email contacts on that campus.',
        path: ['linked_campuses'],
      });
      return;
    }

    const campusPhones = links.some(
      link => serializeContacts(link.phone_numbers || []).length > 0
    );
    const campusEmails = links.some(
      link => serializeContacts(link.email_addresses || []).length > 0
    );

    if (!campusPhones) {
      ctx.addIssue({
        code: 'custom',
        message: 'Add at least one phone number on a linked campus contact set.',
        path: ['linked_campuses'],
      });
    }
    if (!campusEmails) {
      ctx.addIssue({
        code: 'custom',
        message: 'Add at least one email address on a linked campus contact set.',
        path: ['linked_campuses'],
      });
    }

    links.forEach((link, linkIndex) => {
      (link.email_addresses || []).forEach((entry, emailIndex) => {
        const value = (entry.value || '').trim();
        if (value && !isValidEmailAddress(value)) {
          ctx.addIssue({
            code: 'custom',
            message: `Enter a valid email address (example: name@school.edu). Got: ${value}`,
            path: ['linked_campuses', linkIndex, 'email_addresses', emailIndex, 'value'],
          });
        }
      });
    });
  });

export const wizardCollegesStepSchema = z
  .array(wizardCollegeItemSchema)
  .min(1, 'Add at least one school or college to the list.');

export type WizardCollegeItem = z.infer<typeof wizardCollegeItemSchema>;

export const emptyWizardCollegeDraft: WizardCollegeItem = {
  local_id: '',
  code: null,
  name: '',
  category: 'College',
  dean_name: null,
  web_links: createDefaultWebLinks(),
  campus_id: null,
  campus_local_id: null,
  campus_name: null,
  campus_address: null,
  campus_location_label: null,
  linked_campuses: [],
  long_description: null,
  accreditation: null,
  phone_numbers: createDefaultPhoneContacts(),
  fax_numbers: createDefaultFaxContacts(),
  email_addresses: createDefaultEmailContacts(),
};

export function createEmptyWizardCollegeDraft(): WizardCollegeItem {
  return {
    ...emptyWizardCollegeDraft,
    local_id: crypto.randomUUID(),
    phone_numbers: createDefaultPhoneContacts(),
    fax_numbers: createDefaultFaxContacts(),
    email_addresses: createDefaultEmailContacts(),
    web_links: createDefaultWebLinks(),
  };
}

function normalizeCollegeNameKey(name: string | null | undefined): string {
  return (name || '').trim().toLowerCase();
}

function campusLinkIdentityKeys(link: {
  campus_local_id?: string | null;
  campus_id?: number | null;
  name?: string | null;
}): Set<string> {
  const keys = new Set<string>();
  if (link.campus_local_id?.trim()) keys.add(`local:${link.campus_local_id.trim().toLowerCase()}`);
  if (link.campus_id != null) keys.add(`id:${link.campus_id}`);
  if (link.name?.trim()) keys.add(`name:${link.name.trim().toLowerCase()}`);
  return keys;
}

function campusLinksOverlap(
  left: { campus_local_id?: string | null; campus_id?: number | null; name?: string | null },
  right: { campus_local_id?: string | null; campus_id?: number | null; name?: string | null }
): boolean {
  const leftKeys = campusLinkIdentityKeys(left);
  return [...campusLinkIdentityKeys(right)].some(key => leftKeys.has(key));
}

function mergeContactEntries(...lists: Array<ContactEntry[] | undefined>): ContactEntry[] {
  const seen = new Set<string>();
  const merged: ContactEntry[] = [];
  for (const list of lists) {
    for (const entry of serializeContacts(list || [])) {
      const key = `${entry.type}:${entry.value.toLowerCase()}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(entry);
    }
  }
  return merged;
}

function mergeLinkedCampusLists(
  ...lists: Array<WizardCollegeItem['linked_campuses'] | undefined>
): WizardCollegeItem['linked_campuses'] {
  const merged: NonNullable<WizardCollegeItem['linked_campuses']> = [];
  for (const list of lists) {
    for (const link of list || []) {
      const existingIndex = merged.findIndex(item => campusLinksOverlap(item, link));
      if (existingIndex < 0) {
        merged.push({
          ...link,
          phone_numbers: normalizePhoneContacts(link.phone_numbers),
          fax_numbers: normalizeFaxContacts(
            link.fax_numbers,
            (link as { fax_number?: string | null }).fax_number
          ),
          email_addresses: normalizeEmailContacts(link.email_addresses),
          web_links: normalizeWebLinks(link.web_links),
          cascade_contacts: Boolean(link.cascade_contacts),
        });
        continue;
      }
      const existing = merged[existingIndex];
      merged[existingIndex] = {
        ...existing,
        ...link,
        campus_local_id: link.campus_local_id || existing.campus_local_id,
        campus_id: link.campus_id ?? existing.campus_id ?? null,
        name: link.name || existing.name,
        address: link.address ?? existing.address ?? null,
        country_id: link.country_id ?? existing.country_id ?? null,
        state_id: link.state_id ?? existing.state_id ?? null,
        location_id: link.location_id ?? existing.location_id ?? null,
        country_name: link.country_name ?? existing.country_name ?? null,
        state_name: link.state_name ?? existing.state_name ?? null,
        city_name: link.city_name ?? existing.city_name ?? null,
        zipcode: link.zipcode ?? existing.zipcode ?? null,
        location_label: link.location_label ?? existing.location_label ?? null,
        phone_numbers: normalizePhoneContacts(
          mergeContactEntries(existing.phone_numbers, link.phone_numbers)
        ),
        fax_numbers: normalizeFaxContacts(
          mergeContactEntries(existing.fax_numbers, link.fax_numbers),
          (link as { fax_number?: string | null }).fax_number ??
            (existing as { fax_number?: string | null }).fax_number
        ),
        email_addresses: normalizeEmailContacts(
          mergeContactEntries(existing.email_addresses, link.email_addresses)
        ),
        web_links: normalizeWebLinks(
          mergeContactEntries(existing.web_links, link.web_links)
        ),
        cascade_contacts: Boolean(link.cascade_contacts || existing.cascade_contacts),
      };
    }
  }
  return merged;
}

export function hydrateWizardCollege(
  raw: Partial<WizardCollegeItem> & { web_url?: string | null }
): WizardCollegeItem {
  // Explicit linked_campuses (including []) means "use this list". Only synthesize a
  // link from campus_id when the payload never provided linked_campuses (legacy/API).
  const hasExplicitLinkedCampuses = Array.isArray(raw.linked_campuses);
  const linkedCampuses = mergeLinkedCampusLists(
    hasExplicitLinkedCampuses
      ? raw.linked_campuses || []
      : raw.campus_local_id || raw.campus_id
        ? [
            {
              campus_local_id: raw.campus_local_id || String(raw.campus_id),
              campus_id: raw.campus_id ?? null,
              name: raw.campus_name || '',
              address: raw.campus_address ?? null,
              city_name: raw.campus_location_label ?? null,
              location_label: raw.campus_location_label ?? null,
            },
          ].filter(item => item.name || item.campus_local_id)
        : []
  );

  const primaryLink = linkedCampuses[0];

  return {
    ...createEmptyWizardCollegeDraft(),
    ...raw,
    // Keep missing local_id empty so repair can reuse course college_local_id values.
    local_id: raw.local_id?.trim() || '',
    code: raw.code || null,
    name: raw.name || '',
    category: schoolCollegeCategorySchema.safeParse(raw.category).success
      ? (raw.category as SchoolCollegeCategory)
      : 'College',
    dean_name: raw.dean_name || null,
    web_links: normalizeWebLinks(raw.web_links, raw.web_url),
    campus_id: hasExplicitLinkedCampuses
      ? primaryLink?.campus_id ?? null
      : raw.campus_id ?? primaryLink?.campus_id ?? null,
    campus_local_id: hasExplicitLinkedCampuses
      ? primaryLink?.campus_local_id ?? null
      : raw.campus_local_id ?? primaryLink?.campus_local_id ?? null,
    campus_name: hasExplicitLinkedCampuses
      ? primaryLink?.name ?? null
      : raw.campus_name ?? primaryLink?.name ?? null,
    campus_address: hasExplicitLinkedCampuses
      ? primaryLink?.address ?? null
      : raw.campus_address ?? primaryLink?.address ?? null,
    campus_location_label: hasExplicitLinkedCampuses
      ? primaryLink?.location_label ?? null
      : raw.campus_location_label ?? primaryLink?.location_label ?? null,
    linked_campuses: linkedCampuses,
    long_description: raw.long_description || null,
    accreditation: raw.accreditation || null,
    phone_numbers: normalizePhoneContacts(raw.phone_numbers),
    fax_numbers: normalizeFaxContacts(
      raw.fax_numbers,
      (raw as { fax_number?: string | null }).fax_number
    ),
    email_addresses: normalizeEmailContacts(raw.email_addresses),
  };
}

/**
 * One college row per name. Multiple campus mappings belong on linked_campuses,
 * not as duplicate college list entries.
 */
export function mergeWizardCollegesByName(
  colleges: Array<Partial<WizardCollegeItem> | WizardCollegeItem>
): WizardCollegeItem[] {
  const merged: WizardCollegeItem[] = [];
  for (const raw of colleges) {
    const college = hydrateWizardCollege(raw);
    const nameKey = normalizeCollegeNameKey(college.name);
    if (!nameKey) continue;
    const existingIndex = merged.findIndex(
      item => normalizeCollegeNameKey(item.name) === nameKey
    );
    if (existingIndex < 0) {
      merged.push(college);
      continue;
    }
    const existing = merged[existingIndex];
    const linkedCampuses = mergeLinkedCampusLists(
      existing.linked_campuses,
      college.linked_campuses
    );
    const primaryLink = linkedCampuses[0];
    merged[existingIndex] = hydrateWizardCollege({
      ...existing,
      ...college,
      local_id: existing.local_id || college.local_id,
      name: existing.name || college.name,
      code: college.code ?? existing.code,
      category: college.category || existing.category || 'College',
      dean_name: college.dean_name ?? existing.dean_name,
      web_links: normalizeWebLinks(
        serializeContacts(college.web_links || []).length
          ? college.web_links
          : serializeContacts(existing.web_links || []).length
            ? existing.web_links
            : null,
        (college as { web_url?: string | null }).web_url ??
          (existing as { web_url?: string | null }).web_url
      ),
      linked_campuses: linkedCampuses,
      campus_id: primaryLink?.campus_id ?? null,
      campus_local_id: primaryLink?.campus_local_id ?? null,
      campus_name: primaryLink?.name ?? null,
      campus_address: primaryLink?.address ?? existing.campus_address ?? null,
      campus_location_label: primaryLink?.location_label ?? existing.campus_location_label ?? null,
      phone_numbers: normalizePhoneContacts(
        mergeContactEntries(existing.phone_numbers, college.phone_numbers)
      ),
      fax_numbers: normalizeFaxContacts(
        mergeContactEntries(existing.fax_numbers, college.fax_numbers)
      ),
      email_addresses: normalizeEmailContacts(
        mergeContactEntries(existing.email_addresses, college.email_addresses)
      ),
      long_description: college.long_description ?? existing.long_description,
      accreditation: college.accreditation ?? existing.accreditation,
    });
  }
  return merged;
}

/** Keep college local_id values stable so Step 4 course college_local_id links resolve. */
export function repairWizardAcademicCollegeLinks(
  colleges: WizardCollegeItem[],
  courses: Array<{ college_local_id?: string | null }>
): { colleges: WizardCollegeItem[]; courses: typeof courses } {
  const hydratedColleges = mergeWizardCollegesByName(colleges).map(college => ({
    ...college,
    local_id: college.local_id?.trim() || '',
  }));

  const persistedCollegeIds = new Set(
    hydratedColleges.map(college => college.local_id).filter(Boolean)
  );

  const orphanIds = [
    ...new Set(
      courses
        .map(course => course.college_local_id?.trim())
        .filter((id): id is string => Boolean(id) && !persistedCollegeIds.has(id))
    ),
  ];

  const groupSizes = new Map<string, number>();
  for (const course of courses) {
    const collegeLocalId = course.college_local_id?.trim();
    if (!collegeLocalId) continue;
    groupSizes.set(collegeLocalId, (groupSizes.get(collegeLocalId) || 0) + 1);
  }

  const collegesNeedingIds = hydratedColleges.filter(college => !college.local_id);
  const sortedOrphans = [...orphanIds].sort(
    (left, right) =>
      (groupSizes.get(right) || 0) - (groupSizes.get(left) || 0) || left.localeCompare(right)
  );

  // Prefer stamping existing course college_local_id values onto colleges that lack local_id.
  // This keeps course rows visible instead of remapping them to freshly generated IDs.
  if (
    collegesNeedingIds.length > 0 &&
    sortedOrphans.length > 0 &&
    sortedOrphans.length === collegesNeedingIds.length
  ) {
    const collegesBySize = [...collegesNeedingIds].sort(
      (left, right) => right.name.length - left.name.length || left.name.localeCompare(right.name)
    );
    const assignedByName = new Map<string, string>();
    collegesBySize.forEach((college, index) => {
      assignedByName.set(college.name, sortedOrphans[index]);
    });

    const repairedColleges = hydratedColleges.map(college => {
      if (college.local_id) return college;
      return {
        ...college,
        local_id: assignedByName.get(college.name) || crypto.randomUUID(),
      };
    });
    return { colleges: repairedColleges, courses };
  }

  let repairedColleges = hydratedColleges.map(college =>
    college.local_id
      ? college
      : {
          ...college,
          local_id: crypto.randomUUID(),
        }
  );

  const collegeIds = new Set(
    repairedColleges.map(college => college.local_id).filter(Boolean)
  );
  const unresolvedOrphans = [
    ...new Set(
      courses
        .map(course => course.college_local_id?.trim())
        .filter((id): id is string => Boolean(id) && !collegeIds.has(id))
    ),
  ];

  if (unresolvedOrphans.length === 0) {
    return { colleges: repairedColleges, courses };
  }

  const remap = new Map<string, string>();
  if (unresolvedOrphans.length === repairedColleges.length) {
    const sizedOrphans = [...unresolvedOrphans].sort(
      (left, right) =>
        (groupSizes.get(right) || 0) - (groupSizes.get(left) || 0) || left.localeCompare(right)
    );
    const collegesBySize = [...repairedColleges].sort(
      (left, right) => right.name.length - left.name.length || left.name.localeCompare(right.name)
    );
    sizedOrphans.forEach((orphanId, index) => {
      const college = collegesBySize[index];
      if (college?.local_id) remap.set(orphanId, college.local_id);
    });
  }

  const repairedCourses = courses.map(course => {
    const collegeLocalId = course.college_local_id?.trim();
    if (!collegeLocalId || collegeIds.has(collegeLocalId)) return course;
    const mapped = remap.get(collegeLocalId);
    return {
      ...course,
      // Keep unmatched rows visible on the university panel instead of dropping them.
      college_local_id: mapped || null,
    };
  });

  return { colleges: repairedColleges, courses: repairedCourses };
}

export function collegeToApiPayload(college: WizardCollegeItem) {
  const { long_description, accreditation, linked_campuses, ...rest } = college;
  const links = (linked_campuses || []).map(link => ({
    ...link,
    phone_numbers: serializeContacts(link.phone_numbers || []),
    fax_numbers: serializeContacts(link.fax_numbers || []),
    email_addresses: serializeContacts(link.email_addresses || []),
    web_links: serializeContacts(link.web_links || []),
    address: link.address?.trim() || null,
  }));
  const primaryLink = links[0];

  const mergeContactLists = (...lists: Array<ContactEntry[] | undefined>) => {
    const seen = new Set<string>();
    const merged: ContactEntry[] = [];
    for (const list of lists) {
      for (const entry of serializeContacts(list || [])) {
        const key = `${entry.type}:${entry.value.toLowerCase()}`;
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push(entry);
      }
    }
    return merged;
  };

  const collegeWidePhones = serializeContacts(college.phone_numbers);
  const collegeWideFaxes = serializeContacts(college.fax_numbers);
  const collegeWideEmails = serializeContacts(college.email_addresses);
  const collegeWideWebLinks = serializeContacts(college.web_links);
  const linkedWebLinks = mergeContactLists(...links.map(link => link.web_links));
  const web_links =
    linkedWebLinks.length > 0
      ? mergeContactLists(collegeWideWebLinks, linkedWebLinks)
      : collegeWideWebLinks;

  return {
    ...rest,
    local_id: college.local_id?.trim() || null,
    code: college.code?.trim() || null,
    name: college.name.trim(),
    category: college.category || 'College',
    dean_name: college.dean_name?.trim() || null,
    web_links,
    web_url: primaryWebUrl(web_links),
    // Unlinked colleges must not keep a stale campus_id.
    campus_id: primaryLink?.campus_id ?? null,
    campus_local_id: primaryLink?.campus_local_id ?? null,
    campus_name: primaryLink?.name ?? null,
    campus_address: primaryLink?.address ?? null,
    campus_location_label: primaryLink?.location_label ?? null,
    linked_campuses: links,
    long_description: long_description || null,
    accreditation: accreditation || null,
    // Contacts live on linked campus cards; publish their union when campuses are linked.
    phone_numbers:
      links.length > 0
        ? mergeContactLists(...links.map(link => link.phone_numbers))
        : collegeWidePhones,
    fax_numbers:
      links.length > 0
        ? mergeContactLists(...links.map(link => link.fax_numbers))
        : collegeWideFaxes,
    email_addresses:
      links.length > 0
        ? mergeContactLists(...links.map(link => link.email_addresses))
        : collegeWideEmails,
  };
}

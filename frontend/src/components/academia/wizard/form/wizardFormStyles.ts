const inputClass = (hasError?: boolean) =>
  `w-full rounded-xl border bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent ${
    hasError ? 'border-alert ring-1 ring-alert/20' : 'border-border-subtle'
  }`;

export const wizardInputClass = inputClass;

export const wizardLabelClass = 'block text-sm font-bold text-text-main';

export const wizardSectionClass = 'rounded-2xl border border-border-subtle bg-surface-bg/40 p-4';

export const wizardSectionTitleClass = 'mb-2 text-sm font-bold text-text-main';

/** Denser grid used on the merged Institution & Campuses step. */
export const wizardDenseGridClass = 'grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-2 xl:grid-cols-3';

/** Country / State / City / Zipcode on one row (wide screens). */
export const wizardGeoRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 sm:grid-cols-2 xl:grid-cols-4';

/** Phone / Fax / Email on one row (medium+ screens). */
export const wizardContactRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-3';

/** Short name / Long name / Dean on one row (medium+ screens). */
export const wizardNamingRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-[minmax(0,0.85fr)_minmax(0,1.5fr)_minmax(0,1fr)]';

/** School/College code · name · category — name gets most of the row. */
export const wizardSchoolNamingRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 sm:grid-cols-2 md:grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)_minmax(0,11rem)]';

/** Dean name · College web URL on one row. */
export const wizardSchoolMetaRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]';

export const wizardStackClass = 'space-y-3';

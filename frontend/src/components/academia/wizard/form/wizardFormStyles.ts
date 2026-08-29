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

/** First identity controls on one nowrap row (medium+ screens). Institution profile and campus details. */
export const wizardProfileRowClass =
  'col-span-full flex flex-col gap-x-2.5 gap-y-2.5 md:flex-row md:flex-nowrap md:items-start [&_>_*]:min-w-0 [&_>_*]:flex-1';

/**
 * Campus details identity row: Campus ID stays a fixed first column (not min-w-0 / flex-1),
 * then Campus name and Campus type share the remaining width without overflowing off-screen.
 */
export const wizardCampusIdentityRowClass =
  'col-span-full grid grid-cols-1 gap-x-2.5 gap-y-2.5 md:grid-cols-[8.25rem_minmax(0,1.45fr)_minmax(11.5rem,0.95fr)]';

export const wizardCampusIdentityRowClassNoId =
  'col-span-full grid grid-cols-1 gap-x-2.5 gap-y-2.5 md:grid-cols-[minmax(0,1.45fr)_minmax(11.5rem,0.95fr)]';

/** Country / State / City / Zipcode on one row (wide screens). */
export const wizardGeoRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 sm:grid-cols-2 xl:grid-cols-4';

/** Address (wider) · Country · State · City · Zip on one nowrap row (medium+). */
export const wizardAddressRowClass =
  'col-span-full flex flex-col gap-x-2.5 gap-y-2.5 md:flex-row md:flex-nowrap md:items-start [&_>_*]:min-w-0';

/** Phone / Fax / Email on one row (medium+ screens). */
export const wizardContactRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-3';

/** Short name / long name / dean / students count on one row (medium+ screens). */
export const wizardNamingRowClass =
  'col-span-full grid grid-cols-1 gap-x-2.5 gap-y-2.5 md:grid-cols-[minmax(0,13rem)_minmax(0,1.35fr)_minmax(0,1fr)_minmax(0,1fr)]';

/** Equal label height + spacing so inputs align in wizardNamingRowClass. */
export const wizardNamingFieldClass =
  'min-w-0 space-y-1.5 text-sm [&_label]:flex [&_label]:h-[2.75rem] [&_label]:items-end [&_label]:leading-snug';

/** School/College code · name · category — name gets most of the row. */
export const wizardSchoolNamingRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 sm:grid-cols-2 md:grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)_minmax(0,11rem)]';

/** Dean name · College web URL on one row. */
export const wizardSchoolMetaRowClass =
  'col-span-full grid grid-cols-1 gap-x-3 gap-y-2.5 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)]';

export const wizardStackClass = 'space-y-3';

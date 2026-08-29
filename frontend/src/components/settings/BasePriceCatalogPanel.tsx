import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  CheckCircle2,
  Layers,
  ListOrdered,
  Loader2,
  Plus,
  Save,
  Trash2,
} from 'lucide-react';
import {
  applyFeeCatalogAudit,
  createEmptyFeeBundle,
  createEmptyFeeService,
  feeCatalogSchema,
  formatFeeAuditDate,
  formatFeeAuditUser,
  normalizeFeeCatalog,
  buildFeeMasterProcessTitleIndex,
  feeServiceMasterProcessKey,
  formatMasterProcessHeading,
  applyFeeServiceJourneyOrder,
  FLOWX_MASTER_PROCESS_ORDER,
  defaultFeeServiceDescription,
  ensureUniqueFeeServiceIds,
  remapFeeBundleServiceIds,
  resolveFeeServiceDescription,
  suggestServiceIdFromName,
  sumServiceListPrices,
  type FeeCatalog,
  type FeeMasterProcessContext,
  type FlowxMasterProcessKey,
} from '../../schemas/feeCatalogSchema';
import { useAdminSettingsStore } from '../../stores/adminSettingsStore';
import { formatMoneyInr } from '../../utils/invoiceMoney';
import { apiFetch } from '../../utils/api';
import { useConfirmation } from '../../context/ConfirmationContext';
import { useFlowxMaster } from '../../hooks/useFlowx';

const fieldClass =
  'w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm text-text-main outline-none focus:border-primary';

const moneyClass = `${fieldClass} font-mono text-right`;

async function resolveFeeCatalogActor(): Promise<string> {
  try {
    const user = (await apiFetch('users/me')) as {
      first_name?: string | null;
      last_name?: string | null;
      email?: string | null;
    };
    const name = [user.first_name, user.last_name]
      .map(part => (part || '').trim())
      .filter(Boolean)
      .join(' ');
    if (name) return name;
    if (user.email?.trim()) return user.email.trim();
  } catch {
    /* fall through */
  }
  return 'Unknown user';
}

type FormValues = FeeCatalog;

type CatalogSubTab = 'services' | 'packages';

type BasePriceCatalogPanelProps = {
  /** When true, parent can show an unsaved-dot on the Billing sub-tab. */
  onDirtyChange?: (dirty: boolean) => void;
};

const BasePriceCatalogPanel: React.FC<BasePriceCatalogPanelProps> = ({ onDirtyChange }) => {
  const openConfirm = useConfirmation();
  const feeCatalog = useAdminSettingsStore(s => s.feeCatalog);
  const saveFeeCatalog = useAdminSettingsStore(s => s.saveFeeCatalog);
  const masterQuery = useFlowxMaster();
  const masterProcessCtx = useMemo<FeeMasterProcessContext>(() => {
    const stages = masterQuery.data?.stages ?? [];
    const labels: Record<string, string> = {};
    for (const stage of stages) {
      if (stage.stage_key && stage.label?.trim()) {
        labels[stage.stage_key] = stage.label.trim();
      }
    }
    return {
      labels,
      titleToStage: buildFeeMasterProcessTitleIndex(stages),
    };
  }, [masterQuery.data?.stages]);
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [catalogTab, setCatalogTab] = useState<CatalogSubTab>('services');
  /** replace()/setValue array swaps do not always flip RHF isDirty — track edits explicitly. */
  const [catalogDirty, setCatalogDirty] = useState(false);
  const isDirtyRef = useRef(false);

  const {
    register,
    control,
    reset,
    watch,
    setValue,
    getValues,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(feeCatalogSchema),
    defaultValues: feeCatalog,
    mode: 'onChange',
  });

  const {
    fields: serviceFields,
    remove: removeService,
    replace: replaceServices,
  } = useFieldArray({ control, name: 'services', keyName: 'fieldKey' });

  const {
    fields: bundleFields,
    append: appendBundle,
    remove: removeBundle,
    replace: replaceBundles,
  } = useFieldArray({ control, name: 'bundles', keyName: 'fieldKey' });

  const hasUnsavedChanges = isDirty || catalogDirty;
  isDirtyRef.current = hasUnsavedChanges;

  const setServicesAndDirty = (services: FeeCatalog['services']) => {
    replaceServices(services);
    setValue('services', services, { shouldDirty: true, shouldValidate: true });
    setCatalogDirty(true);
  };

  const setBundlesAndDirty = (bundles: FeeCatalog['bundles']) => {
    replaceBundles(bundles);
    setValue('bundles', bundles, { shouldDirty: true, shouldValidate: true });
    setCatalogDirty(true);
  };

  // Keep Master Workflow process order. Never rewrite while the form has local edits.
  useEffect(() => {
    if (isDirtyRef.current) return;
    const current = useAdminSettingsStore.getState().feeCatalog;
    const collapsed = {
      ...normalizeFeeCatalog(current),
    };
    collapsed.services = applyFeeServiceJourneyOrder(collapsed.services, masterProcessCtx);
    const before = current.services
      .map(service => `${service.id}:${service.sortOrder}`)
      .join('|');
    const after = collapsed.services
      .map(service => `${service.id}:${service.sortOrder}`)
      .join('|');
    if (before === after && current.services.length === collapsed.services.length) return;
    saveFeeCatalog(collapsed);
    reset(collapsed);
    setCatalogDirty(false);
  }, [reset, saveFeeCatalog, masterProcessCtx]);

  // Sync store → form only when there are no local edits.
  useEffect(() => {
    if (hasUnsavedChanges) return;
    reset(feeCatalog);
    setCatalogDirty(false);
  }, [feeCatalog, hasUnsavedChanges, reset]);

  useEffect(() => {
    onDirtyChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onDirtyChange]);

  const watchedServices = watch('services') ?? [];
  const watchedBundles = watch('bundles') ?? [];

  const serviceGroups = useMemo(() => {
    const groups: {
      key: FlowxMasterProcessKey | null;
      label: string;
      indices: number[];
    }[] = FLOWX_MASTER_PROCESS_ORDER.map(key => ({
      key,
      label: formatMasterProcessHeading(key, masterProcessCtx),
      indices: [],
    }));
    groups.push({
      key: null,
      label: formatMasterProcessHeading(null, masterProcessCtx),
      indices: [],
    });

    watchedServices.forEach((service, index) => {
      const processKey = feeServiceMasterProcessKey(
        service?.name || '',
        masterProcessCtx,
        service?.masterProcessKey
      );
      const group =
        groups.find(item => item.key === processKey) || groups[groups.length - 1];
      group.indices.push(index);
    });
    return groups;
  }, [watchedServices, masterProcessCtx]);

  const activeServices = useMemo(
    () => watchedServices.filter(service => service?.active !== false && service?.id),
    [watchedServices]
  );

  const serviceActivityCounts = useMemo(() => {
    let active = 0;
    let inactive = 0;
    for (const service of watchedServices) {
      if (!service) continue;
      // Treat only an explicit false as inactive (native checkbox quirks can yield "").
      if (service.active === false) inactive += 1;
      else active += 1;
    }
    return { active, inactive, total: active + inactive };
  }, [watchedServices]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSuccessMessage(null);
    setFormError(null);

    const raw = getValues();
    const { services, idRemap } = ensureUniqueFeeServiceIds(raw.services ?? []);
    const validServiceIds = new Set(services.map(service => service.id));
    let bundles = remapFeeBundleServiceIds(raw.bundles ?? [], idRemap, validServiceIds);

    const usedBundleIds = new Set<string>();
    bundles = bundles.map(bundle => {
      let id = (bundle.id || '').trim();
      if (!id || id.startsWith('new-package') || usedBundleIds.has(id)) {
        id = suggestServiceIdFromName(bundle.name || 'package', [...usedBundleIds]);
      }
      usedBundleIds.add(id);
      return {
        ...bundle,
        id,
        packagePriceInr: 0,
        serviceIds: (bundle.serviceIds || []).filter(serviceId => validServiceIds.has(serviceId)),
      };
    });

    // Keep the form in sync with remapped ids before validation / save.
    setServicesAndDirty(services);
    setBundlesAndDirty(bundles);

    const candidate = {
      currency: raw.currency || 'INR',
      services,
      bundles,
    };
    const parsed = feeCatalogSchema.safeParse(candidate);
    if (!parsed.success) {
      setFormError('Fix the highlighted catalog fields before saving.');
      const issuePaths = parsed.error.issues.map(issue => String(issue.path[0] || ''));
      if (issuePaths.some(path => path === 'bundles')) {
        setCatalogTab('packages');
      } else {
        setCatalogTab('services');
      }
      return;
    }

    setSaving(true);
    try {
      const actor = await resolveFeeCatalogActor();
      const audited = applyFeeCatalogAudit(parsed.data, feeCatalog, actor);
      saveFeeCatalog(audited);
      reset(audited);
      setCatalogDirty(false);
      setSuccessMessage('Base price catalog saved.');
    } finally {
      setSaving(false);
    }
  };

  const addService = (processKey: FlowxMasterProcessKey | '') => {
    setCatalogTab('services');
    setFormError(null);
    const current = getValues('services') ?? [];
    const ids = current.map(service => service.id);
    const now = new Date().toISOString();
    const draft = {
      ...createEmptyFeeService(ids, processKey || ''),
      createdAt: now,
      updatedAt: now,
      createdBy: '',
      updatedBy: '',
    };
    setServicesAndDirty(applyFeeServiceJourneyOrder([...current, draft], masterProcessCtx));
    void resolveFeeCatalogActor().then(actor => {
      const services = getValues('services') ?? [];
      const index = services.findIndex(service => service.id === draft.id);
      if (index < 0) return;
      setValue(`services.${index}.createdBy`, actor, { shouldDirty: true });
      setValue(`services.${index}.updatedBy`, actor, { shouldDirty: true });
      setCatalogDirty(true);
    });
  };

  const addBundle = () => {
    setCatalogTab('packages');
    setFormError(null);
    const ids = (getValues('bundles') ?? []).map(bundle => bundle.id);
    const draft = createEmptyFeeBundle(ids);
    const firstActive = activeServices[0]?.id;
    const serviceIds = firstActive ? [firstActive] : [];
    const now = new Date().toISOString();
    appendBundle(
      {
        ...draft,
        serviceIds,
        description: buildPackageDescription(serviceIds),
        createdAt: now,
        updatedAt: now,
        createdBy: '',
        updatedBy: '',
      },
      { shouldFocus: true }
    );
    setCatalogDirty(true);
    void resolveFeeCatalogActor().then(actor => {
      const bundles = getValues('bundles') ?? [];
      const index = bundles.findIndex(bundle => bundle.id === draft.id);
      if (index < 0) return;
      setValue(`bundles.${index}.createdBy`, actor, { shouldDirty: true });
      setValue(`bundles.${index}.updatedBy`, actor, { shouldDirty: true });
      setCatalogDirty(true);
    });
  };

  const syncServiceIdFromName = (index: number) => {
    const services = getValues('services') ?? [];
    const row = services[index];
    if (!row?.name?.trim()) return;
    const others = services
      .map((service, serviceIndex) => (serviceIndex === index ? '' : service.id))
      .filter(Boolean);
    const nextDescription = resolveFeeServiceDescription(
      row.name,
      row.masterProcessKey,
      row.description
    );
    if (nextDescription !== (row.description || '').trim()) {
      setValue(`services.${index}.description`, nextDescription, {
        shouldDirty: true,
        shouldValidate: true,
      });
      setCatalogDirty(true);
    }
    // Always keep draft / colliding ids unique when the name changes.
    const nextId = suggestServiceIdFromName(row.name, others);
    if (nextId === row.id) return;
    if (row.id && !row.id.startsWith('new-service') && !others.includes(row.id)) {
      // Stable custom ids stay put unless they collide.
      return;
    }
    setValue(`services.${index}.id`, nextId, {
      shouldDirty: true,
      shouldValidate: true,
    });
    setCatalogDirty(true);
  };

  const syncBundleIdFromName = (index: number) => {
    const row = getValues(`bundles.${index}`);
    if (!row?.name?.trim()) return;
    // Keep stable ids after first assignment (except draft placeholders).
    if (row.id && !row.id.startsWith('new-package')) return;
    const others = (getValues('bundles') ?? [])
      .map((bundle, bundleIndex) => (bundleIndex === index ? '' : bundle.id))
      .filter(Boolean);
    setValue(`bundles.${index}.id`, suggestServiceIdFromName(row.name, others), {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  const buildPackageDescription = (serviceIds: string[]) => {
    const selected = new Set(serviceIds);
    const services = getValues('services') ?? [];
    return services
      .filter(service => selected.has(service.id))
      .map(service => service.name?.trim() || service.id)
      .filter(Boolean)
      .join(' + ')
      .slice(0, 240);
  };

  const toggleBundleService = (bundleIndex: number, serviceId: string, checked: boolean) => {
    const current = getValues(`bundles.${bundleIndex}.serviceIds`) ?? [];
    const next = checked
      ? [...new Set([...current, serviceId])]
      : current.filter(id => id !== serviceId);
    setValue(`bundles.${bundleIndex}.serviceIds`, next, {
      shouldDirty: true,
      shouldValidate: true,
    });
    setValue(`bundles.${bundleIndex}.description`, buildPackageDescription(next), {
      shouldDirty: true,
      shouldValidate: true,
    });
    setCatalogDirty(true);
  };

  const confirmRemoveService = async (index: number) => {
    const name = (getValues(`services.${index}.name`) || '').trim() || 'this service';
    const serviceId = getValues(`services.${index}.id`);
    const allowed = await openConfirm({
      title: 'Delete service?',
      message: `Delete service "${name}"? This removes it from the catalog and from any packages that include it. Default Nexus services can be restored automatically if removed; custom services cannot.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!allowed) return;

    const bundles = getValues('bundles') ?? [];
    bundles.forEach((bundle, bundleIndex) => {
      if (!bundle.serviceIds?.includes(serviceId)) return;
      const nextIds = bundle.serviceIds.filter(id => id !== serviceId);
      setValue(`bundles.${bundleIndex}.serviceIds`, nextIds, {
        shouldDirty: true,
        shouldValidate: true,
      });
      setValue(`bundles.${bundleIndex}.description`, buildPackageDescription(nextIds), {
        shouldDirty: true,
        shouldValidate: true,
      });
    });
    removeService(index);
    setCatalogDirty(true);
  };

  const confirmRemoveBundle = async (index: number) => {
    const name = (getValues(`bundles.${index}.name`) || '').trim() || 'this package';
    const allowed = await openConfirm({
      title: 'Delete package?',
      message: `Delete package "${name}"? This cannot be undone.`,
      confirmLabel: 'Delete',
      variant: 'danger',
    });
    if (!allowed) return;
    removeBundle(index);
    setCatalogDirty(true);
  };

  const saveActions = (
    <div className="flex flex-wrap items-center gap-2">
      {!hasUnsavedChanges && !saving ? (
        <span className="text-xs text-text-muted">No unsaved changes</span>
      ) : hasUnsavedChanges ? (
        <span className="text-xs font-medium text-amber-700">Unsaved changes</span>
      ) : null}
      <button
        type="submit"
        disabled={!hasUnsavedChanges || saving}
        className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
        Save base price catalog
      </button>
    </div>
  );

  return (
    <form className="space-y-5" onSubmit={onSubmit} noValidate>
      <input type="hidden" {...register('currency')} />

      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border-subtle bg-card px-4 py-3">
        <div className="min-w-0 space-y-1">
          <h3 className="text-sm font-semibold text-text-main">Base price catalog</h3>
          <p className="text-xs text-text-muted">
            Set list prices for billable services and packages. Changes apply after you save.
          </p>
        </div>
        {saveActions}
      </div>

      {successMessage ? (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <CheckCircle2 size={16} />
          {successMessage}
        </div>
      ) : null}
      {formError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {formError}
        </div>
      ) : null}
      {errors.services?.root?.message || errors.services?.message ? (
        <p className="text-xs text-red-700">
          {errors.services?.root?.message || String(errors.services?.message)}
        </p>
      ) : null}
      {errors.bundles?.root?.message || errors.bundles?.message ? (
        <p className="text-xs text-red-700">
          {errors.bundles?.root?.message || String(errors.bundles?.message)}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface-bg/50 px-3 py-2.5">
        <div
          className="inline-flex max-w-full flex-wrap gap-1 rounded-lg border border-border-subtle bg-card p-1"
          role="tablist"
          aria-label="Catalog sections"
        >
          <button
            type="button"
            role="tab"
            aria-selected={catalogTab === 'services'}
            onClick={() => setCatalogTab('services')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
              catalogTab === 'services'
                ? 'bg-accent text-text-dark-bg shadow-sm'
                : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
            }`}
          >
            <ListOrdered size={13} strokeWidth={2.25} />
            Services
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={catalogTab === 'packages'}
            onClick={() => setCatalogTab('packages')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
              catalogTab === 'packages'
                ? 'bg-accent text-text-dark-bg shadow-sm'
                : 'text-text-muted hover:bg-surface-bg hover:text-text-main'
            }`}
          >
            <Layers size={13} strokeWidth={2.25} />
            Packages
          </button>
        </div>

        {catalogTab === 'packages' ? (
          <button
            type="button"
            onClick={() => void addBundle()}
            disabled={bundleFields.length >= 40 || activeServices.length === 0}
            className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-sm font-semibold text-accent hover:bg-accent/10 disabled:opacity-40"
          >
            <Plus size={16} />
            New package
          </button>
        ) : null}
      </div>

      <p className="text-xs text-text-muted">
        {catalogTab === 'services'
          ? 'Browse services by Master Workflow process. Use Add service on a process heading to create one in that group.'
          : 'Build packages from active services. Charged package price is set later via discount policy at invoice time.'}
      </p>

      <section
        className={
          catalogTab === 'services'
            ? 'space-y-3 rounded-2xl border border-border-subtle bg-surface-bg/40 p-4 md:p-5'
            : 'hidden'
        }
        aria-hidden={catalogTab !== 'services'}
      >
        <div className="overflow-x-auto rounded-xl border border-border-subtle bg-card">
          <table className="min-w-full table-fixed text-left text-sm">
            <thead className="border-b border-border-subtle bg-surface-bg/80 text-xs uppercase tracking-wide text-text-muted">
              <tr>
                <th className="w-14 px-2 py-2 font-semibold">Active</th>
                <th className="px-3 py-2 font-semibold w-[22%]">Service</th>
                <th className="px-3 py-2 font-semibold w-[28%]">Description</th>
                <th className="px-3 py-2 font-semibold text-right">List price (₹)</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Added</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Added by</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Updated</th>
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Updated by</th>
                <th className="px-3 py-2 font-semibold w-12" />
              </tr>
            </thead>
            <tbody>
              {serviceGroups.map(group => (
                <React.Fragment key={group.key ?? 'other'}>
                  <tr className="border-y border-border-subtle bg-surface-bg">
                    <td colSpan={9} className="px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-bold uppercase tracking-wide text-text-main">
                          {group.label}
                        </span>
                        <button
                          type="button"
                          onClick={() => addService(group.key || '')}
                          disabled={serviceFields.length >= 80}
                          className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-card px-2 py-1 text-[11px] font-semibold text-accent hover:bg-accent/5 disabled:opacity-40"
                        >
                          <Plus size={12} />
                          Add service
                        </button>
                      </div>
                    </td>
                  </tr>
                  {group.indices.length === 0 ? (
                    <tr className="border-b border-border-subtle">
                      <td
                        colSpan={9}
                        className="px-3 py-2 text-xs italic text-text-muted"
                      >
                        No services in this process yet.
                      </td>
                    </tr>
                  ) : null}
                  {group.indices.map(index => {
                    const field = serviceFields[index];
                    const service = watchedServices[index];
                    if (!field) return null;
                    return (
                    <tr
                      key={field.fieldKey}
                      className={`border-b border-border-subtle last:border-0 align-middle transition-opacity ${
                        service?.active === false
                          ? 'bg-surface-bg/50 text-text-muted opacity-55'
                          : ''
                      }`}
                    >
                  <td className="w-14 px-2 py-2 text-center">
                    <input
                      type="checkbox"
                      className="h-4 w-4 opacity-100"
                      checked={service?.active !== false}
                      onChange={event => {
                        setValue(`services.${index}.active`, event.target.checked, {
                          shouldDirty: true,
                          shouldValidate: true,
                          shouldTouch: true,
                        });
                        setCatalogDirty(true);
                      }}
                      aria-label={`Active ${watch(`services.${index}.name`) || 'service'}`}
                    />
                  </td>
                  <td className="px-3 py-2 min-w-[12rem] w-[22%]">
                    <input
                      className={`${fieldClass}${
                        service?.active === false ? ' text-text-muted' : ''
                      }`}
                      placeholder="New service"
                      {...register(`services.${index}.name`, {
                        onBlur: () => syncServiceIdFromName(index),
                      })}
                    />
                    {errors.services?.[index]?.name ? (
                      <p className="mt-1 text-xs text-red-700">
                        {errors.services[index]?.name?.message}
                      </p>
                    ) : null}
                    {errors.services?.[index]?.id ? (
                      <p className="mt-1 text-xs text-red-700">
                        {errors.services[index]?.id?.message}
                      </p>
                    ) : null}
                    <input type="hidden" {...register(`services.${index}.id`)} />
                    <input type="hidden" {...register(`services.${index}.masterProcessKey`)} />
                  </td>
                  <td className="px-3 py-2 min-w-[12rem] w-[28%]">
                    <input
                      className={fieldClass}
                      placeholder={
                        defaultFeeServiceDescription(
                          service?.masterProcessKey === 'other'
                            ? ''
                            : service?.masterProcessKey
                        ) || 'Short description'
                      }
                      {...register(`services.${index}.description`)}
                    />
                  </td>
                  <td className="px-3 py-2 min-w-[6rem] w-[9%]">
                    <input
                      type="number"
                      min={0}
                      step={100}
                      className={moneyClass}
                      {...register(`services.${index}.basePriceInr`, { valueAsNumber: true })}
                    />
                    {errors.services?.[index]?.basePriceInr ? (
                      <p className="mt-1 text-xs text-red-700">
                        {errors.services[index]?.basePriceInr?.message}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-text-muted">
                    {formatFeeAuditDate(service?.createdAt || '')}
                    <input type="hidden" {...register(`services.${index}.createdAt`)} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-text-main">
                    {formatFeeAuditUser(service?.createdBy || '')}
                    <input type="hidden" {...register(`services.${index}.createdBy`)} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-text-muted">
                    {formatFeeAuditDate(service?.updatedAt || '')}
                    <input type="hidden" {...register(`services.${index}.updatedAt`)} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-xs text-text-main">
                    {formatFeeAuditUser(service?.updatedBy || '')}
                    <input type="hidden" {...register(`services.${index}.updatedBy`)} />
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => void confirmRemoveService(index)}
                      disabled={serviceFields.length <= 1}
                      className="rounded p-1.5 text-alert hover:bg-alert/10 disabled:opacity-30"
                      aria-label="Remove service"
                    >
                      <Trash2 size={14} />
                    </button>
                    <input
                      type="hidden"
                      {...register(`services.${index}.sortOrder`, { valueAsNumber: true })}
                    />
                  </td>
                </tr>
                    );
                  })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm text-text-muted">
          <span>
            Total:{' '}
            <span className="font-semibold text-text-main">{serviceActivityCounts.total}</span>
          </span>
          <span className="h-3 w-px bg-border-subtle" aria-hidden />
          <span>
            Active:{' '}
            <span className="font-semibold text-emerald-700">{serviceActivityCounts.active}</span>
          </span>
          <span className="h-3 w-px bg-border-subtle" aria-hidden />
          <span>
            Inactive:{' '}
            <span className="font-semibold text-text-muted">{serviceActivityCounts.inactive}</span>
          </span>
        </div>
      </section>

      <section
        className={
          catalogTab === 'packages'
            ? 'space-y-3 rounded-2xl border border-border-subtle bg-surface-bg/40 p-4 md:p-5'
            : 'hidden'
        }
        aria-hidden={catalogTab !== 'packages'}
      >
        <div className="space-y-3">
          {bundleFields.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border-subtle bg-card px-4 py-6 text-center text-sm text-text-muted">
              No packages yet. Use New package for an Essentials or End-to-End style offer.
            </p>
          ) : null}

          {bundleFields.map((field, index) => {
            const bundle = watchedBundles[index];
            const packageListTotal = sumServiceListPrices(
              watchedServices,
              bundle?.serviceIds ?? []
            );
            return (
              <div
                key={field.fieldKey}
                className={`space-y-3 rounded-xl border border-border-subtle bg-card p-4 transition-opacity ${
                  bundle?.active === false ? 'opacity-55' : ''
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <label className="inline-flex items-center gap-2 text-sm font-medium text-text-main">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={watchedBundles[index]?.active !== false}
                      onChange={event => {
                        setValue(`bundles.${index}.active`, event.target.checked, {
                          shouldDirty: true,
                          shouldValidate: true,
                          shouldTouch: true,
                        });
                        setCatalogDirty(true);
                      }}
                    />
                    Active package
                  </label>
                  <button
                    type="button"
                    onClick={() => void confirmRemoveBundle(index)}
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                  >
                    <Trash2 size={12} />
                    Remove
                  </button>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                      Added
                    </p>
                    <p className="mt-0.5 text-xs text-text-main">
                      {formatFeeAuditDate(bundle?.createdAt || '')}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                      Added by
                    </p>
                    <p className="mt-0.5 text-xs text-text-main">
                      {formatFeeAuditUser(bundle?.createdBy || '')}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                      Updated
                    </p>
                    <p className="mt-0.5 text-xs text-text-main">
                      {formatFeeAuditDate(bundle?.updatedAt || '')}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border-subtle bg-surface-bg/60 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                      Updated by
                    </p>
                    <p className="mt-0.5 text-xs text-text-main">
                      {formatFeeAuditUser(bundle?.updatedBy || '')}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
                  <div className="space-y-1.5 md:col-span-3">
                    <label className="block text-xs font-medium text-text-main">Package name</label>
                    <input
                      className={fieldClass}
                      placeholder="New package"
                      {...register(`bundles.${index}.name`, {
                        onBlur: () => syncBundleIdFromName(index),
                      })}
                    />
                    {errors.bundles?.[index]?.name ? (
                      <p className="text-xs text-red-700">{errors.bundles[index]?.name?.message}</p>
                    ) : null}
                    {errors.bundles?.[index]?.id ? (
                      <p className="text-xs text-red-700">{errors.bundles[index]?.id?.message}</p>
                    ) : null}
                  </div>
                  <div className="space-y-1.5 md:col-span-5">
                    <label className="block text-xs font-medium text-text-main">Description</label>
                    <input
                      className={fieldClass}
                      placeholder="What this package covers for the student"
                      {...register(`bundles.${index}.description`)}
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-4">
                    <label className="block text-xs font-medium text-text-main">
                      Invoice description{' '}
                      <span className="font-normal text-text-muted">(optional, max 75)</span>
                    </label>
                    <input
                      className={fieldClass}
                      maxLength={75}
                      placeholder="Shown on invoice under package name"
                      {...register(`bundles.${index}.invoiceDescription`)}
                    />
                    <p className="text-[11px] text-text-muted">
                      {(bundle?.invoiceDescription || '').length}/75 — appears as “package services
                      including …” on invoices
                    </p>
                    {errors.bundles?.[index]?.invoiceDescription ? (
                      <p className="text-xs text-red-700">
                        {errors.bundles[index]?.invoiceDescription?.message}
                      </p>
                    ) : null}
                  </div>
                  <input type="hidden" {...register(`bundles.${index}.id`)} />
                  <input type="hidden" {...register(`bundles.${index}.createdAt`)} />
                  <input type="hidden" {...register(`bundles.${index}.createdBy`)} />
                  <input type="hidden" {...register(`bundles.${index}.updatedAt`)} />
                  <input type="hidden" {...register(`bundles.${index}.updatedBy`)} />
                </div>

                <div className="space-y-1.5">
                  <p className="text-sm font-medium text-text-main">Included services</p>
                  <div className="grid grid-cols-6 gap-1.5">
                    {watchedServices.map(service => {
                      if (!service?.id) return null;
                      const checked = (bundle?.serviceIds ?? []).includes(service.id);
                      return (
                        <label
                          key={`${field.fieldKey}-${service.id}`}
                          className={`flex cursor-pointer items-start gap-2 rounded-lg border px-2.5 py-2 text-sm ${
                            checked
                              ? 'border-accent bg-accent/5 text-text-main'
                              : 'border-border-subtle bg-surface-bg text-text-muted'
                          } ${service.active === false ? 'opacity-50' : ''}`}
                        >
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={checked}
                            onChange={event =>
                              toggleBundleService(index, service.id, event.target.checked)
                            }
                          />
                          <span className="min-w-0">
                            <span className="block font-semibold leading-snug">
                              {service.name || service.id}
                            </span>
                            <span className="font-mono text-xs">
                              ₹{formatMoneyInr(Number(service.basePriceInr) || 0)}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  {errors.bundles?.[index]?.serviceIds ? (
                    <p className="text-xs text-red-700">
                      {errors.bundles[index]?.serviceIds?.message ||
                        errors.bundles[index]?.serviceIds?.root?.message}
                    </p>
                  ) : null}
                </div>

                <div className="grid grid-cols-6 gap-1.5">
                  <div className="rounded-lg border border-accent/30 bg-accent px-2.5 py-2 text-text-dark-bg">
                    <p className="text-sm font-semibold uppercase tracking-wide text-text-dark-bg/80">
                      Total package price
                    </p>
                    <p className="mt-0.5 font-mono text-base tracking-tight">
                      ₹{formatMoneyInr(packageListTotal)}
                    </p>
                  </div>
                </div>

                <input
                  type="hidden"
                  {...register(`bundles.${index}.packagePriceInr`, { valueAsNumber: true })}
                />
                <input
                  type="hidden"
                  {...register(`bundles.${index}.sortOrder`, { valueAsNumber: true })}
                />
              </div>
            );
          })}
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-border-subtle pt-4">
        {saveActions}
      </div>
    </form>
  );
};

export default BasePriceCatalogPanel;

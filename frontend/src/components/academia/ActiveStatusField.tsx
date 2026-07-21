import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

import { apiFetch } from '../../utils/api';
import type { HierarchyStatusImpact } from '../../types/hierarchyStatusImpact';

interface ActiveStatusFieldProps {
  entityType: HierarchyStatusImpact['entity_type'];
  entityId?: string | number;
  value: boolean;
  onChange: (next: boolean) => void;
  initialValue?: boolean;
  disabled?: boolean;
}

const ActiveStatusField: React.FC<ActiveStatusFieldProps> = ({
  entityType,
  entityId,
  value,
  onChange,
  initialValue = true,
  disabled = false,
}) => {
  const [impact, setImpact] = useState<HierarchyStatusImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);

  const entityKey = entityId != null ? String(entityId) : null;
  const statusChanged = value !== initialValue;

  useEffect(() => {
    if (!entityKey || !statusChanged) {
      setImpact(null);
      return;
    }

    let cancelled = false;
    setLoadingImpact(true);
    void apiFetch<HierarchyStatusImpact>(
      `academia/hierarchy/status-impact?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityKey)}&is_active=${value ? 'true' : 'false'}`
    )
      .then(data => {
        if (!cancelled) setImpact(data);
      })
      .catch(() => {
        if (!cancelled) setImpact(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingImpact(false);
      });

    return () => {
      cancelled = true;
    };
  }, [entityKey, entityType, statusChanged, value]);

  const hasImpact =
    impact &&
    impact.message !== 'No status change.' &&
    (impact.majors > 0 || impact.programs > 0 || impact.courses > 0 || !value);

  return (
    <div className="space-y-2">
      <label className="block space-y-1 text-sm">
        <span className="font-medium text-text-main">Status</span>
        <select
          value={value ? 'active' : 'inactive'}
          onChange={event => onChange(event.target.value === 'active')}
          disabled={disabled}
          className="w-full rounded-xl border border-border-subtle bg-surface-bg px-3 py-2 text-sm outline-none focus:border-accent disabled:opacity-50"
        >
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </label>

      {statusChanged && entityKey ? (
        loadingImpact ? (
          <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-bg/60 px-3 py-2 text-xs text-text-muted">
            <Loader2 size={14} className="animate-spin" />
            Calculating hierarchy impact...
          </div>
        ) : hasImpact ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-xs text-text-main">
            <div className="mb-2 flex items-center gap-2 font-semibold text-amber-700">
              <AlertTriangle size={14} />
              Hierarchy impact preview
            </div>
            <p className="text-text-muted">{impact?.message}</p>
            {(impact?.majors || impact?.programs || impact?.courses) ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {impact.majors > 0 ? (
                  <span className="rounded-lg bg-card px-2 py-1 font-medium">
                    {impact.majors} major{impact.majors !== 1 ? 's' : ''}
                  </span>
                ) : null}
                {impact.programs > 0 ? (
                  <span className="rounded-lg bg-card px-2 py-1 font-medium">
                    {impact.programs} program{impact.programs !== 1 ? 's' : ''}
                  </span>
                ) : null}
                {impact.courses > 0 ? (
                  <span className="rounded-lg bg-card px-2 py-1 font-medium">
                    {impact.courses} course{impact.courses !== 1 ? 's' : ''}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null
      ) : null}
    </div>
  );
};

export default ActiveStatusField;

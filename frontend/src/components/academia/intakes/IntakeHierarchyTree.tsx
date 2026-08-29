import { useState } from 'react';
import { Building2, ChevronDown, ChevronRight, GraduationCap, Landmark } from 'lucide-react';

import type { IntakeEntityType, IntakeHierarchyNode } from '../../../types/hierarchicalIntake';

interface IntakeHierarchyTreeProps {
  root: IntakeHierarchyNode;
  onConfigure: (entityType: IntakeEntityType, entityId: number, entityName: string) => void;
}

const entityIcon = (entityType: IntakeEntityType) => {
  if (entityType === 'institution') return Landmark;
  if (entityType === 'campus') return Building2;
  return GraduationCap;
};

const TreeNode: React.FC<{
  node: IntakeHierarchyNode;
  depth: number;
  onConfigure: IntakeHierarchyTreeProps['onConfigure'];
}> = ({ node, depth, onConfigure }) => {
  // Keep every hierarchy level open by default so universities, colleges, and
  // their linked campuses are visible immediately.
  const [expanded, setExpanded] = useState(true);
  const Icon = entityIcon(node.entity_type);
  const hasChildren = node.children.length > 0;
  const entityLabel =
    node.entity_type === 'institution'
      ? 'University'
      : node.entity_type === 'college'
        ? 'College'
        : 'Campus';

  return (
    <div>
      <div
        className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle px-3 py-2"
        style={{ marginLeft: depth * 16 }}
      >
        <div className="flex min-w-0 items-center gap-2">
          {hasChildren ? (
            <button
              type="button"
              onClick={() => setExpanded(prev => !prev)}
              className="text-text-muted"
              aria-label={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
          ) : (
            <span className="w-4" />
          )}
          <Icon size={16} className="shrink-0 text-accent" />
          <div className="min-w-0">
            <p className="truncate font-semibold text-text-main">{node.name}</p>
            <p className="text-xs tabular-nums text-text-muted">
              {entityLabel} ID {node.entity_id}
              {node.intake_count != null
                ? ` · ${node.intake_count} intake${node.intake_count === 1 ? '' : 's'}`
                : ''}
            </p>
          </div>
          {node.is_overridden ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
              Custom
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => onConfigure(node.entity_type, node.entity_id, node.name)}
          className="shrink-0 rounded-lg border border-border-subtle px-3 py-1.5 text-xs font-semibold text-text-main"
        >
          Configure Calendar
        </button>
      </div>
      {expanded
        ? node.children.map(child => (
            <div key={`${child.entity_type}-${child.entity_id}`} className="mt-2">
              <TreeNode node={child} depth={depth + 1} onConfigure={onConfigure} />
            </div>
          ))
        : null}
    </div>
  );
};

const IntakeHierarchyTree: React.FC<IntakeHierarchyTreeProps> = ({ root, onConfigure }) => (
  <div className="space-y-2">
    <TreeNode node={root} depth={0} onConfigure={onConfigure} />
  </div>
);

export default IntakeHierarchyTree;

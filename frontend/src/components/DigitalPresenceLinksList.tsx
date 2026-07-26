import React, { useMemo, useState } from 'react';
import {
  BookOpen,
  Code2,
  ExternalLink,
  Globe,
  GraduationCap,
  Link2,
  Loader2,
  Network,
  Palette,
  Pencil,
  Rocket,
  Trash2,
  Trophy,
} from 'lucide-react';
import type {
  DigitalPlatform,
  DigitalPresenceCategory,
  DigitalPresenceLinkRecord,
} from '../types/digitalPresenceLink';
import { CATEGORY_LABELS } from '../types/digitalPresenceLink';
import EmptyListMessage from './ui/EmptyListMessage';

const cardClass = 'rounded-md border border-border-subtle bg-surface-bg/40 p-3 space-y-2';

const categoryBadgeClass =
  'inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800';

const filterButtonClass = (active: boolean) =>
  `rounded-md border px-2.5 py-1 text-sm font-semibold transition-colors ${
    active
      ? 'border-sky-300 bg-sky-100 text-sky-900'
      : 'border-border-subtle bg-card text-text-muted hover:text-text-main hover:bg-surface-bg'
  }`;

export function getPlatformIcon(platform: DigitalPlatform | null | undefined, size = 16) {
  switch (platform) {
    case 'GITHUB':
      return <Code2 size={size} />;
    case 'LINKEDIN':
      return <Network size={size} />;
    case 'PERSONAL_PORTFOLIO':
      return <Globe size={size} />;
    case 'GOOGLE_SCHOLAR':
      return <GraduationCap size={size} />;
    case 'RESEARCHGATE':
      return <BookOpen size={size} />;
    case 'BEHANCE':
    case 'DRIBBBLE':
      return <Palette size={size} />;
    case 'KAGGLE':
      return <Trophy size={size} />;
    case 'DEVPOST':
      return <Rocket size={size} />;
    default:
      return <Link2 size={size} />;
  }
}

type CategoryFilter = 'ALL' | DigitalPresenceCategory;

interface DigitalPresenceLinksListProps {
  links: DigitalPresenceLinkRecord[];
  readOnly?: boolean;
  showCategoryFilter?: boolean;
  deletingId?: number | null;
  onEdit?: (link: DigitalPresenceLinkRecord) => void;
  onDelete?: (linkId: number) => void;
}

const DigitalPresenceLinksList: React.FC<DigitalPresenceLinksListProps> = ({
  links,
  readOnly = false,
  showCategoryFilter = false,
  deletingId = null,
  onEdit,
  onDelete,
}) => {
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('ALL');

  const filteredLinks = useMemo(() => {
    if (!showCategoryFilter || categoryFilter === 'ALL') return links;
    return links.filter(link => link.category === categoryFilter);
  }, [categoryFilter, links, showCategoryFilter]);

  return (
    <div className="space-y-3">
      {showCategoryFilter ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={filterButtonClass(categoryFilter === 'ALL')}
            onClick={() => setCategoryFilter('ALL')}
          >
            All
          </button>
          {(Object.keys(CATEGORY_LABELS) as DigitalPresenceCategory[]).map(category => (
            <button
              key={category}
              type="button"
              className={filterButtonClass(categoryFilter === category)}
              onClick={() => setCategoryFilter(category)}
            >
              {CATEGORY_LABELS[category]}
            </button>
          ))}
        </div>
      ) : null}

      {filteredLinks.length === 0 ? (
        <EmptyListMessage
          compact
          message={
            links.length === 0
              ? 'No digital presence links added yet.'
              : 'No links match the selected category filter.'
          }
        />
      ) : (
        <div className="space-y-3">
          {filteredLinks.map(link => (
            <div key={link.id} className={cardClass}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2 min-w-0">
                  <span className="mt-0.5 text-sky-700 shrink-0">
                    {getPlatformIcon(link.platform_name)}
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-bold text-text-main">
                        {link.platform_label || 'Platform'}
                      </p>
                      {link.category_label ? (
                        <span className={categoryBadgeClass}>{link.category_label}</span>
                      ) : null}
                    </div>
                    {link.url ? (
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-sky-700 hover:text-sky-900 break-all"
                      >
                        {link.url}
                      </a>
                    ) : null}
                    {link.admission_value_note ? (
                      <p className="text-sm text-text-muted mt-2">
                        <span className="font-semibold text-text-main">Value to Admission: </span>
                        {link.admission_value_note}
                      </p>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  {link.url ? (
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-card px-2.5 py-1 text-sm font-semibold text-sky-700 hover:bg-sky-50"
                    >
                      <ExternalLink size={12} />
                      Visit Link
                    </a>
                  ) : null}
                  {!readOnly && onEdit && onDelete ? (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onEdit(link)}
                        className="inline-flex items-center gap-1 text-sm text-sky-700 hover:text-sky-900"
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(link.id)}
                        disabled={deletingId === link.id}
                        className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-700 disabled:opacity-60"
                      >
                        {deletingId === link.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Trash2 size={12} />
                        )}
                        Delete
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DigitalPresenceLinksList;

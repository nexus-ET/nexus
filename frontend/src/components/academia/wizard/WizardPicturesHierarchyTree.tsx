import { useEffect, useMemo, useState } from 'react';
import { Maximize2, Search, Unlink } from 'lucide-react';

import type { WizardCollegeItem } from '../../../schemas/wizard/step3-colleges';
import {
  pictureDisplayFileName,
  rewriteStoredMediaUrl,
  type WizardPictureItem,
} from '../../../schemas/wizard/step6-pictures';
import EmptyListMessage from '../../ui/EmptyListMessage';
import HeadlessScrollArea from '../../HeadlessScrollArea';
import WizardCollegeTabBar from './WizardCollegeTabBar';
import {
  collegeScopeKey,
  filterPicturesForScope,
  institutionScopeKey,
  pictureAssetKey,
  pictureScopeKey,
  pictureSelectionKey,
  resolveCollegeLocalId,
  type WizardPicturesEntityScope,
} from './wizardPicturesScope';

export interface WizardPicturesHierarchyTreeProps {
  institutionName: string;
  colleges: WizardCollegeItem[];
  pictures: WizardPictureItem[];
  collegeOverrides: Set<string>;
  cascadeToColleges: boolean;
  activeScopeKey: string;
  selectedKeys: Set<string>;
  deletingKey: string | null;
  uploading: boolean;
  onActiveScopeChange: (scopeKey: string) => void;
  onCascadeChange: (enabled: boolean) => void;
  onToggleCollegeOverride: (collegeLocalId: string, enabled: boolean) => void;
  onTogglePictureSelection: (selectionKey: string) => void;
  onSetScopeSelection: (scope: WizardPicturesEntityScope, keys: string[], selected: boolean) => void;
  onUnlinkPicture: (scope: WizardPicturesEntityScope, picture: WizardPictureItem, index: number) => void;
  onUnlinkSelectedInScope: (scope: WizardPicturesEntityScope) => void;
  onUnlinkAllInScope: (scope: WizardPicturesEntityScope) => void;
  onViewPicture: (picture: WizardPictureItem, scopePictures: WizardPictureItem[]) => void;
  renderUploadPanel: (scope: WizardPicturesEntityScope) => React.ReactNode;
  onRemoveCollegeTab?: (collegeLocalId: string) => void;
}

const TYPE_LABELS: Record<string, string> = {
  gallery: 'Gallery',
  logo: 'Logo',
  banner: 'Banner (Hero)',
  campus: 'Banner (Hero)',
};

const TYPE_ORDER = ['logo', 'banner', 'campus', 'gallery'];

function typeLabel(pictureType: string): string {
  return TYPE_LABELS[pictureType] || 'Gallery';
}

function typeSortKey(pictureType: string): number {
  const index = TYPE_ORDER.indexOf(pictureType);
  return index >= 0 ? index : TYPE_ORDER.length;
}

function formatFromPicture(picture: Pick<WizardPictureItem, 'file_name' | 'file_type'>): string | null {
  const mime = (picture.file_type || '').trim().toLowerCase();
  if (mime.startsWith('image/')) {
    const subtype = mime.slice('image/'.length).replace('jpeg', 'jpg').toUpperCase();
    if (subtype) return subtype;
  }
  if (mime) return mime.toUpperCase();
  const name = (picture.file_name || '').trim();
  const dot = name.lastIndexOf('.');
  if (dot > 0 && dot < name.length - 1) {
    return name.slice(dot + 1).toUpperCase();
  }
  return null;
}

function formatFileSize(bytes: number | null | undefined): string | null {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  return `${Math.round(bytes / 1024)} KB`;
}

function joinMetaParts(parts: Array<string | null | undefined>): string {
  return parts.map(part => (part || '').trim()).filter(Boolean).join(' · ');
}

function resolvePictureIndex(
  allPictures: WizardPictureItem[],
  picture: WizardPictureItem
): number {
  return allPictures.findIndex(
    item =>
      (picture.local_id && item.local_id === picture.local_id) ||
      (pictureAssetKey(item) === pictureAssetKey(picture) &&
        pictureScopeKey(item) === pictureScopeKey(picture))
  );
}

function LinkedImagesBrowser({
  pictures,
  allPictures,
  scope,
  selectedKeys,
  deletingKey,
  uploading,
  onToggleSelection,
  onUnlink,
  onView,
}: {
  pictures: WizardPictureItem[];
  allPictures: WizardPictureItem[];
  scope: WizardPicturesEntityScope;
  selectedKeys: Set<string>;
  deletingKey: string | null;
  uploading: boolean;
  onToggleSelection: (selectionKey: string) => void;
  onUnlink: (picture: WizardPictureItem, index: number) => void;
  onView: (picture: WizardPictureItem) => void;
}) {
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const normalizedQuery = query.trim().toLowerCase();

  const typeOptions = useMemo(() => {
    const counts = new Map<string, number>();
    for (const picture of pictures) {
      const key = picture.picture_type || 'gallery';
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return [...counts.entries()]
      .map(([type, count]) => ({ type, label: typeLabel(type), count }))
      .sort((a, b) => typeSortKey(a.type) - typeSortKey(b.type));
  }, [pictures]);

  const filteredPictures = useMemo(() => {
    return pictures
      .filter(picture =>
        typeFilter === 'all' ? true : (picture.picture_type || 'gallery') === typeFilter
      )
      .filter(picture => {
        if (!normalizedQuery) return true;
        const haystack = [
          pictureDisplayFileName(picture),
          typeLabel(picture.picture_type || 'gallery'),
        ]
          .join(' ')
          .toLowerCase();
        return haystack.includes(normalizedQuery);
      })
      .sort((a, b) => {
        const typeCmp =
          typeSortKey(a.picture_type || 'gallery') - typeSortKey(b.picture_type || 'gallery');
        if (typeCmp !== 0) return typeCmp;
        return pictureDisplayFileName(a).localeCompare(pictureDisplayFileName(b));
      });
  }, [normalizedQuery, pictures, typeFilter]);

  const picturesByType = useMemo(() => {
    const sections: Array<{ type: string; label: string; items: WizardPictureItem[] }> = [];
    const indexByType = new Map<string, number>();
    for (const picture of filteredPictures) {
      const type = picture.picture_type || 'gallery';
      let sectionIndex = indexByType.get(type);
      if (sectionIndex === undefined) {
        sectionIndex = sections.length;
        indexByType.set(type, sectionIndex);
        sections.push({ type, label: typeLabel(type), items: [] });
      }
      sections[sectionIndex].items.push(picture);
    }
    return sections;
  }, [filteredPictures]);

  useEffect(() => {
    if (filteredPictures.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (
      !selectedKey ||
      !filteredPictures.some(picture => pictureSelectionKey(picture) === selectedKey)
    ) {
      setSelectedKey(pictureSelectionKey(filteredPictures[0]));
    }
  }, [filteredPictures, selectedKey]);

  const selectedPicture =
    filteredPictures.find(picture => pictureSelectionKey(picture) === selectedKey) || null;

  if (pictures.length === 0) {
    return (
      <EmptyListMessage message="No linked images yet. Upload below or cascade from the university." />
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-bg/30">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
        <p className="text-xs text-text-muted">
          <span className="font-semibold text-text-main">{pictures.length}</span> image
          {pictures.length === 1 ? '' : 's'}
          {typeOptions.length > 0 ? (
            <>
              <span className="mx-1.5 text-border-subtle">·</span>
              <span className="font-semibold text-text-main">{typeOptions.length}</span> type
              {typeOptions.length === 1 ? '' : 's'}
            </>
          ) : null}
          {filteredPictures.length !== pictures.length ? (
            <span className="ml-1.5">(showing {filteredPictures.length})</span>
          ) : null}
        </p>
      </div>

      <div className="space-y-2 border-b border-border-subtle px-3 py-2">
        <div className="relative">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
          />
          <input
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Search images by name or type…"
            className="w-full rounded-lg border border-border-subtle bg-card py-1.5 pl-8 pr-3 text-sm outline-none focus:border-accent"
          />
        </div>
        {typeOptions.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setTypeFilter('all')}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                typeFilter === 'all'
                  ? 'bg-accent/15 text-accent'
                  : 'bg-card text-text-muted hover:text-text-main'
              }`}
            >
              All types
            </button>
            {typeOptions.map(option => (
              <button
                key={option.type}
                type="button"
                onClick={() => setTypeFilter(option.type)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                  typeFilter === option.type
                    ? 'bg-accent/15 text-accent'
                    : 'bg-card text-text-muted hover:text-text-main'
                }`}
              >
                {option.label}
                <span className="ml-1 opacity-70">({option.count})</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {filteredPictures.length === 0 ? (
        <div className="px-3 py-6">
          <EmptyListMessage message="No images match this search or type filter." />
        </div>
      ) : (
        <div className="grid h-[22rem] grid-cols-1 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
          <HeadlessScrollArea className="h-full border-b border-border-subtle md:border-b-0 md:border-r">
            <div className="pb-2">
              {picturesByType.map(section => (
                <div key={section.type}>
                  <div className="sticky top-0 z-10 border-b border-border-subtle bg-surface-bg/95 px-3 py-1.5 backdrop-blur-sm">
                    <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted">
                      {section.label}
                      <span className="ml-1.5 font-semibold normal-case tracking-normal text-text-muted/80">
                        {section.items.length} image{section.items.length === 1 ? '' : 's'}
                      </span>
                    </p>
                  </div>
                  <ul>
                    {section.items.map(picture => {
                      const selectionKey = pictureSelectionKey(picture);
                      const isActive = selectionKey === selectedKey;
                      const isChecked = selectedKeys.has(selectionKey);
                      const imageSrc = rewriteStoredMediaUrl(picture.url) || picture.url || '';
                      return (
                        <li key={selectionKey}>
                          <button
                            type="button"
                            onClick={() => setSelectedKey(selectionKey)}
                            className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors ${
                              isActive ? 'bg-accent/10' : 'hover:bg-card/80'
                            }`}
                          >
                            <span
                              className="shrink-0"
                              onClick={event => event.stopPropagation()}
                              onKeyDown={event => event.stopPropagation()}
                            >
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => onToggleSelection(selectionKey)}
                                aria-label={`Select ${pictureDisplayFileName(picture)}`}
                              />
                            </span>
                            {imageSrc ? (
                              <img
                                src={imageSrc}
                                alt=""
                                className="h-10 w-10 shrink-0 rounded-md border border-border-subtle bg-card object-contain"
                              />
                            ) : (
                              <span className="h-10 w-10 shrink-0 rounded-md border border-border-subtle bg-card" />
                            )}
                            <div className="min-w-0 flex-1">
                              <p
                                className="truncate text-sm font-semibold leading-snug text-text-main"
                                title={pictureDisplayFileName(picture)}
                              >
                                {pictureDisplayFileName(picture)}
                              </p>
                              <p className="mt-0.5 truncate text-xs text-text-muted">
                                {joinMetaParts([
                                  formatFromPicture(picture),
                                  typeLabel(picture.picture_type || 'gallery'),
                                  formatFileSize(picture.file_size),
                                ])}
                              </p>
                            </div>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </HeadlessScrollArea>

          <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card/40">
            {selectedPicture ? (
              <>
                <div className="flex shrink-0 items-center gap-2 border-b border-border-subtle px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p
                      className="truncate text-sm font-semibold leading-snug text-text-main"
                      title={pictureDisplayFileName(selectedPicture)}
                    >
                      {pictureDisplayFileName(selectedPicture)}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-text-muted">
                      {joinMetaParts([
                        formatFromPicture(selectedPicture),
                        typeLabel(selectedPicture.picture_type || 'gallery'),
                        formatFileSize(selectedPicture.file_size),
                      ])}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {(rewriteStoredMediaUrl(selectedPicture.url) || selectedPicture.url) && (
                      <button
                        type="button"
                        onClick={() => onView(selectedPicture)}
                        className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-text-main hover:bg-surface-bg"
                      >
                        <Maximize2 size={12} />
                        View
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={
                        uploading ||
                        deletingKey !== null ||
                        resolvePictureIndex(allPictures, selectedPicture) < 0
                      }
                      onClick={() =>
                        onUnlink(
                          selectedPicture,
                          resolvePictureIndex(allPictures, selectedPicture)
                        )
                      }
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10 disabled:opacity-50"
                    >
                      <Unlink size={12} />
                      Unlink
                    </button>
                  </div>
                </div>
                <div className="relative min-h-0 flex-1 overflow-hidden p-3">
                  {(rewriteStoredMediaUrl(selectedPicture.url) || selectedPicture.url) ? (
                    <button
                      type="button"
                      onClick={() => onView(selectedPicture)}
                      title="View full image"
                      className="absolute inset-3 flex items-center justify-center overflow-hidden rounded-xl border border-border-subtle bg-surface-bg"
                    >
                      <img
                        src={
                          rewriteStoredMediaUrl(selectedPicture.url) ||
                          selectedPicture.url ||
                          ''
                        }
                        alt={pictureDisplayFileName(selectedPicture)}
                        className="h-full w-full object-contain p-2"
                      />
                    </button>
                  ) : (
                    <p className="flex h-full items-center justify-center text-sm text-text-muted">
                      No preview available.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <p className="px-3 py-6 text-sm text-text-muted">Select an image to preview.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const WizardPicturesHierarchyTree: React.FC<WizardPicturesHierarchyTreeProps> = ({
  institutionName,
  colleges,
  pictures,
  collegeOverrides,
  cascadeToColleges,
  activeScopeKey,
  selectedKeys,
  deletingKey,
  uploading,
  onActiveScopeChange,
  onCascadeChange,
  onToggleCollegeOverride,
  onTogglePictureSelection,
  onSetScopeSelection,
  onUnlinkPicture,
  onUnlinkSelectedInScope,
  onUnlinkAllInScope,
  onViewPicture,
  renderUploadPanel,
  onRemoveCollegeTab,
}) => {
  const institutionScope: WizardPicturesEntityScope = { type: 'institution' };
  const institutionKey = institutionScopeKey();
  const knownCollegeKeys = useMemo(
    () => new Set(colleges.map(college => collegeScopeKey(resolveCollegeLocalId(college)))),
    [colleges]
  );

  useEffect(() => {
    if (activeScopeKey === institutionKey) return;
    if (knownCollegeKeys.has(activeScopeKey)) return;
    onActiveScopeChange(institutionKey);
  }, [activeScopeKey, institutionKey, knownCollegeKeys, onActiveScopeChange]);

  const activeCollege = useMemo(() => {
    if (!activeScopeKey.startsWith('college:')) return null;
    const localId = activeScopeKey.slice('college:'.length);
    return colleges.find(college => resolveCollegeLocalId(college) === localId) || null;
  }, [activeScopeKey, colleges]);

  const activeScope: WizardPicturesEntityScope = activeCollege
    ? {
        type: 'college',
        collegeLocalId: resolveCollegeLocalId(activeCollege),
        collegeName: activeCollege.name,
      }
    : institutionScope;

  const activeHasOverride =
    activeScope.type === 'college' && collegeOverrides.has(activeScope.collegeLocalId);

  const activePictures = useMemo(() => {
    if (activeScope.type === 'institution') {
      return filterPicturesForScope(pictures, institutionScope, { collegeOverrides });
    }
    return filterPicturesForScope(pictures, activeScope, {
      collegeOverrides,
      includeInherited: !activeHasOverride && !cascadeToColleges,
    });
  }, [
    activeHasOverride,
    activeScope,
    cascadeToColleges,
    collegeOverrides,
    pictures,
  ]);

  const selectableKeys = activePictures.map(pictureSelectionKey);
  const selectedInScope = selectableKeys.filter(key => selectedKeys.has(key));
  const allSelected =
    selectableKeys.length > 0 && selectedInScope.length === selectableKeys.length;

  return (
    <div className="space-y-4">
      {cascadeToColleges && colleges.length > 0 ? (
        <div
          role="status"
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <p className="font-semibold">Cascade to all colleges is on</p>
          <p className="mt-1">
            University uploads and unlinks also apply to colleges without Override. Turning Override
            off only affects new changes — it does not add images missed while Override was on.
          </p>
        </div>
      ) : null}

      <WizardCollegeTabBar
        institutionLabel={institutionName || 'University'}
        institutionKey={institutionKey}
        colleges={colleges.map(college => {
          const collegeLocalId = resolveCollegeLocalId(college);
          const hasOverride = collegeOverrides.has(collegeLocalId);
          return {
            key: collegeScopeKey(collegeLocalId),
            label: college.name || 'Untitled school',
            title: college.name || 'Untitled school',
            badge: hasOverride ? 'Custom' : null,
            removable: Boolean(onRemoveCollegeTab),
          };
        })}
        activeKey={activeScopeKey}
        onSelect={onActiveScopeChange}
        onRemove={
          onRemoveCollegeTab
            ? key => {
                if (!key.startsWith('college:')) return;
                onRemoveCollegeTab(key.slice('college:'.length));
              }
            : undefined
        }
        ariaLabel="Gallery scopes"
      />

      <div className="rounded-2xl border border-border-subtle bg-card p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h4 className="text-base font-bold text-text-main">
              {activeScope.type === 'institution'
                ? institutionName || 'University'
                : activeCollege?.name || 'School / College'}
            </h4>
            <p className="mt-1 text-sm text-text-muted">
              {activeScope.type === 'institution'
                ? `University · ${activePictures.length} linked image${
                    activePictures.length === 1 ? '' : 's'
                  }`
                : `College · ${activePictures.length} linked image${
                    activePictures.length === 1 ? '' : 's'
                  }${activeHasOverride ? ' · Custom' : ''}`}
            </p>
          </div>

          {activeScope.type === 'institution' ? (
            <label className="flex items-center gap-2 text-xs font-semibold text-text-main">
              <input
                type="checkbox"
                className="rounded border-border-subtle accent-accent"
                checked={cascadeToColleges}
                onChange={event => onCascadeChange(event.target.checked)}
              />
              Cascade to all colleges
            </label>
          ) : (
            <label className="flex items-center gap-2 text-xs font-semibold text-text-main">
              <input
                type="checkbox"
                className="rounded border-border-subtle accent-accent"
                checked={activeHasOverride}
                onChange={event =>
                  onToggleCollegeOverride(activeScope.collegeLocalId, event.target.checked)
                }
              />
              Override university images
            </label>
          )}
        </div>

        {colleges.length === 0 && activeScope.type === 'institution' ? (
          <p className="mb-4 text-sm text-text-muted">
            Add schools / colleges in Step 2 to configure college-level gallery images.
          </p>
        ) : null}

        <div className="space-y-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                Linked images
              </p>
              {activePictures.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  {selectableKeys.length > 0 ? (
                    <label className="inline-flex items-center gap-1.5 text-xs font-semibold text-text-main">
                      <input
                        type="checkbox"
                        className="rounded border-border-subtle accent-accent"
                        checked={allSelected}
                        onChange={event =>
                          onSetScopeSelection(activeScope, selectableKeys, event.target.checked)
                        }
                      />
                      Select all
                      {selectedInScope.length > 0 ? ` (${selectedInScope.length})` : ''}
                    </label>
                  ) : null}
                  {selectedInScope.length > 0 ? (
                    <button
                      type="button"
                      disabled={uploading || deletingKey !== null}
                      onClick={() => onUnlinkSelectedInScope(activeScope)}
                      className="inline-flex items-center gap-1 rounded-lg border border-alert/30 px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10 disabled:opacity-50"
                    >
                      <Unlink size={12} />
                      Unlink selected
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onUnlinkAllInScope(activeScope)}
                    className="inline-flex items-center gap-1 rounded-lg border border-alert/30 px-2 py-1 text-xs font-semibold text-alert hover:bg-alert/10"
                  >
                    <Unlink size={12} />
                    Unlink all
                  </button>
                </div>
              ) : null}
            </div>
            <LinkedImagesBrowser
              key={activeScopeKey}
              pictures={activePictures}
              allPictures={pictures}
              scope={activeScope}
              selectedKeys={selectedKeys}
              deletingKey={deletingKey}
              uploading={uploading}
              onToggleSelection={onTogglePictureSelection}
              onUnlink={(picture, index) => onUnlinkPicture(activeScope, picture, index)}
              onView={picture => onViewPicture(picture, activePictures)}
            />
          </div>

          <div className="rounded-xl border border-border-subtle bg-surface-bg/30 p-4">
            {renderUploadPanel(activeScope)}
          </div>
        </div>
      </div>
    </div>
  );
};

export default WizardPicturesHierarchyTree;

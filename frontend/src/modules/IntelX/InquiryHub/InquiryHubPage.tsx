import { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpenCheck, Plus, Search, Sparkles, X } from 'lucide-react';
import { useConfirmation } from '../../../context/ConfirmationContext';
import { useDebouncedValue } from '../../../hooks/useDebouncedValue';
import { INQUIRY_HIERARCHY, findInquiryNode } from './taxonomy';
import {
  useCreateInquiryFaq,
  useDeleteInquiryFaq,
  useInquiryFaqs,
  useInquiryTaxonomy,
  useUpdateInquiryFaq,
} from './hooks';
import HierarchyNavigator from './HierarchyNavigator';
import FaqEditor from './FaqEditor';
import FaqCard from './FaqCard';
import type { InquiryNode } from './types';

function flattenNodes(nodes: InquiryNode[], depth = 0): Array<InquiryNode & { depth: number }> {
  return nodes.flatMap(node => [
    { ...node, depth },
    ...flattenNodes(node.children, depth + 1),
  ]);
}

export default function InquiryHubPage() {
  const [selectedProcesses, setSelectedProcesses] = useState<string[]>([]);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [addTargetPath, setAddTargetPath] = useState('1.1');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const debouncedSearch = useDebouncedValue(search, 350);
  const taxonomyQuery = useInquiryTaxonomy();
  const taxonomy = taxonomyQuery.data?.length ? taxonomyQuery.data : INQUIRY_HIERARCHY;
  const filterPaths = selectedPaths.length ? selectedPaths : selectedProcesses;
  const faqQuery = useInquiryFaqs(filterPaths, debouncedSearch);
  const createFaq = useCreateInquiryFaq();
  const updateFaq = useUpdateInquiryFaq();
  const deleteFaq = useDeleteInquiryFaq();
  const confirm = useConfirmation();
  const selectedNode = useMemo(() => {
    if (filterPaths.length !== 1) return undefined;
    return findInquiryNode(taxonomy, filterPaths[0]);
  }, [filterPaths, taxonomy]);
  const addTargets = useMemo(() => flattenNodes(taxonomy), [taxonomy]);
  const activeSearch = debouncedSearch.trim();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typingInField =
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.tagName === 'SELECT' ||
        target?.isContentEditable;
      if (typingInField) return;

      const isSearchChord =
        ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') ||
        event.key === '/';
      if (!isSearchChord) return;

      event.preventDefault();
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const deleteItem = async (id: string, question: string) => {
    const accepted = await confirm({
      title: 'Delete this inquiry?',
      message: <>“{question}” will be removed from shared guidance.</>,
      confirmLabel: 'Delete inquiry',
      variant: 'danger',
    });
    if (accepted) deleteFaq.mutate(id);
  };

  return (
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-2xl border border-border-subtle bg-card p-5 shadow-sm">
        <div className="absolute -right-10 -top-12 h-40 w-40 rounded-full bg-accent/10 blur-2xl" />
        <div className="relative flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <span className="rounded-xl bg-accent p-2.5 text-text-dark-bg"><BookOpenCheck size={22} /></span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-extrabold text-text-main">Inquiry Hub</h2>
                <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-accent">Guidance Directory</span>
              </div>
              <p className="mt-1 max-w-2xl text-sm text-text-muted">
                Reusable answers mapped to every stage of the study-abroad journey.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!showAdd && filterPaths.length === 1) setAddTargetPath(filterPaths[0]);
              setShowAdd(value => !value);
            }}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-text-dark-bg hover:brightness-95"
          >
            <Plus size={17} /> Add Q&amp;A
          </button>
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside>
          <HierarchyNavigator
            nodes={taxonomy}
            selectedProcesses={selectedProcesses}
            selectedPaths={selectedPaths}
            onProcessesChange={codes => {
              setSelectedProcesses(codes);
              setShowAdd(false);
            }}
            onPathsChange={codes => {
              setSelectedPaths(codes);
              setShowAdd(false);
            }}
          />
        </aside>

        <main className="min-w-0 space-y-4">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-accent">
                {filterPaths.length === 0
                  ? 'Complete directory'
                  : filterPaths.length === 1
                    ? filterPaths[0] === 'OTHER' ? 'Flexible category' : `Process ${filterPaths[0]}`
                    : `${filterPaths.length} hierarchy selections`}
              </p>
              <h2 className="mt-1 text-xl font-extrabold text-text-main">
                {selectedNode?.name || (filterPaths.length === 0 ? 'All guidance' : 'Selected guidance')}
              </h2>
              <p className="mt-1 text-sm text-text-muted">
                {faqQuery.data?.total ?? 0} saved {faqQuery.data?.total === 1 ? 'answer' : 'answers'}
                {activeSearch ? ` matching “${activeSearch}”` : ''}
              </p>
            </div>
            <label className="relative block w-full sm:max-w-sm">
              <span className="sr-only">Search inquiries</span>
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                ref={searchInputRef}
                value={search}
                onChange={event => setSearch(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Escape') {
                    if (search) {
                      event.preventDefault();
                      setSearch('');
                    } else {
                      searchInputRef.current?.blur();
                    }
                  }
                }}
                placeholder="Search questions or answers"
                className="w-full rounded-xl border border-border-subtle bg-card py-2.5 pl-9 pr-10 text-sm text-text-main outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
              />
              {search ? (
                <button
                  type="button"
                  onClick={() => {
                    setSearch('');
                    searchInputRef.current?.focus();
                  }}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-text-muted hover:bg-black/5 hover:text-text-main"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              ) : (
                <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-border-subtle bg-black/[0.03] px-1.5 py-0.5 text-[10px] font-semibold text-text-muted sm:inline">
                  /
                </kbd>
              )}
            </label>
          </div>

          {showAdd ? (
            <section className="rounded-2xl border border-accent/30 bg-accent/5 p-5">
              <div className="mb-4 flex items-center gap-2">
                <Sparkles size={18} className="text-accent" />
                <h3 className="font-bold text-text-main">Add guidance</h3>
              </div>
              <label className="mb-4 block text-xs font-semibold uppercase tracking-wide text-text-muted">
                Save under
                <select
                  value={addTargetPath}
                  onChange={event => setAddTargetPath(event.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-border-subtle bg-card px-3 py-2.5 text-sm normal-case tracking-normal text-text-main outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                >
                  {addTargets.map(node => (
                    <option key={node.code} value={node.code}>
                      {'— '.repeat(node.depth)}{node.code === 'OTHER' ? '' : `${node.code} `}{node.name}
                    </option>
                  ))}
                </select>
              </label>
              <FaqEditor
                path={addTargetPath}
                busy={createFaq.isPending}
                onCancel={() => setShowAdd(false)}
                onSubmit={async payload => {
                  await createFaq.mutateAsync(payload);
                  setShowAdd(false);
                }}
              />
            </section>
          ) : null}

          {faqQuery.isLoading ? (
            <div className="space-y-3" aria-label="Loading inquiries">
              {[0, 1, 2].map(item => <div key={item} className="h-32 animate-pulse rounded-2xl border border-border-subtle bg-card" />)}
            </div>
          ) : faqQuery.isError ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
              Inquiry Hub could not be loaded. Please retry.
            </div>
          ) : faqQuery.data?.items.length ? (
            <div className="space-y-3">
              {faqQuery.data.items.map(faq => (
                <FaqCard
                  key={faq.id}
                  faq={faq}
                  busy={updateFaq.isPending}
                  onUpdate={payload => updateFaq.mutateAsync({ id: faq.id, ...payload }).then(() => undefined)}
                  onDelete={() => void deleteItem(faq.id, faq.question)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border-subtle bg-card px-6 py-12 text-center">
              <BookOpenCheck size={32} className="mx-auto text-text-muted/60" />
              <h3 className="mt-3 font-bold text-text-main">No guidance found</h3>
              <p className="mt-1 text-sm text-text-muted">
                {activeSearch
                  ? `No matches for “${activeSearch}”. Try another query or clear search.`
                  : 'Add the first question and answer for this process.'}
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

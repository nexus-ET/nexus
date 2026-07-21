const ROWS = 8;

const InstitutionsTableSkeleton: React.FC = () => (
  <div className="divide-y divide-border-subtle/70" aria-hidden="true">
    {Array.from({ length: ROWS }).map((_, index) => (
      <div key={index} className="flex animate-pulse items-center gap-4 px-6 py-4">
        <div className="h-4 flex-1 rounded bg-surface-bg" />
        <div className="hidden h-4 w-24 rounded bg-surface-bg md:block" />
        <div className="hidden h-4 w-20 rounded bg-surface-bg lg:block" />
        <div className="hidden h-4 w-28 rounded bg-surface-bg xl:block" />
        <div className="h-4 w-16 rounded bg-surface-bg" />
      </div>
    ))}
  </div>
);

export default InstitutionsTableSkeleton;

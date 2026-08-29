import { BookOpen } from 'lucide-react';

/** Empty 1.1-style workspace shell for later subprocess pages. */
export default function SubprocessShellWorkspace({
  code,
  title,
}: {
  code: string;
  title: string;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-border-subtle bg-card shadow-[0_1px_0_rgba(50,47,134,0.04)]">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border-subtle bg-gradient-to-r from-accent/[0.06] via-surface-bg to-surface-bg px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent/70">
            Sub-Process {code}
          </p>
          <h3 className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-text-main">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
              <BookOpen size={14} />
            </span>
            {title}
          </h3>
        </div>
      </div>
      <div className="min-h-[12rem] bg-surface-bg/40" />
    </section>
  );
}

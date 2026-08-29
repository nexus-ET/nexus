import { BookOpen } from 'lucide-react';
import { useCounsellingProcessNodes } from './CounsellingProcessStrip';

export default function CounsellingSubprocessPlaceholder({ code }: { code: string }) {
  const nodes = useCounsellingProcessNodes();
  const node = nodes.find(item => item.code === code);
  const title = node?.title || `Sub-process ${code}`;

  return (
    <section className="overflow-hidden rounded-xl border border-border-subtle bg-card shadow-[0_1px_0_rgba(50,47,134,0.04)]">
      <div className="border-b border-border-subtle bg-gradient-to-r from-accent/[0.06] via-surface-bg to-surface-bg px-4 py-3">
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
    </section>
  );
}

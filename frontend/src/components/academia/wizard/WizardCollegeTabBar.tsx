import { GraduationCap, Landmark, Plus, X } from 'lucide-react';

export type WizardCollegeTabItem = {
  key: string;
  label: string;
  title?: string;
  badge?: string | null;
  removable?: boolean;
};

export interface WizardCollegeTabBarProps {
  institutionLabel: string;
  institutionKey: string;
  colleges: WizardCollegeTabItem[];
  activeKey: string;
  onSelect: (key: string) => void;
  onAdd?: () => void;
  onRemove?: (key: string) => void;
  addLabel?: string;
  ariaLabel?: string;
}

export const wizardCollegeTabButtonClass = (active: boolean) =>
  `inline-flex max-w-[14rem] items-center gap-2 rounded-t-lg border-b-2 px-3 py-2.5 text-sm font-semibold transition-colors ${
    active
      ? 'border-accent bg-accent/5 text-accent'
      : 'border-transparent text-text-muted hover:bg-surface-bg/60 hover:text-text-main'
  }`;

/**
 * Institution + college tabs that wrap into multiple rows when many colleges exist.
 * Put the Add action on its own row so it stays visible while tabs reflow.
 */
const WizardCollegeTabBar: React.FC<WizardCollegeTabBarProps> = ({
  institutionLabel,
  institutionKey,
  colleges,
  activeKey,
  onSelect,
  onAdd,
  onRemove,
  addLabel = 'Add school / college',
  ariaLabel = 'Institution and colleges',
}) => (
  <div className="space-y-2">
    {onAdd ? (
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex shrink-0 items-center gap-1 rounded-xl bg-accent px-3 py-1.5 text-sm font-semibold text-text-dark-bg"
        >
          <Plus size={14} />
          {addLabel}
        </button>
      </div>
    ) : null}

    <nav
      className="flex w-full flex-wrap content-start gap-x-1 gap-y-1 border-b border-border-subtle pb-px"
      aria-label={ariaLabel}
      role="tablist"
    >
      <button
        type="button"
        role="tab"
        aria-selected={activeKey === institutionKey}
        onClick={() => onSelect(institutionKey)}
        className={wizardCollegeTabButtonClass(activeKey === institutionKey)}
      >
        <Landmark size={15} className="shrink-0" />
        <span className="truncate">{institutionLabel || 'Institution'}</span>
      </button>

      {colleges.map(college => {
        const isActive = activeKey === college.key;
        return (
          <div key={college.key} className="inline-flex max-w-full items-stretch">
            <button
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelect(college.key)}
              className={wizardCollegeTabButtonClass(isActive)}
              title={college.title || college.label}
            >
              <GraduationCap size={15} className="shrink-0" />
              <span className="truncate">{college.label || 'Untitled school'}</span>
              {college.badge ? (
                <span className="rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent">
                  {college.badge}
                </span>
              ) : null}
            </button>
            {college.removable && onRemove ? (
              <button
                type="button"
                title={`Remove ${college.label || 'school / college'}`}
                aria-label={`Remove ${college.label || 'school / college'}`}
                onClick={() => onRemove(college.key)}
                className="self-center rounded-md p-1 text-text-muted hover:bg-alert/10 hover:text-alert"
              >
                <X size={12} />
              </button>
            ) : null}
          </div>
        );
      })}
    </nav>
  </div>
);

export default WizardCollegeTabBar;

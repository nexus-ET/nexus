export const categoryBadgeClass = (category?: string | null): string => {
  switch ((category || '').trim()) {
    case 'Lead':
      return 'bg-sky-100 text-sky-800 border-sky-200';
    case 'Counselling':
      return 'bg-violet-100 text-violet-900 border-violet-200';
    case 'Admission':
      return 'bg-amber-100 text-amber-900 border-amber-200';
    case 'Visa':
      return 'bg-indigo-100 text-indigo-900 border-indigo-200';
    case 'Pre-Departure':
      return 'bg-yellow-100 text-yellow-900 border-yellow-200';
    case 'Arrival':
      return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    case 'Prospect':
      return 'bg-slate-100 text-slate-800 border-slate-200';
    default:
      return 'bg-surface-bg text-text-muted border-border-subtle';
  }
};

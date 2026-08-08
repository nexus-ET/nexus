import { useEffect, useState } from 'react';
import { Lightbulb, X } from 'lucide-react';
import { useIntelPreferences } from '../../hooks/useNexusIntel';

interface IntelProTipProps {
  tipId: string;
  children: React.ReactNode;
}

const STORAGE_PREFIX = 'nexus.intel.tip.dismissed.';

const IntelProTip: React.FC<IntelProTipProps> = ({ tipId, children }) => {
  const prefs = useIntelPreferences();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    setDismissed(localStorage.getItem(`${STORAGE_PREFIX}${tipId}`) === '1');
  }, [tipId]);

  if (prefs.data?.enable_contextual_tips === false || dismissed) {
    return null;
  }

  return (
    <aside className="relative rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
      <div className="flex items-start gap-2 pr-6">
        <Lightbulb size={16} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-semibold">Intel Pro Tip</p>
          <p className="mt-0.5">{children}</p>
        </div>
      </div>
      <button
        type="button"
        aria-label="Dismiss tip"
        className="absolute right-2 top-2 text-amber-800/70 hover:text-amber-950"
        onClick={() => {
          localStorage.setItem(`${STORAGE_PREFIX}${tipId}`, '1');
          setDismissed(true);
        }}
      >
        <X size={14} />
      </button>
    </aside>
  );
};

export default IntelProTip;

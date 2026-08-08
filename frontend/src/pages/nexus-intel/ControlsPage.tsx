import DailyTriviaCard from '../../components/nexus-intel/DailyTriviaCard';
import IntelProTip from '../../components/nexus-intel/IntelProTip';
import { useIntelPreferences, useUpdateIntelPreferences } from '../../hooks/useNexusIntel';

const ControlsPage: React.FC = () => {
  const prefsQuery = useIntelPreferences();
  const updatePrefs = useUpdateIntelPreferences();
  const prefs = prefsQuery.data;

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-4">
        <h2 className="text-lg font-bold text-text-main">Intel Controls</h2>
        <label className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface-bg px-3 py-3 text-sm">
          <span>
            <span className="block font-semibold text-text-main">Show Intel Tips</span>
            <span className="text-text-muted">Contextual terminology tooltips and pro tips</span>
          </span>
          <input
            type="checkbox"
            checked={prefs?.enable_contextual_tips ?? true}
            onChange={e => updatePrefs.mutate({ enable_contextual_tips: e.target.checked })}
            className="h-4 w-4"
          />
        </label>
        <label className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-surface-bg px-3 py-3 text-sm">
          <span>
            <span className="block font-semibold text-text-main">Enable Daily Trivia</span>
            <span className="text-text-muted">Daily Nexus Intel question on dashboard</span>
          </span>
          <input
            type="checkbox"
            checked={prefs?.enable_daily_trivia ?? true}
            onChange={e => updatePrefs.mutate({ enable_daily_trivia: e.target.checked })}
            className="h-4 w-4"
          />
        </label>
        <IntelProTip tipId="controls-funds">
          Use Proof of Funds with destination-specific holding periods before locking visa timelines.
        </IntelProTip>
      </section>

      <DailyTriviaCard />
    </div>
  );
};

export default ControlsPage;

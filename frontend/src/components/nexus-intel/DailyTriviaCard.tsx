import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useAnswerTrivia, useDailyTrivia, useIntelPreferences } from '../../hooks/useNexusIntel';

const DailyTriviaCard: React.FC = () => {
  const prefs = useIntelPreferences();
  const enabled = prefs.data?.enable_daily_trivia !== false;
  const triviaQuery = useDailyTrivia(enabled);
  const answerMutation = useAnswerTrivia();
  const [selected, setSelected] = useState<number | null>(null);
  const trivia = triviaQuery.data;

  if (!enabled) {
    return (
      <section className="rounded-2xl border border-border-subtle bg-card p-4 text-sm text-text-muted">
        Daily trivia is disabled in your preferences.
      </section>
    );
  }

  if (triviaQuery.isLoading) {
    return (
      <section className="rounded-2xl border border-border-subtle bg-card p-4 text-sm text-text-muted">
        Loading daily trivia…
      </section>
    );
  }

  if (!trivia) {
    return (
      <section className="rounded-2xl border border-border-subtle bg-card p-4 text-sm text-text-muted">
        No daily trivia is scheduled yet.
      </section>
    );
  }

  const answered = trivia.already_answered || Boolean(answerMutation.data);
  const result = answerMutation.data;
  const explanation = result?.explanation || trivia.explanation;
  const streak = result?.streak ?? trivia.streak;
  const correctCount = result?.correct_count ?? trivia.correct_count;

  return (
    <section className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 text-lg font-bold text-text-main">
          <Sparkles size={18} />
          Daily Nexus Intel Question
        </h2>
        <span className="text-xs font-semibold text-text-muted">
          Streak {streak} · Correct {correctCount}
        </span>
      </div>
      <p className="text-sm font-semibold text-text-main">{trivia.question}</p>
      <div className="space-y-1">
        {trivia.options.map((option, index) => (
          <button
            key={option}
            type="button"
            disabled={answered}
            onClick={() => setSelected(index)}
            className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${
              selected === index || trivia.selected_option_index === index
                ? 'border-accent/50 bg-accent/10'
                : 'border-border-subtle bg-surface-bg'
            } disabled:opacity-80`}
          >
            {option}
          </button>
        ))}
      </div>
      {!answered ? (
        <button
          type="button"
          disabled={selected == null || answerMutation.isPending}
          onClick={() =>
            selected != null &&
            answerMutation.mutate({
              trivia_id: trivia.id,
              selected_option_index: selected,
            })
          }
          className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          Submit answer
        </button>
      ) : (
        <p className="text-sm text-text-muted">
          {(result?.is_correct ?? trivia.is_correct) ? 'Correct! ' : 'Keep learning — '}
          {explanation}
        </p>
      )}
    </section>
  );
};

export default DailyTriviaCard;

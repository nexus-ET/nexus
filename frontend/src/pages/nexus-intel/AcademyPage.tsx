import { useState } from 'react';
import { useIntelAcademy } from '../../hooks/useNexusIntel';

const AcademyPage: React.FC = () => {
  const academyQuery = useIntelAcademy();
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-muted">
        Short certification cards (~5 minutes) with interactive quizzes for regulatory refreshers.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {(academyQuery.data || []).map(module => {
          const selected = answers[module.id];
          const showResult = Boolean(revealed[module.id]);
          const correct = module.quiz.correct_option_index;
          return (
            <article key={module.id} className="rounded-2xl border border-border-subtle bg-card p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-bold text-text-main">{module.title}</h3>
                  <p className="text-sm text-text-muted mt-1">{module.summary}</p>
                </div>
                <span className="rounded-full bg-surface-bg px-2 py-1 text-xs font-semibold text-text-muted">
                  {module.duration_minutes} min
                </span>
              </div>
              <div className="rounded-xl border border-border-subtle bg-surface-bg p-3 space-y-2">
                <p className="text-sm font-semibold text-text-main">{module.quiz.question}</p>
                <div className="space-y-1">
                  {module.quiz.options.map((option, index) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setAnswers(prev => ({ ...prev, [module.id]: index }))}
                      className={`block w-full rounded-lg border px-3 py-2 text-left text-sm ${
                        selected === index
                          ? 'border-accent/50 bg-accent/10'
                          : 'border-border-subtle bg-card'
                      }`}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  disabled={selected == null}
                  onClick={() => setRevealed(prev => ({ ...prev, [module.id]: true }))}
                  className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
                >
                  Check answer
                </button>
                {showResult ? (
                  <p className="text-sm text-text-muted">
                    {selected === correct ? 'Correct. ' : 'Not quite. '}
                    {module.quiz.explanation}
                  </p>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
};

export default AcademyPage;

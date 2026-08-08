import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';

const loadingPhrases = [
  'Hold on...',
  'Just a sec.',
  'Looking now...',
  'One moment...',
  'Almost done.',
  'Check this...',
  'Finding it...',
  'Wait here...',
  'Right away...',
  'Stay close...',
  'Getting ready...',
  'Reading text...',
  'Digging in...',
  'Sorting out...',
  'Piece by piece...',
  'Putting it...',
  'Adding up...',
  'Making sense...',
  'Thinking fast...',
  'Almost there...',
  'Hang tight...',
  'Be right back...',
  'Good things...',
  'Take a breath...',
  'Here it is.',
] as const;

const TICK_MS = 1000;
const PHRASE_COUNT = loadingPhrases.length;

/**
 * Fast 1s simple-word ticker while the Intel AI RAG response is pending.
 * Loops with index % 25 when generation takes longer than 25 seconds.
 */
export default function IntelLoadingBubble() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex(prev => (prev + 1) % PHRASE_COUNT);
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const phrase = loadingPhrases[index % PHRASE_COUNT];

  return (
    <div
      className="inline-flex max-w-full items-center gap-2.5 rounded-xl border border-border-subtle/60 bg-card/80 px-3.5 py-2 shadow-sm backdrop-blur-md"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Sparkles size={15} className="shrink-0 animate-spin text-accent" />
      <p
        key={index}
        className="intel-phrase-tick text-sm font-medium text-text-main"
      >
        {phrase}
      </p>
      <style>{`
        @keyframes intel-phrase-tick {
          from { opacity: 0; transform: translateY(3px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .intel-phrase-tick {
          animation: intel-phrase-tick 0.28s ease-out;
        }
      `}</style>
    </div>
  );
}

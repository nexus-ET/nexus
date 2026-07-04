import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import DatePicker from 'react-datepicker';
import { Loader2, Mic, MicOff, Save, Sparkles } from 'lucide-react';
import { apiFetch } from '../utils/api';

type SpeechRecognitionConstructor = new () => SpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

interface CounsellingSummarizeResponse {
  preferred_universities: string[];
  scholarship_interests: string;
  career_goals: string;
  recommendations: string;
  next_follow_up: string | null;
}

interface CounsellingSessionNoteResponse {
  booking_id: number;
  ai_transcription?: string | null;
  preferred_universities?: string[];
  scholarship_interests?: string | null;
  career_goals?: string | null;
  officer_recommendations?: string | null;
  next_follow_up?: string | null;
  updated_at?: string | null;
}

interface CounsellingSessionPanelProps {
  bookingId: number;
  candidateName: string;
  onSaved?: () => void;
}

const CounsellingSessionPanel: React.FC<CounsellingSessionPanelProps> = ({
  bookingId,
  candidateName,
  onSaved,
}) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [aiTranscription, setAiTranscription] = useState('');
  const [preferredUniversities, setPreferredUniversities] = useState<string[]>([]);
  const [universityInput, setUniversityInput] = useState('');
  const [scholarshipInterests, setScholarshipInterests] = useState('');
  const [careerGoals, setCareerGoals] = useState('');
  const [officerRecommendations, setOfficerRecommendations] = useState('');
  const [nextFollowUp, setNextFollowUp] = useState<Date | null>(null);
  const [isDictating, setIsDictating] = useState(false);
  const [dictationSupported, setDictationSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const transcriptionRef = useRef('');
  const dictationBaseRef = useRef('');
  const dictationCommittedRef = useRef('');
  const dictationInterimRef = useRef('');

  const speechRecognitionCtor = useMemo(
    () => window.SpeechRecognition || window.webkitSpeechRecognition,
    []
  );

  useEffect(() => {
    transcriptionRef.current = aiTranscription;
  }, [aiTranscription]);

  useEffect(() => {
    setDictationSupported(Boolean(speechRecognitionCtor));
  }, [speechRecognitionCtor]);

  const applyNote = useCallback((note: CounsellingSessionNoteResponse) => {
    setAiTranscription(note.ai_transcription || '');
    setPreferredUniversities(note.preferred_universities || []);
    setScholarshipInterests(note.scholarship_interests || '');
    setCareerGoals(note.career_goals || '');
    setOfficerRecommendations(note.officer_recommendations || '');
    setNextFollowUp(note.next_follow_up ? new Date(note.next_follow_up) : null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const note = (await apiFetch(
          `bookings/mine/${bookingId}/session-notes`
        )) as CounsellingSessionNoteResponse;
        if (!cancelled) applyNote(note);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load session notes.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applyNote, bookingId]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      recognitionRef.current = null;
    };
  }, []);

  const flushDictationToTranscription = useCallback(() => {
    if (dictationInterimRef.current) {
      dictationCommittedRef.current += dictationInterimRef.current;
      dictationInterimRef.current = '';
    }
    const merged = `${dictationBaseRef.current}${dictationCommittedRef.current}`.trimEnd();
    const withSpacing =
      dictationBaseRef.current && dictationCommittedRef.current && !dictationBaseRef.current.endsWith(' ')
        ? `${dictationBaseRef.current.trimEnd()} ${dictationCommittedRef.current.trim()}`
        : merged;
    setAiTranscription(withSpacing);
    transcriptionRef.current = withSpacing;
  }, []);

  const stopDictation = useCallback(() => {
    flushDictationToTranscription();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setIsDictating(false);
  }, [flushDictationToTranscription]);

  const startDictation = () => {
    if (!speechRecognitionCtor) {
      setError('Speech dictation is not supported in this browser. Try Chrome or Edge.');
      return;
    }
    setError(null);
    dictationBaseRef.current = transcriptionRef.current;
    dictationCommittedRef.current = '';
    dictationInterimRef.current = '';

    const recognition = new speechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalChunk = '';
      let interimChunk = '';

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const spoken = result[0]?.transcript ?? '';
        if (!spoken) continue;
        if (result.isFinal) {
          finalChunk += spoken;
        } else {
          interimChunk += spoken;
        }
      }

      if (finalChunk) {
        dictationCommittedRef.current += finalChunk;
        dictationInterimRef.current = '';
      } else if (interimChunk) {
        dictationInterimRef.current = interimChunk;
      }

      const preview = `${dictationBaseRef.current}${dictationCommittedRef.current}${dictationInterimRef.current}`;
      setAiTranscription(preview);
      transcriptionRef.current = preview;
    };

    recognition.onerror = () => {
      stopDictation();
      setError('Dictation stopped due to a microphone or speech recognition error.');
    };

    recognition.onend = () => {
      flushDictationToTranscription();
      recognitionRef.current = null;
      setIsDictating(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsDictating(true);
  };

  const toggleDictation = () => {
    if (isDictating) {
      stopDictation();
      return;
    }
    startDictation();
  };

  const addUniversity = () => {
    const value = universityInput.trim();
    if (!value) return;
    setPreferredUniversities(prev => (prev.includes(value) ? prev : [...prev, value]));
    setUniversityInput('');
  };

  const removeUniversity = (value: string) => {
    setPreferredUniversities(prev => prev.filter(item => item !== value));
  };

  const handleSummarize = async () => {
    const raw = aiTranscription.trim();
    if (!raw) {
      setError('Add dictation or type session notes before summarizing.');
      return;
    }
    try {
      setSummarizing(true);
      setError(null);
      setSuccess(null);
      const result = (await apiFetch('counselling/summarize', {
        method: 'POST',
        body: JSON.stringify({ raw_text: raw }),
      })) as CounsellingSummarizeResponse;

      if (result.preferred_universities?.length) {
        setPreferredUniversities(result.preferred_universities);
      }
      if (result.scholarship_interests?.trim()) {
        setScholarshipInterests(result.scholarship_interests.trim());
      }
      if (result.career_goals?.trim()) {
        setCareerGoals(result.career_goals.trim());
      }
      if (result.recommendations?.trim()) {
        setOfficerRecommendations(result.recommendations.trim());
      }
      if (result.next_follow_up) {
        setNextFollowUp(new Date(result.next_follow_up));
      }
      setSuccess('AI summary applied to the form. Review and edit before saving.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to summarize session notes.');
    } finally {
      setSummarizing(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      await apiFetch(`bookings/mine/${bookingId}/session-notes`, {
        method: 'POST',
        body: JSON.stringify({
          ai_transcription: aiTranscription.trim() || null,
          preferred_universities: preferredUniversities,
          scholarship_interests: scholarshipInterests.trim() || null,
          career_goals: careerGoals.trim() || null,
          officer_recommendations: officerRecommendations.trim() || null,
          next_follow_up: nextFollowUp ? nextFollowUp.toISOString().slice(0, 10) : null,
        }),
      });
      setSuccess('Counselling session notes saved.');
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save session notes.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">
        <Loader2 size={22} className="animate-spin mr-2" />
        Loading counselling session...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Document the counselling session for <strong className="text-text-main">{candidateName}</strong>.
        Dictate or type notes, summarize with AI, then save structured fields.
      </p>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {success}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <section className="rounded-xl border border-border-subtle bg-surface-bg/40 p-4 space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-text-main">AI Assistant</h4>
            <p className="text-xs text-text-muted mt-1">Voice input and AI extraction for session notes.</p>
          </div>

          <div className="rounded-xl border border-violet-200 bg-violet-50/70 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-violet-900">Voice / Audio Input</p>
                <p className="text-xs text-violet-800/80 mt-0.5">
                  {dictationSupported
                    ? 'Tap the microphone and speak your session notes.'
                    : 'Dictation works best in Chrome or Edge on desktop.'}
                </p>
              </div>
              <button
                type="button"
                onClick={toggleDictation}
                disabled={!dictationSupported}
                className={`inline-flex h-12 w-12 items-center justify-center rounded-full border shadow-sm transition-colors ${
                  isDictating
                    ? 'border-red-300 bg-red-100 text-red-700'
                    : 'border-violet-300 bg-white text-violet-700 hover:bg-violet-100'
                } disabled:opacity-50`}
                aria-label={isDictating ? 'Stop dictation' : 'Start dictation'}
              >
                {isDictating ? <MicOff size={22} /> : <Mic size={22} />}
              </button>
            </div>
            {isDictating && (
              <p className="text-xs font-medium text-red-700 animate-pulse">Listening… tap again to stop.</p>
            )}
          </div>

          <button
            type="button"
            onClick={handleSummarize}
            disabled={summarizing || !aiTranscription.trim()}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-violet-700 px-4 py-3 text-sm font-semibold text-white hover:bg-violet-800 disabled:opacity-60"
          >
            {summarizing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            AI Summarize &amp; Auto-Fill
          </button>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">
              AI Transcription / Summary Preview
            </label>
            <textarea
              value={aiTranscription}
              onChange={event => setAiTranscription(event.target.value)}
              rows={10}
              placeholder="Dictated or typed session notes appear here..."
              className="w-full rounded-lg border border-border-subtle bg-card px-3 py-2 text-sm resize-y"
            />
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-card p-4 space-y-4">
          <div>
            <h4 className="text-sm font-semibold text-text-main">Session Form</h4>
            <p className="text-xs text-text-muted mt-1">Structured counselling documentation.</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Preferred Universities</label>
            <div className="flex gap-2">
              <input
                value={universityInput}
                onChange={event => setUniversityInput(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addUniversity();
                  }
                }}
                placeholder="Type a university and press Enter"
                className="flex-1 rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={addUniversity}
                className="rounded-lg border border-border-subtle px-3 py-2 text-xs font-semibold hover:bg-surface-bg"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {preferredUniversities.map(university => (
                <span
                  key={university}
                  className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-bg px-2.5 py-1 text-xs"
                >
                  {university}
                  <button
                    type="button"
                    onClick={() => removeUniversity(university)}
                    className="text-text-muted hover:text-text-main"
                    aria-label={`Remove ${university}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Scholarship Interests</label>
            <textarea
              value={scholarshipInterests}
              onChange={event => setScholarshipInterests(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm resize-y"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Career Goals</label>
            <textarea
              value={careerGoals}
              onChange={event => setCareerGoals(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm resize-y"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Officer Recommendations</label>
            <textarea
              value={officerRecommendations}
              onChange={event => setOfficerRecommendations(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm resize-y"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5">Next Follow-up</label>
            <DatePicker
              selected={nextFollowUp}
              onChange={(date: Date | null) => setNextFollowUp(date)}
              dateFormat="dd MMM yyyy"
              placeholderText="Select follow-up date"
              className="w-full rounded-lg border border-border-subtle bg-surface-bg px-3 py-2 text-sm"
              wrapperClassName="w-full"
              popperProps={{ strategy: 'fixed' }}
              isClearable
            />
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-text-dark-bg hover:opacity-90 disabled:opacity-60"
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Session Notes
          </button>
        </section>
      </div>
    </div>
  );
};

export default CounsellingSessionPanel;

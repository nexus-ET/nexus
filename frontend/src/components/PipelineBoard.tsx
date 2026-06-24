import React, { useMemo, useState } from 'react';
import { AlertCircle, GripVertical, UserRound } from 'lucide-react';
import { useNexusState, PipelineCard } from '../hooks/useNexusState';
import SessionWrapUpDrawer from './SessionWrapUpDrawer';

interface PipelineBoardProps {
  onSelectLead: (card: PipelineCard) => void;
}

const PipelineBoard: React.FC<PipelineBoardProps> = ({ onSelectLead }) => {
  const { pipeline, moveCandidate, refreshPipeline, refreshTasks, refreshPulse } = useNexusState();
  const [draggingLeadId, setDraggingLeadId] = useState<number | null>(null);
  const [wrapUpBookingId, setWrapUpBookingId] = useState<number | null>(null);
  const [wrapUpCandidateName, setWrapUpCandidateName] = useState('');

  const stages = pipeline?.stages ?? [];
  const columns = pipeline?.columns ?? {};

  const totalCards = useMemo(
    () => Object.values(columns).reduce((sum, cards) => sum + cards.length, 0),
    [columns]
  );

  const handleDrop = async (stageKey: string) => {
    if (draggingLeadId === null) return;
    await moveCandidate(draggingLeadId, stageKey);
    setDraggingLeadId(null);
  };

  const openWrapUp = (card: PipelineCard) => {
    if (!card.latest_booking_id) return;
    setWrapUpBookingId(card.latest_booking_id);
    setWrapUpCandidateName(card.full_name);
  };

  return (
    <div className="flex h-full flex-col rounded-xl border border-[#84d2f6]/50 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-[#84d2f6]/40 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-[#03045e]">Admission Pipeline</h2>
          <p className="text-xs text-[#386fa4]">{totalCards} active candidates</p>
        </div>
      </div>

      <div className="custom-scrollbar flex flex-1 gap-3 overflow-x-auto p-4">
        {stages.map(stage => (
          <div
            key={stage.key}
            className="min-w-[220px] flex-1 rounded-lg bg-[#f7f9f9] p-2"
            onDragOver={event => event.preventDefault()}
            onDrop={() => void handleDrop(stage.key)}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#386fa4]">{stage.label}</p>
              <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-[#03045e]">
                {(columns[stage.key] ?? []).length}
              </span>
            </div>

            <div className="space-y-2">
              {(columns[stage.key] ?? []).map(card => (
                <div
                  key={card.lead_id}
                  draggable
                  onDragStart={() => setDraggingLeadId(card.lead_id)}
                  onDragEnd={() => setDraggingLeadId(null)}
                  onClick={() => onSelectLead(card)}
                  className="cursor-pointer rounded-lg border border-[#84d2f6]/40 bg-white p-3 shadow-sm transition hover:border-[#59a5d8]"
                >
                  <div className="flex items-start gap-2">
                    <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-[#84d2f6]" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <UserRound className="h-3.5 w-3.5 text-[#386fa4]" />
                        <p className="truncate text-sm font-medium text-[#03045e]">{card.full_name}</p>
                      </div>
                      {card.is_stalled && (
                        <p className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-amber-700">
                          <AlertCircle className="h-3 w-3" />
                          Stalled
                        </p>
                      )}
                      {card.latest_booking_id && (
                        <button
                          type="button"
                          onClick={event => {
                            event.stopPropagation();
                            openWrapUp(card);
                          }}
                          className="mt-2 rounded-md bg-[#03045e] px-2 py-1 text-[10px] font-medium text-white hover:bg-[#386fa4]"
                        >
                          Session Wrap-up
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <SessionWrapUpDrawer
        open={wrapUpBookingId !== null}
        bookingId={wrapUpBookingId}
        candidateName={wrapUpCandidateName}
        onClose={() => {
          setWrapUpBookingId(null);
          setWrapUpCandidateName('');
        }}
        onSubmitted={async () => {
          await Promise.all([refreshPipeline(), refreshTasks(), refreshPulse()]);
        }}
      />
    </div>
  );
};

export default PipelineBoard;

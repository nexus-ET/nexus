import React from 'react';
import { ClipboardList, Clock3, Loader2, Radio, Users } from 'lucide-react';
import ChatWindow from '../components/ChatWindow';
import PipelineBoard from '../components/PipelineBoard';
import SystemHealthBar from '../components/SystemHealthBar';
import { ChatConfigProvider } from '../hooks/useChat';
import { NexusStateProvider, PipelineCard, useNexusState } from '../hooks/useNexusState';

const PulseWidgets: React.FC = () => {
  const { pulse } = useNexusState();
  if (!pulse) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#84d2f6]/50 bg-white p-4 text-sm text-[#386fa4]">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading operational pulse...
      </div>
    );
  }

  const widgets = [
    { label: 'Pending Review', value: pulse.pending_review, icon: ClipboardList },
    { label: 'Stalled Candidates', value: pulse.stalled_candidates, icon: Clock3 },
    { label: 'Open Tasks', value: pulse.open_tasks, icon: Radio },
    { label: 'Scheduled Sessions', value: pulse.scheduled_sessions, icon: Users },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {widgets.map(widget => (
        <div
          key={widget.label}
          className="rounded-xl border border-[#84d2f6]/50 bg-white p-3 shadow-sm"
        >
          <div className="flex items-center gap-2 text-[#386fa4]">
            <widget.icon className="h-4 w-4" />
            <p className="text-xs font-medium">{widget.label}</p>
          </div>
          <p className="mt-2 text-2xl font-semibold text-[#322f86]">{widget.value}</p>
        </div>
      ))}
    </div>
  );
};

const TaskWidget: React.FC = () => {
  const { tasks } = useNexusState();

  return (
    <div className="rounded-xl border border-[#84d2f6]/50 bg-white shadow-sm">
      <div className="border-b border-[#84d2f6]/40 px-4 py-3">
        <h3 className="text-sm font-semibold text-[#322f86]">Session Wrap-up Tasks</h3>
        <p className="text-xs text-[#386fa4]">{tasks.length} open action items</p>
      </div>
      <div className="custom-scrollbar max-h-56 space-y-2 overflow-y-auto p-3">
        {tasks.length === 0 ? (
          <p className="text-xs text-[#386fa4]">No pending tasks from recent wrap-ups.</p>
        ) : (
          tasks.map(task => (
            <div key={task.id} className="rounded-lg bg-[#f7f9f9] px-3 py-2">
              <p className="text-sm font-medium text-[#322f86]">{task.title}</p>
              <p className="text-[10px] text-[#386fa4]">
                {task.candidate_name} · {new Date(task.created_at).toLocaleDateString()}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

const CommandCenterLayout: React.FC = () => {
  const { highlightLeadInChat, setSelectedLeadId } = useNexusState();

  const handleSelectLead = (card: PipelineCard) => {
    setSelectedLeadId(card.lead_id);
    highlightLeadInChat(card.lead_id, card.full_name);
  };

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div>
        <h1 className="text-2xl font-bold text-[#322f86]">Mission Control</h1>
        <p className="text-sm text-[#386fa4]">
          Real-time operational hub for counselling, pipeline execution, and team collaboration.
        </p>
      </div>

      <SystemHealthBar />

      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <section className="space-y-4">
          <PulseWidgets />
        </section>

        <section className="flex min-h-[640px] flex-col gap-4">
          <div className="min-h-[480px] flex-1">
            <PipelineBoard onSelectLead={handleSelectLead} />
          </div>
          <TaskWidget />
        </section>

        <section className="min-h-[640px]">
          <ChatWindow />
        </section>
      </div>
    </div>
  );
};

const AdminCommandCenter: React.FC = () => (
  <ChatConfigProvider>
    <NexusStateProvider>
      <CommandCenterLayout />
    </NexusStateProvider>
  </ChatConfigProvider>
);

export default AdminCommandCenter;

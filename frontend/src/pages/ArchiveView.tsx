// src/components/ArchiveView.tsx
import React, { useState, useEffect } from 'react';
import { 
  Download, 
  RefreshCw, 
  CheckSquare, 
  Square, 
  ExternalLink, 
  Activity,
  History,
  ShieldCheck,
  Loader2
} from 'lucide-react';
// ⚡ IMPORT YOUR CENTRALIZED CLIENT WRAPPER
import { apiFetch } from '../utils/api'; 

type ArchiveTab = 'Enrolled' | 'Disqualified' | 'Opted Out';

const ArchiveView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ArchiveTab>('Enrolled');
  const [archivedData, setArchivedData] = useState<any[]>([]);
  const [selectedRowId, setSelectedRowId] = useState<string | number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isReactivating, setIsReactivating] = useState<boolean>(false);

  // 1. Fetch data based on the selected segment sub-filter tab string value
  async function loadArchiveData() {
    try {
      setLoading(true);
      setError(null);
      
      let statusQueryParam = 'ENROLLED';
      if (activeTab === 'Disqualified') statusQueryParam = 'DISQUALIFIED';
      if (activeTab === 'Opted Out') statusQueryParam = 'OPTED_OUT';

      // Safe variation matrix checking fallback router paths dynamically using the central wrapper
      const pathVariations = [
        `leads/archive?status=${statusQueryParam}`,
        `leads/archive/all?status=${statusQueryParam}`,
        `archive?status=${statusQueryParam}`
      ];
      
      let data: any = null;
      let lastErrorMessage = "";

      for (const path of pathVariations) {
        try {
          // apiFetch automatically normalizes arrays/leads maps and appends Ngrok bypass parameters
          data = await apiFetch(path, { method: 'GET' });
          if (data) break; 
        } catch (e: any) {
          lastErrorMessage = e.message || e;
          console.warn(`Archive path structure variant failed: ${path}`);
        }
      }

      if (!data) {
        throw new Error(lastErrorMessage || "Could not connect to archive data matrices across fallback variations.");
      }

      const normalizedData = Array.isArray(data) ? data : [];
      setArchivedData(normalizedData);
      
      if (normalizedData.length > 0) {
        const firstItem = normalizedData[0];
        setSelectedRowId(firstItem.id !== undefined ? firstItem.id : 0);
      } else {
        setSelectedRowId(null);
      }
    } catch (err: any) {
      console.error("Archive fetch failed:", err);
      setError(err.message || "Failed to load database records.");
    } finally {
      setLoading(false);
    }
  }

  // Reload data layer instantly when tabs toggle
  useEffect(() => {
    loadArchiveData();
  }, [activeTab]);

  // Find the full detailed row profile match for the selected item view card
  const selectedStudent = archivedData.find(s => s.id === selectedRowId) || null;

  // 2. Action: Move user back from Cold Storage into active pipeline queues
  async function handleReactivate() {
    if (selectedRowId === null || selectedRowId === undefined) return;
    try {
      setIsReactivating(true);
      
      // Multi-routing loop to match potential reactivate router binding updates
      const actionVariations = [
        `leads/${selectedRowId}/reactivate`,
        `leads/reactivate/${selectedRowId}`,
        `archive/${selectedRowId}/reactivate`
      ];

      let actionSuccess = false;

      for (const actionPath of actionVariations) {
        try {
          await apiFetch(actionPath, { method: 'POST' });
          actionSuccess = true;
          break;
        } catch (e) {
          console.warn(`Reactivation attempt path skipped: ${actionPath}`);
        }
      }

      if (!actionSuccess) {
        throw new Error("Target action route rejected transmission payload.");
      }

      alert(`Lead context successfully restored to active pipelines.`);
      await loadArchiveData();
    } catch (err: any) {
      alert(`Failed to execute re-activation stream: ${err.message}`);
    } finally {
      setIsReactivating(false);
    }
  }

  return (
    <div className="flex flex-col bg-surface-bg h-[calc(100vh-140px)] border border-border-subtle/50 rounded-2xl overflow-hidden shadow-2xl text-text-main transition-colors duration-300">
      
      {/* --- TOP SEGMENTED TAB DECK --- */}
      <header className="p-4 bg-card border-b border-border-subtle flex items-center justify-between">
        <div className="flex bg-surface-bg p-1 rounded-xl border border-border-subtle/70 shadow-inner">
          {(['Enrolled', 'Disqualified', 'Opted Out'] as ArchiveTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-2 rounded-lg text-xs font-black transition-all duration-200 ${
                activeTab === tab 
                  ? 'bg-card text-accent shadow-lg ring-1 ring-border-subtle' 
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 text-text-muted text-[10px] font-bold uppercase tracking-widest">
          <History size={14} className="text-accent" />
          Historical Record Access • SECURE_NODE_04
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        
        {/* --- LEFT COLUMN: MASTER HISTORICAL TABLE (70%) --- */}
        <section className="w-[70%] overflow-y-auto custom-scrollbar border-r border-border-subtle/40 bg-card/30">
          {loading ? (
            <div className="flex flex-col items-center justify-center p-24 gap-3">
              <Loader2 className="animate-spin h-6 w-6 text-accent" />
              <p className="text-xs font-bold text-text-muted uppercase tracking-wider">Querying archived ledger metadata...</p>
            </div>
          ) : error ? (
            <div className="p-16 text-center text-sm font-semibold text-alert bg-alert/5 border-b border-border-subtle">
              Database Connection Failed: {error}
            </div>
          ) : archivedData.length === 0 ? (
            <div className="p-16 text-center text-xs font-semibold uppercase tracking-wider text-text-muted">
              No student profiles logged under historical state '{activeTab}'.
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 z-20 bg-card/90 backdrop-blur-md shadow-sm border-b border-border-subtle">
                <tr>
                  <th className="p-4 w-10">
                    <Square size={14} className="text-text-muted/40" />
                  </th>
                  <th className="p-4 text-[10px] font-black uppercase tracking-widest text-text-muted">Student Name</th>
                  <th className="p-4 text-[10px] font-black uppercase tracking-widest text-text-muted">Resolution Reason</th>
                  <th className="p-4 text-[10px] font-black uppercase tracking-widest text-text-muted text-center">Channel</th>
                  <th className="p-4 text-[10px] font-black uppercase tracking-widest text-text-muted">Audit Documentation</th>
                  <th className="p-4 text-[10px] font-black uppercase tracking-widest text-text-muted text-right">Archive Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/20">
                {archivedData.map((s, idx) => {
                  const rowId = s.id !== undefined ? s.id : idx;
                  const studentName = s.full_name || s.name || s.lead_name || 'Unnamed Record';
                  const resolutionReason = s.resolution_reason || s.reason || s.status_note || "Archived Processing";
                  const channelSource = s.channel || s.source || "Email";
                  const timestamp = s.updated_at || s.archive_date || s.created_at;

                  return (
                    <tr 
                      key={rowId}
                      onClick={() => setSelectedRowId(rowId)}
                      className={`group cursor-pointer transition-all ${
                        selectedRowId === rowId ? 'bg-accent/5' : 'hover:bg-card/40'
                      }`}
                    >
                      <td className="p-4">
                        {selectedRowId === rowId ? (
                          <CheckSquare size={14} className="text-accent" />
                        ) : (
                          <Square size={14} className="text-text-muted/30 group-hover:text-text-muted" />
                        )}
                      </td>
                      <td className="p-4">
                        <span className={`text-xs font-bold ${selectedRowId === rowId ? 'text-accent' : 'text-text-main'}`}>
                          {studentName}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <div className={`w-1.5 h-1.5 rounded-full ${
                            activeTab === 'Enrolled' ? 'bg-chart-secondary' : activeTab === 'Disqualified' ? 'bg-alert' : 'text-text-muted'
                          }`} />
                          <span className="text-xs text-text-muted font-medium">{resolutionReason}</span>
                        </div>
                      </td>
                      <td className="p-4 text-center">
                        <span className="text-[10px] font-mono text-text-muted bg-surface-bg px-2 py-1 rounded-md uppercase border border-border-subtle/60">
                          {channelSource}
                        </span>
                      </td>
                      <td className="p-4">
                        <button className="flex items-center gap-2 text-accent hover:opacity-80 transition-colors text-[10px] font-black uppercase tracking-tighter bg-accent/5 border border-accent/20 px-3 py-1.5 rounded-lg group-hover:border-accent/40">
                          <Download size={12} />
                          View Audit PDF
                        </button>
                      </td>
                      <td className="p-4 text-right">
                        <span className="text-[10px] text-text-muted font-bold">
                          {timestamp ? new Date(timestamp).toLocaleDateString([], {month: 'short', day: '2-digit', year: 'numeric'}) : "Unknown"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        {/* --- RIGHT COLUMN: INSPECTION PANEL (30%) --- */}
        <aside className="w-[30%] flex flex-col bg-card/20 p-6 relative">
          {selectedStudent ? (
            <div className="flex-1 flex flex-col justify-between h-full">
              <div className="overflow-y-auto custom-scrollbar space-y-8">
                {/* Final ML Score Tier */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-muted">ML Final Conv Score</h3>
                    <ShieldCheck size={16} className="text-accent" />
                  </div>
                  <div className="bg-card border border-border-subtle rounded-2xl p-6 flex flex-col items-center justify-center shadow-xl relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-transparent pointer-events-none" />
                    <span className="text-5xl font-black text-text-main tracking-tighter mb-1">
                      {selectedStudent.ml_conversion_score !== undefined ? selectedStudent.ml_conversion_score : (selectedStudent.score || 0)}%
                    </span>
                    <span className={`text-[10px] font-black uppercase px-3 py-1 rounded-full border ${
                      (selectedStudent.ml_conversion_score || selectedStudent.score || 0) >= 80 
                        ? 'bg-chart-secondary/10 text-chart-secondary border-chart-secondary/20' 
                        : 'bg-text-muted/10 text-text-muted border-border-subtle'
                    }`}>
                      {(selectedStudent.ml_conversion_score || selectedStudent.score || 0) >= 80 ? 'Tier 1: Conversion High' : 'Tier 2: Disengaged'}
                    </span>
                  </div>
                </div>

                {/* AI Retrospective Summary Card */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Activity size={14} className="text-accent" />
                    <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-muted">AI Retrospective Summary</h3>
                  </div>
                  <div className="bg-card/60 border border-border-subtle rounded-xl p-5 shadow-inner">
                    <p className="text-xs text-text-muted leading-relaxed font-medium italic">
                      "{selectedStudent.academic_summary || selectedStudent.summary || "No final summary note appended by the LangGraph parser engine during the terminal transition phase."}"
                    </p>
                    <div className="mt-6 pt-4 border-t border-border-subtle/40 flex items-center justify-between opacity-50">
                      <span className="text-[9px] font-mono text-text-muted">STUDENT ID: #{selectedStudent.id}</span>
                      <ExternalLink size={12} className="text-text-muted" />
                    </div>
                  </div>
                </div>
              </div>

              {/* RE-ACTIVATION LAUNCHPAD */}
              <div className="mt-auto pt-6 border-t border-border-subtle">
                <button 
                  onClick={handleReactivate}
                  disabled={isReactivating}
                  className="w-full group flex items-center justify-center gap-3 border-2 border-accent text-accent hover:bg-accent/10 py-4 rounded-xl text-xs font-black uppercase tracking-[0.15em] transition-all active:scale-95 disabled:opacity-40"
                >
                  <RefreshCw size={16} className={`transition-transform duration-500 ${isReactivating ? 'animate-spin' : 'group-hover:rotate-180'}`} />
                  {isReactivating ? 'Re-Activating...' : 'Re-Activate & Re-Engage AI'}
                </button>
                <p className="text-center text-[9px] text-text-muted mt-4 font-bold uppercase tracking-tighter">
                  Caution: This will move the lead back to Active Pipelines.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-text-muted italic">
              Select a row item to parse audit context profiles.
            </div>
          )}
        </aside>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: var(--border-subtle, #334155); border-radius: 10px; }
      `}} />
    </div>
  );
};

export default ArchiveView;
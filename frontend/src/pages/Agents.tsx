import React, { useCallback, useEffect, useState } from 'react';
import {
  Bot,
  BrainCircuit,
  Loader2,
  RefreshCw,
  Save,
  UserCheck,
  UserX,
  Users,
} from 'lucide-react';
import { apiFetch } from '../utils/api';
import StatusChangeModal from '../components/StatusChangeModal';
import UserStatusPill from '../components/UserStatusPill';

type AgentsTab = 'brain' | 'staff';

interface AgentConfig {
  id: number;
  system_prompt: string;
  ai_model: string;
  escalation_threshold: number;
  keywords_trigger: string;
  is_active: boolean;
  updated_at?: string;
}

interface StatusChangeReason {
  id: number;
  reason_type: string;
  reason: string;
  description: string;
}

interface StaffMember {
  id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  role_label: string;
  is_active: boolean;
  lead_count: number;
  creation_reason?: number | null;
  creation_date?: string | null;
  deactivation_reason?: number | null;
  deactivation_date?: string | null;
  activation_reason?: number | null;
  activation_date?: string | null;
  deactivation_reason_detail?: StatusChangeReason | null;
}

export const ROLE_LABELS: Record<string, string> = {
  'Web Admin': 'Web Admin',
  'Student Advisor': 'Student Advisor',
  'Student Manager': 'Student Manager',
  'Super Admin': 'Super Admin',
  admin: 'Web Admin',
  user: 'Staff',
};

const DEFAULT_CONFIG: AgentConfig = {
  id: 0,
  system_prompt: '',
  ai_model: 'gpt-4o-mini',
  escalation_threshold: 70,
  keywords_trigger: 'human,advisor,agent,talk to,person',
  is_active: true,
};

const getInactiveReasonLabel = (member: StaffMember): string | null => {
  if (member.is_active) return null;
  return member.deactivation_reason_detail?.reason || 'Inactive';
};

const formatStaffName = (member: StaffMember): string => {
  const first = member.first_name?.trim() || '';
  const last = member.last_name?.trim() || '';
  if (first && last) return `${first} ${last}`;
  return first || last || member.email;
};

const Agents: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AgentsTab>('brain');
  const [config, setConfig] = useState<AgentConfig>(DEFAULT_CONFIG);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingStaff, setLoadingStaff] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [statusChangeTarget, setStatusChangeTarget] = useState<StaffMember | null>(null);
  const [statusChangeMode, setStatusChangeMode] = useState<'activate' | 'deactivate'>('deactivate');
  const [statusChanging, setStatusChanging] = useState(false);
  const [statusChangeError, setStatusChangeError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      setLoadingConfig(true);
      setError(null);
      const data = await apiFetch('agents/config');
      setConfig(data as AgentConfig);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load agent configuration.');
    } finally {
      setLoadingConfig(false);
    }
  }, []);

  const loadStaff = useCallback(async () => {
    try {
      setLoadingStaff(true);
      setError(null);
      const data = await apiFetch('agents/staff');
      setStaff(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load staff roster.');
    } finally {
      setLoadingStaff(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
    loadStaff();
  }, [loadConfig, loadStaff]);

  const handleSaveConfig = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const saved = await apiFetch('agents/config', {
        method: 'POST',
        body: JSON.stringify({
          system_prompt: config.system_prompt.trim(),
          ai_model: config.ai_model.trim(),
          escalation_threshold: Number(config.escalation_threshold),
          keywords_trigger: config.keywords_trigger.trim(),
          is_active: config.is_active,
        }),
      });
      setConfig(saved as AgentConfig);
      setSuccess('Agent configuration saved. Webhook processing will use these settings immediately.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save agent configuration.');
    } finally {
      setSaving(false);
    }
  };

  const openStatusChangeModal = (member: StaffMember, mode: 'activate' | 'deactivate') => {
    if (mode === 'deactivate' && !member.is_active) return;
    if (mode === 'activate' && member.is_active) return;
    setStatusChangeError(null);
    setStatusChangeMode(mode);
    setStatusChangeTarget(member);
  };

  const closeStatusChangeModal = () => {
    setStatusChangeTarget(null);
    setStatusChangeError(null);
  };

  const handleStatusChange = async (statusChangeReasonId: number) => {
    if (!statusChangeTarget) return;

    const endpoint =
      statusChangeMode === 'deactivate'
        ? `users/${statusChangeTarget.id}/deactivate`
        : `users/${statusChangeTarget.id}/activate`;

    try {
      setStatusChanging(true);
      setStatusChangeError(null);
      setError(null);
      await apiFetch(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({ status_change_reason_id: statusChangeReasonId }),
      });
      const memberName = formatStaffName(statusChangeTarget);
      closeStatusChangeModal();
      setSuccess(
        statusChangeMode === 'deactivate'
          ? `${memberName} was deactivated. Super Admins have been notified by email.`
          : `${memberName} was reactivated.`
      );
      await loadStaff();
    } catch (err: unknown) {
      setStatusChangeError(
        err instanceof Error ? err.message : `Failed to ${statusChangeMode} staff member.`
      );
    } finally {
      setStatusChanging(false);
    }
  };

  return (
    <div className="relative z-10 max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Bot size={18} className="text-accent" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-text-muted">
              Agent Management
            </span>
          </div>
          <h2 className="text-2xl font-extrabold text-text-main tracking-tight">Agent Console</h2>
          <p className="text-text-muted text-sm">
            Configure the Nexus AI brain and monitor staff workload from one console.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            loadConfig();
            loadStaff();
          }}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all self-start"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
          {error}
        </div>
      )}

      {success && (
        <div className="p-4 bg-accent/10 border border-accent/20 rounded-xl text-xs text-text-main font-medium">
          {success}
        </div>
      )}

      <div className="inline-flex rounded-xl border border-border-subtle bg-card p-1">
        <button
          type="button"
          onClick={() => setActiveTab('brain')}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
            activeTab === 'brain'
              ? 'bg-accent text-text-dark-bg shadow-sm'
              : 'text-text-muted hover:text-text-main hover:bg-surface-bg'
          }`}
        >
          <BrainCircuit size={16} />
          The Brain
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('staff')}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
            activeTab === 'staff'
              ? 'bg-accent text-text-dark-bg shadow-sm'
              : 'text-text-muted hover:text-text-main hover:bg-surface-bg'
          }`}
        >
          <Users size={16} />
          The Staff
        </button>
      </div>

      {activeTab === 'brain' ? (
        <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30">
            <h3 className="text-sm font-bold text-text-main">AI Brain Configuration</h3>
            <p className="text-[11px] text-text-muted mt-1">
              Saved settings are pushed to runtime immediately for webhook processing.
            </p>
          </div>

          {loadingConfig ? (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-text-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading agent configuration...
            </div>
          ) : (
            <form onSubmit={handleSaveConfig} className="px-6 py-5 space-y-4">
              <label className="block text-xs font-semibold text-text-muted">
                System Prompt
                <textarea
                  required
                  rows={8}
                  value={config.system_prompt}
                  onChange={e => setConfig(prev => ({ ...prev, system_prompt: e.target.value }))}
                  className="mt-1.5 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                />
              </label>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="block text-xs font-semibold text-text-muted">
                  AI Model
                  <input
                    type="text"
                    required
                    value={config.ai_model}
                    onChange={e => setConfig(prev => ({ ...prev, ai_model: e.target.value }))}
                    className="mt-1.5 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                    placeholder="gpt-4o-mini"
                  />
                </label>

                <label className="block text-xs font-semibold text-text-muted">
                  Escalation Threshold
                  <input
                    type="number"
                    min={0}
                    max={100}
                    required
                    value={config.escalation_threshold}
                    onChange={e =>
                      setConfig(prev => ({ ...prev, escalation_threshold: Number(e.target.value) }))
                    }
                    className="mt-1.5 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                  />
                </label>
              </div>

              <label className="block text-xs font-semibold text-text-muted">
                Keywords Trigger
                <input
                  type="text"
                  required
                  value={config.keywords_trigger}
                  onChange={e => setConfig(prev => ({ ...prev, keywords_trigger: e.target.value }))}
                  className="mt-1.5 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                  placeholder="human,advisor,agent,talk to,person"
                />
                <span className="block mt-1.5 text-[11px] text-text-muted">
                  Comma-separated phrases that force a human handoff.
                </span>
              </label>

              <label className="inline-flex items-center gap-2 text-sm text-text-main">
                <input
                  type="checkbox"
                  checked={config.is_active}
                  onChange={e => setConfig(prev => ({ ...prev, is_active: e.target.checked }))}
                  className="rounded border-border-subtle"
                />
                Agent is active
              </label>

              <div className="flex items-center justify-end pt-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-text-dark-bg text-sm font-semibold hover:opacity-90 transition-all disabled:opacity-50"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  Save Configuration
                </button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border-subtle rounded-2xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border-subtle bg-surface-bg/30">
            <h3 className="text-sm font-bold text-text-main">Staff Roster</h3>
            <p className="text-[11px] text-text-muted mt-1">
              Active lead counts reflect assigned leads and shared handoff workload.
            </p>
          </div>

          {loadingStaff ? (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-text-muted">
              <Loader2 size={16} className="animate-spin" />
              Loading staff roster...
            </div>
          ) : staff.length === 0 ? (
            <div className="px-6 py-16 text-center text-sm text-text-muted">
              No staff members found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[10px] font-black text-text-muted uppercase tracking-widest border-b border-border-subtle">
                    <th className="px-6 py-4">Employee</th>
                    <th className="px-6 py-4">Email</th>
                    <th className="px-6 py-4">Role</th>
                    <th className="px-6 py-4">Status</th>
                    <th className="px-6 py-4 text-right">Active Leads</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle/50">
                  {staff.map(member => (
                    <tr key={member.id} className="hover:bg-surface-bg/30 transition-colors">
                      <td className="px-6 py-4 text-sm font-bold text-text-main">
                        {formatStaffName(member)}
                      </td>
                      <td className="px-6 py-4 text-sm text-text-muted">{member.email}</td>
                      <td className="px-6 py-4">
                        <span className="px-2.5 py-1 rounded-full text-[10px] font-semibold bg-accent/10 text-accent">
                          {ROLE_LABELS[member.role || ''] || member.role_label || 'Staff'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <UserStatusPill
                          isActive={member.is_active}
                          statusReason={getInactiveReasonLabel(member)}
                        />
                      </td>
                      <td className="px-6 py-4 text-right text-sm font-bold text-text-main">
                        {member.lead_count}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => openStatusChangeModal(member, 'activate')}
                            disabled={member.is_active}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-accent/20 text-xs font-semibold text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            <UserCheck size={14} />
                            Activate
                          </button>
                          <button
                            type="button"
                            onClick={() => openStatusChangeModal(member, 'deactivate')}
                            disabled={!member.is_active}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-alert/20 text-xs font-semibold text-alert hover:bg-alert/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            <UserX size={14} />
                            Deactivate
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <StatusChangeModal
        open={Boolean(statusChangeTarget)}
        mode={statusChangeMode}
        userName={statusChangeTarget ? formatStaffName(statusChangeTarget) : ''}
        saving={statusChanging}
        error={statusChangeError}
        onClose={closeStatusChangeModal}
        onConfirm={handleStatusChange}
      />
    </div>
  );
};

export default Agents;

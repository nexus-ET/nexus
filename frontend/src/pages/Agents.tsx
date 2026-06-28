import React, { useCallback, useEffect, useState } from 'react';
import { Bot, BrainCircuit, ClipboardList, Loader2, RefreshCw, Save } from 'lucide-react';
import { apiFetch } from '../utils/api';
import AuditLog from '../components/AuditLog';

type AgentsTab = 'brain' | 'audit';

interface AgentConfig {
  id: number;
  system_prompt: string;
  ai_model: string;
  escalation_threshold: number;
  keywords_trigger: string;
  is_active: boolean;
  updated_at?: string;
}

interface AiModelOption {
  value: string;
  label: string;
  provider: string;
  model_id: string;
  description: string;
}

const DEFAULT_CONFIG: AgentConfig = {
  id: 0,
  system_prompt: '',
  ai_model: 'ollama:llama3.1',
  escalation_threshold: 70,
  keywords_trigger: 'human,advisor,agent,talk to,person',
  is_active: true,
};

const Agents: React.FC = () => {
  const [activeTab, setActiveTab] = useState<AgentsTab>('brain');
  const [config, setConfig] = useState<AgentConfig>(DEFAULT_CONFIG);
  const [modelOptions, setModelOptions] = useState<AiModelOption[]>([]);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadModelOptions = useCallback(async () => {
    try {
      const data = await apiFetch('agents/models');
      setModelOptions(Array.isArray(data) ? (data as AiModelOption[]) : []);
    } catch {
      setModelOptions([]);
    }
  }, []);

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

  useEffect(() => {
    loadConfig();
    loadModelOptions();
  }, [loadConfig, loadModelOptions]);

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
          <h2 className="text-2xl font-extrabold text-text-main tracking-tight">AI Agent Brain</h2>
          <p className="text-text-muted text-sm">
            Configure the Nexus AI brain, review the audit flight recorder, and pick an inference provider.
          </p>
        </div>

        {activeTab === 'brain' && (
          <button
            type="button"
            onClick={loadConfig}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border-subtle bg-card text-xs font-semibold text-text-muted hover:text-text-main hover:bg-surface-bg transition-all self-start"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        )}
      </div>

      {error && activeTab === 'brain' && (
        <div className="p-4 bg-alert/10 border border-alert/20 rounded-xl text-xs text-alert font-medium">
          {error}
        </div>
      )}

      {success && activeTab === 'brain' && (
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
          Configuration
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('audit')}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
            activeTab === 'audit'
              ? 'bg-accent text-text-dark-bg shadow-sm'
              : 'text-text-muted hover:text-text-main hover:bg-surface-bg'
          }`}
        >
          <ClipboardList size={16} />
          Audit Dashboard
        </button>
      </div>

      {activeTab === 'audit' ? (
        <AuditLog />
      ) : (
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
                AI Service
                <select
                  required
                  value={config.ai_model}
                  onChange={e => setConfig(prev => ({ ...prev, ai_model: e.target.value }))}
                  className="mt-1.5 w-full px-3 py-2 bg-surface-bg border border-border-subtle rounded-xl text-sm text-text-main focus:outline-none focus:border-accent focus:ring-4 focus:ring-accent/10"
                >
                  {(modelOptions.length
                    ? modelOptions
                    : [{ value: config.ai_model, label: config.ai_model, provider: '', model_id: '', description: '' }]
                  ).map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                {modelOptions.find(option => option.value === config.ai_model)?.description && (
                  <span className="block mt-1.5 text-[11px] text-text-muted">
                    {modelOptions.find(option => option.value === config.ai_model)?.description}
                  </span>
                )}
                <span className="block mt-1.5 text-[11px] text-text-muted">
                  Ollama runs locally (no API key). Ensure Ollama is running and the model is pulled, e.g.{' '}
                  <code className="text-[10px]">ollama pull llama3.1</code>. Cloud options need{' '}
                  <code className="text-[10px]">OPENAI_API_KEY</code> or{' '}
                  <code className="text-[10px]">GROQ_API_KEY</code>.
                </span>
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
                <span className="block mt-1.5 text-[11px] text-text-muted">
                  Minimum AI reliability (0–100). Hand off when model confidence falls below this score.
                </span>
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
      )}
    </div>
  );
};

export default Agents;

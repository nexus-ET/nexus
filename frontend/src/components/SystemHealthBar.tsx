import React from 'react';
import { Activity, AlertTriangle, CheckCircle2, Shield, Wifi, WifiOff } from 'lucide-react';
import { useNexusState } from '../hooks/useNexusState';

const SystemHealthBar: React.FC = () => {
  const { connected, pulse } = useNexusState();
  const securityHealthy = pulse?.security_healthy ?? true;

  return (
    <div
      className={`rounded-xl border px-4 py-3 shadow-sm transition-colors ${
        securityHealthy
          ? 'border-[#84d2f6]/60 bg-white'
          : 'border-red-300 bg-red-50'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className={`h-5 w-5 ${securityHealthy ? 'text-[#59a5d8]' : 'text-red-500'}`} />
          <div>
            <p className="text-sm font-semibold text-[#03045e]">Nexus Operational Pulse</p>
            <p className="text-xs text-[#386fa4]">
              {pulse?.security_checked_at
                ? `Last audit: ${new Date(pulse.security_checked_at).toLocaleString()}`
                : 'Awaiting first security audit run'}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs font-medium">
          <span className="inline-flex items-center gap-1 rounded-full bg-[#f7f9f9] px-3 py-1 text-[#386fa4]">
            {connected ? <Wifi className="h-3.5 w-3.5 text-[#59a5d8]" /> : <WifiOff className="h-3.5 w-3.5 text-red-500" />}
            {connected ? 'Live sync' : 'Reconnecting'}
          </span>

          <span
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1 ${
              securityHealthy ? 'bg-emerald-50 text-emerald-700' : 'bg-red-100 text-red-700'
            }`}
          >
            {securityHealthy ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
            Security {pulse?.security_status ?? 'unknown'}
          </span>

          <span className="inline-flex items-center gap-1 rounded-full bg-[#03045e]/5 px-3 py-1 text-[#03045e]">
            <Shield className="h-3.5 w-3.5" />
            Fortress headers active
          </span>
        </div>
      </div>
    </div>
  );
};

export default SystemHealthBar;

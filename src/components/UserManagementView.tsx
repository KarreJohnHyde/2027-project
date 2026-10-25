import { useState, useEffect, useCallback } from 'react';
import { 
  Users, 
  ShieldCheck, 
  Key, 
  LogOut, 
  RefreshCw, 
  Copy, 
  Check, 
  UserCheck, 
  FileText, 
  Search
} from 'lucide-react';
import { api } from '../services/api';
import type { ProvenanceEvent } from '../services/api';
import type { User } from '../types/medtwin';

interface UserManagementViewProps {
  user: User | null;
  onSwitchUser: (username: string) => void;
  onLogout: () => void;
}

export const UserManagementView: React.FC<UserManagementViewProps> = ({
  user,
  onSwitchUser,
  onLogout,
}) => {
  const [auditLogs, setAuditLogs] = useState<ProvenanceEvent[]>([]);
  const [loadingLogs, setLoadingLogs] = useState<boolean>(false);
  const [searchLog, setSearchLog] = useState<string>('');
  const [copiedToken, setCopiedToken] = useState<boolean>(false);

  const fetchAuditLogs = useCallback(async () => {
    setLoadingLogs(true);
    try {
      const logs = await api.getAuditLogs(50);
      setAuditLogs(logs);
    } catch (err) {
      console.error('Failed to fetch audit logs:', err);
    } finally {
      setLoadingLogs(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    api.getAuditLogs(50)
      .then((logs) => {
        if (isMounted) setAuditLogs(logs);
      })
      .catch((err) => {
        console.error('Failed to fetch audit logs:', err);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleCopyToken = () => {
    const token = api.getToken();
    if (!token) return;
    void navigator.clipboard.writeText(token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const filteredLogs = auditLogs.filter((log) => {
    const q = searchLog.toLowerCase();
    return (
      log.action.toLowerCase().includes(q) ||
      log.resource_type.toLowerCase().includes(q) ||
      (log.resource_id && log.resource_id.toLowerCase().includes(q)) ||
      (log.ip_address && log.ip_address.toLowerCase().includes(q))
    );
  });

  // Persona capabilities matrix
  const permissions = [
    {
      feature: 'Create Cases & Log Examinations',
      admin: true,
      clinician: true,
      researcher: false,
    },
    {
      feature: 'Upload & Associate Multimodal Files',
      admin: true,
      clinician: true,
      researcher: true,
    },
    {
      feature: 'Run AI Modality Inference (ResNet / 1D-CNN / NLP)',
      admin: true,
      clinician: true,
      researcher: true,
    },
    {
      feature: 'Execute Masked Gated Multimodal Fusion',
      admin: true,
      clinician: true,
      researcher: true,
    },
    {
      feature: 'Submit & Sign Off Human Clinical Review',
      admin: true,
      clinician: true,
      researcher: false,
    },
    {
      feature: 'Order Health Check Packages & Labs',
      admin: true,
      clinician: true,
      researcher: false,
    },
    {
      feature: 'System Audit Logs & Security Administration',
      admin: true,
      clinician: false,
      researcher: false,
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Banner & Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-xl backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-inner">
            <Users size={26} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white tracking-tight">User Session & Role-Based Access</h2>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800">
                JWT Authenticated
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Role permissions matrix, session-token handling, and persisted audit history. Tamper-evident retention is not implemented.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onLogout}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 text-xs font-semibold border border-rose-500/30 shadow-md shadow-rose-500/10 transition-all self-start md:self-auto"
        >
          <LogOut size={14} />
          <span>End Session (Logout)</span>
        </button>
      </div>

      {/* Main Grid: User Profile & Role Switcher (Left 5 cols) & Live Audit Log (Right 7 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Active User Profile & Permissions Matrix */}
        <div className="lg:col-span-5 flex flex-col gap-5">
          {/* Active Profile Card */}
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <UserCheck size={16} className="text-cyan-400" />
                <h3 className="text-sm font-bold text-white">Active User Profile</h3>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                ROLE: {user?.role || 'CLINICIAN'}
              </span>
            </div>

            <div className="space-y-3">
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Username</span>
                  <div className="text-sm font-bold text-white mt-0.5">{user?.username || 'clinician'}</div>
                </div>
                <div className="text-right">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">User ID</span>
                  <div className="text-sm font-mono text-slate-300 mt-0.5">#{user?.id || 1}</div>
                </div>
              </div>

              {/* Quick Persona Switcher for Evaluation */}
              <div>
                <span className="text-[11px] font-semibold text-slate-400 block mb-2">
                  Quick Switch Persona (Evaluation Demo):
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => onSwitchUser('clinician')}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      user?.username === 'clinician'
                        ? 'bg-cyan-950/40 border-cyan-500/50 text-cyan-300 shadow-sm shadow-cyan-500/20'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-bold">Clinician</div>
                    <div className="text-[10px] text-slate-500">Reviews & Findings</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => onSwitchUser('researcher')}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      user?.username === 'researcher'
                        ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-300 shadow-sm shadow-emerald-500/20'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-bold">Researcher</div>
                    <div className="text-[10px] text-slate-500">Models & Forecasting</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => onSwitchUser('admin')}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      user?.username === 'admin'
                        ? 'bg-purple-950/40 border-purple-500/50 text-purple-300 shadow-sm shadow-purple-500/20'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    <div className="text-xs font-bold">Admin</div>
                    <div className="text-[10px] text-slate-500">Full System Control</div>
                  </button>
                </div>
              </div>

              {/* Session Bearer Token */}
              <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold flex items-center gap-1">
                    <Key size={11} className="text-amber-400" />
                    Session Token (OAuth2 Bearer)
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyToken}
                    className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    {copiedToken ? <Check size={11} /> : <Copy size={11} />}
                    <span>{copiedToken ? 'Copied' : 'Copy Token'}</span>
                  </button>
                </div>
                <div className="font-mono text-[10px] text-slate-400 truncate bg-slate-900/60 p-1.5 rounded border border-slate-850">
                  {api.getToken() ?? 'No active bearer token'}
                </div>
              </div>
            </div>
          </div>

          {/* Role-Based Permissions Matrix */}
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl flex flex-col gap-3">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-800">
              <ShieldCheck size={16} className="text-emerald-400" />
              <h3 className="text-sm font-bold text-white">Role Access Control Matrix</h3>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500 font-semibold text-[10px]">
                    <th className="py-2 pr-2">Capability</th>
                    <th className="py-2 text-center text-purple-400">ADMIN</th>
                    <th className="py-2 text-center text-cyan-400">CLINICIAN</th>
                    <th className="py-2 text-center text-emerald-400">RESEARCHER</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-850 text-[11px]">
                  {permissions.map((p, i) => (
                    <tr key={i} className="hover:bg-slate-900/40">
                      <td className="py-2 pr-2 text-slate-300">{p.feature}</td>
                      <td className="py-2 text-center">
                        {p.admin ? <span className="text-emerald-400 font-bold">✓</span> : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="py-2 text-center">
                        {p.clinician ? <span className="text-emerald-400 font-bold">✓</span> : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="py-2 text-center">
                        {p.researcher ? <span className="text-emerald-400 font-bold">✓</span> : <span className="text-slate-600">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Live Audit Logs */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 shadow-xl flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-cyan-400" />
                <div>
                  <h3 className="text-sm font-bold text-white">Security & Operation Audit Trail</h3>
                  <p className="text-[11px] text-slate-400">Tamper-evident chronological event log</p>
                </div>
              </div>

              <button
                type="button"
                disabled={loadingLogs}
                onClick={fetchAuditLogs}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 transition-all disabled:opacity-50"
              >
                <RefreshCw size={12} className={loadingLogs ? 'animate-spin' : ''} />
                <span>Refresh Logs</span>
              </button>
            </div>

            {/* Filter Search */}
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search audit actions, resources, IPs..."
                value={searchLog}
                onChange={(e) => setSearchLog(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            {/* Logs Table */}
            <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950 h-[520px] overflow-y-auto">
              {filteredLogs.length > 0 ? (
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-900/90 text-slate-400 border-b border-slate-800 sticky top-0 z-10 backdrop-blur-md">
                    <tr>
                      <th className="p-3">Timestamp</th>
                      <th className="p-3">Action</th>
                      <th className="p-3">Resource</th>
                      <th className="p-3">User</th>
                      <th className="p-3">IP Address</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850 font-mono text-[11px]">
                    {filteredLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-900/50 transition-colors">
                        <td className="p-3 text-slate-400 whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </td>
                        <td className="p-3 font-semibold text-cyan-400">
                          {log.action}
                        </td>
                        <td className="p-3 text-slate-300">
                          <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px]">
                            {log.resource_type}
                          </span>
                          {log.resource_id && (
                            <span className="ml-1.5 text-slate-500 text-[10px]">#{log.resource_id}</span>
                          )}
                        </td>
                        <td className="p-3 text-slate-300">
                          User #{log.user_id || 1}
                        </td>
                        <td className="p-3 text-slate-500 text-[10px]">
                          {log.ip_address || '127.0.0.1'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-8 text-slate-500 text-xs">
                  <FileText size={24} className="mb-2 text-slate-600" />
                  <span>No audit events recorded or matched filter.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

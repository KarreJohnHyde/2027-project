import React from 'react';
import { ShieldAlert, UserCheck, Activity, Database, CheckCircle2, AlertTriangle } from 'lucide-react';
import type { User } from '../types/medtwin';

interface HeaderProps {
  user: User | null;
  onSwitchUser: (username: string) => void;
  systemStatus: {
    app_name: string;
    version: string;
    active_cases_count: number;
    models_status: Record<string, string>;
  } | null;
}

export const Header: React.FC<HeaderProps> = ({ user, onSwitchUser, systemStatus }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      {/* Persistent Research & Non-Diagnostic Banner */}
      <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 flex items-center justify-between text-xs text-amber-300">
        <div className="flex items-center gap-2 font-medium">
          <ShieldAlert size={15} className="text-amber-400 shrink-0" />
          <span>
            <strong>MEDTWIN RESEARCH PROTOTYPE:</strong> Software-only research framework (IEEE manuscript compliant).
            NOT A VALIDATED CLINICAL DIAGNOSTIC DEVICE. Results require human clinician review.
          </span>
        </div>
        <div className="hidden md:flex items-center gap-3 text-amber-400/80 text-[11px]">
          <span>Single-modality cases abstain from fusion</span>
          <span>•</span>
          <span>Held-out TRE registration gate active</span>
        </div>
      </div>

      {/* Main Bar */}
      <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
            <Activity size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">MedTwin</h1>
              <span className="px-2 py-0.5 text-[10px] font-semibold bg-cyan-950 text-cyan-400 border border-cyan-800 rounded-full">
                v1.0.0-research
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Multimodal Digital Twin for 3D Anatomical Tracking & Longitudinal Forecasting
            </p>
          </div>
        </div>

        {/* Status Pills & User Switcher */}
        <div className="flex items-center gap-3">
          {/* Backend Connection */}
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300">
            <Database size={13} className="text-emerald-400" />
            <span>FastAPI Backend:</span>
            {systemStatus ? (
              <span className="text-emerald-400 font-medium flex items-center gap-1">
                <CheckCircle2 size={12} /> Connected
              </span>
            ) : (
              <span className="text-amber-400 font-medium flex items-center gap-1">
                <AlertTriangle size={12} /> Offline
              </span>
            )}
          </div>

          {/* User Account & Role Switcher */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-xs">
            <UserCheck size={14} className="text-indigo-400" />
            <span className="text-slate-400">Role:</span>
            <select
              value={user?.username || 'clinician'}
              onChange={(e) => onSwitchUser(e.target.value)}
              className="bg-slate-950 text-indigo-300 font-medium border border-slate-700 rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
            >
              <option value="clinician">Dr. Sarah Chen (Clinician)</option>
              <option value="researcher">Alex Rivera (Researcher)</option>
              <option value="admin">System Admin</option>
            </select>
          </div>
        </div>
      </div>
    </header>
  );
};

import React, { useState } from 'react';
import { Activity, ArrowRight, Lock, ShieldAlert, User as UserIcon } from 'lucide-react';

import { api } from '../services/api';
import type { User } from '../services/api';

interface LoginPageProps {
  onLoginSuccess: (user: User) => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMsg(null);
    setLoading(true);
    try {
      const session = await api.login(username.trim(), password);
      onLoginSuccess(session.user);
    } catch (error: unknown) {
      setErrorMsg(error instanceof Error ? error.message : 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col justify-between overflow-hidden bg-slate-950 text-slate-100">
      <div className="pointer-events-none absolute left-[-10%] top-[-10%] h-[500px] w-[500px] rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-10%] right-[-10%] h-[500px] w-[500px] rounded-full bg-indigo-500/10 blur-3xl" />

      <header className="flex items-center justify-between border-b border-slate-800/80 bg-slate-950/60 px-6 py-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-indigo-600 text-white shadow-lg shadow-cyan-500/20">
            <Activity size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-white">MedTwin</span>
              <span className="rounded-full border border-cyan-800 bg-cyan-950 px-2 py-0.5 font-mono text-[10px] text-cyan-300">
                v0.2.0 research
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Authenticated multimodal clinical-evidence research workspace
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-400">
          <ShieldAlert size={14} />
          <span className="hidden font-medium sm:inline">
            Research prototype — not for diagnostic use
          </span>
        </div>
      </header>

      <div className="flex flex-1 items-center justify-center p-4">
        <div className="relative w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl backdrop-blur-xl sm:p-8">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl border border-cyan-500/30 bg-gradient-to-br from-cyan-500/20 to-indigo-500/20 text-cyan-400 shadow-inner">
              <Lock size={26} />
            </div>
            <h2 className="text-xl font-bold tracking-tight text-white">Authorized access</h2>
            <p className="mt-1 text-xs text-slate-400">
              Sign in with an account configured by the MedTwin administrator.
            </p>
          </div>

          {errorMsg && (
            <div
              className="mb-5 flex items-center gap-2.5 rounded-xl border border-rose-800 bg-rose-950/60 p-3 text-xs text-rose-300"
              role="alert"
            >
              <ShieldAlert size={16} className="shrink-0 text-rose-400" />
              <span>{errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="medtwin-username" className="mb-1.5 block text-xs font-semibold text-slate-300">
                Username
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                  <UserIcon size={16} />
                </div>
                <input
                  id="medtwin-username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                  placeholder="Username"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 py-2.5 pl-10 pr-3 font-mono text-xs text-white transition-colors focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label htmlFor="medtwin-password" className="mb-1.5 block text-xs font-semibold text-slate-300">
                Password
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                  <Lock size={16} />
                </div>
                <input
                  id="medtwin-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  placeholder="Password"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 py-2.5 pl-10 pr-3 font-mono text-xs text-white transition-colors focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-600 to-indigo-600 px-4 py-3 text-xs font-semibold text-white shadow-lg shadow-cyan-600/20 transition-all hover:scale-[1.01] hover:from-cyan-500 hover:to-indigo-500 active:scale-[0.99] disabled:opacity-50"
            >
              <span>{loading ? 'Authenticating…' : 'Sign in to MedTwin'}</span>
              <ArrowRight size={15} />
            </button>
          </form>

          <p className="mt-5 border-t border-slate-800/80 pt-4 text-center text-[11px] text-slate-500">
            Development accounts exist only when environment-controlled seeding is enabled.
          </p>
        </div>
      </div>

      <footer className="border-t border-slate-800/80 bg-slate-950/80 p-4 text-center text-xs text-slate-500">
        MedTwin is research software, not a validated medical device. A configured model,
        checkpoint, and evaluation artifact are required before inference can be presented.
      </footer>
    </div>
  );
};

export default LoginPage;

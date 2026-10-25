import { useState, type FormEvent } from "react";
import { Activity, LockKeyhole } from "lucide-react";
import { api, type User } from "../services/api";
import { errorMessage } from "../lib/format";
import { Button, ErrorBlock, Field, TextInput } from "../components/ui";

export default function LoginPage({ onLoginSuccess }: { onLoginSuccess: (user: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await api.login(username.trim(), password);
      onLoginSuccess(session.user);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <header className="flex items-center gap-2.5 border-b border-line px-5 py-3">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-fg"><Activity aria-hidden size={17} /></div>
        <div>
          <p className="text-sm font-semibold leading-4">MedTwin 2.0</p>
          <p className="text-[11px] text-ink-3">Unified patient-case workspace · evidence provenance · clinical research workflows</p>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-2xl border border-line bg-surface p-6 shadow-card">
          <div className="mb-5">
            <LockKeyhole aria-hidden className="text-accent-text" size={22} />
            <h1 className="mt-3 text-lg font-semibold">Sign in</h1>
            <p className="mt-1 text-xs leading-5 text-ink-2">Use an account configured by your MedTwin administrator. There are no built-in or fallback credentials.</p>
          </div>
          <form onSubmit={submit} className="space-y-3.5">
            <Field label="Username" htmlFor="login-username">
              <TextInput id="login-username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </Field>
            <Field label="Password" htmlFor="login-password">
              <TextInput id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
            </Field>
            {error && <ErrorBlock message={error} />}
            <Button type="submit" variant="primary" loading={busy} className="w-full">Sign in</Button>
          </form>
        </div>
      </main>
      <footer className="border-t border-line px-5 py-3 text-center text-[11px] leading-5 text-ink-3">
        Research software, not a validated medical device. Real evidence only: results that do not exist are shown as unavailable, never estimated.
      </footer>
    </div>
  );
}

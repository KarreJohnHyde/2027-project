import { useState, type FormEvent } from "react";
import { Activity, LockKeyhole } from "lucide-react";
import { api, type User } from "../services/api";
import { errorMessage } from "../lib/format";
import { Button, ErrorBlock, Field, TextInput } from "../components/ui";

type Mode = "login" | "register";

const PASSWORD_AUTOCOMPLETE: Record<Mode, string> = { login: "current-password", register: "new-password" };

export default function LoginPage({ onLoginSuccess }: { onLoginSuccess: (user: User) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (mode === "register" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      if (mode === "register") {
        await api.register({
          username: username.trim(),
          email: email.trim(),
          full_name: fullName.trim() || undefined,
          password,
        });
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setSuccess("Your unverified standard account has been created. Sign in with your new username and password. Professional actions require authorised verification.");
      } else {
        const session = await api.login(username.trim(), password);
        onLoginSuccess(session.user);
      }
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
            <h1 className="mt-3 text-lg font-semibold">{mode === "register" ? "Create your account" : "Sign in"}</h1>
            <p className="mt-1 text-xs leading-5 text-ink-2">
              {mode === "register"
                ? "Register with your own username and password. New accounts are non-privileged and unverified; professional access is provisioned separately."
                : "Sign in with your account, or create a new account to get started."}
            </p>
          </div>
          <form onSubmit={submit} className="space-y-3.5">
            {mode === "register" && (
              <>
                <Field label="Full name (optional)" htmlFor="register-full-name">
                  <TextInput id="register-full-name" autoComplete="name" maxLength={128} value={fullName} onChange={(event) => setFullName(event.target.value)} />
                </Field>
                <Field label="Email" htmlFor="register-email">
                  <TextInput id="register-email" type="email" autoComplete="email" maxLength={128} required value={email} onChange={(event) => setEmail(event.target.value)} />
                </Field>
              </>
            )}
            <Field label="Username" htmlFor="login-username" hint={mode === "register" ? "Use 3–50 characters." : undefined}>
              <TextInput id="login-username" autoComplete="username" minLength={mode === "register" ? 3 : undefined} maxLength={mode === "register" ? 50 : undefined} required value={username} onChange={(event) => setUsername(event.target.value)} />
            </Field>
            <Field label="Password" htmlFor="login-password">
              <TextInput id="login-password" type="password" autoComplete={PASSWORD_AUTOCOMPLETE[mode]} minLength={mode === "register" ? 6 : undefined} required value={password} onChange={(event) => setPassword(event.target.value)} />
            </Field>
            {mode === "register" && (
              <Field label="Confirm password" htmlFor="register-confirm-password">
                <TextInput id="register-confirm-password" type="password" autoComplete="new-password" minLength={6} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
              </Field>
            )}
            {error && <ErrorBlock message={error} />}
            {success && <p role="status" className="rounded-lg border border-[color-mix(in_srgb,var(--mt-good)_35%,transparent)] bg-[color-mix(in_srgb,var(--mt-good)_8%,transparent)] px-3 py-2 text-xs leading-5 text-good-text">{success}</p>}
            <Button type="submit" variant="primary" loading={busy} className="w-full">
              {mode === "register" ? "Create account" : "Sign in"}
            </Button>
          </form>
          <p className="mt-4 text-center text-xs text-ink-2">
            {mode === "register" ? "Already have an account?" : "New to MedTwin?"}{" "}
            <button
              type="button"
              className="font-medium text-accent-text underline-offset-2 hover:underline"
              onClick={() => {
                setMode(mode === "register" ? "login" : "register");
                setError(null);
                setSuccess(null);
              }}
            >
              {mode === "register" ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
      </main>
      <footer className="border-t border-line px-5 py-3 text-center text-[11px] leading-5 text-ink-3">
        Research software, not a validated medical device. Real evidence only: results that do not exist are shown as unavailable, never estimated.
      </footer>
    </div>
  );
}

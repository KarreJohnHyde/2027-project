import { useState, type FormEvent } from "react";
import { Activity, ArrowRight, PlayCircle, UserRound } from "lucide-react";
import { api, type User, type VisitorEntry } from "../services/api";
import { errorMessage } from "../lib/format";
import { rememberCase } from "../state/workspace";
import { Button, Disclosure, ErrorBlock, Field, SelectInput, TextInput } from "../components/ui";

/** The key of an entry-page workspace, kept in this browser so the person can continue later. */
const VISITOR_KEY = "medtwin.visitor";

type StoredVisitor = { token: string; name: string; expiresAt: string };

const GENDERS: Array<{ value: VisitorEntry["gender"]; label: string }> = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];

const ROLES: Array<{ value: VisitorEntry["role"]; label: string }> = [
  { value: "patient", label: "Patient" },
  { value: "caregiver", label: "Caregiver or family member" },
  { value: "doctor", label: "Doctor" },
  { value: "nurse", label: "Nurse" },
  { value: "lab_expert", label: "Laboratory expert" },
  { value: "radiologist", label: "Radiologist" },
  { value: "surgeon", label: "Surgeon" },
  { value: "researcher", label: "Researcher" },
  { value: "student", label: "Student" },
  { value: "other", label: "Other" },
];

function storedVisitor(): StoredVisitor | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(VISITOR_KEY) ?? "null") as StoredVisitor | null;
    return value && new Date(value.expiresAt).getTime() > Date.now() ? value : null;
  } catch {
    return null;
  }
}

function keepVisitor(value: StoredVisitor | null) {
  try {
    if (value) window.localStorage.setItem(VISITOR_KEY, JSON.stringify(value));
    else window.localStorage.removeItem(VISITOR_KEY);
  } catch {
    // Without storage the workspace still works now; it just cannot be continued later from this browser.
  }
}

/** The front door: a browser-bound workspace identity; case authorization still applies. */
export default function EntryPage({ onEnter }: { onEnter: (user: User) => void }) {
  const [returning, setReturning] = useState<StoredVisitor | null>(() => (typeof window === "undefined" ? null : storedVisitor()));
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<VisitorEntry["gender"] | "">("");
  const [role, setRole] = useState<VisitorEntry["role"] | "">("");
  const [busy, setBusy] = useState<"enter" | "continue" | "demo" | "account" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function attempt(kind: NonNullable<typeof busy>, action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(null);
    }
  }

  function enter(event: FormEvent) {
    event.preventDefault();
    if (!gender || !role) return;
    void attempt("enter", async () => {
      const session = await api.enterWorkspace({ name: name.trim(), age: Number(age), gender, role });
      keepVisitor({ token: session.access_token, name: session.user.full_name ?? name.trim(), expiresAt: session.expires_at });
      onEnter(session.user);
    });
  }

  function resume() {
    if (!returning) return;
    void attempt("continue", async () => {
      const user = await api.resumeWorkspace(returning.token);
      if (user) {
        onEnter(user);
        return;
      }
      keepVisitor(null);
      setReturning(null);
      throw new Error("This browser's entry has expired. Enter your details again.");
    });
  }

  function demo() {
    void attempt("demo", async () => {
      const session = await api.startGuestDemo();
      rememberCase(session.case_id);
      onEnter(session.user);
    });
  }

  function signIn(event: FormEvent) {
    event.preventDefault();
    void attempt("account", async () => {
      onEnter((await api.login(username.trim(), password)).user);
    });
  }

  const ageValue = Number(age);
  const complete = name.trim().length > 0 && age !== "" && Number.isInteger(ageValue) && ageValue >= 0 && ageValue <= 120 && gender !== "" && role !== "";

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
        <div className="w-full max-w-sm space-y-4 rounded-2xl border border-line bg-surface p-6 shadow-card">
          <div>
            <UserRound aria-hidden size={18} className="text-accent-text" />
            <h1 className="mt-3 text-lg font-semibold">Welcome to MedTwin</h1>
            <p className="mt-1 text-xs leading-5 text-ink-2">Enter a workspace identity to use the research tools. Case access follows ownership and explicit sharing permissions.</p>
          </div>
          {returning && (
            <div className="space-y-2 rounded-lg border border-line bg-surface-2 p-3">
              <Button variant="primary" icon={ArrowRight} loading={busy === "continue"} disabled={busy !== null} className="w-full" onClick={resume}>
                Continue as {returning.name}
              </Button>
              <button type="button" className="w-full text-center text-[11px] text-ink-3 underline-offset-2 hover:underline" onClick={() => { keepVisitor(null); setReturning(null); }}>
                Not you? Enter as someone else
              </button>
            </div>
          )}
          <form onSubmit={enter} className="space-y-3.5">
            <Field label="Name" htmlFor="entry-name">
              <TextInput id="entry-name" autoComplete="name" maxLength={80} required value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="Age" htmlFor="entry-age">
              <TextInput id="entry-age" type="number" inputMode="numeric" min={0} max={120} required value={age} onChange={(event) => setAge(event.target.value)} />
            </Field>
            <Field label="Gender" htmlFor="entry-gender">
              <SelectInput id="entry-gender" required value={gender} onChange={(event) => setGender(event.target.value as VisitorEntry["gender"])}>
                <option value="" disabled>Select</option>
                {GENDERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </SelectInput>
            </Field>
            <Field label="Role" htmlFor="entry-role" hint="Self-described; it does not change what you can use.">
              <SelectInput id="entry-role" required value={role} onChange={(event) => setRole(event.target.value as VisitorEntry["role"])}>
                <option value="" disabled>Select</option>
                {ROLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </SelectInput>
            </Field>
            {error && <ErrorBlock message={error} />}
            <Button type="submit" variant="primary" loading={busy === "enter"} disabled={!complete || busy !== null} className="w-full">Enter MedTwin</Button>
          </form>
          <p className="text-[11px] leading-4 text-ink-3">
            Use approved, de-identified evidence. Your cases are private by default; an administrator may explicitly configure a shared installation.
            This browser remembers who you are; clearing its data means entering again.
          </p>
          <div className="border-t border-line pt-4">
            <Button variant="secondary" icon={PlayCircle} loading={busy === "demo"} disabled={busy !== null} className="w-full" onClick={demo}>Try the demo</Button>
            <p className="mt-2 text-center text-[11px] leading-4 text-ink-3">A temporary workspace with a fictional sample case (two lab reports and a CT report), open for 24 hours.</p>
          </div>
          <Disclosure summary="Have a username and password from before?">
            <form onSubmit={signIn} className="space-y-3 pt-2">
              <Field label="Username or email" htmlFor="login-username">
                <TextInput id="login-username" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
              </Field>
              <Field label="Password" htmlFor="login-password">
                <TextInput id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
              </Field>
              <Button type="submit" variant="secondary" loading={busy === "account"} disabled={busy !== null} className="w-full">Open my existing workspace</Button>
            </form>
          </Disclosure>
        </div>
      </main>
      <footer className="border-t border-line px-5 py-3 text-center text-[11px] leading-5 text-ink-3">
        Research software, not a validated medical device. Real evidence only: results that do not exist are shown as unavailable, never estimated.
      </footer>
    </div>
  );
}

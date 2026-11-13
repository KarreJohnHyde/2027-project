import { useRef, useState, type FormEvent } from "react";
import { Activity, ArrowRight, BookOpen, PlayCircle, RefreshCw, WifiOff } from "lucide-react";
import { api, isServerUnavailable, newIdempotencyKey, type EntryGender, type EntryRole, type User, type VisitorEntry } from "../services/api";
import { errorMessage } from "../lib/format";
import { rememberCase, useWorkspace } from "../state/workspace";
import { Link } from "../lib/router";
import { Button, ErrorBlock, Field, SelectInput, TextInput } from "../components/ui";
import { ENTRY_ROLE_GROUPS } from "../data/entryRoles";

const GENDERS: Array<{ value: EntryGender; label: string }> = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "Prefer not to say" },
];


type Problems = { name?: string; age?: string; role?: string };

function check(name: string, age: string, role: string): Problems {
  const problems: Problems = {};
  if (!name.trim()) problems.name = "Enter your name.";
  else if (name.trim().length > 80) problems.name = "Use 80 characters or fewer.";
  if (age.trim() !== "") {
    const value = Number(age);
    if (!Number.isInteger(value) || value < 0 || value > 120) problems.age = "Enter a whole number from 0 to 120, or leave it empty.";
  }
  if (!role) problems.role = "Choose the role that describes you best.";
  return problems;
}

/**
 * The front door. A person enters their details once; this browser is then remembered by an HttpOnly session cookie
 * and goes straight to the workspace on later visits. There is no username or password here, and nothing is matched
 * by name: two people with the same name are two separate visitors.
 */
export default function EntryPage({ onEnter }: { onEnter: (user: User) => void }) {
  const sessionCheck = useWorkspace((state) => state.sessionCheck);
  const bootstrap = useWorkspace((state) => state.bootstrap);
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<EntryGender | "">("");
  const [role, setRole] = useState<EntryRole | "">("");
  const [problems, setProblems] = useState<Problems>({});
  const [busy, setBusy] = useState<"enter" | "demo" | "retry" | null>(null);
  const [error, setError] = useState<{ message: string; unavailable: boolean } | null>(null);
  // One key per submission: pressing again after a failure reuses it, so the server never makes two profiles for one
  // press that did reach it. Changing the details starts a new submission.
  const entryKey = useRef<string | null>(null);
  const demoKey = useRef<string | null>(null);

  function edited<T>(setter: (value: T) => void) {
    return (value: T) => {
      entryKey.current = null;
      setter(value);
    };
  }

  async function attempt(kind: "enter" | "demo", action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      // If this browser's session could not be checked earlier, check again first: a returning visitor must reach
      // their own workspace, not a new one.
      if (sessionCheck) {
        const existing = await api.restoreSession();
        if (existing) {
          onEnter(existing.user);
          return;
        }
      }
      await action();
    } catch (failure) {
      setError({ message: errorMessage(failure), unavailable: isServerUnavailable(failure) });
    } finally {
      setBusy(null);
    }
  }

  function enter(event: FormEvent) {
    event.preventDefault();
    const found = check(name, age, role);
    setProblems(found);
    if (Object.keys(found).length > 0 || !role) return;
    const entry: VisitorEntry = { name: name.trim(), age: age.trim() === "" ? null : Number(age), gender: gender || null, role };
    entryKey.current ??= newIdempotencyKey("entry");
    const key = entryKey.current;
    void attempt("enter", async () => {
      const session = await api.enterWorkspace(entry, key);
      onEnter(session.user);
    });
  }

  function demo() {
    demoKey.current ??= newIdempotencyKey("demo");
    const key = demoKey.current;
    void attempt("demo", async () => {
      const session = await api.startGuestDemo(key);
      rememberCase(session.case_id);
      onEnter(session.user);
    });
  }

  function retry() {
    setBusy("retry");
    setError(null);
    void bootstrap().finally(() => setBusy(null));
  }

  const banner = error?.unavailable ? error : sessionCheck ? { message: sessionCheck.message, unavailable: sessionCheck.unavailable } : null;

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <header className="flex items-center gap-2.5 border-b border-line px-5 py-3">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-fg"><Activity aria-hidden size={17} /></div>
        <div>
          <p className="text-sm font-semibold leading-4">MedTwin 2.0</p>
          <p className="text-[11px] text-ink-3">Patient-case research workspace · evidence provenance</p>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-full max-w-sm space-y-5 rounded-2xl border border-line bg-surface p-6 shadow-card">
          <div>
            <h1 className="text-lg font-semibold">Welcome to MedTwin</h1>
            <p className="mt-1 text-sm text-ink-2">Enter your details to begin.</p>
          </div>

          {banner && (
            <div role="alert" className="space-y-2 rounded-lg border border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-warning)_8%,transparent)] p-3 text-sm">
              <p className="flex items-start gap-2 font-medium text-warning-text">
                <WifiOff aria-hidden size={16} className="mt-0.5 shrink-0" /> {banner.unavailable ? "Server unavailable" : "Could not check this browser's session"}
              </p>
              <p className="text-xs leading-5 text-ink-2">{banner.message}</p>
              <p className="text-xs leading-5 text-ink-2">The fictional teaching cases below work without the server.</p>
              <Button size="sm" icon={RefreshCw} loading={busy === "retry"} disabled={busy !== null} onClick={retry}>Retry</Button>
            </div>
          )}

          <form onSubmit={enter} noValidate className="space-y-3.5">
            <Field label="Name" htmlFor="entry-name" hint={problems.name ? <span className="text-critical-text">{problems.name}</span> : undefined}>
              <TextInput
                id="entry-name" autoComplete="name" maxLength={80} required aria-invalid={problems.name ? true : undefined}
                value={name} onChange={(event) => edited(setName)(event.target.value)}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Age (optional)" htmlFor="entry-age" hint={problems.age ? <span className="text-critical-text">{problems.age}</span> : undefined}>
                <TextInput
                  id="entry-age" type="number" inputMode="numeric" min={0} max={120} aria-invalid={problems.age ? true : undefined}
                  value={age} onChange={(event) => edited(setAge)(event.target.value)}
                />
              </Field>
              <Field label="Gender (optional)" htmlFor="entry-gender">
                <SelectInput id="entry-gender" value={gender} onChange={(event) => edited(setGender)(event.target.value as EntryGender | "")}>
                  <option value="">Not given</option>
                  {GENDERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </SelectInput>
              </Field>
            </div>
            <Field label="Role" htmlFor="entry-role" hint={problems.role ? <span className="text-critical-text">{problems.role}</span> : "Self-described. It does not change what you can access."}>
              <SelectInput id="entry-role" required aria-invalid={problems.role ? true : undefined} value={role} onChange={(event) => edited(setRole)(event.target.value as EntryRole | "")}>
                <option value="" disabled>Select</option>
                {ENTRY_ROLE_GROUPS.map((group) => (
                  <optgroup key={group.label} label={group.label}>
                    {group.roles.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </optgroup>
                ))}
              </SelectInput>
            </Field>
            {error && !error.unavailable && <ErrorBlock message={error.message} />}
            <Button type="submit" variant="primary" icon={ArrowRight} loading={busy === "enter"} disabled={busy !== null} className="w-full">Enter MedTwin</Button>
          </form>

          <div className="space-y-2 border-t border-line pt-4">
            <Button variant="secondary" icon={PlayCircle} loading={busy === "demo"} disabled={busy !== null} className="w-full" onClick={demo}>Try Demo</Button>
            <p className="text-center text-[11px] leading-4 text-ink-3">A separate temporary workspace with one fictional sample case, open for 24 hours.</p>
            <Link to="/examples" className="flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-accent-text hover:bg-accent-soft">
              <BookOpen aria-hidden size={15} /> Fictional teaching cases: Alex, Maya and Sam
            </Link>
          </div>

          <p className="text-[11px] leading-4 text-ink-3">
            This browser remembers you, so next time you go straight to your workspace. Clearing this browser's data, or signing out, ends that.
            Your cases are private by default. Use de-identified evidence only.
          </p>
        </div>
      </main>
      <footer className="space-y-1 border-t border-line px-5 py-3 text-center text-[11px] leading-5 text-ink-3">
        <p>Research software, not a validated medical device. Results that do not exist are shown as unavailable, never estimated.</p>
        <p><Link to="/account" className="underline-offset-2 hover:underline">Registered account access</Link></p>
      </footer>
    </div>
  );
}

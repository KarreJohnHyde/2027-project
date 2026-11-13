import { useEffect, useRef, useState, type FormEvent } from "react";
import { Activity, ArrowLeft, KeyRound } from "lucide-react";
import { api, type User } from "../services/api";
import { errorMessage } from "../lib/format";
import { Link } from "../lib/router";
import { Button, ErrorBlock, Field, LoadingBlock, TextInput } from "../components/ui";

/** The code of a one-time sign-in link (/account#link=CODE). It sits in the fragment, which is never sent to a server. */
function linkCode(): string | null {
  if (typeof window === "undefined") return null;
  const code = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("link");
  return code && code.length >= 16 ? code : null;
}

/**
 * Access for accounts registered with a password before the entry page existed (administrators and verified
 * professionals among them). It is deliberately off the normal entry flow: ownership of such an account is proven by
 * its password, never by entering a matching name.
 */
export default function AccountAccessPage({ onEnter }: { onEnter: (user: User) => void }) {
  const [identifier, setIdentifier] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(() => linkCode() !== null);
  const redeemed = useRef(false);

  // A one-time link opens the account at once. The code is removed from the address bar and history first, so
  // reloading or going back never tries a used link again.
  useEffect(() => {
    const code = linkCode();
    if (!code || redeemed.current) return;
    redeemed.current = true;
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}`);
    void api.redeemSignInLink(code)
      .then((session) => onEnter(session.user))
      .catch((failure: unknown) => setError(errorMessage(failure)))
      .finally(() => setOpening(false));
  }, [onEnter]);

  function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    void api.login(identifier.trim(), secret)
      .then((session) => onEnter(session.user))
      .catch((failure: unknown) => setError(errorMessage(failure)))
      .finally(() => setBusy(false));
  }

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <header className="flex items-center gap-2.5 border-b border-line px-5 py-3">
        <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-fg"><Activity aria-hidden size={17} /></div>
        <p className="text-sm font-semibold">MedTwin 2.0</p>
      </header>
      <main className="flex flex-1 items-center justify-center p-4">
        <div className="w-full max-w-sm space-y-4 rounded-2xl border border-line bg-surface p-6 shadow-card">
          <div>
            <KeyRound aria-hidden size={18} className="text-accent-text" />
            <h1 className="mt-3 text-lg font-semibold">Registered account</h1>
            <p className="mt-1 text-xs leading-5 text-ink-2">For accounts that were registered with a password. Everyone else enters from the welcome page.</p>
          </div>
          {opening && <LoadingBlock label="Opening your account from the sign-in link" />}
          <form onSubmit={submit} className="space-y-3" hidden={opening}>
            <Field label="Username or email" htmlFor="account-identifier">
              <TextInput id="account-identifier" autoComplete="username" required value={identifier} onChange={(event) => setIdentifier(event.target.value)} />
            </Field>
            <Field label="Password" htmlFor="account-secret">
              <TextInput id="account-secret" type="password" autoComplete="current-password" required value={secret} onChange={(event) => setSecret(event.target.value)} />
            </Field>
            {error && <ErrorBlock message={error} />}
            <Button type="submit" variant="primary" loading={busy} disabled={!identifier.trim() || !secret} className="w-full">Open account</Button>
          </form>
          <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-ink-2 underline-offset-2 hover:underline"><ArrowLeft aria-hidden size={13} /> Back to the welcome page</Link>
        </div>
      </main>
    </div>
  );
}

import { useState, type FormEvent } from "react";
import { Activity, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { api, type RequestedDepartment, type RequestedRole, type User } from "../services/api";
import { errorMessage } from "../lib/format";
import { Button, ErrorBlock, Field, IconButton, SelectInput, TextInput } from "../components/ui";

type Mode = "login" | "register";

const PASSWORD_AUTOCOMPLETE: Record<Mode, string> = { login: "current-password", register: "new-password" };
const REQUESTED_ROLES: Array<{ value: RequestedRole; label: string }> = [
  { value: "standard_user", label: "Normal user" },
  { value: "patient", label: "Patient" },
  { value: "medical_staff", label: "Medical staff" },
  { value: "nurse", label: "Nurse" },
  { value: "lab_expert", label: "Lab expert" },
  { value: "doctor", label: "Doctor / clinician" },
  { value: "surgeon", label: "Surgeon" },
  { value: "department_expert", label: "Department expert" },
  { value: "researcher", label: "Researcher" },
];
const REQUESTED_DEPARTMENTS: Array<{ value: RequestedDepartment; label: string }> = [
  { value: "anesthesiology", label: "Anesthesiology" },
  { value: "cardiology", label: "Cardiology" },
  { value: "cardiothoracic_surgery", label: "Cardiothoracic surgery" },
  { value: "dermatology", label: "Dermatology" },
  { value: "emergency_medicine", label: "Emergency medicine" },
  { value: "endocrinology", label: "Endocrinology" },
  { value: "family_medicine", label: "Family medicine" },
  { value: "gastroenterology", label: "Gastroenterology" },
  { value: "general_surgery", label: "General surgery" },
  { value: "hematology", label: "Hematology" },
  { value: "infectious_disease", label: "Infectious disease" },
  { value: "internal_medicine", label: "Internal medicine" },
  { value: "laboratory_medicine", label: "Laboratory medicine / pathology" },
  { value: "nephrology", label: "Nephrology" },
  { value: "neurology", label: "Neurology" },
  { value: "neurosurgery", label: "Neurosurgery" },
  { value: "obstetrics_gynecology", label: "Obstetrics and gynecology" },
  { value: "oncology", label: "Oncology" },
  { value: "ophthalmology", label: "Ophthalmology" },
  { value: "orthopedic_surgery", label: "Orthopedic surgery" },
  { value: "otolaryngology", label: "Otolaryngology (ENT)" },
  { value: "pediatrics", label: "Pediatrics" },
  { value: "psychiatry", label: "Psychiatry" },
  { value: "pulmonology", label: "Pulmonology / respiratory medicine" },
  { value: "radiology", label: "Radiology" },
  { value: "rehabilitation_medicine", label: "Rehabilitation medicine" },
  { value: "urology", label: "Urology" },
  { value: "other", label: "Other department" },
];
const DEPARTMENT_ROLES: RequestedRole[] = ["doctor", "surgeon", "department_expert"];

export default function LoginPage({ onLoginSuccess }: { onLoginSuccess: (user: User) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [requestedRole, setRequestedRole] = useState<RequestedRole>("standard_user");
  const [requestedDepartment, setRequestedDepartment] = useState<RequestedDepartment | "">("");
  const [otherDepartment, setOtherDepartment] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
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
        const registration = await api.register({
          username: username.trim(),
          email: email.trim(),
          full_name: fullName.trim() || undefined,
          password,
          requested_role: requestedRole,
          ...(DEPARTMENT_ROLES.includes(requestedRole)
            ? {
                requested_department: requestedDepartment || undefined,
                requested_department_other:
                  requestedDepartment === "other" ? otherDepartment.trim() || undefined : undefined,
              }
            : {}),
        });
        setMode("login");
        setPassword("");
        setConfirmPassword("");
        setSuccess(
          registration.profileRequestSaved
            ? "Your unverified standard account has been created and your profile request recorded. Sign in with your new username and password. Professional access must be authorised and provisioned separately."
            : "Your account was created, but this server does not support saving profile or department requests. Contact the administrator to have your requested profile recorded. Your account remains unverified.",
        );
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
          <form onSubmit={submit} autoComplete={mode === "register" ? "off" : undefined} className="space-y-3.5">
            {mode === "register" && (
              <>
                <Field label="Full name (optional)" htmlFor="register-full-name">
                  <TextInput id="register-full-name" autoComplete="name" maxLength={128} value={fullName} onChange={(event) => setFullName(event.target.value)} />
                </Field>
                <Field label="Email" htmlFor="register-email">
                  <TextInput id="register-email" type="email" autoComplete="email" maxLength={128} required value={email} onChange={(event) => setEmail(event.target.value)} />
                </Field>
                <Field label="Account type / access request" htmlFor="register-role" hint="This records your requested profile; it does not grant clinical or professional permissions.">
                  <SelectInput
                    id="register-role"
                    required
                    value={requestedRole}
                    onChange={(event) => {
                      setRequestedRole(event.target.value as RequestedRole);
                      setRequestedDepartment("");
                      setOtherDepartment("");
                    }}
                  >
                    {REQUESTED_ROLES.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
                  </SelectInput>
                </Field>
                {DEPARTMENT_ROLES.includes(requestedRole) && (
                  <>
                    <Field label="Hospital department / specialty" htmlFor="register-department">
                      <SelectInput
                        id="register-department"
                        required
                        value={requestedDepartment}
                        onChange={(event) => setRequestedDepartment(event.target.value as RequestedDepartment | "")}
                      >
                        <option value="">Select a department</option>
                        {REQUESTED_DEPARTMENTS.map((department) => (
                          <option key={department.value} value={department.value}>{department.label}</option>
                        ))}
                      </SelectInput>
                    </Field>
                    {requestedDepartment === "other" && (
                      <Field label="Department name" htmlFor="register-department-other">
                        <TextInput
                          id="register-department-other"
                          required
                          maxLength={100}
                          value={otherDepartment}
                          onChange={(event) => setOtherDepartment(event.target.value)}
                        />
                      </Field>
                    )}
                  </>
                )}
              </>
            )}
            <Field
              label={mode === "register" ? "Username" : "Username or email"}
              htmlFor="login-username"
              hint={mode === "register" ? "Use 3–50 characters." : undefined}
            >
              <TextInput
                id="login-username"
                autoComplete={mode === "register" ? "off" : "username"}
                placeholder={mode === "login" ? "Enter your username or email" : undefined}
                minLength={mode === "register" ? 3 : undefined}
                maxLength={mode === "register" ? 128 : undefined}
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </Field>
            <Field label="Password" htmlFor="login-password">
              <span className="relative block">
                <TextInput id="login-password" type={showPassword ? "text" : "password"} autoComplete={PASSWORD_AUTOCOMPLETE[mode]} minLength={mode === "register" ? 6 : undefined} required value={password} onChange={(event) => setPassword(event.target.value)} className="pr-10" />
                <IconButton
                  label={showPassword ? "Hide password" : "Show password"}
                  icon={showPassword ? EyeOff : Eye}
                  active={showPassword}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 border-0 bg-transparent hover:bg-surface-2"
                />
              </span>
            </Field>
            {mode === "register" && (
              <Field label="Confirm password" htmlFor="register-confirm-password">
                <span className="relative block">
                  <TextInput id="register-confirm-password" type={showConfirmPassword ? "text" : "password"} autoComplete="new-password" minLength={6} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="pr-10" />
                  <IconButton
                    label={showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"}
                    icon={showConfirmPassword ? EyeOff : Eye}
                    active={showConfirmPassword}
                    aria-pressed={showConfirmPassword}
                    onClick={() => setShowConfirmPassword((visible) => !visible)}
                    className="absolute right-1 top-1/2 -translate-y-1/2 border-0 bg-transparent hover:bg-surface-2"
                  />
                </span>
              </Field>
            )}
            {error && (
              <>
                <ErrorBlock
                  message={
                    mode === "register" && error === "Username or email already registered."
                      ? "An account with that username or email already exists. Sign in if it is your account, or try a different username and email."
                      : error
                  }
                />
                {mode === "register" && error === "Username or email already registered." && (
                  <Button
                    variant="secondary"
                    className="w-full"
                    onClick={() => {
                      setMode("login");
                      setError(null);
                      setSuccess("Sign in with the username and password for your existing account. If the username is different, update it before signing in.");
                    }}
                  >
                    Go to sign in
                  </Button>
                )}
              </>
            )}
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
                const nextMode = mode === "register" ? "login" : "register";
                if (nextMode === "register") {
                  setUsername("");
                  setPassword("");
                  setConfirmPassword("");
                  setShowPassword(false);
                  setShowConfirmPassword(false);
                }
                setMode(nextMode);
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

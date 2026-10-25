import { useEffect, useId, useState, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { AlertTriangle, Ban, Check, CheckCircle2, ChevronDown, CircleDashed, Copy, Info, LoaderCircle, X, XCircle } from "lucide-react";
import { humanize } from "../lib/format";

type Tone = "neutral" | "good" | "warning" | "serious" | "critical" | "info" | "accent" | "unavailable";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-line bg-surface-2 text-ink-2",
  good: "border-[color-mix(in_srgb,var(--mt-good)_35%,transparent)] bg-[color-mix(in_srgb,var(--mt-good)_10%,transparent)] text-good-text",
  warning: "border-[color-mix(in_srgb,var(--mt-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-warning)_12%,transparent)] text-warning-text",
  serious: "border-[color-mix(in_srgb,var(--mt-serious)_45%,transparent)] bg-[color-mix(in_srgb,var(--mt-serious)_12%,transparent)] text-serious-text",
  critical: "border-[color-mix(in_srgb,var(--mt-critical)_40%,transparent)] bg-[color-mix(in_srgb,var(--mt-critical)_10%,transparent)] text-critical-text",
  info: "border-[color-mix(in_srgb,var(--mt-map-verified)_35%,transparent)] bg-[color-mix(in_srgb,var(--mt-map-verified)_10%,transparent)] text-info-text",
  accent: "border-[color-mix(in_srgb,var(--mt-accent)_35%,transparent)] bg-accent-soft text-accent-text",
  unavailable: "border-line-strong bg-surface-2 text-ink-2 hatch",
};

const TONE_ICON: Record<Tone, typeof Info> = {
  neutral: Info,
  good: CheckCircle2,
  warning: AlertTriangle,
  serious: AlertTriangle,
  critical: XCircle,
  info: Info,
  accent: Info,
  unavailable: CircleDashed,
};

const CRITICAL = /^(ERROR|FAILED|REJECT|REJECTED|INVALID|LICENSE_BLOCKED|INSPECTION_FAILED|LOAD_FAILED|VALIDATOR_FAILED|CONFLICT)|_FAILED$|^FAIL$|_MISMATCH$/;
// Negative codes are tested before GOOD, so e.g. VALIDATION_FLAG_FALSE never reads as "VALID".
const UNAVAILABLE = /^(NOT_|NO_|UN(AVAILABLE|SUPPORTED)|INSUFFICIENT|INDETERMINATE|MODEL_NOT|MODEL_UNAVAILABLE|REGISTRATION_UNAVAILABLE|ESTIMAND|DEPENDENCY_MISSING|WEIGHTS_MISSING|CHECKPOINT_MISSING|MAPPING_UNSUPPORTED|PROPOSED_ONLY|ABSTAIN|INTERVENTION_NOT|DATA_UNAVAILABLE|UNDEFINED|BLOCKED|DISABLED|OFF)|NOT_AVAILABLE|UNSUPPORTED|_MISSING$|NOT_COMPUTED|NOT_RUN|NOT_TRAINED|NOT_VALIDATED|NOT_IDENTIFIABLE|_FALSE$|_INCOMPLETE$|UNVERIFIED$/;
const WARNING = /PENDING|UNVALIDATED|NOT_VALIDATED_IN|PARTIAL|BBOX|SCHEMATIC|UNREGISTERED|DISCOVERED|UNCERTAIN|HYPOTHETICAL|NEEDS_|CURATED|REVIEW|AMBIGUOUS|PREVIEW|RESTRICTED|NON_COMMERCIAL|IMPLEMENTED_NOT|READY_UNVALIDATED|REDUCED|WARN/;
const GOOD = /^(COMPLETED|HEALTHY|READY|VALID|PASS|PASSED|SUPPORTED|COMPUTED|OBSERVED|CONFIRMED|AVAILABLE|ACCEPTED|LOADED|CONNECTED|VERIFIED|IMPLEMENTED_AND_TESTED|SOURCE_FRAME_SHARED|WITHIN|ATTRIBUTION|SHARE_ALIKE|AFFIRMED|CERTAIN|OPERATIONAL|SUCCESS)/;
const SERIOUS = /^(ABOVE|BELOW)_DOCUMENTED|^(HIGH|LOW|CRITICAL_HIGH|CRITICAL_LOW|ABNORMAL)$/;

export function toneFor(status: string): Tone {
  const code = status.toUpperCase();
  if (CRITICAL.test(code)) return "critical";
  if (SERIOUS.test(code)) return "serious";
  if (UNAVAILABLE.test(code)) return "unavailable";
  if (WARNING.test(code)) return "warning";
  if (GOOD.test(code)) return "good";
  return "neutral";
}

export function Badge({ tone = "neutral", icon = true, children, title }: { tone?: Tone; icon?: boolean; children: ReactNode; title?: string }) {
  const Icon = TONE_ICON[tone];
  return (
    <span title={title} className={`inline-flex max-w-full items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11px] font-medium leading-4 ${TONE_CLASSES[tone]}`}>
      {icon && <Icon aria-hidden size={12} className="shrink-0" />}
      <span className="truncate">{children}</span>
    </span>
  );
}

/** Machine status codes keep their exact value in the title attribute. */
export function StatusBadge({ status, label }: { status: string | null | undefined; label?: string }) {
  if (!status) return <Badge tone="neutral">—</Badge>;
  return (
    <Badge tone={toneFor(status)} title={status}>
      {label ?? humanize(status)}
    </Badge>
  );
}

export function Card({ title, eyebrow, actions, children, className = "", padded = true, id }: { title?: ReactNode; eyebrow?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean; id?: string }) {
  return (
    <section id={id} className={`min-w-0 rounded-xl border border-line bg-surface shadow-card ${className}`}>
      {(title || actions || eyebrow) && (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {eyebrow && <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">{eyebrow}</p>}
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`min-w-0 max-w-full ${padded ? "p-4" : ""}`}>{children}</div>
    </section>
  );
}

export function PageHeader({ eyebrow, title, description, actions, children }: { eyebrow?: string; title: string; description?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <p className="text-xs font-medium text-accent-text">{eyebrow}</p>}
        <h1 className="mt-0.5 text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {description && <div className="mt-1.5 text-sm leading-6 text-ink-2">{description}</div>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Metric({ label, value, note, status }: { label: string; value: ReactNode; note?: ReactNode; status?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-ink-2">{label}</p>
        {status && <StatusBadge status={status} />}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      {note && <p className="mt-1 text-xs leading-5 text-ink-3">{note}</p>}
    </div>
  );
}

export function EmptyState({ icon: Icon = Ban, title, detail, action }: { icon?: typeof Info; title: string; detail?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong bg-surface-2 px-5 py-8 text-center">
      <Icon aria-hidden className="mb-2.5 text-ink-3" size={22} />
      <p className="text-sm font-medium text-ink">{title}</p>
      {detail && <div className="mt-1 max-w-lg text-xs leading-5 text-ink-2">{detail}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** The visual form of a result that does not exist: code + reason on a hatched field. */
export function Unavailable({ code, reason, children, compact = false }: { code: string; reason?: ReactNode; children?: ReactNode; compact?: boolean }) {
  return (
    <div className={`hatch rounded-lg border border-line-strong bg-surface-2 ${compact ? "p-2.5" : "p-4"}`} role="status">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={code} />
        <code className="text-[11px] text-ink-3">{code}</code>
      </div>
      {reason && <p className="mt-1.5 text-xs leading-5 text-ink-2">{reason}</p>}
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-transparent bg-accent text-accent-fg hover:brightness-110",
  secondary: "border-line-strong bg-surface text-ink hover:bg-surface-2",
  ghost: "border-transparent bg-transparent text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger: "border-transparent bg-critical text-white hover:brightness-110",
};

export function Button({ variant = "secondary", size = "md", icon: Icon, loading = false, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md"; icon?: typeof Info; loading?: boolean }) {
  const sizing = size === "sm" ? "h-7 px-2.5 text-xs gap-1.5" : "h-9 px-3 text-sm gap-2";
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex shrink-0 items-center justify-center rounded-lg border font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${sizing} ${BUTTON_VARIANTS[variant]} ${className}`}
    >
      {loading ? <LoaderCircle aria-hidden className="animate-spin" size={size === "sm" ? 13 : 15} /> : Icon && <Icon aria-hidden size={size === "sm" ? 13 : 15} />}
      {children}
    </button>
  );
}

export function IconButton({ label, icon: Icon, active = false, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: typeof Info; active?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      {...props}
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition disabled:cursor-not-allowed disabled:opacity-40 ${active ? "border-[color-mix(in_srgb,var(--mt-accent)_45%,transparent)] bg-accent-soft text-accent-text" : "border-line bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink"} ${className}`}
    >
      <Icon aria-hidden size={15} />
    </button>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label, size = "md" }: { options: Array<{ value: T; label: ReactNode; disabled?: boolean; title?: string }>; value: T; onChange: (value: T) => void; label: string; size?: "sm" | "md" }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full flex-wrap rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((option) => (
        <button
          type="button"
          role="radio"
          aria-checked={value === option.value}
          key={option.value}
          title={option.title}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={`rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${size === "sm" ? "px-2 py-1 text-[11px]" : "px-2.5 py-1.5 text-xs"} ${value === option.value ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:text-ink"}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="block min-w-0">
      <span className="text-xs font-medium text-ink-2">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-[11px] leading-4 text-ink-3">{hint}</span>}
    </label>
  );
}

const CONTROL = "w-full rounded-lg border border-line-strong bg-surface px-2.5 text-sm text-ink outline-none transition placeholder:text-ink-3 focus:border-[var(--mt-focus)] disabled:opacity-50";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} h-9 ${props.className ?? ""}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${CONTROL} py-2 ${props.className ?? ""}`} />;
}

export function SelectInput({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="relative block">
      <select {...props} className={`${CONTROL} h-9 appearance-none pr-8 ${props.className ?? ""}`}>
        {children}
      </select>
      <ChevronDown aria-hidden className="pointer-events-none absolute right-2.5 top-2.5 text-ink-3" size={15} />
    </span>
  );
}

export function KeyValue({ items, columns = 2 }: { items: Array<{ label: string; value: ReactNode; mono?: boolean }>; columns?: 1 | 2 | 3 }) {
  const grid = columns === 1 ? "" : columns === 2 ? "sm:grid-cols-2" : "sm:grid-cols-3";
  return (
    <dl className={`grid gap-x-4 gap-y-3 ${grid}`}>
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-[11px] font-medium text-ink-3">{item.label}</dt>
          <dd className={`mt-0.5 break-words text-sm text-ink ${item.mono ? "font-mono text-xs" : ""}`}>{item.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Hash({ value, length = 16 }: { value: string | null | undefined; length?: number }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="text-ink-3">—</span>;
  async function copy() {
    try {
      await navigator.clipboard.writeText(value ?? "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }
  return (
    <span className="inline-flex max-w-full items-center gap-1 font-mono text-xs text-ink-2">
      <span className="truncate" title={value}>{value.length > length ? `${value.slice(0, length)}…` : value}</span>
      <button type="button" aria-label="Copy full value" onClick={copy} className="rounded p-0.5 text-ink-3 hover:bg-surface-2 hover:text-ink">
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </span>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-xs text-ink-2">
      <LoaderCircle aria-hidden className="animate-spin" size={15} />
      {label}
    </span>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-32 items-center justify-center rounded-lg border border-line bg-surface-2">
      <Spinner label={label} />
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-[color-mix(in_srgb,var(--mt-critical)_35%,transparent)] bg-[color-mix(in_srgb,var(--mt-critical)_8%,transparent)] p-3 text-sm text-critical-text">
      <span className="flex min-w-0 items-start gap-2">
        <XCircle aria-hidden className="mt-0.5 shrink-0" size={16} />
        <span className="break-words">{message}</span>
      </span>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Dialog({ title, description, onClose, children, footer, wide = false }: { title: string; description?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const titleId = useId();
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className={`flex max-h-[92vh] w-full flex-col rounded-t-2xl border border-line bg-surface shadow-card sm:rounded-2xl ${wide ? "sm:max-w-3xl" : "sm:max-w-lg"}`}>
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-xs leading-5 text-ink-2">{description}</p>}
          </div>
          <IconButton label="Close dialog" icon={X} onClick={onClose} />
        </header>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

/** A source excerpt with the extracted span highlighted, preserving the exact characters. */
export function SourceExcerpt({ text, start, end, offset = 0 }: { text: string; start?: number | null; end?: number | null; offset?: number }) {
  if (start === null || start === undefined || end === null || end === undefined || start < offset || end > offset + text.length || end <= start) {
    return <blockquote className="border-l-2 border-line-strong pl-3 text-sm leading-6 text-ink">{text}</blockquote>;
  }
  const localStart = start - offset;
  const localEnd = end - offset;
  return (
    <blockquote className="border-l-2 border-line-strong pl-3 text-sm leading-6 text-ink">
      {text.slice(0, localStart)}
      <mark className="rounded-sm bg-[color-mix(in_srgb,var(--mt-accent)_22%,transparent)] px-0.5 text-ink">{text.slice(localStart, localEnd)}</mark>
      {text.slice(localEnd)}
    </blockquote>
  );
}

export function Disclosure({ summary, children, defaultOpen = false }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-lg border border-line bg-surface-2">
      <summary className="flex list-none items-center justify-between gap-2 px-3 py-2 text-xs font-medium text-ink [&::-webkit-details-marker]:hidden">
        {summary}
        <ChevronDown aria-hidden className="shrink-0 text-ink-3 transition group-open:rotate-180" size={14} />
      </summary>
      <div className="border-t border-line px-3 py-3">{children}</div>
    </details>
  );
}

export function Table({ headers, children, dense = false }: { headers: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="w-full min-w-0 max-w-full overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line text-[11px] font-medium text-ink-3">
            {headers.map((header, index) => (
              <th key={index} scope="col" className={`whitespace-nowrap font-medium ${dense ? "px-2 py-1.5" : "px-3 py-2"}`}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody className={`divide-y divide-line tabular ${dense ? "[&_td]:px-2 [&_td]:py-1.5" : "[&_td]:px-3 [&_td]:py-2.5"} [&_td]:align-top`}>{children}</tbody>
      </table>
    </div>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-3">{children}</h3>
      {aside}
    </div>
  );
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "Not available";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(date);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 0.001 || abs >= 1e6)) return value.toExponential(2);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat().format(value);
}

/** Machine status codes are shown verbatim but readable: "MODEL_NOT_VALIDATED" -> "Model not validated". */
export function humanize(code: string | null | undefined): string {
  if (!code) return "—";
  const words = code.replace(/[_-]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function shortHash(hash: string | null | undefined, length = 12): string {
  return hash ? `${hash.slice(0, length)}…` : "—";
}

export function todayInputValue(): string {
  const local = new Date();
  local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
  return local.toISOString().slice(0, 10);
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    const requestId =
      "requestId" in error && typeof error.requestId === "string"
        ? error.requestId
        : null;
    return requestId ? `${error.message} (request ${requestId})` : error.message;
  }
  return "The request could not be completed.";
}

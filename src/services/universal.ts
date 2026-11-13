import { API_CREDENTIALS, API_V1_BASE, CLIENT_HEADER } from "./api";

/** Additive clients share the application's existing cookie/session boundary. */
export async function universalFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!path.startsWith("/") || path.startsWith("//") || /[\r\n]/.test(path)) throw new Error("Invalid API resource path");
  const headers = new Headers(init.headers);
  headers.set(CLIENT_HEADER, "web");
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_V1_BASE}${path}`, { ...init, headers, credentials: API_CREDENTIALS });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const record = payload?.detail && typeof payload.detail === "object" && !Array.isArray(payload.detail) ? payload.detail as Record<string, unknown> : null;
    const reason = record && (typeof record.reason === "string" ? record.reason : typeof record.message === "string" ? record.message : null);
    const detail = typeof payload?.detail === "string" ? payload.detail : reason ? `${typeof record?.code === "string" ? `${record.code}: ` : ""}${reason}` : `Request failed (${response.status})`;
    throw new Error(`${detail}${response.headers.get("x-request-id") ? ` · request ${response.headers.get("x-request-id")}` : ""}`);
  }
  return response;
}

export async function universalJson<T>(path: string, init?: RequestInit): Promise<T> {
  return (await universalFetch(path, init)).json() as Promise<T>;
}

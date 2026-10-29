import { api, ApiError, API_V1_BASE } from "../services/api";
import type { LandmarkPair } from "./landmarkValidation";

export type LandmarkManifest = {
  id: number;
  finding_id: number;
  case_id: number;
  coordinate_frame: string;
  requested_region: string;
  fit_pairs: number;
  held_out_pairs: number;
  fit_landmarks?: LandmarkPair[];
  held_out_landmarks?: LandmarkPair[];
  threshold_mm: number;
  status: "PROPOSED" | "APPROVED" | "REJECTED";
  created_by_id: number;
  created_at: string;
  decided_by_id: number | null;
  decided_at: string | null;
  decision_comment: string | null;
};

export type LandmarkProposal = {
  coordinate_frame: string;
  requested_region: string;
  fit_pairs: LandmarkPair[];
  held_out_pairs: LandmarkPair[];
  threshold_mm: number;
};

export type RegistrationGateResult = {
  finding_id: number;
  coordinate_frame: string;
  transform_matrix: number[][] | null;
  held_out_landmarks_count: number;
  tre_error: number | null;
  tre_threshold: number;
  passed_gate: boolean;
  representation_level: string;
  assigned_region: string | null;
  mapping_status: string;
  explanatory_reason: string;
};

// Keep this feature's transport separate from the shared API client. Authentication
// remains the same bearer token; no private URLs, credentials or identifiers persist.
async function request<T>(endpoint: string, body?: unknown): Promise<T> {
  const token = api.getToken();
  if (!token) throw new ApiError(401, "Sign in to review case landmark evidence.");
  const response = await fetch(`${API_V1_BASE}${endpoint}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  let data: unknown;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) {
    if (response.status === 401) api.setToken(null);
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : undefined;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map(item => typeof item?.msg === "string" ? item.msg : "Invalid request").join("; ")
        : `Landmark request failed (${response.status}).`;
    throw new ApiError(response.status, message, detail, response.headers.get("X-Request-ID"));
  }
  return data as T;
}

export const landmarkApi = {
  list: (findingId: number) => request<LandmarkManifest[]>(`/findings/${findingId}/landmark-manifests`),
  propose: (findingId: number, proposal: LandmarkProposal) => request<LandmarkManifest>(`/findings/${findingId}/landmark-manifests`, proposal),
  decide: (manifestId: number, decision: "APPROVED" | "REJECTED", comment: string) => request<LandmarkManifest>(`/landmark-manifests/${manifestId}/decision`, { decision, comment }),
  evaluate: (findingId: number, manifestId: number) => request<RegistrationGateResult>(`/findings/${findingId}/registration-gate`, { finding_id: findingId, manifest_id: manifestId }),
};

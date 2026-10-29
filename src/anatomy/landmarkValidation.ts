export type LandmarkPair = { source: [number, number, number]; target: [number, number, number] };

export function parseLandmarkPairs(text: string, purpose: "fitting" | "held-out"): LandmarkPair[] {
  let value: unknown;
  try { value = JSON.parse(text); } catch { throw new Error(`Enter the ${purpose} landmarks as a JSON array of source/target coordinate pairs.`); }
  const minimum = purpose === "fitting" ? 3 : 1;
  const maximum = purpose === "fitting" ? 200 : 100;
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    throw new Error(`${purpose} landmarks require ${minimum}–${maximum} pairs.`);
  }
  for (const [index, pair] of value.entries()) {
    if (!pair || typeof pair !== "object" || Object.keys(pair).some(key => key !== "source" && key !== "target")) {
      throw new Error(`${purpose} pair ${index + 1} must contain only source and target.`);
    }
    for (const side of ["source", "target"] as const) {
      const coordinates = pair[side];
      if (!Array.isArray(coordinates) || coordinates.length !== 3 || coordinates.some(item => typeof item !== "number" || !Number.isFinite(item))) {
        throw new Error(`${purpose} pair ${index + 1}: ${side} must contain three finite numbers in millimetres.`);
      }
    }
  }
  return value as LandmarkPair[];
}

export function validateLandmarkPartition(fit: LandmarkPair[], heldOut: LandmarkPair[]) {
  const fitted = new Set(fit.map(pair => JSON.stringify([pair.source, pair.target])));
  if (heldOut.some(pair => fitted.has(JSON.stringify([pair.source, pair.target])))) {
    throw new Error("Held-out landmarks must not repeat fitting pairs; declare them before fitting.");
  }
}

export function canManageLandmarks(
  user: { id: number; role: string; verification_status: string; is_active: boolean } | null,
  ownerId: number | null,
  members: Array<{ user_id: number; role: string }>,
): boolean {
  return Boolean(user?.is_active && user.verification_status === "VERIFIED"
    && ["clinician", "admin"].includes(user.role)
    && (user.role === "admin" || user.id === ownerId || members.some(member => member.user_id === user.id && member.role === "EDITOR")));
}

export function canDecideLandmarks(canManage: boolean, userId: number | undefined, proposerId: number, status: string, coordinatesAvailable: boolean) {
  return canManage && coordinatesAvailable && status === "PROPOSED" && userId !== undefined && userId !== proposerId;
}

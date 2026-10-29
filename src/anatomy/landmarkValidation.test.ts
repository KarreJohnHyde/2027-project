import assert from "node:assert/strict";
import test from "node:test";
import { canDecideLandmarks, canManageLandmarks, parseLandmarkPairs, validateLandmarkPartition } from "./landmarkValidation.ts";

const pair = { source: [0, 1, 2] as [number, number, number], target: [3, 4, 5] as [number, number, number] };
test("landmark parser accepts measured numeric pairs, not empty or nonnumeric defaults", () => {
  assert.deepEqual(parseLandmarkPairs(JSON.stringify([pair]), "held-out"), [pair]);
  assert.throws(() => parseLandmarkPairs("", "held-out"));
  assert.throws(() => parseLandmarkPairs("[]", "fitting"));
  assert.throws(() => parseLandmarkPairs(JSON.stringify([{ source: ["0", 1, 2], target: [1, 2, 3] }]), "held-out"));
  assert.throws(() => parseLandmarkPairs('[{"source":[1e400,1,2],"target":[1,2,3]}]', "held-out"));
});
test("held-out coordinates must not repeat fitting pairs", () => {
  assert.throws(() => validateLandmarkPartition([pair], [pair]));
  assert.doesNotThrow(() => validateLandmarkPartition([pair], [{ source: [9, 8, 7], target: [6, 5, 4] }]));
});
test("landmark mutations need independently verified clinical role and case edit access", () => {
  const clinician = { id: 10, role: "clinician", verification_status: "VERIFIED", is_active: true };
  assert.equal(canManageLandmarks(clinician, 10, []), true);
  assert.equal(canManageLandmarks(clinician, 99, [{ user_id: 10, role: "EDITOR" }]), true);
  assert.equal(canManageLandmarks(clinician, 99, [{ user_id: 10, role: "VIEWER" }]), false);
  assert.equal(canManageLandmarks({ ...clinician, verification_status: "UNVERIFIED" }, 10, []), false);
  assert.equal(canManageLandmarks({ ...clinician, role: "researcher" }, 10, []), false);
  assert.equal(canManageLandmarks(null, 10, []), false);
});
test("independent decisions refuse own proposals, unavailable points and decided manifests", () => {
  assert.equal(canDecideLandmarks(true, 20, 10, "PROPOSED", true), true);
  assert.equal(canDecideLandmarks(true, 10, 10, "PROPOSED", true), false);
  assert.equal(canDecideLandmarks(true, 20, 10, "PROPOSED", false), false);
  assert.equal(canDecideLandmarks(true, 20, 10, "APPROVED", true), false);
});

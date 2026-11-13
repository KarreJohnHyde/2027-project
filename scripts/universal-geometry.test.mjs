import test from "node:test";
import assert from "node:assert/strict";
import { INDEX_PLANES, anatomicalDirection, displayToVoxel, inverseAffine, planeCorners, planeSize, transformPoint, voxelToDisplay } from "../src/lib/universalGeometry.ts";

test("index to source display and inverse agree for all native and DICOM planes", () => {
  const dimensions = [13, 17, 7];
  for (const flip of [true, false]) for (const axis of INDEX_PLANES) for (const voxel of [[0, 0, 0], [12, 16, 6], [4, 9, 2]]) {
    const [u, v] = voxelToDisplay(axis, voxel, dimensions, flip);
    assert.deepEqual(displayToVoxel(axis, u, v, voxel, dimensions, flip), voxel);
    const size = planeSize(axis, dimensions);
    assert.ok(u >= 0 && u < size[0] && v >= 0 && v < size[1]);
    assert.equal(planeCorners(axis, voxel, dimensions, flip).length, 4);
  }
  assert.deepEqual(voxelToDisplay("coronal", [4, 9, 2], dimensions, true), [4, 4]);
  assert.deepEqual(voxelToDisplay("coronal", [4, 9, 2], dimensions, false), [4, 2]);
});
test("oblique and reflected affine inverse preserves coordinates and source laterality", () => {
  const c = Math.cos(.7), s = Math.sin(.7);
  const matrix = [[-2*c, -3*s, 0, 40], [-2*s, 3*c, 0, -12], [0, 0, 5, 8], [0, 0, 0, 1]];
  const point = [4.5, 9.25, 2.125];
  const roundtrip = transformPoint(inverseAffine(matrix), transformPoint(matrix, point));
  roundtrip.forEach((v, i) => assert.ok(Math.abs(v - point[i]) < 1e-10));
  assert.equal(anatomicalDirection([1, 0, 0], "RAS_MM"), "R");
  assert.equal(anatomicalDirection([1, 0, 0], "LPS_MM"), "L");
  assert.equal(anatomicalDirection([0, -1, 0], "LPS_MM"), "A");
  assert.equal(anatomicalDirection([0, 0, 1], "RAS_MM"), "S");
  assert.equal(anatomicalDirection([1, 0, 0], null), "Unknown");
  assert.equal(anatomicalDirection([1, 1, 0], "RAS_MM"), "RA");
});
test("malformed or singular transforms and non-finite coordinates refuse", () => {
  assert.throws(() => inverseAffine([[0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]), /NONINVERTIBLE_GEOMETRY/);
  assert.throws(() => transformPoint([[1]], [0, 0, 0]), /MALFORMED_GEOMETRY/);
  assert.throws(() => transformPoint([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], [NaN, 0, 0]), /MALFORMED_GEOMETRY/);
});

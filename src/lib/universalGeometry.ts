export type VoxelPoint = [number, number, number]
export type Matrix4Rows = number[][]
export type IndexPlane = "axial" | "coronal" | "sagittal"
export const INDEX_PLANES: IndexPlane[] = ["axial", "coronal", "sagittal"]

export function transformPoint(
  matrix: Matrix4Rows,
  point: VoxelPoint,
): VoxelPoint {
  if (
    matrix.length !== 4 ||
    matrix.some(
      (row) => row.length !== 4 || row.some((v) => !Number.isFinite(v)),
    ) ||
    point.some((v) => !Number.isFinite(v))
  )
    throw new Error("MALFORMED_GEOMETRY")
  if (matrix[3].some((v, i) => Math.abs(v - (i === 3 ? 1 : 0)) > 1e-10))
    throw new Error("MALFORMED_GEOMETRY")
  return [0, 1, 2].map(
    (row) =>
      matrix[row][0] * point[0] +
      matrix[row][1] * point[1] +
      matrix[row][2] * point[2] +
      matrix[row][3],
  ) as VoxelPoint
}

export function inverseAffine(matrix: Matrix4Rows): Matrix4Rows {
  transformPoint(matrix, [0, 0, 0])
  const a = matrix.map((row, i) => [
    ...row,
    ...[0, 1, 2, 3].map((j) => (i === j ? 1 : 0)),
  ])
  for (let col = 0; col < 4; col++) {
    let pivot = col
    for (let row = col + 1; row < 4; row++)
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row
    if (Math.abs(a[pivot][col]) < 1e-12)
      throw new Error("NONINVERTIBLE_GEOMETRY")
    ;[a[col], a[pivot]] = [a[pivot], a[col]]
    const divisor = a[col][col]
    a[col] = a[col].map((v) => v / divisor)
    for (let row = 0; row < 4; row++)
      if (row !== col) {
        const multiple = a[row][col]
        a[row] = a[row].map((v, j) => v - multiple * a[col][j])
      }
  }
  return a.map((row) => row.slice(4))
}

/** Exact mapping of canonical imaging_readers/render_series_slice PNGs, including vertical flips. */
export function planeSize(
  axis: IndexPlane,
  dimensions: VoxelPoint,
): [number, number] {
  return axis === "axial"
    ? [dimensions[0], dimensions[1]]
    : axis === "coronal"
      ? [dimensions[0], dimensions[2]]
      : [dimensions[1], dimensions[2]]
}
export function planeIndex(axis: IndexPlane, voxel: VoxelPoint): number {
  return voxel[axis === "axial" ? 2 : axis === "coronal" ? 1 : 0]
}
export function voxelToDisplay(
  axis: IndexPlane,
  voxel: VoxelPoint,
  dimensions: VoxelPoint,
  flipVertical = true,
): [number, number] {
  return axis === "axial"
    ? [voxel[0], voxel[1]]
    : [
        voxel[axis === "coronal" ? 0 : 1],
        flipVertical ? dimensions[2] - 1 - voxel[2] : voxel[2],
      ]
}
export function displayToVoxel(
  axis: IndexPlane,
  u: number,
  v: number,
  selected: VoxelPoint,
  dimensions: VoxelPoint,
  flipVertical = true,
): VoxelPoint {
  const z = flipVertical ? dimensions[2] - 1 - v : v
  const point: VoxelPoint =
    axis === "axial"
      ? [u, v, selected[2]]
      : axis === "coronal"
        ? [u, selected[1], z]
        : [selected[0], u, z]
  return point.map((value, i) =>
    Math.max(0, Math.min(dimensions[i] - 1, Math.round(value))),
  ) as VoxelPoint
}

/** Corners at voxel centre positions; no synthetic anatomical surface is produced. */
export function planeCorners(
  axis: IndexPlane,
  selected: VoxelPoint,
  dimensions: VoxelPoint,
  flipVertical = true,
): VoxelPoint[] {
  const [width, height] = planeSize(axis, dimensions)
  return [
    [0, 0],
    [width - 1, 0],
    [width - 1, height - 1],
    [0, height - 1],
  ].map(([u, v]) =>
    displayToVoxel(axis, u, v, selected, dimensions, flipVertical),
  )
}

export function anatomicalDirection(
  vector: VoxelPoint,
  frame: "RAS_MM" | "LPS_MM" | null,
): string {
  if (!frame) return "Unknown"
  const maximum = Math.max(...vector.map(Math.abs))
  if (maximum < 1e-10) return "Unknown"
  const labels =
    frame === "RAS_MM"
      ? [
          ["L", "R"],
          ["P", "A"],
          ["I", "S"],
        ]
      : [
          ["R", "L"],
          ["A", "P"],
          ["I", "S"],
        ]
  return vector
    .map((v, i) => ({ v, i }))
    .filter(({ v }) => Math.abs(v) / maximum > 0.15)
    .sort((a, b) => Math.abs(b.v) - Math.abs(a.v))
    .map(({ v, i }) => labels[i][v > 0 ? 1 : 0])
    .join("")
}

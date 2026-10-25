/** Decodes a COCO compressed RLE string (column-major runs) into a row-major 0/1 mask. */
export function decodeCocoRle(counts: string, height: number, width: number): Uint8Array {
  const runs: number[] = [];
  let position = 0;
  while (position < counts.length) {
    let value = 0;
    let shift = 0;
    let more = true;
    let chunk = 0;
    while (more) {
      chunk = counts.charCodeAt(position) - 48;
      value |= (chunk & 0x1f) << (5 * shift);
      more = (chunk & 0x20) !== 0;
      position += 1;
      shift += 1;
      if (!more && (chunk & 0x10) !== 0) value |= -1 << (5 * shift);
    }
    if (runs.length > 2) value += runs[runs.length - 2];
    runs.push(value);
  }
  const mask = new Uint8Array(height * width);
  let offset = 0;
  runs.forEach((run, index) => {
    if (index % 2 === 1) {
      for (let k = offset; k < offset + run; k += 1) mask[(k % height) * width + Math.floor(k / height)] = 1;
    }
    offset += run;
  });
  return mask;
}

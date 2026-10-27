import type { MedicalMeasurement } from "../services/api";
import { formatNumber, humanize } from "./format";

/** One row per distinct measurement: reprinted occurrences are folded into their first printing. */
export function distinctMeasurements(measurements: MedicalMeasurement[]): MedicalMeasurement[] {
  return measurements.filter((measurement) => measurement.duplicate_of_measurement_id == null);
}

/** "Also printed on p.4, p.6" for a measurement that appears on several pages or files. */
export function occurrenceNote(measurement: MedicalMeasurement): string | null {
  const others = (measurement.source_occurrences ?? []).filter((item) => item.measurement_id !== measurement.id);
  if (others.length === 0) return null;
  const pages = others.map((item) => (item.source_page ? `p.${item.source_page}` : `file ${item.source_file_id}`));
  return `Also printed on ${pages.join(", ")}; counted once`;
}

/** The value as printed, keeping approximate (~) and censored (<, >) operators visible. */
export function documentedValue(measurement: MedicalMeasurement, digits = 4): string {
  const operator = measurement.result_operator && measurement.result_operator !== "=" ? `${measurement.result_operator} ` : "";
  return `${operator}${formatNumber(measurement.value, digits)} ${measurement.unit}`.trim();
}

/** The interval printed on the report, or why none applies to this patient. Never a catalog range. */
export function intervalText(measurement: MedicalMeasurement): string {
  if (measurement.reference_text && measurement.reference_source === "DOCUMENTED_IN_SOURCE") return measurement.reference_text;
  const options = measurement.reference_options ?? [];
  if (options.length > 0) {
    const printed = options.map((option) => (option.label ? `${option.label}: ${option.text}` : option.text)).join("; ");
    return `Printed: ${printed}. Not applied (${humanize(measurement.reference_selection ?? "indeterminate")})`;
  }
  return measurement.reference_text ?? "Not documented";
}

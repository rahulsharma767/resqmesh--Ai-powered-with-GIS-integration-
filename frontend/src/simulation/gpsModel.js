/**
 * GPS simulation: maintains the distinction between the engine's true
 * ("actual") position -- taken directly off the real road route -- and a
 * noisy "reported" position, the way a real consumer GPS chipset would
 * report a position with some circular error.
 *
 * Quality states and their accuracy bands (radius, meters), per spec:
 *   GOOD      ~ 5-12m
 *   DEGRADED  ~ 25-45m
 *   POOR      ~ 60-90m
 *
 * The noise itself is drawn from the engine's seeded RNG stream, so the
 * exact sequence of "reported" positions is reproducible for a given seed.
 */

export const GPS_QUALITY = {
  GOOD: "GOOD",
  DEGRADED: "DEGRADED",
  POOR: "POOR",
};

export const GPS_ACCURACY_RANGE_M = {
  [GPS_QUALITY.GOOD]: [5, 12],
  [GPS_QUALITY.DEGRADED]: [25, 45],
  [GPS_QUALITY.POOR]: [60, 90],
};

/**
 * Sample one GPS reading for the current quality state.
 * Returns { accuracyM, dxMeters, dyMeters } -- accuracy radius and the
 * (east, north) noise offset to apply to the true position to get the
 * "reported" position.
 */
export function sampleGpsReading(rng, quality) {
  const [lo, hi] = GPS_ACCURACY_RANGE_M[quality] || GPS_ACCURACY_RANGE_M.GOOD;
  const accuracyM = rng.range(lo, hi);
  // 2D gaussian noise whose magnitude is scaled by the accuracy radius, so
  // a POOR fix wanders much further from the true point than a GOOD one.
  const dxMeters = rng.gaussian(0, accuracyM / 2);
  const dyMeters = rng.gaussian(0, accuracyM / 2);
  return { accuracyM, dxMeters, dyMeters };
}

/** Human label + severity tone for the dashboard badge. */
export function gpsQualityMeta(quality) {
  switch (quality) {
    case GPS_QUALITY.POOR:
      return { label: "POOR", tone: "critical" };
    case GPS_QUALITY.DEGRADED:
      return { label: "DEGRADED", tone: "high" };
    default:
      return { label: "GOOD", tone: "low" };
  }
}

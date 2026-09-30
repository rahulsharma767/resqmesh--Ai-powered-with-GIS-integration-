/**
 * Pure geographic helpers used to animate a real vehicle along a real road
 * route returned by the backend's A* router.
 *
 * Route coordinates from the backend are [lon, lat] pairs (GeoJSON order --
 * see person2_backend/backend/app/routing/router.py). We keep that order
 * throughout this module for consistency with the wire format, and only
 * convert to {lat, lon} at the Leaflet boundary (Leaflet wants [lat, lon]).
 */

const EARTH_RADIUS_M = 6371000;

export function haversineMeters([lon1, lat1], [lon2, lat2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const a =
    Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

export function bearingDeg([lon1, lat1], [lon2, lat2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const toDeg = (r) => (r * 180) / Math.PI;
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const dLambda = toRad(lon2 - lon1);
  const y = Math.sin(dLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

/**
 * Precompute cumulative distance (meters) at each vertex of a [lon,lat][]
 * path. path[0] has cumulative distance 0. Used so we can place a vehicle
 * at any "distance traveled so far" in O(log n) via binary search instead
 * of re-walking the whole path every animation frame.
 */
export function cumulativeDistances(path) {
  const cum = [0];
  for (let i = 1; i < path.length; i++) {
    cum.push(cum[i - 1] + haversineMeters(path[i - 1], path[i]));
  }
  return cum;
}

export function pathLengthMeters(cumDistances) {
  return cumDistances.length ? cumDistances[cumDistances.length - 1] : 0;
}

/**
 * Given a path and its precomputed cumulative distances, return the
 * {position:[lon,lat], headingDeg, segmentIndex} for a given distance (m)
 * traveled along the path. Clamps to the ends of the path.
 */
export function pointAtDistance(path, cumDistances, distanceM) {
  if (path.length === 0) return null;
  if (path.length === 1) {
    return { position: path[0], headingDeg: 0, segmentIndex: 0 };
  }
  const total = cumDistances[cumDistances.length - 1];
  const d = Math.max(0, Math.min(distanceM, total));

  // binary search for the segment [i, i+1] containing d
  let lo = 0;
  let hi = cumDistances.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (cumDistances[mid] <= d) lo = mid;
    else hi = mid;
  }
  const segStart = cumDistances[lo];
  const segEnd = cumDistances[hi];
  const segLen = segEnd - segStart || 1;
  const t = (d - segStart) / segLen;
  const [lon1, lat1] = path[lo];
  const [lon2, lat2] = path[hi];
  const position = [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t];
  const headingDeg = bearingDeg(path[lo], path[hi]);
  return { position, headingDeg, segmentIndex: lo };
}

/** Offset a [lon,lat] point by dxMeters (east) / dyMeters (north). Small-scale approx, fine for GPS jitter (<200m). */
export function offsetMeters([lon, lat], dxMeters, dyMeters) {
  const dLat = dyMeters / 111320;
  const dLon = dxMeters / (111320 * Math.cos((lat * Math.PI) / 180));
  return [lon + dLon, lat + dLat];
}

export function toLatLng([lon, lat]) {
  return [lat, lon];
}

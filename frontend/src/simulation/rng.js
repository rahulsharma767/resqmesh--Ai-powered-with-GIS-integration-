/**
 * Seeded, deterministic PRNG (mulberry32) used by the entire simulation
 * engine. Every stochastic element in the simulation -- GPS jitter, traffic
 * micro-variation, tie-break choices -- is derived from ONE seeded stream so
 * that (seed + scenario + config) always reproduces the same event sequence.
 *
 * This is intentionally NOT Math.random(): Math.random() cannot be seeded in
 * the browser, so reproducibility (required by the spec) would be
 * impossible with it.
 */

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class SeededRandom {
  constructor(seed) {
    this.seed = Number(seed) >>> 0;
    this._rng = mulberry32(this.seed);
  }

  /** Reset the stream back to the original seed (used by restart()). */
  reset() {
    this._rng = mulberry32(this.seed);
  }

  /** Uniform float in [0, 1). */
  next() {
    return this._rng();
  }

  /** Uniform float in [min, max). */
  range(min, max) {
    return min + this._rng() * (max - min);
  }

  /** Integer in [min, max] inclusive. */
  int(min, max) {
    return Math.floor(this.range(min, max + 1));
  }

  /** True with probability p (0..1). */
  bool(p = 0.5) {
    return this._rng() < p;
  }

  /** Gaussian sample (Box-Muller) using this stream -- used for GPS jitter. */
  gaussian(mean = 0, stdDev = 1) {
    let u = 0;
    let v = 0;
    while (u === 0) u = this._rng();
    while (v === 0) v = this._rng();
    const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
    return mean + z * stdDev;
  }

  pick(arr) {
    return arr[this.int(0, arr.length - 1)];
  }
}

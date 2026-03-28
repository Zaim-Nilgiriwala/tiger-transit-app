/**
 * Polyline Projection Utilities
 *
 * Pure math functions for projecting GPS positions onto route polylines,
 * interpolating along polyline paths, and computing tangent headings.
 *
 * Used by the animated bus marker system to make buses follow the actual
 * road path between position updates rather than straight-line lerping.
 *
 * All functions operate on Coordinate type ({latitude, longitude}).
 * Uses simple Euclidean math -- adequate for meter-scale campus distances
 * where curvature of the Earth is negligible.
 */
import type { Coordinate } from '../types/gtfs.types';

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Euclidean distance between two coordinates (degrees, not meters -- fine for comparison) */
function dist(a: Coordinate, b: Coordinate): number {
  const dx = a.longitude - b.longitude;
  const dy = a.latitude - b.latitude;
  return Math.sqrt(dx * dx + dy * dy);
}

/** Linear interpolation between two coordinates */
function lerp(a: Coordinate, b: Coordinate, t: number): Coordinate {
  return {
    latitude: a.latitude + (b.latitude - a.latitude) * t,
    longitude: a.longitude + (b.longitude - a.longitude) * t,
  };
}

/**
 * Project a point onto a line segment [segA, segB], returning the clamped
 * parameter t (0-1) and the projected point.
 */
function projectOntoSegment(
  point: Coordinate,
  segA: Coordinate,
  segB: Coordinate
): { t: number; projected: Coordinate; distance: number } {
  const dx = segB.longitude - segA.longitude;
  const dy = segB.latitude - segA.latitude;
  const lenSq = dx * dx + dy * dy;

  let t: number;
  if (lenSq === 0) {
    // Zero-length segment
    t = 0;
  } else {
    t = ((point.longitude - segA.longitude) * dx + (point.latitude - segA.latitude) * dy) / lenSq;
    t = Math.max(0, Math.min(1, t));
  }

  const projected: Coordinate = {
    latitude: segA.latitude + t * dy,
    longitude: segA.longitude + t * dx,
  };

  return { t, projected, distance: dist(point, projected) };
}

// ---------------------------------------------------------------------------
// Exported functions
// ---------------------------------------------------------------------------

export interface ProjectionResult {
  /** Segment index (0-based) where the closest point lies */
  index: number;
  /** Fraction along that segment (0-1) */
  fraction: number;
  /** The projected coordinate on the polyline */
  point: Coordinate;
  /** Distance from input point to the projected point */
  distance: number;
}

/**
 * Find the closest point on a polyline to the given point.
 *
 * Iterates each segment, computes perpendicular projection (clamped to
 * segment endpoints), returns the segment index, fraction along that
 * segment, projected coordinate, and distance from input point.
 */
export function projectOntoPolyline(
  point: Coordinate,
  polyline: Coordinate[]
): ProjectionResult {
  let bestIndex = 0;
  let bestFraction = 0;
  let bestPoint: Coordinate = polyline[0];
  let bestDistance = Infinity;

  for (let i = 0; i < polyline.length - 1; i++) {
    const { t, projected, distance } = projectOntoSegment(point, polyline[i], polyline[i + 1]);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = i;
      bestFraction = t;
      bestPoint = projected;
    }
  }

  return {
    index: bestIndex,
    fraction: bestFraction,
    point: bestPoint,
    distance: bestDistance,
  };
}

/**
 * Interpolate along the polyline path between two positions.
 *
 * Given a start position and end position on the polyline (both as segment
 * index + fraction), linearly interpolate at parameter t (0-1) along the
 * polyline path between them.
 *
 * Walks segments between start and end, accumulating distance, then finds
 * the point at the target distance.
 */
export function interpolateAlongPolyline(
  polyline: Coordinate[],
  fromIndex: number,
  fromFraction: number,
  toIndex: number,
  toFraction: number,
  t: number
): Coordinate {
  // Clamp t
  t = Math.max(0, Math.min(1, t));

  // Start and end points on the polyline
  const startPt = lerp(polyline[fromIndex], polyline[Math.min(fromIndex + 1, polyline.length - 1)], fromFraction);
  const endPt = lerp(polyline[toIndex], polyline[Math.min(toIndex + 1, polyline.length - 1)], toFraction);

  if (t === 0) return startPt;
  if (t === 1) return endPt;

  // Build the sub-path: startPt -> intermediate polyline vertices -> endPt
  const subPath: Coordinate[] = [startPt];

  // Add intermediate vertices between fromIndex+1 and toIndex (inclusive)
  const startSeg = fromIndex + 1;
  const endSeg = toIndex;

  // Handle forward direction (normal case: toIndex >= fromIndex)
  if (toIndex > fromIndex) {
    for (let i = startSeg; i <= endSeg; i++) {
      subPath.push(polyline[i]);
    }
  }
  // If fromIndex == toIndex and fromFraction < toFraction, they're on the same segment
  // No intermediate vertices needed

  subPath.push(endPt);

  // Compute total distance along the sub-path
  let totalDist = 0;
  const segDists: number[] = [];
  for (let i = 0; i < subPath.length - 1; i++) {
    const d = dist(subPath[i], subPath[i + 1]);
    segDists.push(d);
    totalDist += d;
  }

  if (totalDist === 0) return startPt;

  // Find the point at t * totalDist along the sub-path
  const targetDist = t * totalDist;
  let accumulated = 0;

  for (let i = 0; i < segDists.length; i++) {
    if (accumulated + segDists[i] >= targetDist) {
      const segT = (targetDist - accumulated) / segDists[i];
      return lerp(subPath[i], subPath[i + 1], segT);
    }
    accumulated += segDists[i];
  }

  // Floating point edge case: return end point
  return endPt;
}

/**
 * Compute the heading (compass bearing) at a given position on the polyline.
 *
 * Returns heading in degrees (0=north, clockwise) derived from the segment
 * direction vector at polyline[index] to polyline[index+1].
 */
export function tangentAtPoint(
  polyline: Coordinate[],
  index: number,
  _fraction: number
): number {
  // Clamp index to valid range
  const i = Math.min(index, polyline.length - 2);
  if (i < 0) return 0;

  const from = polyline[i];
  const to = polyline[i + 1];

  const dx = to.longitude - from.longitude;
  const dy = to.latitude - from.latitude;

  // atan2 gives angle from positive x-axis (east), counter-clockwise
  // Convert to compass bearing: 0=north, clockwise
  const radians = Math.atan2(dx, dy);
  let degrees = (radians * 180) / Math.PI;
  if (degrees < 0) degrees += 360;

  return degrees;
}

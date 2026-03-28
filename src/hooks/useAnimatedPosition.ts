/**
 * useAnimatedPosition - Playback buffer interpolation hook
 *
 * Animates bus markers smoothly along route polylines between position
 * updates using requestAnimationFrame. The marker follows the actual road
 * path (polyline projection) rather than straight-line lerping.
 *
 * Approach: When a new vehicle position arrives, project it onto the route
 * polyline and animate from the previous projected position to the new one
 * over the real time delta between updates. This creates smooth, physically
 * accurate movement along the road.
 *
 * Falls back to simple linear lerp if no route shape is available.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Coordinate, VehiclePosition } from '../types/gtfs.types';
import {
  projectOntoPolyline,
  interpolateAlongPolyline,
  tangentAtPoint,
} from '../utils/polylineProjection';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PolylinePosition {
  lat: number;
  lon: number;
  timestamp: number;
  shapeIndex: number;
  shapeFraction: number;
}

interface AnimatedResult {
  latitude: number;
  longitude: number;
  heading: number;
  isAnimating: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** If time between updates exceeds this, use fallback 1s animation */
const GAP_THRESHOLD_MS = 30_000;

/** Maximum animation duration to avoid ultra-slow crawls */
const MAX_ANIM_DURATION_MS = 15_000;

/** Minimum animation duration for very fast updates */
const MIN_ANIM_DURATION_MS = 200;

// ---------------------------------------------------------------------------
// Helper: simple bearing between two points
// ---------------------------------------------------------------------------
function bearing(from: { lat: number; lon: number }, to: { lat: number; lon: number }): number {
  const dx = to.lon - from.lon;
  const dy = to.lat - from.lat;
  const radians = Math.atan2(dx, dy);
  let degrees = (radians * 180) / Math.PI;
  if (degrees < 0) degrees += 360;
  return degrees;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAnimatedPosition(
  vehicle: VehiclePosition,
  routeShape: Coordinate[] | undefined,
  visible: boolean,
): AnimatedResult {
  // Refs for animation state (not in React state to avoid re-render per frame)
  const prevPos = useRef<PolylinePosition | null>(null);
  const currPos = useRef<PolylinePosition | null>(null);
  const animStartTime = useRef<number>(0);
  const animDuration = useRef<number>(0);
  const rafId = useRef<number>(0);

  // Track last processed vehicle identity to detect new positions
  const lastVehicleLat = useRef<number>(0);
  const lastVehicleLon = useRef<number>(0);
  const lastVehicleTimestamp = useRef<number>(0);

  // Output state -- only this triggers re-renders
  const [result, setResult] = useState<AnimatedResult>({
    latitude: vehicle.lat,
    longitude: vehicle.lon,
    heading: vehicle.heading,
    isAnimating: false,
  });

  // -------------------------------------------------------------------------
  // Animation frame loop
  // -------------------------------------------------------------------------
  const animate = useCallback(() => {
    const prev = prevPos.current;
    const curr = currPos.current;
    if (!prev || !curr || animDuration.current === 0) return;

    const elapsed = Date.now() - animStartTime.current;
    const t = Math.min(elapsed / animDuration.current, 1);

    let latitude: number;
    let longitude: number;
    let heading: number;

    if (routeShape && routeShape.length >= 2) {
      // Interpolate along polyline path
      const coord = interpolateAlongPolyline(
        routeShape,
        prev.shapeIndex,
        prev.shapeFraction,
        curr.shapeIndex,
        curr.shapeFraction,
        t,
      );
      latitude = coord.latitude;
      longitude = coord.longitude;

      // Derive heading from polyline tangent at current interpolated position
      // Estimate current index/fraction based on lerp between prev and curr indices
      const currentIndex = Math.round(
        prev.shapeIndex + (curr.shapeIndex - prev.shapeIndex) * t,
      );
      const currentFraction =
        prev.shapeIndex === curr.shapeIndex
          ? prev.shapeFraction + (curr.shapeFraction - prev.shapeFraction) * t
          : t < 0.5
            ? prev.shapeFraction
            : curr.shapeFraction;
      heading = tangentAtPoint(routeShape, currentIndex, currentFraction);
    } else {
      // Fallback: simple linear lerp
      latitude = prev.lat + (curr.lat - prev.lat) * t;
      longitude = prev.lon + (curr.lon - prev.lon) * t;
      heading = bearing(prev, curr);
    }

    const isAnimating = t < 1;

    setResult({ latitude, longitude, heading, isAnimating });

    if (isAnimating) {
      rafId.current = requestAnimationFrame(animate);
    }
  }, [routeShape]);

  // -------------------------------------------------------------------------
  // Handle new vehicle position updates
  // -------------------------------------------------------------------------
  useEffect(() => {
    // Detect if position actually changed
    if (
      vehicle.lat === lastVehicleLat.current &&
      vehicle.lon === lastVehicleLon.current &&
      vehicle.timestamp === lastVehicleTimestamp.current
    ) {
      return;
    }

    lastVehicleLat.current = vehicle.lat;
    lastVehicleLon.current = vehicle.lon;
    lastVehicleTimestamp.current = vehicle.timestamp;

    // If not visible, just update position instantly (no animation)
    if (!visible) {
      prevPos.current = null;
      currPos.current = null;
      cancelAnimationFrame(rafId.current);
      setResult({
        latitude: vehicle.lat,
        longitude: vehicle.lon,
        heading: vehicle.heading,
        isAnimating: false,
      });
      return;
    }

    // Project the new position onto the route shape
    let shapeIndex = 0;
    let shapeFraction = 0;

    if (routeShape && routeShape.length >= 2) {
      const projection = projectOntoPolyline(
        { latitude: vehicle.lat, longitude: vehicle.lon },
        routeShape,
      );
      shapeIndex = projection.index;
      shapeFraction = projection.fraction;
    }

    const newPos: PolylinePosition = {
      lat: vehicle.lat,
      lon: vehicle.lon,
      timestamp: vehicle.timestamp,
      shapeIndex,
      shapeFraction,
    };

    if (!prevPos.current) {
      // First appearance: place instantly, no animation
      prevPos.current = newPos;
      currPos.current = newPos;
      animDuration.current = 0;
      setResult({
        latitude: vehicle.lat,
        longitude: vehicle.lon,
        heading: vehicle.heading,
        isAnimating: false,
      });
      return;
    }

    // We have a previous position -- start animation
    const timeDelta = vehicle.timestamp - (currPos.current?.timestamp ?? vehicle.timestamp);

    // Cancel any in-progress animation
    cancelAnimationFrame(rafId.current);

    // Shift prev to where curr was
    prevPos.current = currPos.current;
    currPos.current = newPos;

    if (timeDelta > GAP_THRESHOLD_MS || timeDelta <= 0) {
      // Large gap or backward timestamp: use fallback 1s animation
      animDuration.current = 1000;
    } else {
      animDuration.current = Math.max(
        MIN_ANIM_DURATION_MS,
        Math.min(timeDelta, MAX_ANIM_DURATION_MS),
      );
    }

    animStartTime.current = Date.now();

    // Start animation loop
    setResult((prev) => ({ ...prev, isAnimating: true }));
    rafId.current = requestAnimationFrame(animate);
  }, [vehicle.lat, vehicle.lon, vehicle.timestamp, visible, routeShape, animate]);

  // -------------------------------------------------------------------------
  // Cleanup: cancel animation on unmount or when visibility changes
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!visible) {
      cancelAnimationFrame(rafId.current);
    }

    return () => {
      cancelAnimationFrame(rafId.current);
    };
  }, [visible]);

  return result;
}

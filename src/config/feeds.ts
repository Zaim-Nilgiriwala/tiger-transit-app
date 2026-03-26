/**
 * Feed Configuration
 *
 * Polling and staleness constants for Tiger Transit vehicle data.
 * Feed URLs removed -- data now sourced from Supabase via useVehicleSubscription.
 */

/** Polling interval in milliseconds (5 seconds) -- used by Edge Function poll cadence */
export const POLL_INTERVAL_MS = 5_000;

/** Vehicles older than this are considered stale and filtered out (2 minutes) */
export const STALE_THRESHOLD_MS = 2 * 60 * 1_000;

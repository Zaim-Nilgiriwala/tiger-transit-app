/**
 * GTFS-RT Feed Configuration
 *
 * Feed URLs and polling constants for Tiger Transit's ETASpot GTFS-RT feeds.
 * Position and trip update feeds are hosted on S3 as protobuf binary files.
 */

/** Vehicle position updates feed (protobuf binary) */
export const POSITION_FEED_URL =
  'https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb';

/** Trip updates feed with ETAs and delays (protobuf binary) */
export const TRIP_UPDATES_FEED_URL =
  'https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb';

/** Polling interval in milliseconds (5 seconds) */
export const POLL_INTERVAL_MS = 5_000;

/** Vehicles older than this are considered stale and filtered out (2 minutes) */
export const STALE_THRESHOLD_MS = 2 * 60 * 1_000;

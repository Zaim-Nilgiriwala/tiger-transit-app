/**
 * GTFS-RT Protobuf Decode Service
 *
 * Fetches and decodes GTFS-RT position and trip update feeds from ETASpot S3.
 * Trip updates are processed FIRST so ETA enrichment data is available when
 * mapping position updates to VehiclePosition objects.
 *
 * Uses protobufjs with Root.fromJSON() for Hermes-safe protobuf decoding
 * (no eval(), no dynamic code generation).
 */
import * as protobuf from 'protobufjs';
import { VehiclePosition } from '../types/gtfs.types';
import {
  POSITION_FEED_URL,
  TRIP_UPDATES_FEED_URL,
  STALE_THRESHOLD_MS,
} from '../config/feeds';

// ---------------------------------------------------------------------------
// Embedded GTFS-RT proto descriptor (minimal subset needed for decoding)
// ---------------------------------------------------------------------------
const gtfsRealtimeDescriptor: protobuf.INamespace = {
  nested: {
    transit_realtime: {
      nested: {
        FeedMessage: {
          fields: {
            header: { type: 'FeedHeader', id: 1 },
            entity: { rule: 'repeated', type: 'FeedEntity', id: 2 },
          },
        },
        FeedHeader: {
          fields: {
            gtfsRealtimeVersion: { type: 'string', id: 1 },
            timestamp: { type: 'uint64', id: 4 },
          },
        },
        FeedEntity: {
          fields: {
            id: { type: 'string', id: 1 },
            vehicle: { type: 'VehiclePosition', id: 4 },
            tripUpdate: { type: 'TripUpdate', id: 3 },
          },
        },
        VehiclePosition: {
          fields: {
            trip: { type: 'TripDescriptor', id: 1 },
            vehicle: { type: 'VehicleDescriptor', id: 8 },
            position: { type: 'Position', id: 2 },
            timestamp: { type: 'uint64', id: 5 },
            stopId: { type: 'string', id: 7 },
            currentStatus: { type: 'VehicleStopStatus', id: 4 },
          },
        },
        VehicleDescriptor: {
          fields: {
            id: { type: 'string', id: 1 },
            label: { type: 'string', id: 2 },
          },
        },
        Position: {
          fields: {
            latitude: { type: 'float', id: 1 },
            longitude: { type: 'float', id: 2 },
            bearing: { type: 'float', id: 3 },
            speed: { type: 'float', id: 4 },
          },
        },
        TripDescriptor: {
          fields: {
            tripId: { type: 'string', id: 1 },
            routeId: { type: 'string', id: 5 },
            startDate: { type: 'string', id: 3 },
            startTime: { type: 'string', id: 2 },
            scheduleRelationship: { type: 'ScheduleRelationship', id: 4 },
          },
          nested: {
            ScheduleRelationship: {
              values: {
                SCHEDULED: 0,
                ADDED: 1,
                UNSCHEDULED: 2,
                CANCELED: 3,
              },
            },
          },
        },
        TripUpdate: {
          fields: {
            trip: { type: 'TripDescriptor', id: 1 },
            stopTimeUpdate: {
              rule: 'repeated',
              type: 'StopTimeUpdate',
              id: 2,
            },
            delay: { type: 'int32', id: 5 },
            timestamp: { type: 'uint64', id: 4 },
          },
        },
        StopTimeUpdate: {
          fields: {
            stopSequence: { type: 'uint32', id: 1 },
            stopId: { type: 'string', id: 4 },
            arrival: { type: 'StopTimeEvent', id: 2 },
            departure: { type: 'StopTimeEvent', id: 3 },
            scheduleRelationship: {
              type: 'ScheduleRelationship',
              id: 5,
            },
          },
          nested: {
            ScheduleRelationship: {
              values: {
                SCHEDULED: 0,
                SKIPPED: 1,
                NO_DATA: 2,
              },
            },
          },
        },
        StopTimeEvent: {
          fields: {
            delay: { type: 'int32', id: 1 },
            time: { type: 'int64', id: 2 },
            uncertainty: { type: 'int32', id: 3 },
          },
        },
        VehicleStopStatus: {
          values: {
            INCOMING_AT: 0,
            STOPPED_AT: 1,
            IN_TRANSIT_TO: 2,
          },
        },
      },
    },
  },
};

// Build the protobuf root and look up FeedMessage once at module load
const root = protobuf.Root.fromJSON(gtfsRealtimeDescriptor);
const FeedMessage = root.lookupType('transit_realtime.FeedMessage');

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------
interface TripEta {
  nextStopId: string;
  etaSeconds: number;
  delay: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DecodedFeed = any;

// ---------------------------------------------------------------------------
// Feed fetching
// ---------------------------------------------------------------------------
async function fetchFeed(url: string): Promise<DecodedFeed> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `Feed fetch failed: ${res.status} ${res.statusText} for ${url}`,
    );
  }
  const buffer = await res.arrayBuffer();
  return FeedMessage.decode(new Uint8Array(buffer));
}

// ---------------------------------------------------------------------------
// Trip update processing (run FIRST so ETAs are available for positions)
// ---------------------------------------------------------------------------
function processTripUpdates(feed: DecodedFeed): Map<string, TripEta> {
  const tripEtas = new Map<string, TripEta>();
  const now = Math.floor(Date.now() / 1000);

  for (const entity of feed.entity ?? []) {
    const tu = entity.tripUpdate;
    if (!tu) continue;

    const tripId: string | undefined = tu.trip?.tripId;
    if (!tripId) continue;

    // Find the first upcoming stop time update with an arrival time in the future
    let nextStop: { stopId: string; eta: number } | null = null;
    for (const stu of tu.stopTimeUpdate ?? []) {
      const arrivalTime = stu.arrival?.time;
      const arrivalSec = arrivalTime ? Number(arrivalTime) : 0;
      if (arrivalSec > now && stu.stopId) {
        nextStop = {
          stopId: stu.stopId,
          eta: arrivalSec - now,
        };
        break;
      }
    }

    tripEtas.set(tripId, {
      nextStopId: nextStop?.stopId ?? '',
      etaSeconds: nextStop?.eta ?? 0,
      delay: Number(tu.delay) || 0,
    });
  }

  return tripEtas;
}

// ---------------------------------------------------------------------------
// Position update processing (enriched with trip ETAs)
// ---------------------------------------------------------------------------
function processPositionUpdates(
  feed: DecodedFeed,
  tripEtas: Map<string, TripEta>,
): VehiclePosition[] {
  const vehicles: VehiclePosition[] = [];
  const now = Date.now();

  for (const entity of feed.entity ?? []) {
    const vp = entity.vehicle;
    if (!vp?.position) continue;

    const vehicleId: string = vp.vehicle?.id || entity.id || '';
    const routeId: string = vp.trip?.routeId;
    if (!routeId) continue;

    const pos = vp.position;
    if (!pos.latitude || !pos.longitude) continue;

    const tripId: string = vp.trip?.tripId || '';
    const tripEta = tripEtas.get(tripId);

    const timestamp = vp.timestamp
      ? Number(vp.timestamp) * 1000
      : now;

    // Stale filter: skip vehicles older than STALE_THRESHOLD_MS
    if (now - timestamp > STALE_THRESHOLD_MS) continue;

    vehicles.push({
      vehicleId,
      routeId,
      lat: pos.latitude,
      lon: pos.longitude,
      heading: pos.bearing || 0,
      speed: pos.speed || 0,
      load: 0,
      capacity: 0,
      nextStopId: vp.stopId || tripEta?.nextStopId || '',
      etaSeconds: tripEta?.etaSeconds || 0,
      onTime: tripEta ? (tripEta.delay <= 0 ? 1 : 0) : 0,
      lastStopId: '',
      isDelayed: (tripEta?.delay || 0) > 300,
      timestamp,
    });
  }

  return vehicles;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Fetch and decode both GTFS-RT feeds, returning enriched VehiclePosition[].
 *
 * 1. Fetches position and trip update feeds in parallel
 * 2. Processes trip updates FIRST (builds tripId -> TripEta map)
 * 3. Processes position updates, enriching with trip ETA data
 * 4. Filters out stale vehicles (timestamp > 2 minutes old)
 *
 * Throws on fetch failure -- callers should handle retry logic.
 */
export async function fetchAndDecodeFeeds(): Promise<VehiclePosition[]> {
  const [positionFeed, tripFeed] = await Promise.all([
    fetchFeed(POSITION_FEED_URL),
    fetchFeed(TRIP_UPDATES_FEED_URL),
  ]);

  // Process trip updates FIRST so ETAs are available for position enrichment
  const tripEtas = processTripUpdates(tripFeed);

  // Process position updates with trip ETA enrichment and stale filtering
  return processPositionUpdates(positionFeed, tripEtas);
}

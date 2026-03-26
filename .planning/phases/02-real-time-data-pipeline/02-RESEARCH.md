# Phase 2: Real-Time Data Pipeline (REWORK) - Research

**Researched:** 2026-03-26
**Domain:** Supabase Realtime + Edge Functions, ETASpot PHP API integration, React Native data subscriptions
**Confidence:** HIGH

## Summary

This phase replaces the client-side GTFS-RT protobuf polling pipeline with a server-side ETASpot PHP API poller (Supabase Edge Function triggered by pg_cron) that writes to a Supabase `vehicles` table, which the React Native client subscribes to via Supabase Realtime WebSocket. The existing `vehiclesSlice` Redux store, `BusMarker` component, and all UI consumers remain unchanged -- only the data source layer (service + hook) is swapped.

The project already has a `supabase/` directory with CLI config (Deno 2 edge runtime, Postgres 17, realtime enabled), existing migrations for `position_updates` and `gtfs` schemas, and the `supabase` directory is already excluded from `tsconfig.json`. The ETASpot PHP API has been verified live and returns JSON with all needed fields (lat, lng, h, routeID, equipmentID, receiveTime, load, capacity, nextStopID, lastStopID, minutesToNextStops, onSchedule, direction).

**Primary recommendation:** Use pg_cron (5-second interval) triggering an Edge Function via pg_net HTTP POST. The Edge Function fetches ETASpot PHP, transforms data, and upserts into a `vehicles` table in the `public` schema. Client subscribes via Supabase Realtime `postgres_changes` on the `vehicles` table, dispatching to the existing `vehiclesSlice`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Primary source: ETASpot PHP API `get_vehicles` endpoint (`auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING`)
- PHP provides: lat, lng, heading (`h`), load, capacity, onSchedule (delay seconds), receiveTime, nextStopID, lastStopID, routeID, equipmentID, direction
- ETASpot's `minutesToNextStops` ETAs are NOT used -- all ETAs will come from the XGBoost model (future phase). PHP ETAs are garbage.
- Route ID mapping needed for 3 compound IDs: 215->215_202_201_156, 226->226_32, 235->235_93
- Speed/velocity is NOT in the PHP response -- must be derived from position history
- Supabase Realtime WebSocket subscription -- client subscribes to `vehicles` table changes, no client-side polling loop
- Singleton `supabaseClient.ts` initializes the Supabase client (reads URL + anon key from environment variables, `.env` filled in later)
- `useVehicleSubscription` hook subscribes to Realtime and dispatches to Redux `vehiclesSlice` -- follows the same pattern as the existing `useGtfsPolling` hook it replaces
- Supabase credentials via environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- Polls ETASpot PHP API every 5s, transforms and writes to Supabase `vehicles` table
- Position deduplication: compare new lat/lng/heading with previous -- skip write if identical (no bus movement)
- Position history: append each new (non-duplicate) position to a `position_history` table for future speed derivation and model training data
- Auto-cleanup of old history rows (configurable retention)
- Route ID mapping happens in the proxy (215->215_202_201_156, etc.) so frontend sees consistent GTFS route IDs
- On every new (non-duplicate) position write, the proxy has a hook point to call the FastAPI model (no-op for now)
- Proxy transforms PHP fields to match existing `VehiclePosition` type
- Zero frontend component changes needed -- BusMarker, RouteDetailView, RouteOverlay, RouteList all continue reading from `vehiclesSlice` unchanged
- Fields not available from PHP: `speed` (0 until derived from history), `etaSeconds` (0 until model is trained)
- Archive existing protobuf code to `src/archived/` directory, not deleted
- Replace `useGtfsPolling()` call in MapScreen with `useVehicleSubscription()`
- Stale vehicle filtering (>2 min) handled by proxy (uses `receiveTime` from PHP)
- `inService=1` parameter on PHP endpoint pre-filters vehicles

### Claude's Discretion
- Supabase table schema design (vehicles, position_history, predictions)
- Worker implementation approach (Edge Function vs standalone script vs pg_cron)
- Realtime subscription channel configuration
- Position history auto-cleanup strategy (time-based TTL vs row count)
- How to handle proxy errors (ETASpot down, Supabase write failure)

### Deferred Ideas (OUT OF SCOPE)
- XGBoost model training and deployment -- separate workstream
- Speed derivation from position history -- computed in Supabase when model needs it
- Service alerts from GTFS-RT protobuf alerts feed -- Phase 6
- `get_stop_etas` endpoint for Stop Detail View arrival board -- Phase 6
- `get_routes` / `get_stops` / `get_patterns` as alternative to bundled GTFS static data -- evaluate later
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-01 | Backend proxy polls ETASpot PHP API every 5s and writes to Supabase; client reads from Supabase | Edge Function + pg_cron architecture, Realtime subscription pattern |
| DATA-02 | Vehicle positions update every 5 seconds while app is in foreground via Supabase Realtime | `postgres_changes` subscription with AppState lifecycle management |
| DATA-03 | Polling stops when app is backgrounded and resumes immediately on foreground | Channel removeChannel/resubscribe on AppState change; same pattern as existing useGtfsPolling |
| DATA-04 | Multi-stop ETAs from PHP `minutesToNextStops` available in Redux | CONTEXT says ETAs are NOT used (garbage). Store raw `minutesToNextStops` JSON for future reference only; `etaSeconds` stays 0 |
| DATA-05 | GTFS static data loads on app launch | Already complete -- no changes needed |
| DATA-06 | Supabase backend proxy handles ETASpot route ID mapping | Route ID map constant in Edge Function: `{215: '215_202_201_156', 226: '226_32', 235: '235_93'}` |
| DATA-07 | Vehicle speed derived from consecutive position history | Position history table created with schema; speed derivation deferred (returns 0 for now) |
| MAP-02 | Live bus markers on map with positions updated every 5s | Supabase Realtime delivers updates; existing BusMarker renders from vehiclesSlice unchanged |
| MAP-04 | Bus markers display directional heading and route-colored markers | PHP `h` field maps to `heading`; BusMarker already implements directional rotation |
| MAP-09 | Vehicles with timestamps older than 2 minutes are hidden | Proxy filters on `receiveTime`; client can also filter as safety net |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @supabase/supabase-js | ^2.100 | Supabase client (Realtime, DB queries) | Official Supabase SDK, includes Realtime subscription support |
| react-native-url-polyfill | latest | URL parsing polyfill for React Native | Required by @supabase/supabase-js in RN environment |

### Supporting (already installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @reduxjs/toolkit | ^2.6.1 | State management | vehiclesSlice already exists and is reused |
| react-redux | ^9.2.0 | React bindings for Redux | useAppSelector/useAppDispatch hooks |

### Backend (Supabase Edge Functions -- Deno runtime, no npm install)
| Import | Purpose | How Used |
|--------|---------|----------|
| @supabase/supabase-js (npm: specifier) | DB client inside Edge Function | `import { createClient } from 'npm:@supabase/supabase-js@2'` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Supabase Realtime | Client-side polling (setInterval + supabase.from().select()) | Simpler but wastes bandwidth; Realtime gives push-based updates with less latency |
| pg_cron + Edge Function | Standalone Node.js worker process | Node worker needs separate hosting; pg_cron is built into Supabase |
| pg_cron + Edge Function | pg_cron calling a SQL function directly | SQL function cannot call external HTTP APIs (ETASpot); need pg_net or Edge Function |

**Installation (client-side only):**
```bash
npx expo install @supabase/supabase-js react-native-url-polyfill
```

Note: `expo-sqlite` is NOT needed -- we are not using Supabase Auth (no session persistence required). The official quickstart includes it for auth session storage, but this project has no auth.

## Architecture Patterns

### Recommended Project Structure
```
src/
  config/
    supabase.ts          # Supabase client singleton (NEW)
    feeds.ts             # Kept for STALE_THRESHOLD_MS constant
  hooks/
    useVehicleSubscription.ts  # Realtime subscription hook (NEW, replaces useGtfsPolling)
    useGtfsPolling.ts          # ARCHIVED (moved to src/archived/)
  services/
    gtfsRealtimeService.ts     # ARCHIVED (moved to src/archived/)
  archived/
    useGtfsPolling.ts          # Preserved protobuf polling hook
    gtfsRealtimeService.ts     # Preserved protobuf decode service
    feeds.ts                   # Preserved S3 feed URLs (keep copy; original stays for STALE_THRESHOLD_MS)
    tripRoutes.ts              # Preserved trip-to-route mapping (no longer needed with PHP routeID)
  store/slices/
    vehiclesSlice.ts           # UNCHANGED -- same actions, same shape

supabase/
  functions/
    poll-vehicles/
      index.ts                 # Edge Function: fetch ETASpot, transform, upsert (NEW)
  migrations/
    YYYYMMDD_create_vehicles_table.sql     # vehicles table (NEW)
    YYYYMMDD_create_position_history.sql   # position_history table (NEW)
    YYYYMMDD_setup_cron_polling.sql        # pg_cron + pg_net schedule (NEW)
```

### Pattern 1: Supabase Client Singleton
**What:** Single shared Supabase client instance for the entire app
**When to use:** Always -- avoid creating multiple clients (each opens its own WebSocket)
**Example:**
```typescript
// src/config/supabase.ts
// Source: https://supabase.com/docs/guides/getting-started/quickstarts/expo-react-native
import 'react-native-url-polyfill/auto';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  // No auth config needed -- this project has no user authentication
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});
```

### Pattern 2: Realtime Subscription Hook with AppState
**What:** Hook that subscribes to Supabase Realtime `postgres_changes`, manages lifecycle with AppState
**When to use:** In MapScreen, replacing `useGtfsPolling()`
**Example:**
```typescript
// src/hooks/useVehicleSubscription.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { RealtimeChannel } from '@supabase/supabase-js';
import { supabase } from '../config/supabase';
import { useAppDispatch } from '../store';
import { setPositions, setConnected } from '../store/slices/vehiclesSlice';
import { VehiclePosition } from '../types/gtfs.types';
import { STALE_THRESHOLD_MS } from '../config/feeds';

export function useVehicleSubscription() {
  const dispatch = useAppDispatch();
  const channelRef = useRef<RealtimeChannel | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // Fetch current snapshot from vehicles table
  const fetchSnapshot = useCallback(async () => {
    const { data, error } = await supabase
      .from('vehicles')
      .select('*');
    if (!error && data) {
      const now = Date.now();
      const positions: VehiclePosition[] = data
        .filter((v) => now - v.timestamp < STALE_THRESHOLD_MS)
        .map(mapRowToVehiclePosition);
      dispatch(setPositions(positions));
      dispatch(setConnected(true));
      setIsConnected(true);
    }
  }, [dispatch]);

  // Subscribe to realtime changes
  const subscribe = useCallback(() => {
    // Always fetch snapshot first (covers any missed updates)
    fetchSnapshot();

    const channel = supabase
      .channel('vehicles-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'vehicles' },
        () => {
          // On any change, re-fetch full snapshot
          // This is simpler than merging individual INSERT/UPDATE/DELETE
          fetchSnapshot();
        }
      )
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          dispatch(setConnected(true));
          setIsConnected(true);
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          dispatch(setConnected(false));
          setIsConnected(false);
        }
      });

    channelRef.current = channel;
  }, [dispatch, fetchSnapshot]);

  // Unsubscribe
  const unsubscribe = useCallback(() => {
    if (channelRef.current) {
      supabase.removeChannel(channelRef.current);
      channelRef.current = null;
    }
  }, []);

  useEffect(() => {
    subscribe();

    const handleAppState = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        subscribe();
      } else {
        unsubscribe();
      }
    };

    const sub = AppState.addEventListener('change', handleAppState);

    return () => {
      unsubscribe();
      sub.remove();
    };
  }, [subscribe, unsubscribe]);

  return { isConnected };
}
```

### Pattern 3: Edge Function Polling Worker (Deno)
**What:** Supabase Edge Function triggered by pg_cron every 5 seconds to poll ETASpot
**When to use:** Server-side data ingestion
**Example:**
```typescript
// supabase/functions/poll-vehicles/index.ts
import { createClient } from 'npm:@supabase/supabase-js@2';

const ETASPOT_URL = 'https://auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING';

// Route ID mapping: ETASpot numeric -> GTFS compound IDs
const ROUTE_ID_MAP: Record<number, string> = {
  215: '215_202_201_156',
  226: '226_32',
  235: '235_93',
};

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
);

Deno.serve(async (_req) => {
  const res = await fetch(ETASPOT_URL);
  const json = await res.json();
  const vehicles = json.get_vehicles || [];

  const now = Date.now();
  const STALE_MS = 2 * 60 * 1000;

  // Transform and filter
  const rows = vehicles
    .filter((v: any) => v.inService === 1 && (now - v.receiveTime) < STALE_MS)
    .map((v: any) => {
      const routeId = ROUTE_ID_MAP[v.routeID] || String(v.routeID);
      return {
        vehicle_id: String(v.equipmentID),
        route_id: routeId,
        lat: v.lat,
        lon: v.lng,
        heading: v.h || 0,
        speed: 0, // Not available from PHP; derived from history later
        load: v.load || 0,
        capacity: v.capacity || 0,
        next_stop_id: String(v.nextStopID || ''),
        last_stop_id: String(v.lastStopID || ''),
        eta_seconds: 0, // ETAs are garbage per user decision
        on_time: v.onSchedule <= 0 ? 1 : 0,
        is_delayed: (v.onSchedule || 0) > 300,
        timestamp: v.receiveTime,
        direction: v.direction || '',
        raw_minutes_to_next_stops: JSON.stringify(v.minutesToNextStops || []),
        updated_at: new Date().toISOString(),
      };
    });

  // Upsert all vehicles (keyed on vehicle_id)
  const { error } = await supabase
    .from('vehicles')
    .upsert(rows, { onConflict: 'vehicle_id' });

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  // TODO: Position history append + deduplication (compare with previous)
  // TODO: Hook point for FastAPI model call (no-op for now)

  return new Response(JSON.stringify({ ok: true, count: rows.length }), { status: 200 });
});
```

### Pattern 4: pg_cron + pg_net Scheduling
**What:** Postgres-level scheduling that triggers the Edge Function every 5 seconds
**When to use:** To create the 5-second polling loop without a long-running process
**Example:**
```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Store secrets in vault (production)
-- SELECT vault.create_secret('https://YOUR_PROJECT.supabase.co', 'project_url');
-- SELECT vault.create_secret('YOUR_SERVICE_ROLE_KEY', 'service_role_key');

-- Create the trigger function
CREATE OR REPLACE FUNCTION invoke_poll_vehicles()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  project_url TEXT;
  service_key TEXT;
BEGIN
  -- Read from vault in production; for local dev, use hardcoded values
  SELECT decrypted_secret INTO project_url FROM vault.decrypted_secrets WHERE name = 'project_url';
  SELECT decrypted_secret INTO service_key FROM vault.decrypted_secrets WHERE name = 'service_role_key';

  PERFORM net.http_post(
    url := project_url || '/functions/v1/poll-vehicles',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || service_key,
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  );
END;
$$;

-- Schedule every 5 seconds
SELECT cron.schedule('poll-vehicles', '5 seconds', 'SELECT invoke_poll_vehicles()');
```

### Anti-Patterns to Avoid
- **Long-running Edge Function loop:** Edge Functions have a 150s (free) / 400s (paid) wall clock limit. Never use `setInterval` inside an Edge Function -- use pg_cron to trigger it externally.
- **Multiple Supabase client instances:** Each `createClient()` opens a new WebSocket. Create ONE singleton and import it everywhere.
- **Merging individual Realtime events into state:** The `postgres_changes` payload only contains the changed row, not all vehicles. Trying to merge individual INSERT/UPDATE/DELETE events is error-prone (race conditions, missed deletes). Instead, re-fetch the full `vehicles` table on each change notification.
- **Client-side polling as primary:** Do NOT use `setInterval` + `supabase.from('vehicles').select()` as the primary update mechanism. Realtime is more efficient and lower latency.
- **Storing ETASpot's `minutesToNextStops` ETAs in `etaSeconds`:** The user explicitly said PHP ETAs are garbage. Store them as raw JSON for reference but set `etaSeconds` to 0.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 5-second server polling | Custom Node.js worker with hosting | pg_cron + pg_net + Edge Function | Built into Supabase, no separate infrastructure |
| Real-time push to clients | WebSocket server | Supabase Realtime (postgres_changes) | Managed, auto-reconnects, works with RLS |
| Database upsert with conflict handling | Manual INSERT + ON CONFLICT SQL | `supabase.from().upsert({ onConflict })` | Handles batching, typing, error handling |
| URL polyfill for React Native | Custom URL shim | react-native-url-polyfill | Battle-tested, required by Supabase SDK |
| Environment variable access | Custom config loader | `process.env.EXPO_PUBLIC_*` | Expo's built-in convention, works with .env files |

**Key insight:** The entire backend polling infrastructure is built from Supabase primitives (pg_cron, pg_net, Edge Functions, Realtime). No external servers, no hosting decisions, no deployment pipelines beyond `supabase functions deploy`.

## Common Pitfalls

### Pitfall 1: Supabase Realtime Not Receiving Changes
**What goes wrong:** Client subscribes to `postgres_changes` but never receives updates
**Why it happens:** The table is not added to the `supabase_realtime` publication, or RLS blocks the anon key from reading
**How to avoid:** Migration MUST include:
```sql
ALTER PUBLICATION supabase_realtime ADD TABLE vehicles;
ALTER TABLE vehicles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anonymous read" ON vehicles FOR SELECT TO anon USING (true);
```
**Warning signs:** Subscribe callback fires with `SUBSCRIBED` status but no change events arrive

### Pitfall 2: Edge Function Cold Start Delays
**What goes wrong:** First invocation after idle period takes 1-3 seconds extra
**Why it happens:** Deno edge runtime boots a new isolate
**How to avoid:** Not avoidable, but irrelevant for this use case -- pg_cron fires every 5 seconds, keeping the function warm. If the function occasionally takes 6-7 seconds instead of 1-2, the next cron tick is already queued.
**Warning signs:** Occasional gaps in position updates >5 seconds; normal and expected

### Pitfall 3: pg_cron Sub-Minute Scheduling Requires Postgres >= 15.1.1.61
**What goes wrong:** `'5 seconds'` cron expression fails or is ignored
**Why it happens:** Sub-minute scheduling was added in pg_cron for newer Postgres versions
**How to avoid:** The project uses Postgres 17 (confirmed in `config.toml`), which supports sub-second scheduling. Verify on deployed Supabase project as well.
**Warning signs:** Cron job appears scheduled but never fires at the expected rate

### Pitfall 4: Realtime Silent Disconnection on Background
**What goes wrong:** After returning from background, Realtime channel is stuck in CLOSED/TIMED_OUT state
**Why it happens:** Mobile OS kills WebSocket connections when app is backgrounded. Supabase Realtime auto-reconnects but can get stuck.
**How to avoid:** On AppState `active`, always `removeChannel` the old channel and create a fresh subscription. Also fetch a full snapshot immediately on foreground resume to catch any missed updates.
**Warning signs:** `connected` state stays false after returning to foreground; positions freeze

### Pitfall 5: EXPO_PUBLIC_ Prefix Required for Env Vars
**What goes wrong:** `process.env.SUPABASE_URL` returns `undefined`
**Why it happens:** Expo only exposes env vars with the `EXPO_PUBLIC_` prefix to client code
**How to avoid:** Name variables `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_ANON_KEY` in `.env`
**Warning signs:** Supabase client creation fails silently or throws on first query

### Pitfall 6: Vehicles Table in Wrong Schema
**What goes wrong:** Realtime subscription doesn't fire, or queries return empty
**Why it happens:** Existing migrations use custom schemas (`position_updates`, `gtfs`). Supabase Realtime only listens to the `public` schema by default.
**How to avoid:** Create the `vehicles` table in the `public` schema. If needed later, the publication can be configured for other schemas, but `public` is the path of least resistance.
**Warning signs:** Edge Function writes succeed but client sees no updates

### Pitfall 7: Race Condition Between Snapshot Fetch and Realtime
**What goes wrong:** Initial `fetchSnapshot()` returns stale data, then a Realtime event arrives before the snapshot response
**Why it happens:** Subscribe and fetch happen asynchronously
**How to avoid:** The "re-fetch on every change" pattern avoids this entirely -- every Realtime notification triggers a fresh full read, so the latest state always wins.

## Code Examples

### ETASpot PHP API Response (Verified Live)
```json
{
  "get_vehicles": [
    {
      "routeID": 232,
      "patternID": 27192,
      "equipmentID": "jAUnt 2",
      "tripID": "5629",
      "lat": 32.60043,
      "lng": -85.48868,
      "load": 0,
      "capacity": 25,
      "h": 103,
      "onSchedule": -612,
      "receiveTime": 1774561645000,
      "nextStopID": 274,
      "lastStopID": 275,
      "direction": "Outbound",
      "directionAbbr": "O",
      "inService": 1,
      "minutesToNextStops": [
        {
          "stopID": 274,
          "minutes": 48,
          "time": "06:29PM",
          "status": "06:29PM",
          "statuscolor": "#B91D1D"
        }
      ]
    }
  ]
}
```

### Vehicles Table Schema (Recommended)
```sql
-- public.vehicles -- current state of each active vehicle
CREATE TABLE public.vehicles (
  vehicle_id TEXT PRIMARY KEY,            -- equipmentID from PHP
  route_id TEXT NOT NULL,                 -- GTFS compound route ID (after mapping)
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  heading REAL NOT NULL DEFAULT 0,        -- degrees, from PHP 'h'
  speed REAL NOT NULL DEFAULT 0,          -- 0 until derived from history
  load INTEGER NOT NULL DEFAULT 0,
  capacity INTEGER NOT NULL DEFAULT 0,
  next_stop_id TEXT NOT NULL DEFAULT '',
  last_stop_id TEXT NOT NULL DEFAULT '',
  eta_seconds INTEGER NOT NULL DEFAULT 0, -- 0 until model trained
  on_time SMALLINT NOT NULL DEFAULT 0,    -- 1 = on time, 0 = not
  is_delayed BOOLEAN NOT NULL DEFAULT false,
  timestamp BIGINT NOT NULL,              -- receiveTime ms from PHP
  direction TEXT NOT NULL DEFAULT '',
  raw_minutes_to_next_stops JSONB DEFAULT '[]'::jsonb,  -- raw PHP ETAs for reference
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.vehicles;

-- RLS for anonymous read access
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_vehicles" ON public.vehicles
  FOR SELECT TO anon USING (true);

-- Index for route-based queries
CREATE INDEX idx_vehicles_route_id ON public.vehicles(route_id);
```

### Position History Table Schema (Recommended)
```sql
-- public.position_history -- append-only log for speed derivation and model training
CREATE TABLE public.position_history (
  id BIGSERIAL PRIMARY KEY,
  vehicle_id TEXT NOT NULL,
  route_id TEXT NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  heading REAL NOT NULL DEFAULT 0,
  timestamp BIGINT NOT NULL,              -- receiveTime ms
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for vehicle lookups and time-based cleanup
CREATE INDEX idx_pos_history_vehicle_time ON public.position_history(vehicle_id, timestamp DESC);
CREATE INDEX idx_pos_history_recorded_at ON public.position_history(recorded_at);

-- No RLS needed -- this table is only written by the Edge Function (service_role key)
-- and read by server-side processes for speed derivation
```

### Data Mapping (PHP -> VehiclePosition Redux Type)
```typescript
// Maps a Supabase vehicles row to the existing VehiclePosition type
function mapRowToVehiclePosition(row: any): VehiclePosition {
  return {
    vehicleId: row.vehicle_id,
    routeId: row.route_id,
    lat: row.lat,
    lon: row.lon,
    heading: row.heading,
    speed: row.speed,
    load: row.load,
    capacity: row.capacity,
    nextStopId: row.next_stop_id,
    etaSeconds: row.eta_seconds,
    onTime: row.on_time,
    lastStopId: row.last_stop_id,
    isDelayed: row.is_delayed,
    timestamp: row.timestamp,
  };
}
```

### Environment Variables (.env)
```bash
# Client-side (must use EXPO_PUBLIC_ prefix)
EXPO_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321  # Local dev
EXPO_PUBLIC_SUPABASE_ANON_KEY=your-local-anon-key

# Edge Function secrets (set via Supabase CLI or dashboard, NOT in .env)
# SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are auto-injected by Supabase runtime
```

### Position Deduplication in Edge Function
```typescript
// Fetch previous positions for comparison
const { data: prevVehicles } = await supabase
  .from('vehicles')
  .select('vehicle_id, lat, lon, heading');

const prevMap = new Map(
  (prevVehicles || []).map((v) => [v.vehicle_id, v])
);

// Filter to only vehicles with changed positions
const changedRows = rows.filter((row) => {
  const prev = prevMap.get(row.vehicle_id);
  if (!prev) return true; // New vehicle
  return (
    prev.lat !== row.lat ||
    prev.lon !== row.lon ||
    prev.heading !== row.heading
  );
});

// Only upsert changed vehicles
if (changedRows.length > 0) {
  await supabase.from('vehicles').upsert(changedRows, { onConflict: 'vehicle_id' });

  // Append changed positions to history
  const historyRows = changedRows.map((r) => ({
    vehicle_id: r.vehicle_id,
    route_id: r.route_id,
    lat: r.lat,
    lon: r.lon,
    heading: r.heading,
    timestamp: r.timestamp,
  }));
  await supabase.from('position_history').insert(historyRows);
}
```

### Auto-Cleanup of Position History
```sql
-- pg_cron job: delete position_history older than 7 days, runs daily
SELECT cron.schedule(
  'cleanup-position-history',
  '0 3 * * *',  -- 3 AM daily
  $$DELETE FROM public.position_history WHERE recorded_at < NOW() - INTERVAL '7 days'$$
);
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Client-side GTFS-RT protobuf decode | Server-side PHP API polling via Supabase | Project decision 2026-03-26 | Richer data (load, capacity, ETAs), single server request regardless of user count |
| setInterval client polling | Supabase Realtime WebSocket subscription | This phase | Push-based updates, lower latency, auto-reconnect |
| protobufjs in Hermes runtime | JSON from Supabase REST/Realtime | This phase | No protobuf parsing complexity, simpler client code |
| Trip-to-route ID mapping on client | Route ID mapping in Edge Function proxy | This phase | Frontend sees consistent GTFS route IDs without extra data |

**Deprecated/outdated:**
- `gtfsRealtimeService.ts` -- protobuf decode service, replaced by Supabase Realtime subscription
- `useGtfsPolling.ts` -- client polling hook, replaced by `useVehicleSubscription.ts`
- `feeds.ts` S3 URL constants -- no longer needed (keep `STALE_THRESHOLD_MS` and `POLL_INTERVAL_MS`)
- `tripRoutes.ts` -- trip-to-route mapping, no longer needed (PHP provides routeID directly)
- `protobufjs` dependency -- can be removed from package.json after archiving

## Open Questions

1. **pg_cron 5-second reliability on hosted Supabase**
   - What we know: pg_cron supports 1-59 second intervals on Postgres >= 15.1.1.61. Local dev uses Postgres 17.
   - What's unclear: Some users report sub-minute scheduling issues on hosted Supabase. Our project's Supabase plan tier may affect this.
   - Recommendation: Implement with pg_cron 5-second schedule. If it doesn't work on the hosted instance, fall back to 10-second or use `* * * * *` (every minute) with the Edge Function running an internal loop for 55 seconds (12 fetches per invocation). Test during deployment.

2. **Stale vehicle cleanup from vehicles table**
   - What we know: Vehicles that go out of service should be removed from the `vehicles` table so they stop appearing.
   - What's unclear: Should the Edge Function DELETE vehicles not present in the latest PHP response? Or should the client filter by timestamp?
   - Recommendation: Edge Function should DELETE from `vehicles` any `vehicle_id` not present in the latest successful PHP response. This handles vehicles going out of service. Client also filters by `timestamp` as a safety net.

3. **Vault availability for local development**
   - What we know: Supabase Vault is used to store secrets (project URL, service role key) for pg_cron -> Edge Function calls.
   - What's unclear: Whether Vault is available in local Supabase CLI (`supabase start`) environment.
   - Recommendation: For local dev, the Edge Function is invoked directly via `supabase functions serve` + manual curl or the Supabase dashboard. pg_cron scheduling is set up only on the hosted instance. For local development, Edge Function can be tested standalone.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None currently configured |
| Config file | None -- see Wave 0 |
| Quick run command | N/A |
| Full suite command | N/A |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Edge Function fetches ETASpot and upserts to vehicles table | integration | Manual: `curl` Edge Function, verify DB rows | No -- Wave 0 |
| DATA-02 | Client receives vehicle updates via Realtime within 5s | manual-only | Manual: run app, observe markers update | N/A (requires live Supabase) |
| DATA-03 | Subscription pauses/resumes with AppState | manual-only | Manual: background/foreground app, observe | N/A (requires device) |
| DATA-04 | minutesToNextStops stored as raw JSON, etaSeconds=0 | unit | Verify Edge Function transform output | No -- Wave 0 |
| DATA-06 | Route ID mapping (215->compound) | unit | Test ROUTE_ID_MAP transform | No -- Wave 0 |
| DATA-07 | Position history rows created for non-duplicate positions | integration | Verify position_history after Edge Function run | No -- Wave 0 |
| MAP-02 | Bus markers render from Supabase-sourced positions | manual-only | Manual: visual verification on device | N/A |
| MAP-04 | Heading from PHP 'h' field renders directional marker | manual-only | Manual: visual verification | N/A |
| MAP-09 | Stale vehicles (>2min) not shown | unit | Test stale filter logic in Edge Function | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** Manual verification (Edge Function curl + app visual check)
- **Per wave merge:** Full manual test pass (background/foreground, marker rendering, data freshness)
- **Phase gate:** All vehicles visible with correct headings, positions updating in real-time

### Wave 0 Gaps
- [ ] No test framework configured -- consider adding Jest for unit tests of transform/mapping logic
- [ ] No automated tests for Edge Function logic (route mapping, stale filtering, deduplication)
- [ ] Edge Function testing requires running `supabase functions serve` locally
- [ ] Realtime subscription testing requires live Supabase instance (local or hosted)

*(Most phase requirements are integration/manual-only due to the distributed nature of the system: Edge Function -> Database -> Realtime -> Client)*

## Sources

### Primary (HIGH confidence)
- [Supabase Realtime Postgres Changes](https://supabase.com/docs/guides/realtime/postgres-changes) -- subscription API, filter syntax, RLS requirements, publication setup
- [Supabase Expo React Native Quickstart](https://supabase.com/docs/guides/getting-started/quickstarts/expo-react-native) -- client setup, EXPO_PUBLIC_ env vars, polyfills
- [Supabase Edge Functions](https://supabase.com/docs/guides/functions) -- Deno runtime, deployment, limits
- [Supabase Edge Function Limits](https://supabase.com/docs/guides/functions/limits) -- 150s/400s wall clock, 256MB memory, 2s CPU
- [Supabase Scheduling Edge Functions](https://supabase.com/docs/guides/functions/schedule-functions) -- pg_cron + pg_net integration
- [Supabase Cron](https://supabase.com/docs/guides/cron) -- sub-minute scheduling support (1-59 seconds)
- ETASpot PHP API (live verified) -- `auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING`

### Secondary (MEDIUM confidence)
- [@supabase/supabase-js npm](https://www.npmjs.com/package/@supabase/supabase-js) -- v2.100.1 latest
- [Expo Using Supabase guide](https://docs.expo.dev/guides/using-supabase/) -- Expo-specific integration notes
- [Supabase Realtime reconnection discussion](https://github.com/orgs/supabase/discussions/27513) -- AppState handling patterns

### Tertiary (LOW confidence)
- [pg_cron sub-second scheduling discussion](https://github.com/orgs/supabase/discussions/18274) -- Some users report issues with sub-minute scheduling; needs validation on hosted instance

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Supabase official docs + verified live API response
- Architecture: HIGH -- pg_cron + Edge Function is the documented Supabase pattern for periodic tasks
- Pitfalls: HIGH -- documented in official troubleshooting guides and community discussions
- Edge Function limits: HIGH -- from official limits documentation
- pg_cron 5-second scheduling: MEDIUM -- supported in Postgres 17 but community reports mixed results on hosted Supabase

**Research date:** 2026-03-26
**Valid until:** 2026-04-26 (30 days -- Supabase APIs stable, ETASpot endpoint verified live)

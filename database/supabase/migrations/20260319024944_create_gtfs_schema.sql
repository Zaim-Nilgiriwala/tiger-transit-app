-- This file creates the schema and tables for GTFS data

-- Create the GTFS schema
CREATE SCHEMA IF NOT EXISTS gtfs;


-- This is the table for GTFS calendar.txt data
CREATE TABLE gtfs.calendar (
    service_id TEXT PRIMARY KEY,
    monday SMALLINT NOT NULL,
    tuesday SMALLINT NOT NULL,
    wednesday SMALLINT NOT NULL,
    thursday SMALLINT NOT NULL,
    friday SMALLINT NOT NULL,
    saturday SMALLINT NOT NULL,
    sunday SMALLINT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);


-- This is the table for GTFS routes.txt data
CREATE TABLE gtfs.routes (
    route_id TEXT PRIMARY KEY,
    route_long_name TEXT,
    route_short_name TEXT,
    route_color TEXT,
    route_sort_order TEXT
);


-- This is the table for GTFS shapes.txt data
CREATE TABLE gtfs.shapes (
    shape_id TEXT NOT NULL,
    shape_pt_lat DOUBLE PRECISION NOT NULL,
    shape_pt_lon DOUBLE PRECISION NOT NULL,
    shape_pt_sequence SMALLINT NOT NULL,
    shape_dist_traveled DOUBLE PRECISION,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);


-- This is the table for GTFS stops.txt data
CREATE TABLE gtfs.stops (
    stop_id TEXT PRIMARY KEY,
    stop_name TEXT NOT NULL,
    stop_lat DOUBLE PRECISION NOT NULL,
    stop_lon DOUBLE PRECISION NOT NULL
);


-- This is the table for GTFS trips.txt data
CREATE TABLE gtfs.trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    shape_id TEXT,
    trip_headsign TEXT,
    direction_id SMALLINT,
    trip_short_name TEXT,
    block_id TEXT,
    block_service_id TEXT,
    block_name TEXT,
    FOREIGN KEY (route_id) REFERENCES gtfs.routes(route_id),
    FOREIGN KEY (service_id) REFERENCES gtfs.calendar(service_id)
);


-- This is the table for GTFS stop_times.txt data
CREATE TABLE gtfs.stop_times (
    trip_id TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    stop_sequence SMALLINT NOT NULL,
    arrival_time TIME,  --check
    departure_time TIME, -- check
    shape_dist_traveled DOUBLE PRECISION,
    timepoint SMALLINT,
    stop_headsign TEXT,
    PRIMARY KEY (trip_id, stop_sequence),
    FOREIGN KEY (trip_id) REFERENCES gtfs.trips(trip_id),
    FOREIGN KEY (stop_id) REFERENCES gtfs.stops(stop_id)
);

-- Allow entering the schema
GRANT USAGE ON SCHEMA gtfs TO service_role;

-- Allow ONLY reading tables
GRANT SELECT ON ALL TABLES IN SCHEMA gtfs TO service_role;

-- Remove write permissions (just to be safe)
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gtfs FROM service_role;
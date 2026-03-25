-- position_updates.pb table (not all data included, only the fields we deemed necessary or useful)
CREATE TABLE position_updates.position_updates (
    vehicle_id TEXT NOT NULL,
    position_timestamp TIMESTAMPTZ NOT NULL,
    trip_id TEXT, --not null?
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    next_stop_id TEXT,
    current_stop_sequence INTEGER,
    current_stop_status TEXT,
    vehicle_label TEXT,
    primary key (vehicle_id, position_timestamp)
);
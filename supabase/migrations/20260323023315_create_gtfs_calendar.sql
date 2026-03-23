-- This file is used to create the table for GTFS calendar.txt data
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
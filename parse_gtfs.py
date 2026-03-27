import partridge as ptg
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

# For stop_times.txt, use this function to convert the time columns from second values into actual times
def seconds_to_time(seconds):
    if pd.isna(seconds):
        return None
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# Load the GTFS feed from the specified directory and apply the config
feed = ptg.load_feed("./gtfs")


# Extract the relevant tables (and their relevant columns) from the feed
# Files left out: agency.txt, calendar_dates.txt, fare_attributes.txt, fare_rules.txt, feed_info.txt, frequencies.txt, transfers.txt

# calendar.txt is the main file that defines the service patterns for the transit system. 
# It specifies which days of the week each service operates, as well as the start and end dates for each service.
calendar = feed.calendar[["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"]]
# Excluded Column(s): service_name (empty)


# routes.txt defines the different routes that the transit system operates on. 
routes = feed.routes[["route_id", "route_long_name", "route_short_name","route_color", "route_sort_order"]]
# Excluded Column(s): route_type (All 3 = bus), agency_id (empty), route_desc (empty), route_url (empty), route_text_color (empty)


# shapes.txt defines the geometric paths that vehicles follow along their routes. 
# Each shape is defined as a series of points (latitude and longitude) that describe the path of the vehicle.
shapes = feed.shapes
# Excluded Column(s): None


# stop_times.txt defines the times at which vehicles arrive at and depart from stops and from which stop.
# This also defines whether a stop is a timepoint (a stop where the vehicle is expected to leave at a specific time)
stop_times = feed.stop_times[["trip_id", "stop_id", "stop_sequence","arrival_time", "departure_time", "shape_dist_traveled", "timepoint", "stop_headsign"]]
# Excluded Column(s): drop_off_type (empty)

# Convert arrival and departure times from float64 seconds to an actual time (str)
stop_times["arrival_time"] = stop_times["arrival_time"].apply(seconds_to_time)
stop_times["departure_time"] = stop_times["departure_time"].apply(seconds_to_time)


# stops.txt defines the locations where vehicles stop to pick up and drop off passengers.
stops = feed.stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]]
# Excluded Column(s): stop_code (No Relevance), stop_desc (empty), zone_id (empty), stop_url (empty), location_type (All 0 = stop/platform), parent_station (empty), stop_timezone (empty), wheelchair_boarding (empty)


# trips.txt defines each individual trip that a vehicle is scheduled to make along its route.
trips = feed.trips[["trip_id", "route_id", "service_id", "shape_id", "trip_headsign", "direction_id", "trip_short_name", "block_id", "block_service_id", "block_name"]]
# Excluded Column(s): wheelchair_accessible (empty), bikes_allowed (empty)


# Place the dataframes into a list for easier iteration when inserting into the database
dfs = [
    ("calendar", calendar), 
    ("routes", routes), 
    ("shapes", shapes), 
    ("stops", stops), 
    ("trips", trips),
    ("stop_times", stop_times)
]

# Connect to the PostgreSQL database and insert the data from the dataframes into the corresponding tables
conn = psycopg2.connect("postgresql://postgres:postgres@localhost:54322/postgres")
cur = conn.cursor()

for table_name,df in dfs:
    execute_values(
        cur,
        f"INSERT INTO gtfs.{table_name} VALUES %s",
        df.values.tolist()
    )

conn.commit()

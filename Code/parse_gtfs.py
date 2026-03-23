import partridge as ptg
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

feed = ptg.load_feed("./gtfs")

# Extract the relevant tables (and their relevant columns) from the feed
# Files left out: agency.txt, calendar_dates.txt, fare_attributes.txt, fare_rules.txt, feed_info.txt, frequencies.txt, transfers.txt

# Does not include
calendar = feed.calendar[["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"]]

# calendar.to_csv("calendar.csv", index=False, header=True)

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:54322/postgres")
cur = conn.cursor()

execute_values(
    cur,
    "INSERT INTO gtfs.calendar VALUES %s",
    calendar.values.tolist()
)

conn.commit()


# routes = feed.routes


# shapes = feed.shapes


# stop_times = feed.stop_times


# stops = feed.stops


# trips = feed.trips

# print(calendar)
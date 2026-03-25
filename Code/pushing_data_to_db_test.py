
from supabase import create_client, Client

SUPABASE_URL = "http://127.0.0.1:54321 "
SUPABASE_KEY = "sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.schema("position_updates").table("position_updates").insert({
    "vehicle_id": "test_vehicle_123",
    "position_timestamp": "2023-01-01 00:00:00+00",
    "trip_id": "test_trip_123",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "next_stop_id": "test_stop_123",
    "current_stop_sequence": 1,
    "current_stop_status": "at_stop",
    "vehicle_label": "test_vehicle_label"
}).execute()

print(response.data)
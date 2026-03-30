"""
Analyze all available fields in Auburn GTFS-RT feeds to show complete data structure.
"""

import requests
from google.transit import gtfs_realtime_pb2
import json

ALERTS_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/alerts.pb"
VEH_POS_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb"
TRIP_UPD_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb"

def fetch_and_parse(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(r.content)
    return msg

def analyze_vehicle_position(vp):
    """Extract all fields from a VehiclePosition entity"""
    fields = {}

    # Trip descriptor
    if vp.trip.trip_id:
        fields['trip_id'] = vp.trip.trip_id
    if vp.trip.route_id:
        fields['route_id'] = vp.trip.route_id
    if vp.trip.direction_id is not None:
        fields['direction_id'] = vp.trip.direction_id
    if vp.trip.start_time:
        fields['start_time'] = vp.trip.start_time
    if vp.trip.start_date:
        fields['start_date'] = vp.trip.start_date
    if vp.trip.schedule_relationship is not None:
        fields['schedule_relationship'] = vp.trip.schedule_relationship

    # Vehicle descriptor
    if vp.vehicle.id:
        fields['vehicle_id'] = vp.vehicle.id
    if vp.vehicle.label:
        fields['vehicle_label'] = vp.vehicle.label
    if vp.vehicle.license_plate:
        fields['license_plate'] = vp.vehicle.license_plate

    # Position
    fields['latitude'] = vp.position.latitude
    fields['longitude'] = vp.position.longitude
    if vp.position.HasField('bearing'):
        fields['bearing'] = vp.position.bearing
    if vp.position.HasField('odometer'):
        fields['odometer'] = vp.position.odometer
    if vp.position.HasField('speed'):
        fields['speed'] = vp.position.speed

    # Other fields
    if vp.current_stop_sequence is not None:
        fields['current_stop_sequence'] = vp.current_stop_sequence
    if vp.stop_id:
        fields['stop_id'] = vp.stop_id
    if vp.current_status is not None:
        fields['current_status'] = vp.current_status
    if vp.timestamp:
        fields['timestamp'] = vp.timestamp
    if vp.congestion_level is not None:
        fields['congestion_level'] = vp.congestion_level
    if vp.occupancy_status is not None:
        fields['occupancy_status'] = vp.occupancy_status

    return fields

def analyze_trip_update(tu):
    """Extract all fields from a TripUpdate entity"""
    fields = {}

    # Trip descriptor (same as vehicle position)
    if tu.trip.trip_id:
        fields['trip_id'] = tu.trip.trip_id
    if tu.trip.route_id:
        fields['route_id'] = tu.trip.route_id
    if tu.trip.direction_id is not None:
        fields['direction_id'] = tu.trip.direction_id
    if tu.trip.start_time:
        fields['start_time'] = tu.trip.start_time
    if tu.trip.start_date:
        fields['start_date'] = tu.trip.start_date

    # Vehicle descriptor
    if tu.vehicle.id:
        fields['vehicle_id'] = tu.vehicle.id
    if tu.vehicle.label:
        fields['vehicle_label'] = tu.vehicle.label

    # Timestamp
    if tu.timestamp:
        fields['timestamp'] = tu.timestamp

    # Stop time updates
    fields['num_stop_time_updates'] = len(tu.stop_time_update)
    if tu.stop_time_update:
        stu = tu.stop_time_update[0]  # Look at first stop
        stop_fields = {}
        if stu.stop_sequence is not None:
            stop_fields['stop_sequence'] = stu.stop_sequence
        if stu.stop_id:
            stop_fields['stop_id'] = stu.stop_id
        if stu.HasField('arrival'):
            arr = {}
            if stu.arrival.HasField('delay'):
                arr['delay'] = stu.arrival.delay
            if stu.arrival.time:
                arr['time'] = stu.arrival.time
            if stu.arrival.uncertainty is not None:
                arr['uncertainty'] = stu.arrival.uncertainty
            stop_fields['arrival'] = arr
        if stu.HasField('departure'):
            dep = {}
            if stu.departure.HasField('delay'):
                dep['delay'] = stu.departure.delay
            if stu.departure.time:
                dep['time'] = stu.departure.time
            if stu.departure.uncertainty is not None:
                dep['uncertainty'] = stu.departure.uncertainty
            stop_fields['departure'] = dep
        if stu.schedule_relationship is not None:
            stop_fields['schedule_relationship'] = stu.schedule_relationship
        fields['first_stop_example'] = stop_fields

    return fields

def analyze_alert(alert):
    """Extract all fields from an Alert entity"""
    fields = {}

    # Active periods
    if alert.active_period:
        periods = []
        for ap in alert.active_period:
            periods.append({
                'start': ap.start if ap.start else None,
                'end': ap.end if ap.end else None
            })
        fields['active_periods'] = periods

    # Informed entities
    if alert.informed_entity:
        entities = []
        for ie in alert.informed_entity:
            entity = {}
            if ie.agency_id:
                entity['agency_id'] = ie.agency_id
            if ie.route_id:
                entity['route_id'] = ie.route_id
            if ie.route_type is not None:
                entity['route_type'] = ie.route_type
            if ie.trip.trip_id:
                entity['trip_id'] = ie.trip.trip_id
            if ie.stop_id:
                entity['stop_id'] = ie.stop_id
            entities.append(entity)
        fields['informed_entities'] = entities

    # Cause and effect
    if alert.cause is not None:
        fields['cause'] = alert.cause
    if alert.effect is not None:
        fields['effect'] = alert.effect

    # Text
    if alert.HasField('url'):
        fields['url'] = alert.url.translation[0].text if alert.url.translation else None
    if alert.HasField('header_text'):
        fields['header_text'] = alert.header_text.translation[0].text if alert.header_text.translation else None
    if alert.HasField('description_text'):
        fields['description_text'] = alert.description_text.translation[0].text if alert.description_text.translation else None

    return fields

print("=" * 80)
print("ANALYZING AUBURN GTFS-RT FEEDS - ALL AVAILABLE FIELDS")
print("=" * 80)

# Fetch all feeds
print("\nFetching feeds...")
veh_msg = fetch_and_parse(VEH_POS_URL)
trip_msg = fetch_and_parse(TRIP_UPD_URL)
alert_msg = fetch_and_parse(ALERTS_URL)

print(f"\nFeed Header Info:")
print(f"  Version: {veh_msg.header.gtfs_realtime_version}")
print(f"  Vehicle Positions: {len(veh_msg.entity)} entities")
print(f"  Trip Updates: {len(trip_msg.entity)} entities")
print(f"  Alerts: {len(alert_msg.entity)} entities")

# Analyze first vehicle position
print("\n" + "=" * 80)
print("VEHICLE POSITION - EXAMPLE WITH ALL FIELDS")
print("=" * 80)
if veh_msg.entity:
    for ent in veh_msg.entity:
        if ent.HasField('vehicle'):
            vp_fields = analyze_vehicle_position(ent.vehicle)
            print(json.dumps(vp_fields, indent=2))
            break

# Analyze first trip update
print("\n" + "=" * 80)
print("TRIP UPDATE - EXAMPLE WITH ALL FIELDS")
print("=" * 80)
if trip_msg.entity:
    for ent in trip_msg.entity:
        if ent.HasField('trip_update'):
            tu_fields = analyze_trip_update(ent.trip_update)
            print(json.dumps(tu_fields, indent=2))
            break

# Analyze alerts
print("\n" + "=" * 80)
print("ALERTS - ALL AVAILABLE FIELDS")
print("=" * 80)
if alert_msg.entity and any(e.HasField('alert') for e in alert_msg.entity):
    for ent in alert_msg.entity:
        if ent.HasField('alert'):
            alert_fields = analyze_alert(ent.alert)
            print(json.dumps(alert_fields, indent=2))
            break
else:
    print("No alerts currently active")
    print("\nTypical alert fields include:")
    print("  - active_periods: [{start, end}]")
    print("  - informed_entities: [{agency_id, route_id, stop_id, trip_id}]")
    print("  - cause: enum (accident, construction, etc.)")
    print("  - effect: enum (detour, delay, no_service, etc.)")
    print("  - header_text, description_text, url: localized strings")

print("\n" + "=" * 80)
print("SUMMARY OF ALL AVAILABLE DATA")
print("=" * 80)
print("\nThe GTFS-RT feeds provide:")
print("\n1. VEHICLE POSITIONS (real-time location)")
print("   - GPS coordinates (lat/lon)")
print("   - Bearing (direction vehicle is facing)")
print("   - Speed (m/s)")
print("   - Vehicle ID and label")
print("   - Associated trip/route info")
print("   - Current stop and stop sequence")
print("   - Timestamp")
print("   - Congestion level (if available)")
print("   - Occupancy status (if available)")

print("\n2. TRIP UPDATES (schedule adherence)")
print("   - Trip and route identifiers")
print("   - Vehicle assignment")
print("   - Stop-by-stop predictions:")
print("     * Stop ID and sequence")
print("     * Arrival time (absolute or delay)")
print("     * Departure time (absolute or delay)")
print("     * Uncertainty values")
print("   - Schedule relationship (scheduled, added, canceled, etc.)")

print("\n3. ALERTS (service disruptions)")
print("   - Active time periods")
print("   - Affected routes/stops/trips")
print("   - Cause (accident, weather, construction, etc.)")
print("   - Effect (detour, delay, no service, etc.)")
print("   - Header and description text")
print("   - URL for more info")

print("\nAll timestamps are in Unix epoch seconds (UTC)")
print("=" * 80)

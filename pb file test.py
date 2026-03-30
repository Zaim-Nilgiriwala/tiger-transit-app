"""
Fetch Auburn ETA Spot GTFS + GTFS-RT feeds and print a human-readable summary.

Setup:
  pip install requests gtfs-realtime-bindings

Run:
  python fetch_auburn_feeds.py
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, List

import requests
from google.transit import gtfs_realtime_pb2


GTFS_ZIP_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/gtfs.zip"
ALERTS_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/alerts.pb"
VEH_POS_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb"
TRIP_UPD_URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb"


# -------------------------
# Helpers
# -------------------------

def _dt(ts: int) -> str:
    """Unix seconds -> readable UTC time."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def parse_gtfs_rt(feed_bytes: bytes) -> gtfs_realtime_pb2.FeedMessage:
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(feed_bytes)
    return msg


def download_and_read_gtfs_zip(zip_bytes: bytes) -> Dict[str, List[Dict[str, str]]]:
    """
    Load selected GTFS tables into memory as list-of-dicts for quick joins.
    Keeps it simple and avoids pandas dependency.
    """
    import csv

    want = {"routes.txt", "trips.txt", "stops.txt", "stop_times.txt"}
    tables: Dict[str, List[Dict[str, str]]] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name in want:
                with zf.open(name) as f:
                    # GTFS is UTF-8 typically; fallback to latin1 if needed
                    raw = f.read()
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        text = raw.decode("latin1")
                    reader = csv.DictReader(io.StringIO(text))
                    tables[name] = list(reader)

    missing = want - set(tables.keys())
    if missing:
        print(f"Warning: GTFS missing expected files: {sorted(missing)}")

    return tables


@dataclass
class GtfsIndex:
    route_id_to_shortlong: Dict[str, str]
    stop_id_to_name: Dict[str, str]
    trip_id_to_route_id: Dict[str, str]
    trip_id_to_headsign: Dict[str, str]


def build_gtfs_index(tables: Dict[str, List[Dict[str, str]]]) -> GtfsIndex:
    route_id_to_shortlong: Dict[str, str] = {}
    stop_id_to_name: Dict[str, str] = {}
    trip_id_to_route_id: Dict[str, str] = {}
    trip_id_to_headsign: Dict[str, str] = {}

    for r in tables.get("routes.txt", []):
        rid = r.get("route_id", "")
        short = (r.get("route_short_name") or "").strip()
        long = (r.get("route_long_name") or "").strip()
        name = short if short else long
        if short and long and short != long:
            name = f"{short} — {long}"
        route_id_to_shortlong[rid] = name or rid

    for s in tables.get("stops.txt", []):
        sid = s.get("stop_id", "")
        name = (s.get("stop_name") or "").strip()
        stop_id_to_name[sid] = name or sid

    for t in tables.get("trips.txt", []):
        tid = t.get("trip_id", "")
        rid = t.get("route_id", "")
        hs = (t.get("trip_headsign") or "").strip()
        trip_id_to_route_id[tid] = rid
        trip_id_to_headsign[tid] = hs

    return GtfsIndex(
        route_id_to_shortlong=route_id_to_shortlong,
        stop_id_to_name=stop_id_to_name,
        trip_id_to_route_id=trip_id_to_route_id,
        trip_id_to_headsign=trip_id_to_headsign,
    )


def pretty_vehicle_position(ent: gtfs_realtime_pb2.FeedEntity, idx: GtfsIndex) -> str:
    vp = ent.vehicle
    v = vp.vehicle.id or vp.vehicle.label or "unknown_vehicle"
    trip_id = vp.trip.trip_id
    route_id = vp.trip.route_id or idx.trip_id_to_route_id.get(trip_id, "")
    route_name = idx.route_id_to_shortlong.get(route_id, route_id or "unknown_route")
    headsign = idx.trip_id_to_headsign.get(trip_id, "").strip()
    pos = vp.position
    lat = pos.latitude
    lon = pos.longitude
    bearing = int(pos.bearing) if pos.HasField("bearing") else None
    speed = pos.speed if pos.HasField("speed") else None
    ts = vp.timestamp

    bits = [f"Vehicle {v} @ ({lat:.5f}, {lon:.5f})"]
    if route_name:
        bits.append(f"route={route_name}")
    if trip_id:
        bits.append(f"trip_id={trip_id}")
    if headsign:
        bits.append(f"headsign={headsign}")
    if bearing is not None:
        bits.append(f"bearing={bearing}°")
    if speed is not None:
        bits.append(f"speed={speed:.2f} m/s")
    if ts:
        bits.append(f"time={_dt(ts)}")
    return " | ".join(bits)


def summarize_trip_updates(msg: gtfs_realtime_pb2.FeedMessage, idx: GtfsIndex, limit: int = 10) -> List[str]:
    out: List[str] = []
    for ent in msg.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip_id = tu.trip.trip_id
        route_id = tu.trip.route_id or idx.trip_id_to_route_id.get(trip_id, "")
        route_name = idx.route_id_to_shortlong.get(route_id, route_id or "unknown_route")
        headsign = idx.trip_id_to_headsign.get(trip_id, "").strip()

        # Show next 1-2 stop updates (if present)
        stop_updates = []
        for stu in tu.stop_time_update[:2]:
            sid = stu.stop_id
            sname = idx.stop_id_to_name.get(sid, sid or "unknown_stop")
            arr = stu.arrival.time if stu.HasField("arrival") and stu.arrival.time else None
            dep = stu.departure.time if stu.HasField("departure") and stu.departure.time else None
            dly = stu.arrival.delay if stu.HasField("arrival") and stu.arrival.HasField("delay") else None
            piece = f"{sname}"
            if arr:
                piece += f" arr={_dt(arr)}"
            if dep:
                piece += f" dep={_dt(dep)}"
            if dly is not None:
                piece += f" delay={dly}s"
            stop_updates.append(piece)

        header = f"TripUpdate route={route_name}"
        if trip_id:
            header += f" trip_id={trip_id}"
        if headsign:
            header += f" headsign={headsign}"
        if stop_updates:
            header += " | next: " + " ; ".join(stop_updates)
        out.append(header)

        if len(out) >= limit:
            break
    return out


def summarize_alerts(msg: gtfs_realtime_pb2.FeedMessage, limit: int = 10) -> List[str]:
    out: List[str] = []
    for ent in msg.entity:
        if not ent.HasField("alert"):
            continue
        alert = ent.alert

        # best-effort: pick first header_text / description_text in English if present
        def pick_translated(ts) -> str:
            for tr in ts.translation:
                if tr.language in ("en", "", None):
                    return tr.text
            return ts.translation[0].text if ts.translation else ""

        header = pick_translated(alert.header_text) if alert.HasField("header_text") else ""
        desc = pick_translated(alert.description_text) if alert.HasField("description_text") else ""

        # active period times (optional)
        ap = ""
        if alert.active_period:
            p0 = alert.active_period[0]
            start = _dt(p0.start) if p0.start else "?"
            end = _dt(p0.end) if p0.end else "?"
            ap = f" (active {start} → {end})"

        txt = (header or "Alert") + ap
        if desc and desc != header:
            txt += f" — {desc}"
        out.append(txt)

        if len(out) >= limit:
            break
    return out


# -------------------------
# Main
# -------------------------

def main() -> None:
    print("Downloading GTFS (static)...")
    gtfs_zip = fetch_bytes(GTFS_ZIP_URL)
    tables = download_and_read_gtfs_zip(gtfs_zip)
    idx = build_gtfs_index(tables)
    print(f"Loaded GTFS tables: {', '.join(sorted(tables.keys()))}")

    print("\nDownloading GTFS-RT feeds...")
    alerts_msg = parse_gtfs_rt(fetch_bytes(ALERTS_URL))
    vehpos_msg = parse_gtfs_rt(fetch_bytes(VEH_POS_URL))
    tripupd_msg = parse_gtfs_rt(fetch_bytes(TRIP_UPD_URL))

    # Feed headers (timestamps in seconds)
    print("\nFeed headers:")
    print(f"  Alerts:          { _dt(alerts_msg.header.timestamp) if alerts_msg.header.timestamp else 'no timestamp' }")
    print(f"  VehiclePositions:{ _dt(vehpos_msg.header.timestamp) if vehpos_msg.header.timestamp else 'no timestamp' }")
    print(f"  TripUpdates:     { _dt(tripupd_msg.header.timestamp) if tripupd_msg.header.timestamp else 'no timestamp' }")

    # Alerts
    alerts = summarize_alerts(alerts_msg, limit=10)
    print("\n--- Alerts (up to 10) ---")
    if alerts:
        for a in alerts:
            print(" -", a)
    else:
        print(" (none)")

    # Vehicle positions
    print("\n--- Vehicle Positions (first 10) ---")
    shown = 0
    for ent in vehpos_msg.entity:
        if ent.HasField("vehicle"):
            print(" -", pretty_vehicle_position(ent, idx))
            shown += 1
            if shown >= 10:
                break
    if shown == 0:
        print(" (none)")

    # Trip updates
    print("\n--- Trip Updates (up to 100) ---")
    tus = summarize_trip_updates(tripupd_msg, idx, limit=100)
    if tus:
        for t in tus:
            print(" -", t)
    else:
        print(" (none)")

    print("\nDone.")


if __name__ == "__main__":
    main()

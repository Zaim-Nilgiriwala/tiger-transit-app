import time
import requests
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToJson
from google.protobuf.json_format import MessageToDict
import json

# URL for position updates in GTFS Realtime format
URL = "https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb"

while True:
    data = requests.get(URL).content
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    
    feed_dict = MessageToDict(feed)

    with open("position_updates.jsonl", "a") as f:
        json.dump(feed_dict, f)
        f.write("\n")
    time.sleep(10)

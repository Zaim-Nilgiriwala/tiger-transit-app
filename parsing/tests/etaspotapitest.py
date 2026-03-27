import requests, time
from datetime import datetime
 
URL = "https://auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1"


LOG = "transit_log.txt"

last = {}
while True:
    now = datetime.now().strftime("%H:%M:%S")
    lines = [f"\n[{now}]"]
    vehicles = requests.get(URL).json()["get_vehicles"]
    for v in vehicles:
        eid = v["equipmentID"]
        rt  = v["receiveTime"]
        if eid in last:
            gap = rt - last[eid]
            lines.append(f"  {eid}: {'Updated! Gap: ' + str(gap) + 'ms' if gap else 'No change'}")
        else:
            lines.append(f"  {eid}: first seen")
        last[eid] = rt
    output = "\n".join(lines)
    print(output)
    with open(LOG, "a") as f:
        f.write(output + "\n")
    time.sleep(1)
 
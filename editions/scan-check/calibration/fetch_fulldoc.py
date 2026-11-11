import csv, json, os, re, sys, time, requests
from pathlib import Path
TRP = "https://transkribus.eu/TrpServer/rest"
MAP = "/Users/sinairusinek/Documents/GitHub/Hasidigital/editions/transkribus-collection-map.tsv"
out = Path(sys.argv[1]); out.mkdir(exist_ok=True)
s = requests.Session()
r = s.post(f"{TRP}/auth/login", data={"user": os.environ["TRANSKRIBUS_USER"], "pw": os.environ["TRANSKRIBUS_PASS"]}, timeout=60)
s.cookies.set("JSESSIONID", re.search(r"<sessionId>(.*?)</sessionId>", r.text).group(1))
rows = list(csv.DictReader(open(MAP, encoding="utf-8"), delimiter="\t"))
for row in rows:
    f = out / f"{row['docId']}.json"
    if f.exists(): continue
    for a in range(3):
        try:
            j = s.get(f"{TRP}/collections/49371/{row['docId']}/fulldoc", params={"nrOfTranscripts": -1}, headers={"Accept": "application/json"}, timeout=180)
            j.raise_for_status(); f.write_text(j.text); break
        except Exception as e:
            print(row['docId'], e); time.sleep(5)
print("done", len(list(out.glob('*.json'))))

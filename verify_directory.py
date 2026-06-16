"""Verify every bank code for the 7 openiban-directory countries against
openiban, producing openiban_valid_codes.json — the allowlist the generator
uses so those countries emit only openiban-accepted IBANs.
"""
import csv
import http.client
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from iban import IBANGenerator

g = IBANGenerator("unused")
DIRECTORY = {"DE", "AT", "BE", "NL", "CH", "LI", "LU"}
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/149"
_tls = threading.local()
_lock = threading.Lock()
done = 0

rows = list(csv.DictReader(open("all_bank_data.csv", newline="", encoding="utf-8")))
tasks = [(r["country_code"], r["bank_code"], int(r["iban_length"]))
         for r in rows if r["country_code"] in DIRECTORY]
print(f"verifying {len(tasks)} codes across {len(DIRECTORY)} directory countries")


def check(args):
    global done
    cc, code, length = args
    bban, _ = g.build_bban(cc, code, length)
    iban = cc + g.compute_check(cc, bban) + bban
    ok = None
    for _ in range(4):
        conn = getattr(_tls, "c", None) or http.client.HTTPSConnection("openiban.com", timeout=20)
        _tls.c = conn
        try:
            conn.request("GET", f"/validate/{iban}?validateBankCode=true",
                         headers={"User-Agent": UA, "referer": "https://openiban.com/",
                                  "x-requested-with": "XMLHttpRequest"})
            d = json.loads(conn.getresponse().read())
            ok = bool(d.get("valid") and d.get("checkResults", {}).get("bankCode") is True)
            break
        except Exception:
            try: conn.close()
            except Exception: pass
            _tls.c = None
            time.sleep(1)
    with _lock:
        done += 1
        if done % 250 == 0:
            print(f"  ...{done}/{len(tasks)}", flush=True)
    return cc, code, ok


valid = {cc: [] for cc in DIRECTORY}
with ThreadPoolExecutor(max_workers=12) as pool:
    for cc, code, ok in pool.map(check, tasks):
        if ok:
            valid[cc].append(code)

json.dump(valid, open("openiban_valid_codes.json", "w"))
print("\nopeniban-valid codes per country:")
for cc in sorted(valid):
    total = sum(1 for t in tasks if t[0] == cc)
    print(f"  {cc}: {len(valid[cc])}/{total}")
print("wrote openiban_valid_codes.json")

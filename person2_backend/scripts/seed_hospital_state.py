"""
Part 7 -- Create SIMULATED hospital live-state data.

*** THIS IS SIMULATED DATA, NOT REAL-TIME BED/CAPACITY DATA. ***
mumbai_hospitals.csv (Part 3) is static government directory information --
it has no live bed counts. This generates a synthetic live-state layer,
kept in a completely separate file/table, so a real hospital API feed can
replace ONLY this file later without touching the static directory or any
routing/selection code (both just read whatever is in hospital_state.csv).

Only hospitals with usable_for_routing == True get a state row -- if a
hospital can't be routed to, it can never be selected for dispatch, so
simulating its bed state would be meaningless.

Writes: data/simulation/hospital_state.csv
  hospital_id, available_beds, icu_available, emergency_available, status, last_updated
"""
import csv
import os
import sys
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import MUMBAI_HOSPITALS_CSV as HOSPITALS_CSV, HOSPITAL_STATE_CSV as OUT_CSV, ensure_dirs

ensure_dirs()

random.seed(11)
SIM_TIMESTAMP = datetime.now(timezone.utc).isoformat()


def sim_beds(total_beds_str):
    """If the directory listed a bed count, simulate availability as a fraction of it.
    Otherwise fall back to a generic small-hospital range."""
    if total_beds_str:
        try:
            total = int(float(total_beds_str))
            if total > 0:
                return random.randint(0, total)
        except ValueError:
            pass
    return random.randint(0, 20)


with open(HOSPITALS_CSV) as f:
    hospitals = list(csv.DictReader(f))

rows = []
for h in hospitals:
    if h['usable_for_routing'] != 'True':
        continue

    available_beds = sim_beds(h['total_beds'])

    # emergency_available: weight toward the directory's own stated Emergency_Services
    # flag when present, otherwise assume a moderate baseline probability
    stated_emergency = bool(h['emergency_services'])
    if stated_emergency:
        emergency_available = random.random() < 0.9
    else:
        emergency_available = random.random() < 0.5

    icu_available = random.random() < 0.4

    if available_beds == 0:
        status = 'FULL'
    elif available_beds <= 3:
        status = 'LIMITED'
    else:
        status = 'OPEN'

    rows.append({
        'hospital_id': h['hospital_id'],
        'available_beds': available_beds,
        'icu_available': icu_available,
        'emergency_available': emergency_available,
        'status': status,
        'last_updated': SIM_TIMESTAMP,
        'is_simulated': True,
    })

with open(OUT_CSV, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['hospital_id', 'available_beds', 'icu_available',
                                            'emergency_available', 'status', 'last_updated', 'is_simulated'])
    writer.writeheader()
    writer.writerows(rows)

from collections import Counter
print(f"Generated SIMULATED live-state for {len(rows)} hospitals -> {OUT_CSV}")
print("Status distribution:", Counter(r['status'] for r in rows))
print(f"ICU available: {sum(1 for r in rows if r['icu_available'])}/{len(rows)}")
print(f"Emergency available: {sum(1 for r in rows if r['emergency_available'])}/{len(rows)}")

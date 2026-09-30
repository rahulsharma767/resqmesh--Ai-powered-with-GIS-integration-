"""
Part 6 -- Create SIMULATED ambulance fleet data.

*** THIS IS SIMULATED DATA, NOT REAL AMBULANCE GPS/FLEET DATA. ***
No live ambulance dataset was provided or is available. This generates a
clearly-labeled synthetic fleet for prototype testing. Every location is
snapped to an actual road-graph node (so it's always routable), but the
existence, position, and status of these ambulances is entirely fabricated
for testing purposes.

The schema is designed so a real ambulance GPS/telemetry feed can replace
this file later without changing any downstream code -- selection and
routing code only depends on the columns below, not on how they were
produced.

Writes: data/simulation/ambulances.csv
  ambulance_id, latitude, longitude, status, ambulance_type, equipment,
  capacity, current_location_node
"""
import csv
import os
import sys
import random
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import ROAD_NODES_CSV as NODES_CSV, AMBULANCES_CSV as OUT_CSV, ensure_dirs

ensure_dirs()

random.seed(7)

N_AMBULANCES = 150

STATUS_WEIGHTS = {'AVAILABLE': 0.55, 'BUSY': 0.35, 'OFFLINE': 0.10}
TYPE_WEIGHTS = {'BASIC': 0.50, 'ALS': 0.35, 'ICU': 0.15}

TYPE_EQUIPMENT = {
    'BASIC': ['first_aid', 'stretcher', 'oxygen_basic', 'spinal_board'],
    'ALS': ['first_aid', 'stretcher', 'oxygen_basic', 'spinal_board',
            'defibrillator', 'cardiac_monitor', 'iv_therapy', 'advanced_airway'],
    'ICU': ['first_aid', 'stretcher', 'oxygen_basic', 'spinal_board',
            'defibrillator', 'cardiac_monitor', 'iv_therapy', 'advanced_airway',
            'ventilator', 'infusion_pump', 'icu_grade_monitoring'],
}
TYPE_CAPACITY = {'BASIC': 1, 'ALS': 1, 'ICU': 2}


def weighted_choice(weights_dict):
    items = list(weights_dict.keys())
    weights = list(weights_dict.values())
    return random.choices(items, weights=weights, k=1)[0]


# Load road graph nodes to snap ambulance locations onto real routable points
with open(NODES_CSV) as f:
    reader = csv.reader(f)
    next(reader)
    nodes = [(int(r[0]), float(r[1]), float(r[2])) for r in reader]

sampled_nodes = random.sample(nodes, N_AMBULANCES)

rows = []
for i, (node_id, lat, lon) in enumerate(sampled_nodes, start=1):
    amb_type = weighted_choice(TYPE_WEIGHTS)
    status = weighted_choice(STATUS_WEIGHTS)
    rows.append({
        'ambulance_id': f'AMB-{i:03d}',
        'latitude': f'{lat:.7f}',
        'longitude': f'{lon:.7f}',
        'status': status,
        'ambulance_type': amb_type,
        'equipment': json.dumps(TYPE_EQUIPMENT[amb_type]),
        'capacity': TYPE_CAPACITY[amb_type],
        'current_location_node': node_id,
        'is_simulated': True,
    })

with open(OUT_CSV, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['ambulance_id', 'latitude', 'longitude', 'status',
                                            'ambulance_type', 'equipment', 'capacity',
                                            'current_location_node', 'is_simulated'])
    writer.writeheader()
    writer.writerows(rows)

from collections import Counter
print(f"Generated {len(rows)} SIMULATED ambulances -> {OUT_CSV}")
print("Status distribution:", Counter(r['status'] for r in rows))
print("Type distribution:", Counter(r['ambulance_type'] for r in rows))

"""
Part 5 -- Connect hospitals to the road graph.

For each hospital with usable_for_routing == True, find the nearest node in
the Mumbai road graph using a KDTree (scipy) in an equirectangular-projected
local coordinate space (accurate enough for city-scale nearest-neighbor;
avoids true geodesic KDTree complexity for a ~50km-wide area).

Writes: data/processed/hospital_nearest_node.csv
  hospital_id, hospital_name, latitude, longitude, nearest_graph_node, distance_m_to_node
"""
import csv
import math
import os
import sys
from scipy.spatial import cKDTree
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (MUMBAI_HOSPITALS_CSV as HOSPITALS_CSV, ROAD_NODES_CSV as GRAPH_NODES_CSV,
                    HOSPITAL_NEAREST_NODE_CSV as OUT_CSV, ensure_dirs)

ensure_dirs()

# Load road graph nodes
node_ids = []
node_lats = []
node_lons = []
with open(GRAPH_NODES_CSV) as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        node_ids.append(int(row[0]))
        node_lats.append(float(row[1]))
        node_lons.append(float(row[2]))

node_lats = np.array(node_lats)
node_lons = np.array(node_lons)
mean_lat_rad = math.radians(np.mean(node_lats))
cos_mean_lat = math.cos(mean_lat_rad)

# Project to local equirectangular meters (approx) for KDTree
R = 6371000.0
node_x = np.radians(node_lons) * cos_mean_lat * R
node_y = np.radians(node_lats) * R
tree = cKDTree(np.column_stack([node_x, node_y]))

# Load hospitals
with open(HOSPITALS_CSV) as f:
    hospitals = list(csv.DictReader(f))

out_rows = []
connected = 0
for h in hospitals:
    if h['usable_for_routing'] != 'True':
        continue
    lat, lon = float(h['lat']), float(h['lon'])
    hx = math.radians(lon) * cos_mean_lat * R
    hy = math.radians(lat) * R
    dist, idx = tree.query([hx, hy])
    nearest_node = node_ids[idx]
    out_rows.append({
        'hospital_id': h['hospital_id'],
        'hospital_name': h['hospital_name'],
        'latitude': h['lat'],
        'longitude': h['lon'],
        'nearest_graph_node': nearest_node,
        'distance_m_to_node': f'{dist:.1f}',
    })
    connected += 1

with open(OUT_CSV, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['hospital_id', 'hospital_name', 'latitude', 'longitude', 'nearest_graph_node', 'distance_m_to_node'])
    writer.writeheader()
    writer.writerows(out_rows)

dists = [float(r['distance_m_to_node']) for r in out_rows]
print(f"Connected {connected} hospitals to nearest road-graph node.")
print(f"Distance to nearest node: min={min(dists):.1f}m max={max(dists):.1f}m mean={sum(dists)/len(dists):.1f}m")
print(f"Hospitals with nearest-node distance > 500m (possible graph gap): {sum(1 for d in dists if d > 500)}")

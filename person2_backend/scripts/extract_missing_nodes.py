"""
Pass 3: targeted lookup of node coordinates for the (small) set of node ids
that kept ways reference but which fell outside the initial Mumbai bbox filter
(boundary-crossing ways). Appends them to the node cache.
"""
import sys
import os
import csv
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbf_reader import iter_primitive_blocks, decode_dense_nodes
from paths import (OSM_PBF_RAW as PBF, MISSING_NODE_IDS_CACHE as MISSING_IDS_FILE,
                    NODES_BBOX_CACHE as NODES_CSV, ensure_dirs)

ensure_dirs()

with open(MISSING_IDS_FILE) as f:
    want_ids = set(int(line.strip()) for line in f if line.strip())
print(f"Looking for {len(want_ids)} missing node ids across the whole Western Zone node section...", flush=True)

t0 = time.time()
found = {}
block_idx = 0
for ctx, groups in iter_primitive_blocks(PBF):
    has_dense = any(2 in g for g in groups)
    if not has_dense:
        if block_idx > 0:
            break
        continue
    block_idx += 1
    for g in groups:
        if 2 in g:
            for node_id, lat, lon in decode_dense_nodes(ctx, g, node_bbox=None):
                if node_id in want_ids:
                    found[node_id] = (lat, lon)
    if len(found) == len(want_ids):
        break
    if block_idx % 1000 == 0:
        print(f"...{block_idx} blocks scanned, {len(found)}/{len(want_ids)} found, {time.time()-t0:.1f}s", flush=True)

print(f"Found {len(found)}/{len(want_ids)} in {time.time()-t0:.1f}s", flush=True)

with open(NODES_CSV, 'a', newline='') as f:
    writer = csv.writer(f)
    for node_id, (lat, lon) in found.items():
        writer.writerow([node_id, f'{lat:.7f}', f'{lon:.7f}'])

missing_still = want_ids - set(found.keys())
if missing_still:
    print(f"WARNING: {len(missing_still)} node ids not found anywhere in the file "
          f"(dangling references / likely edge artifacts): {list(missing_still)[:20]}...")
else:
    print("All missing node refs resolved.")

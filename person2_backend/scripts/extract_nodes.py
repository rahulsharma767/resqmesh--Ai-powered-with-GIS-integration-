"""
Pass 1: scan the whole PBF's dense-node blocks, keep only nodes whose lat/lon
fall inside a generous Mumbai bounding box (buffer around the real ward extent:
lat 18.89-19.27, lon 72.78-72.98). Writes node_id,lat,lon to a CSV cache so we
don't have to re-decode 34M nodes for every downstream step.
"""
import sys
import os
import time
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbf_reader import iter_primitive_blocks, decode_dense_nodes
from paths import OSM_PBF_RAW as PBF, NODES_BBOX_CACHE as OUT, ensure_dirs

ensure_dirs()

# Generous buffer beyond the real Mumbai ward extent (18.89-19.27 lat, 72.78-72.98 lon)
BBOX = (18.80, 72.60, 19.35, 73.10)  # min_lat, min_lon, max_lat, max_lon

t0 = time.time()
block_idx = 0
kept = 0
seen = 0

with open(OUT, 'w', newline='') as fout:
    writer = csv.writer(fout)
    writer.writerow(['node_id', 'lat', 'lon'])
    for ctx, groups in iter_primitive_blocks(PBF):
        has_dense = any(2 in g for g in groups)
        if not has_dense:
            # We've moved past the nodes section (ways/relations blocks don't have dense nodes)
            if block_idx > 0:
                break
            continue
        block_idx += 1
        for g in groups:
            if 2 in g:
                for node_id, lat, lon in decode_dense_nodes(ctx, g, node_bbox=BBOX):
                    writer.writerow([node_id, f'{lat:.7f}', f'{lon:.7f}'])
                    kept += 1
        # rough seen-count bookkeeping via block size assumption (8000/block typical)
        seen = block_idx * 8000
        if block_idx % 500 == 0:
            elapsed = time.time() - t0
            print(f"...{block_idx} node blocks processed, ~{seen} nodes scanned, {kept} kept, {elapsed:.1f}s elapsed", flush=True)

t1 = time.time()
print(f"DONE. {block_idx} node blocks, {kept} nodes kept inside bbox, took {t1-t0:.1f}s")

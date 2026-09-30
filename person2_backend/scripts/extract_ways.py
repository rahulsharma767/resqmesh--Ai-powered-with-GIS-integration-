"""
Pass 2: scan the ways section of the PBF. Keep a way if:
  - it has a 'highway' tag whose value is in ALLOWED_HIGHWAY (vehicle-drivable
    road classes -- excludes footway/path/cycleway/steps/pedestrian/etc.)
  - AND at least one of its node refs falls in our Mumbai-bbox node set
      (data/cache/mumbai_bbox_nodes.csv from extract_nodes.py)

Writes:
  data/cache/mumbai_ways.csv       -- way_id, highway, name, oneway, maxspeed_kph, ref_node_ids (pipe-separated)
  data/cache/missing_node_ids.txt  -- node ids referenced by kept ways but not
                                       present in mumbai_bbox_nodes.csv (need a
                                       follow-up node pass to fetch their coords)

Documented assumption: ALLOWED_HIGHWAY set below defines what counts as a
"road" for ambulance routing. service=driveway/parking_aisle service roads
are included since ambulances may need to enter hospital/building forecourts;
pure pedestrian infrastructure is excluded.
"""
import sys
import os
import csv
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbf_reader import iter_primitive_blocks, decode_ways
from paths import (OSM_PBF_RAW as PBF, NODES_BBOX_CACHE as NODES_CSV,
                    WAYS_CACHE as OUT_WAYS, MISSING_NODE_IDS_CACHE as OUT_MISSING, ensure_dirs)

ensure_dirs()

ALLOWED_HIGHWAY = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'unclassified', 'residential', 'living_street',
    'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
    'service',
}

print("Loading Mumbai bbox node id set...", flush=True)
t0 = time.time()
node_ids = set()
with open(NODES_CSV) as f:
    reader = csv.reader(f)
    next(reader)  # header
    for row in reader:
        node_ids.add(int(row[0]))
print(f"Loaded {len(node_ids)} node ids in {time.time()-t0:.1f}s", flush=True)

t0 = time.time()
block_idx = 0
kept_ways = 0
scanned_ways = 0
highway_tag_count = 0
missing_refs = set()
started_ways_section = False

with open(OUT_WAYS, 'w', newline='', encoding='utf-8') as fout:
    writer = csv.writer(fout)
    writer.writerow(['way_id', 'highway', 'name', 'oneway', 'maxspeed_raw', 'refs'])

    for ctx, groups in iter_primitive_blocks(PBF):
        has_way = any(3 in g for g in groups)
        if not has_way:
            if started_ways_section:
                break
            continue
        started_ways_section = True
        block_idx += 1

        for g in groups:
            if 3 in g:
                for way_id, tags, refs in decode_ways(ctx, g):
                    scanned_ways += 1
                    hw = tags.get('highway')
                    if not hw:
                        continue
                    highway_tag_count += 1
                    if hw not in ALLOWED_HIGHWAY:
                        continue
                    if not any(r in node_ids for r in refs):
                        continue
                    kept_ways += 1
                    for r in refs:
                        if r not in node_ids:
                            missing_refs.add(r)
                    writer.writerow([
                        way_id, hw, tags.get('name', ''),
                        tags.get('oneway', ''), tags.get('maxspeed', ''),
                        '|'.join(str(r) for r in refs)
                    ])
        if block_idx % 50 == 0:
            print(f"...{block_idx} way blocks, {scanned_ways} ways scanned, "
                  f"{highway_tag_count} with highway tag, {kept_ways} kept, "
                  f"{time.time()-t0:.1f}s elapsed", flush=True)

with open(OUT_MISSING, 'w', encoding='utf-8') as f:
    for r in missing_refs:
        f.write(f"{r}\n")

print(f"DONE. {block_idx} way blocks scanned, {scanned_ways} total ways, "
      f"{highway_tag_count} with highway tag, {kept_ways} kept for Mumbai.")
print(f"Missing node refs needing a follow-up lookup: {len(missing_refs)}")
print(f"Took {time.time()-t0:.1f}s")

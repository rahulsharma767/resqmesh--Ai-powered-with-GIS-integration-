import time, sys
sys.path.insert(0, '.')
from pbf_reader import iter_primitive_blocks, decode_dense_nodes, decode_ways

PBF = '/mnt/user-data/uploads/western-zone-260822.osm.pbf'

# Mumbai generous bbox (slightly wider than ward boundary extent, to be safe)
MUMBAI_BBOX = (18.80, 72.60, 19.35, 73.10)  # min_lat, min_lon, max_lat, max_lon

t0 = time.time()
block_count = 0
node_count_seen = 0
node_count_kept = 0
for ctx, groups in iter_primitive_blocks(PBF):
    block_count += 1
    for g in groups:
        if 2 in g:  # dense nodes
            for node_id, lat, lon in decode_dense_nodes(ctx, g, node_bbox=None):
                node_count_seen += 1
            # redo with bbox filter for keep count (cheap re-iterate; just for the benchmark)
    if block_count >= 20:
        break
t1 = time.time()
print(f"Scanned {block_count} node blocks, {node_count_seen} nodes total, in {t1-t0:.2f}s")
print(f"=> {node_count_seen/(t1-t0):.0f} nodes/sec, {(t1-t0)/block_count*1000:.1f} ms/block")

# Estimate full node-section time (~4299 blocks based on earlier inspection)
est_total_blocks = 4299
print(f"Estimated full node-pass time: {(t1-t0)/block_count*est_total_blocks:.1f}s (~{(t1-t0)/block_count*est_total_blocks/60:.1f} min)")

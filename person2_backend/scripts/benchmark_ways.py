import time, sys
sys.path.insert(0, '.')
from pbf_reader import iter_primitive_blocks, decode_ways

PBF = '/mnt/user-data/uploads/western-zone-260822.osm.pbf'

t0 = time.time()
block_count = 0
way_count = 0
started = False
for ctx, groups in iter_primitive_blocks(PBF):
    has_way = any(3 in g for g in groups)
    if not has_way:
        if started:
            break  # we've passed the ways section
        continue
    started = True
    block_count += 1
    for g in groups:
        if 3 in g:
            for way_id, tags, refs in decode_ways(ctx, g):
                way_count += 1
    if block_count >= 20:
        break
t1 = time.time()
print(f"Scanned {block_count} way blocks, {way_count} ways, in {t1-t0:.2f}s")
if block_count:
    print(f"=> {way_count/(t1-t0):.0f} ways/sec, {(t1-t0)/block_count*1000:.1f} ms/block")
    est_total_way_blocks = 4697 - 4299  # from earlier inspection
    print(f"Estimated full ways-section time: {(t1-t0)/block_count*est_total_way_blocks:.1f}s")

"""
Minimal pure-Python OSM PBF reader.

WHY THIS EXISTS:
This sandbox has no internet access, so standard OSM PBF libraries
(osmium, pyrosm) cannot be installed. This module implements just
enough of the Protocol Buffers wire format + the OSM PBF schema
(fileformat.proto / osmformat.proto) to stream nodes and ways out of
a .osm.pbf file, filtered by a bounding box and tag predicate, without
ever loading the whole file into memory.

Reference: https://wiki.openstreetmap.org/wiki/PBF_Format
This is a read-only, extraction-only reader (no full OSM editing API).
"""
import struct
import zlib
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Generic protobuf wire-format decoding
# ---------------------------------------------------------------------------

def read_varint(buf, pos):
    """Decode a base-128 varint starting at pos. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def zigzag_decode(n):
    return (n >> 1) ^ -(n & 1)


def parse_message(buf):
    """
    Parse a protobuf message into {field_number: [values]}.
    - varint fields -> raw int (caller applies zigzag/signed interpretation)
    - length-delimited fields -> raw bytes (caller re-parses as string/submessage/packed)
    - fixed32/fixed64 -> raw int
    Returns dict[int, list]
    """
    out = {}
    pos = 0
    n = len(buf)
    while pos < n:
        key, pos = read_varint(buf, pos)
        field_no = key >> 3
        wire_type = key & 0x7
        if wire_type == 0:  # varint
            val, pos = read_varint(buf, pos)
        elif wire_type == 1:  # 64-bit
            val = struct.unpack_from('<Q', buf, pos)[0]
            pos += 8
        elif wire_type == 2:  # length-delimited
            length, pos = read_varint(buf, pos)
            val = buf[pos:pos + length]
            pos += length
        elif wire_type == 5:  # 32-bit
            val = struct.unpack_from('<I', buf, pos)[0]
            pos += 4
        else:
            raise ValueError(f"Unsupported wire type {wire_type} at pos {pos}")
        out.setdefault(field_no, []).append(val)
    return out


def parse_packed_varint(buf):
    """A length-delimited field containing back-to-back varints (packed repeated)."""
    vals = []
    pos = 0
    n = len(buf)
    while pos < n:
        v, pos = read_varint(buf, pos)
        vals.append(v)
    return vals


# ---------------------------------------------------------------------------
# OSM PBF blob framing
# ---------------------------------------------------------------------------

def iter_blobs(path):
    """Yield (blob_type: str, decompressed_bytes) for every blob in the file."""
    with open(path, 'rb') as f:
        while True:
            hdr_len_bytes = f.read(4)
            if len(hdr_len_bytes) < 4:
                return
            hdr_len = struct.unpack('>I', hdr_len_bytes)[0]
            blob_header_bytes = f.read(hdr_len)
            bh = parse_message(blob_header_bytes)
            blob_type = bh[1][0].decode('utf-8')
            datasize = bh[3][0]
            blob_bytes = f.read(datasize)
            blob = parse_message(blob_bytes)
            if 1 in blob:  # raw
                raw = blob[1][0]
            elif 3 in blob:  # zlib_data
                raw = zlib.decompress(blob[3][0])
            else:
                raise ValueError("Unsupported blob compression (only raw/zlib supported)")
            yield blob_type, raw


# ---------------------------------------------------------------------------
# OSM primitive decoding
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: int
    lat: float
    lon: float
    tags: dict


@dataclass
class Way:
    id: int
    refs: list
    tags: dict


def _decode_stringtable(raw_bytes):
    msg = parse_message(raw_bytes)
    return [b.decode('utf-8', errors='replace') for b in msg.get(1, [])]


def _decode_dense_nodes(raw_bytes, stringtable, granularity, lat_offset, lon_offset):
    msg = parse_message(raw_bytes)
    ids = parse_packed_varint(msg[1][0]) if 1 in msg else []
    ids = [zigzag_decode(v) for v in ids]
    lats = parse_packed_varint(msg[8][0]) if 8 in msg else []
    lats = [zigzag_decode(v) for v in lats]
    lons = parse_packed_varint(msg[9][0]) if 9 in msg else []
    lons = [zigzag_decode(v) for v in lons]
    kv_flat = parse_packed_varint(msg[10][0]) if 10 in msg else []

    # delta-decode ids/lats/lons
    nodes = []
    cur_id = cur_lat = cur_lon = 0
    for i in range(len(ids)):
        cur_id += ids[i]
        cur_lat += lats[i]
        cur_lon += lons[i]
        lat = 1e-9 * (lat_offset + (granularity * cur_lat))
        lon = 1e-9 * (lon_offset + (granularity * cur_lon))
        nodes.append([cur_id, lat, lon, {}])

    # keys_vals: flat list of stringtable indices, terminated per-node by a 0
    idx = 0
    node_i = 0
    while idx < len(kv_flat) and node_i < len(nodes):
        k = kv_flat[idx]
        if k == 0:
            node_i += 1
            idx += 1
            continue
        v = kv_flat[idx + 1]
        nodes[node_i][3][stringtable[k]] = stringtable[v]
        idx += 2

    return [Node(id=n[0], lat=n[1], lon=n[2], tags=n[3]) for n in nodes]


def _decode_ways(raw_list, stringtable):
    ways = []
    for raw in raw_list:
        msg = parse_message(raw)
        way_id = msg[1][0]
        keys = parse_packed_varint(msg[2][0]) if 2 in msg else []
        vals = parse_packed_varint(msg[3][0]) if 3 in msg else []
        tags = {stringtable[k]: stringtable[v] for k, v in zip(keys, vals)}
        refs_delta = parse_packed_varint(msg[8][0]) if 8 in msg else []
        refs_delta = [zigzag_decode(v) for v in refs_delta]
        refs = []
        cur = 0
        for d in refs_delta:
            cur += d
            refs.append(cur)
        ways.append(Way(id=way_id, refs=refs, tags=tags))
    return ways


def iter_primitive_blocks(path):
    """Yield raw PrimitiveBlock field-dicts + decoded stringtable/granularity, per block."""
    for blob_type, raw in iter_blobs(path):
        if blob_type != 'OSMData':
            continue
        block = parse_message(raw)
        stringtable = _decode_stringtable(block[1][0])
        granularity = parse_message(b'')  # placeholder, real values pulled below
        gran = 100
        lat_off = 0
        lon_off = 0
        # granularity/lat_offset/lon_offset are simple varint fields (17,19,20)
        pb_top = parse_message(raw)
        if 17 in pb_top:
            gran = pb_top[17][0]
        if 19 in pb_top:
            lat_off = zigzag_decode(pb_top[19][0]) if False else pb_top[19][0]
        if 20 in pb_top:
            lon_off = pb_top[20][0]
        groups_raw = block.get(2, [])
        yield stringtable, gran, lat_off, lon_off, groups_raw


def extract(path, bbox=None, way_filter=None, node_filter=None, progress_every=20):
    """
    Stream the PBF file once, yielding Node and Way objects.
    bbox: (min_lon, min_lat, max_lon, max_lat) or None for no filter (nodes only cheaply filterable)
    way_filter(tags) -> bool : keep way if True
    node_filter(tags) -> bool : keep standalone tagged node if True
    Returns (nodes_by_id: dict[id]->Node kept because referenced or matched filter is NOT
             built here - see build_graph.py which does a 2-pass extraction).
    This generator yields ('node', Node) and ('way', Way) tuples for ALL primitives;
    caller applies bbox/filter logic (kept here minimal to avoid re-parsing tags twice).
    """
    blocks_seen = 0
    for stringtable, gran, lat_off, lon_off, groups_raw in iter_primitive_blocks(path):
        blocks_seen += 1
        for graw in groups_raw:
            group = parse_message(graw)
            if 2 in group:  # dense nodes
                nodes = _decode_dense_nodes(group[2][0], stringtable, gran, lat_off, lon_off)
                for nd in nodes:
                    if bbox and not (bbox[0] <= nd.lon <= bbox[2] and bbox[1] <= nd.lat <= bbox[3]):
                        continue
                    yield ('node', nd)
            if 3 in group:  # ways
                ways = _decode_ways(group[3], stringtable)
                for w in ways:
                    if way_filter and not way_filter(w.tags):
                        continue
                    yield ('way', w)
        if progress_every and blocks_seen % progress_every == 0:
            print(f"  ...processed {blocks_seen} primitive blocks", flush=True)

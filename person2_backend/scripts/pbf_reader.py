"""
Minimal pure-Python OSM PBF reader.

No osmium/pyrosm/protobuf-generated-classes dependency. Implements just enough
of the protobuf wire format + OSM fileformat.proto / osmformat.proto structure
to walk Blob -> PrimitiveBlock -> DenseNodes / Ways / Relations.

This exists because the sandbox has no network access to install pyrosm/osmium.
"""
import struct
import zlib


def read_varint(data, pos):
    result = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def zigzag_decode(v):
    return (v >> 1) ^ (-(v & 1))


def parse_fields(data):
    """Generic protobuf wire-format parser -> {field_num: [values]}"""
    fields = {}
    pos = 0
    n = len(data)
    while pos < n:
        tag, pos = read_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x7
        if wire_type == 0:
            val, pos = read_varint(data, pos)
        elif wire_type == 2:
            length, pos = read_varint(data, pos)
            val = data[pos:pos + length]
            pos += length
        elif wire_type == 5:
            val = data[pos:pos + 4]
            pos += 4
        elif wire_type == 1:
            val = data[pos:pos + 8]
            pos += 8
        else:
            raise ValueError(f"Unsupported wire type {wire_type} at pos {pos}")
        fields.setdefault(field_num, []).append(val)
    return fields


def iter_blobs(path):
    """Yield (blob_type: str, decompressed_bytes: bytes) for every blob in the PBF."""
    with open(path, 'rb') as f:
        while True:
            len_bytes = f.read(4)
            if len(len_bytes) < 4:
                break
            blobheader_len = struct.unpack('>I', len_bytes)[0]
            blobheader_data = f.read(blobheader_len)
            bh_fields = parse_fields(blobheader_data)
            btype = bh_fields.get(1, [b''])[0].decode('utf-8', errors='replace')
            datasize = bh_fields.get(3, [0])[0]
            blob_data = f.read(datasize)

            blob_fields = parse_fields(blob_data)
            if 3 in blob_fields:  # zlib_data
                decompressed = zlib.decompress(blob_fields[3][0])
            elif 1 in blob_fields:  # raw
                decompressed = blob_fields[1][0]
            else:
                decompressed = b''
            yield btype, decompressed


def decode_packed_varints(data):
    """Decode a packed-repeated varint field's raw bytes into a list of ints."""
    out = []
    pos = 0
    n = len(data)
    while pos < n:
        v, pos = read_varint(data, pos)
        out.append(v)
    return out


def decode_packed_svarints(data):
    return [zigzag_decode(v) for v in decode_packed_varints(data)]


class PrimitiveBlockContext:
    """Holds stringtable + granularity/offset for decoding one PrimitiveBlock."""

    __slots__ = ('stringtable', 'granularity', 'lat_offset', 'lon_offset', 'date_granularity')

    def __init__(self, pb_fields):
        st_raw = pb_fields.get(1, [b''])[0]
        st_fields = parse_fields(st_raw)
        # field 1 repeated bytes = each string
        self.stringtable = [s.decode('utf-8', errors='replace') for s in st_fields.get(1, [])]
        self.granularity = pb_fields.get(17, [100])[0]
        self.lat_offset = pb_fields.get(19, [0])[0]
        self.lon_offset = pb_fields.get(20, [0])[0]
        if isinstance(self.granularity, bytes):
            self.granularity = int.from_bytes(self.granularity, 'little', signed=True)
        if isinstance(self.lat_offset, bytes):
            self.lat_offset = int.from_bytes(self.lat_offset, 'little', signed=True)
        if isinstance(self.lon_offset, bytes):
            self.lon_offset = int.from_bytes(self.lon_offset, 'little', signed=True)
        self.date_granularity = pb_fields.get(18, [1000])[0]

    def coord(self, lat_raw, lon_raw):
        lat = 1e-9 * (self.lat_offset + (self.granularity * lat_raw))
        lon = 1e-9 * (self.lon_offset + (self.granularity * lon_raw))
        return lat, lon


def iter_primitive_blocks(path, want_types=('OSMData',)):
    """Yield PrimitiveBlockContext, primitive_group_fields_list for each OSMData blob."""
    for btype, decompressed in iter_blobs(path):
        if btype not in want_types:
            continue
        pb_fields = parse_fields(decompressed)
        ctx = PrimitiveBlockContext(pb_fields)
        groups = [parse_fields(g) for g in pb_fields.get(2, [])]
        yield ctx, groups


def decode_dense_nodes(ctx, group_fields, node_bbox=None, want_tags=False):
    """
    Decode a DenseNodes group (field 2 of PrimitiveGroup).
    Yields (node_id, lat, lon[, tags_dict]) for nodes, optionally filtered to bbox.
    node_bbox = (min_lat, min_lon, max_lat, max_lon) or None for no filter.
    """
    dense_raw = group_fields[2][0]
    dfields = parse_fields(dense_raw)
    ids_delta = decode_packed_svarints(dfields.get(1, [b''])[0])
    lats_delta = decode_packed_svarints(dfields.get(8, [b''])[0])
    lons_delta = decode_packed_svarints(dfields.get(9, [b''])[0])

    keys_vals = None
    if want_tags and 10 in dfields:
        keys_vals = decode_packed_varints(dfields[10][0])

    n = len(ids_delta)
    node_id = 0
    lat_raw = 0
    lon_raw = 0
    kv_pos = 0
    st = ctx.stringtable

    for i in range(n):
        node_id += ids_delta[i]
        lat_raw += lats_delta[i]
        lon_raw += lons_delta[i]
        lat, lon = ctx.coord(lat_raw, lon_raw)

        tags = None
        if keys_vals is not None:
            tags = {}
            while kv_pos < len(keys_vals) and keys_vals[kv_pos] != 0:
                k = st[keys_vals[kv_pos]]
                v = st[keys_vals[kv_pos + 1]]
                tags[k] = v
                kv_pos += 2
            kv_pos += 1  # skip the 0 terminator
        elif want_tags:
            tags = {}

        if node_bbox is not None:
            min_lat, min_lon, max_lat, max_lon = node_bbox
            if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                continue

        if want_tags:
            yield node_id, lat, lon, tags
        else:
            yield node_id, lat, lon


def decode_ways(ctx, group_fields):
    """
    Decode Way messages (field 3 of PrimitiveGroup, repeated Way message).
    Yields (way_id, tags_dict, node_refs_list).
    """
    st = ctx.stringtable
    for way_raw in group_fields[3]:
        wf = parse_fields(way_raw)
        way_id = wf[1][0]
        if isinstance(way_id, bytes):
            way_id = int.from_bytes(way_id, 'little', signed=True)
        keys = decode_packed_varints(wf.get(2, [b''])[0]) if 2 in wf else []
        vals = decode_packed_varints(wf.get(3, [b''])[0]) if 3 in wf else []
        tags = {st[k]: st[v] for k, v in zip(keys, vals)}
        refs_delta = decode_packed_svarints(wf.get(8, [b''])[0]) if 8 in wf else []
        refs = []
        ref_id = 0
        for d in refs_delta:
            ref_id += d
            refs.append(ref_id)
        yield way_id, tags, refs

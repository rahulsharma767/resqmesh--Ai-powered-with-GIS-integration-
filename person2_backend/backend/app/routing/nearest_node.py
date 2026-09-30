"""
Snap an arbitrary lat/lon to the nearest road-graph node. Used to place an
incident onto the routable graph (hospitals already have a precomputed
nearest_graph_node from Part 5 -- this is the same operation for incidents,
which arrive as free-form coordinates at request time).

The KDTree is built once and cached at module level; rebuilding it per
request would violate Part 17's "don't do expensive geographic work inside
request handlers" rule.
"""
import csv
import math
import os
import sys
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'scripts'))
from paths import ROAD_NODES_CSV as NODES_CSV  # noqa: E402

_tree = None
_node_ids = None
_cos_mean_lat = None
R = 6371000.0


def _load():
    global _tree, _node_ids, _cos_mean_lat
    node_ids, lats, lons = [], [], []
    with open(NODES_CSV) as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            node_ids.append(int(row[0]))
            lats.append(float(row[1]))
            lons.append(float(row[2]))
    lats = np.array(lats)
    lons = np.array(lons)
    _cos_mean_lat = math.cos(math.radians(np.mean(lats)))
    x = np.radians(lons) * _cos_mean_lat * R
    y = np.radians(lats) * R
    _tree = cKDTree(np.column_stack([x, y]))
    _node_ids = node_ids


def nearest_node(lat, lon):
    global _tree, _node_ids, _cos_mean_lat
    if _tree is None:
        _load()
    x = math.radians(lon) * _cos_mean_lat * R
    y = math.radians(lat) * R
    dist, idx = _tree.query([x, y])
    return _node_ids[idx], dist

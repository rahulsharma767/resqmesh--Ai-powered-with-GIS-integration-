"""
Loads the Mumbai road graph (edges/nodes CSVs) into a networkx.DiGraph and
pickles it to disk so it only has to be parsed from CSV once. Downstream
services (routing, ambulance/hospital selection) load the pickle, which is
fast (~1-2s) instead of re-parsing ~65MB of CSV on every process start.

Per Part 17 (scalability): "save a reusable processed graph rather than
rebuilding it every API request" -- this script IS that save step.
"""
import csv
import os
import sys
import pickle
import time
import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (ROAD_EDGES_CSV as EDGES_CSV, ROAD_NODES_CSV as NODES_CSV,
                    ROAD_GRAPH_PKL as OUT_PKL, ensure_dirs)

ensure_dirs()


def build_and_cache_graph():
    t0 = time.time()
    G = nx.DiGraph()

    node_coord = {}
    with open(NODES_CSV, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            nid = int(row[0])
            lat, lon = float(row[1]), float(row[2])
            node_coord[nid] = (lat, lon)
            G.add_node(nid, lat=lat, lon=lon)

    with open(EDGES_CSV, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            u, v = int(row[0]), int(row[1])
            length_m, speed_kph, travel_time_min = float(row[2]), float(row[3]), float(row[4])
            highway, name, way_id, oneway_flag = row[5], row[6], row[7], row[8]
            G.add_edge(u, v, length_m=length_m, speed_kph=speed_kph,
                       travel_time_min=travel_time_min, highway=highway,
                       name=name, way_id=way_id, oneway_flag=oneway_flag)

    print(f"Built graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges in {time.time()-t0:.1f}s")

    with open(OUT_PKL, 'wb') as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Cached to {OUT_PKL}")
    return G


if __name__ == '__main__':
    build_and_cache_graph()
